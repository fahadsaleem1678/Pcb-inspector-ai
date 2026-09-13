import time
from typing import Any
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from pcb_inspector.config import Settings
from pcb_inspector.database import Inspection, InspectionEvent, SubmissionOutbox
from pcb_inspector.schemas import Report, Status


class Repository:
    """Durable local queue. State transitions and audit events share a transaction."""

    def __init__(self, engine: Engine):
        self.engine = engine

    @staticmethod
    def _event(session: Session, inspection_id: str, kind: str, now: float, **data: Any) -> None:
        session.add(
            InspectionEvent(
                id=str(uuid4()),
                inspection_id=inspection_id,
                event_type=kind,
                created_at=now,
                event_data=data,
            )
        )

    def create(
        self,
        inspection_id: str,
        owner_id: str,
        image_key: str,
        width: int,
        height: int,
        request_id: str,
        queue_backend: str = "database",
    ) -> None:
        if queue_backend not in ("database", "sqs"):
            raise ValueError("Invalid queue backend")
        now = time.time()
        with Session(self.engine) as session, session.begin():
            session.add(
                Inspection(
                    id=inspection_id,
                    owner_id=owner_id,
                    image_key=image_key,
                    queue_backend=queue_backend,
                    width=width,
                    height=height,
                    status=Status.QUEUED,
                    created_at=now,
                    available_at=now,
                    attempts=0,
                )
            )
            session.flush()
            if queue_backend == "sqs":
                session.add(
                    SubmissionOutbox(
                        id=str(uuid4()),
                        inspection_id=inspection_id,
                        created_at=now,
                        available_at=now,
                        attempts=0,
                    )
                )
            self._event(session, inspection_id, "inspection_queued", now, request_id=request_id)

    def get(self, inspection_id: str, owner_id: str) -> Inspection | None:
        with Session(self.engine) as session:
            return session.scalar(
                select(Inspection).where(
                    Inspection.id == inspection_id,
                    Inspection.owner_id == owner_id,
                )
            )

    def history(self, owner_id: str, limit: int, offset: int) -> list[Inspection]:
        with Session(self.engine) as session:
            return list(
                session.scalars(
                    select(Inspection)
                    .where(Inspection.owner_id == owner_id)
                    .order_by(Inspection.created_at.desc(), Inspection.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )

    def claim(
        self,
        settings: Settings,
        now: float | None = None,
        *,
        inspection_id: str | None = None,
    ) -> Inspection | None:
        now = time.time() if now is None else now
        eligible = or_(
            and_(Inspection.status == Status.QUEUED, Inspection.available_at <= now),
            and_(Inspection.status == Status.PROCESSING, Inspection.lease_until <= now),
        )
        eligible = and_(eligible, Inspection.queue_backend == settings.queue_backend)
        if settings.queue_backend == "sqs" and inspection_id is None:
            raise ValueError("SQS claims require a message-bound inspection ID")
        if inspection_id is not None:
            eligible = and_(eligible, Inspection.id == inspection_id)
        # Retry contention and drain a bounded number of expired, exhausted jobs per poll.
        for _ in range(10):
            with Session(self.engine, expire_on_commit=False) as session, session.begin():
                job_id = session.scalar(
                    select(Inspection.id)
                    .where(eligible)
                    .order_by(Inspection.created_at, Inspection.id)
                    .limit(1)
                )
                if job_id is None:
                    return None
                token = str(uuid4())
                job = session.scalar(
                    update(Inspection)
                    .where(
                        Inspection.id == job_id,
                        eligible,
                    )
                    .values(
                        status=Status.PROCESSING,
                        lease_token=token,
                        lease_until=now + settings.lease_seconds,
                    )
                    .returning(Inspection)
                )
                if job is None:
                    continue
                if job.attempts >= settings.max_attempts:
                    job.status = Status.FAILED
                    job.error_code = "RETRY_LIMIT_EXCEEDED"
                    job.completed_at = now
                    job.lease_token = None
                    job.lease_until = None
                    self._event(
                        session, job.id, "inspection_failed", now, error_code=job.error_code
                    )
                    continue
                job.attempts += 1
                job.error_code = None
                self._event(session, job.id, "inspection_processing", now, attempt=job.attempts)
                return job
        return None

    def complete(self, job: Inspection, report: Report, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with Session(self.engine) as session, session.begin():
            changed = session.scalar(
                update(Inspection)
                .where(
                    Inspection.id == job.id,
                    Inspection.status == Status.PROCESSING,
                    Inspection.lease_token == job.lease_token,
                    Inspection.lease_until > now,
                )
                .values(
                    status=Status.COMPLETED,
                    completed_at=now,
                    lease_token=None,
                    lease_until=None,
                    model_version=report.model_version,
                    overall_result=report.overall_result,
                    report=report.model_dump(mode="json"),
                    error_code=None,
                )
                .returning(Inspection.id)
            )
            if changed is None:
                return False
            self._event(
                session,
                job.id,
                "inspection_completed",
                now,
                model_version=report.model_version,
                is_demo=report.is_demo,
            )
            return True

    def fail(self, job: Inspection, settings: Settings, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        terminal = job.attempts >= settings.max_attempts
        with Session(self.engine) as session, session.begin():
            changed = session.scalar(
                update(Inspection)
                .where(
                    Inspection.id == job.id,
                    Inspection.status == Status.PROCESSING,
                    Inspection.lease_token == job.lease_token,
                    Inspection.lease_until > now,
                )
                .values(
                    status=Status.FAILED if terminal else Status.QUEUED,
                    completed_at=now if terminal else None,
                    available_at=now + settings.retry_delay_seconds * 2 ** (job.attempts - 1),
                    error_code="INFERENCE_FAILED",
                    lease_token=None,
                    lease_until=None,
                )
                .returning(Inspection.id)
            )
            if changed is None:
                return False
            self._event(
                session,
                job.id,
                "inspection_failed" if terminal else "inspection_retry_scheduled",
                now,
                attempt=job.attempts,
                error_code="INFERENCE_FAILED",
            )
            return True

    def renew(self, job: Inspection, settings: Settings, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        with Session(self.engine) as session, session.begin():
            return (
                session.scalar(
                    update(Inspection)
                    .where(
                        Inspection.id == job.id,
                        Inspection.status == Status.PROCESSING,
                        Inspection.lease_token == job.lease_token,
                        Inspection.lease_until > now,
                    )
                    .values(lease_until=now + settings.lease_seconds)
                    .returning(Inspection.id)
                )
                is not None
            )

    def message_job(self, event_id: str, inspection_id: str) -> Inspection | None:
        with Session(self.engine) as session:
            return session.scalar(
                select(Inspection)
                .join(
                    SubmissionOutbox,
                    SubmissionOutbox.inspection_id == Inspection.id,
                )
                .where(
                    SubmissionOutbox.id == event_id,
                    Inspection.id == inspection_id,
                    Inspection.queue_backend == "sqs",
                )
            )
