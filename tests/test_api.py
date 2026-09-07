import io
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from pcb_inspector.api import create_app
from pcb_inspector.database import InspectionEvent
from pcb_inspector.worker import Worker


def test_upload_worker_results_history_and_restart(client, app, settings, png):
    response = client.post("/api/v1/inspections/upload", files={"file": ("board.png", png)})
    assert response.status_code == 202
    assert response.headers["x-request-id"]
    job_id = response.json()["inspection_id"]
    url = f"/api/v1/inspections/{job_id}"
    assert client.get(url).json()["status"] == "QUEUED"
    assert client.get(url + "/results").status_code == 409

    worker = Worker(app.state.repository, app.state.storage, settings)
    assert worker.run_once()
    assert not worker.run_once()
    report = client.get(url + "/results").json()
    assert report["is_demo"] is True
    assert report["overall_result"] == "NOT_EVALUATED"
    assert report["detections"] == []
    assert report["model_version"] == "demo-no-model-0.1.0"
    assert (report["image_width"], report["image_height"]) == (128, 96)
    assert "no trained model" in " ".join(report["limitations"])
    status = client.get(url).json()
    assert status["status"] == "COMPLETED"
    assert status["created_at"].endswith("Z")
    assert status["completed_at"] is not None
    download = client.get(url + "/report")
    assert download.json() == report
    assert download.headers["content-disposition"].startswith("attachment;")
    image = client.get(url + "/image")
    assert image.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(image.content)).size == (128, 96)
    assert client.get("/api/v1/inspections").json()["items"][0]["id"] == job_id

    with Session(app.state.repository.engine) as session:
        events = list(session.scalars(select(InspectionEvent).order_by(InspectionEvent.created_at)))
        assert [event.event_type for event in events] == [
            "inspection_queued",
            "inspection_processing",
            "inspection_completed",
        ]
        assert events[0].event_data["request_id"] == response.headers["x-request-id"]

    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(url + "/results").json() == report


def test_invalid_image_never_creates_a_job(client):
    response = client.post("/api/v1/inspections/upload", files={"file": ("fake.jpg", b"not jpeg")})
    assert response.status_code == 422
    assert client.get("/api/v1/inspections").json()["items"] == []


def test_content_is_validated_instead_of_filename_and_mime(client, png):
    response = client.post(
        "/api/v1/inspections/upload", files={"file": ("../../bad.exe", png, "text/plain")}
    )
    assert response.status_code == 202
    job_id = response.json()["inspection_id"]
    assert client.get(f"/api/v1/inspections/{job_id}/image").headers["content-type"] == "image/png"


def test_size_limit_and_streaming_body_limit(settings, png):
    tiny = settings.model_copy(update={"max_upload_bytes": 100})
    with TestClient(create_app(tiny)) as client:
        assert (
            client.post("/api/v1/inspections/upload", files={"file": ("x.png", png)}).status_code
            == 413
        )
        chunks = (b"x" * 16384 for _ in range(5))
        response = client.post(
            "/api/v1/inspections/upload",
            content=chunks,
            headers={"Content-Type": "multipart/form-data; boundary=x"},
        )
        # A malformed stream can be rejected before crossing the limit.
        assert response.status_code in {400, 413}
        boundary = b'--x\r\nContent-Disposition: form-data; name="file"; filename="x.png"\r\n\r\n'
        response = client.post(
            "/api/v1/inspections/upload",
            content=iter([boundary, b"x" * 70000, b"\r\n--x--\r\n"]),
            headers={"Content-Type": "multipart/form-data; boundary=x"},
        )
        assert response.status_code == 413


def test_history_pagination_and_missing_ids(client, png):
    for _ in range(3):
        assert (
            client.post("/api/v1/inspections/upload", files={"file": ("x.png", png)}).status_code
            == 202
        )
    first = client.get("/api/v1/inspections?limit=2").json()["items"]
    second = client.get("/api/v1/inspections?limit=2&offset=2").json()["items"]
    assert len(first) == 2 and len(second) == 1
    assert len({job["id"] for job in first + second}) == 3
    assert client.get("/api/v1/inspections?limit=101").status_code == 422
    assert client.get("/api/v1/inspections?offset=-1").status_code == 422
    assert client.get(f"/api/v1/inspections/{uuid4()}").status_code == 404
    assert client.get("/api/v1/inspections/not-a-uuid").status_code == 422
    assert (
        client.post("/api/v1/inspections/url", json={"image_url": "http://localhost"}).status_code
        == 405
    )


def test_owner_isolation_on_all_read_endpoints(client, settings, png):
    job_id = client.post("/api/v1/inspections/upload", files={"file": ("x.png", png)}).json()[
        "inspection_id"
    ]
    other = settings.model_copy(update={"local_user_id": "another-local-user"})
    with TestClient(create_app(other)) as client2:
        assert client2.get("/api/v1/inspections").json()["items"] == []
        for suffix in ["", "/results", "/report", "/image"]:
            assert client2.get(f"/api/v1/inspections/{job_id}{suffix}").status_code == 404


def test_health_ready_metrics_and_readiness_failure(client, settings):
    assert client.get("/health").json()["is_demo"] is True
    assert client.get("/ready").status_code == 200
    assert "pcb_api_requests_total" in client.get("/metrics").text
    invalid = settings.model_copy(update={"database_url": "sqlite:///:memory:"})
    with TestClient(create_app(invalid)) as fresh:
        assert fresh.get("/health").status_code == 200
        assert fresh.get("/ready").status_code == 503


def test_database_failure_cleans_new_object(app, png, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("sensitive database detail")

    monkeypatch.setattr(app.state.repository, "create", fail)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/v1/inspections/upload", files={"file": ("x.png", png)})
        assert response.status_code == 500
        assert "sensitive" not in response.text
    assert list(app.state.storage.root.rglob("*.png")) == []
