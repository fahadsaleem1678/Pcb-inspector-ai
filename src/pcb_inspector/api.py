import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from pcb_inspector.auth import Authenticator, Principal, PrincipalDependency
from pcb_inspector.config import Settings
from pcb_inspector.database import Inspection, make_engine
from pcb_inspector.images import InvalidImage, validate_image
from pcb_inspector.observability import Metrics, configure_logging
from pcb_inspector.repository import Repository
from pcb_inspector.schemas import History, InspectionSummary, Report, Status, Submission
from pcb_inspector.storage import LocalObjectStore

logger = logging.getLogger(__name__)


class BodyTooLarge(Exception):
    pass


class UploadBodyLimit:
    """Bound bytes before multipart spooling, including chunked requests."""

    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        used = 0
        too_large = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal used, too_large
            message = await receive()
            if message["type"] == "http.request":
                used += len(message.get("body", b""))
                if used > self.max_bytes:
                    too_large = True
                    raise BodyTooLarge
            return message

        async def limited_send(message: Message) -> None:
            nonlocal response_started
            # FastAPI may translate a multipart receive exception into a 400;
            # replace that response with the correct size-limit response below.
            if too_large:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, limited_send)
        except BodyTooLarge:
            too_large = True
        if too_large and not response_started:
            await JSONResponse({"detail": "Request body exceeds the size limit"}, 413)(
                scope,
                receive,
                send,
            )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.database_url)
    repository = Repository(engine)
    storage = LocalObjectStore(settings.storage_path)
    metrics = Metrics()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.environment == "local":
            configure_logging()
        yield
        engine.dispose()

    app = FastAPI(
        title="PCB Inspector AI",
        version="0.1.0",
        lifespan=lifespan,
        description="Local single-user demo. No trained detector is installed.",
    )
    app.state.authenticator = Authenticator(settings)
    app.state.repository = repository
    app.state.storage = storage
    app.state.settings = settings
    # Allow a bounded multipart envelope beyond the separately enforced file limit.
    app.add_middleware(UploadBodyLimit, max_bytes=settings.max_upload_bytes + 64 * 1024)

    @app.middleware("http")
    async def observe(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Cache-Control"] = "no-store"
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", "unmatched")
            metrics.requests.labels(request.method, route, str(status)).inc()
            metrics.latency.labels(request.method, route).observe(time.perf_counter() - started)
            logger.info("request_completed:%s", status, extra={"request_id": request_id})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        logger.error("request_error:%s", type(exc).__name__, extra={"request_id": request_id})
        return JSONResponse(
            {"detail": "Internal service error", "request_id": request_id},
            status_code=500,
            headers={"X-Request-ID": request_id, "Cache-Control": "no-store"},
        )

    @app.get("/api/v1/auth/me")
    def identity(principal: PrincipalDependency) -> Principal:
        return principal

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "environment": settings.environment, "is_demo": True}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        try:
            with engine.connect() as connection:
                connection.execute(select(Inspection.id).limit(1))
            probe = f".health/{uuid4()}.txt"
            try:
                storage.put(probe, b"ready")
                if storage.get(probe) != b"ready":
                    raise OSError("Storage probe failed")
            finally:
                storage.delete(probe)
        except Exception as exc:
            raise HTTPException(503, "Database schema or object storage is not ready") from exc
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    def prometheus_metrics() -> Response:
        return Response(
            generate_latest(metrics.registry), headers={"Content-Type": CONTENT_TYPE_LATEST}
        )

    @app.post("/api/v1/inspections/upload", response_model=Submission, status_code=202)
    async def upload(
        request: Request, principal: PrincipalDependency, file: Annotated[UploadFile, File()]
    ) -> Submission:
        try:
            content = await file.read(settings.max_upload_bytes + 1)
        finally:
            await file.close()
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(413, "Image exceeds the upload size limit")
        try:
            image = await run_in_threadpool(validate_image, content, settings)
        except InvalidImage as exc:
            raise HTTPException(422, str(exc)) from exc
        inspection_id = str(uuid4())
        key = f"uploads/{inspection_id}/original.png"

        def persist() -> None:
            storage.put(key, image.content)
            try:
                repository.create(
                    inspection_id,
                    principal.owner_id,
                    key,
                    image.width,
                    image.height,
                    request.state.request_id,
                )
            except Exception:
                storage.delete(key)
                raise

        await run_in_threadpool(persist)
        return Submission(inspection_id=inspection_id)

    def owned_job(inspection_id: UUID, principal: Principal) -> Inspection:
        job = repository.get(str(inspection_id), principal.owner_id)
        if job is None:
            raise HTTPException(404, "Inspection not found")
        return job

    def completed_report(inspection_id: UUID, principal: Principal) -> Report:
        job = owned_job(inspection_id, principal)
        if job.status != Status.COMPLETED or job.report is None:
            raise HTTPException(409, {"message": "Results are not available", "status": job.status})
        return Report.model_validate(job.report)

    @app.get("/api/v1/inspections", response_model=History)
    def history(
        principal: PrincipalDependency,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> History:
        return History(
            items=[
                InspectionSummary.model_validate(job)
                for job in repository.history(principal.owner_id, limit, offset)
            ],
            limit=limit,
            offset=offset,
        )

    @app.get("/api/v1/inspections/{inspection_id}", response_model=InspectionSummary)
    def status(inspection_id: UUID, principal: PrincipalDependency) -> InspectionSummary:
        return InspectionSummary.model_validate(owned_job(inspection_id, principal))

    @app.get("/api/v1/inspections/{inspection_id}/results", response_model=Report)
    def results(inspection_id: UUID, principal: PrincipalDependency) -> Report:
        return completed_report(inspection_id, principal)

    @app.get("/api/v1/inspections/{inspection_id}/report")
    def download_report(inspection_id: UUID, principal: PrincipalDependency) -> JSONResponse:
        return JSONResponse(
            completed_report(inspection_id, principal).model_dump(mode="json"),
            headers={"Content-Disposition": f'attachment; filename="{inspection_id}.json"'},
        )

    @app.get("/api/v1/inspections/{inspection_id}/image")
    def original_image(inspection_id: UUID, principal: PrincipalDependency) -> FileResponse:
        path = storage.path(owned_job(inspection_id, principal).image_key)
        if not path.is_file():
            raise HTTPException(404, "Image not found")
        return FileResponse(path, media_type="image/png")

    return app
