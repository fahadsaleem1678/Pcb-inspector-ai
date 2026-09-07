import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from pcb_inspector.inference import decide
from pcb_inspector.schemas import BoundingBox, Detection, Report
from pcb_inspector.worker import Worker


def submit(client, png):
    return client.post("/api/v1/inspections/upload", files={"file": ("x.png", png)}).json()[
        "inspection_id"
    ]


def report(job):
    return Report(
        inspection_id=job.id,
        model_version="test",
        is_demo=True,
        overall_result="NOT_EVALUATED",
        inference_time_ms=1,
        image_width=128,
        image_height=96,
        detections=[],
        ignored_detection_count=0,
        limitations=[],
    )


def test_exclusive_claim_and_fenced_completion(client, app, settings, png):
    job_id = submit(client, png)
    repo = app.state.repository
    now = time.time() + 1
    first = repo.claim(settings, now)
    assert first.id == job_id
    assert repo.claim(settings, now + 1) is None
    expiry = now + settings.lease_seconds
    assert not repo.complete(first, report(first), expiry)
    second = repo.claim(settings, expiry)
    assert second.attempts == 2 and second.lease_token != first.lease_token
    assert not repo.complete(first, report(first), expiry + 1)
    assert not repo.fail(first, settings, expiry + 1)
    assert repo.complete(second, report(second), expiry + 1)
    assert not repo.complete(second, report(second), expiry + 2)
    assert repo.claim(settings, expiry + 3) is None


def test_concurrent_workers_cannot_own_same_job(client, app, settings, png):
    submit(client, png)
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = list(pool.map(lambda _: app.state.repository.claim(settings), range(4)))
    assert len([job for job in jobs if job is not None]) == 1


def test_repeated_worker_failure_becomes_terminal(client, app, settings, png):
    job_id = submit(client, png)
    job = app.state.repository.get(job_id, settings.local_user_id)
    app.state.storage.delete(job.image_key)
    worker = Worker(app.state.repository, app.state.storage, settings)
    for _ in range(settings.max_attempts):
        assert worker.run_once()
    assert not worker.run_once()
    state = client.get(f"/api/v1/inspections/{job_id}").json()
    assert state["status"] == "FAILED"
    assert state["attempts"] == settings.max_attempts
    assert state["error_code"] == "INFERENCE_FAILED"
    assert client.get(f"/api/v1/inspections/{job_id}/results").status_code == 409


def test_crashed_final_attempt_is_reaped(client, app, settings, png):
    job_id = submit(client, png)
    repo = app.state.repository
    now = time.time() + 1
    for attempt in range(settings.max_attempts):
        claimed = repo.claim(settings, now + attempt * settings.lease_seconds)
        assert claimed.attempts == attempt + 1
    assert repo.claim(settings, now + settings.max_attempts * settings.lease_seconds) is None
    job = repo.get(job_id, settings.local_user_id)
    assert job.status == "FAILED"
    assert job.error_code == "RETRY_LIMIT_EXCEEDED"


def test_retry_delay_is_respected(client, app, settings, png):
    submit(client, png)
    repo = app.state.repository
    delayed = settings.model_copy(update={"retry_delay_seconds": 5})
    now = time.time() + 1
    job = repo.claim(delayed, now)
    assert repo.fail(job, delayed, now + 1)
    assert repo.claim(delayed, now + 5) is None
    assert repo.claim(delayed, now + 6).attempts == 2


@pytest.mark.parametrize(
    "confidence,count,band",
    [(0.699, 0, None), (0.70, 1, "review"), (0.899, 1, "review"), (0.90, 1, "high")],
)
def test_decision_boundaries(confidence, count, band):
    detection = Detection(
        defect_type="solder_bridge",
        confidence=confidence,
        bbox=BoundingBox(x1=1, y1=1, x2=10, y2=10),
    )
    findings, ignored = decide([detection], 128, 96)
    assert len(findings) == count
    assert ignored == 1 - count
    if findings:
        assert findings[0].severity == "critical"
        assert findings[0].confidence_band == band


def test_invalid_model_output_is_rejected():
    with pytest.raises(ValidationError):
        BoundingBox(x1=10, y1=1, x2=5, y2=10)
    with pytest.raises(ValidationError):
        BoundingBox(x1=1, y1=1, x2=float("nan"), y2=10)
    bbox = BoundingBox(x1=1, y1=1, x2=130, y2=10)
    with pytest.raises(ValueError, match="out-of-bounds"):
        decide([Detection(defect_type="solder_bridge", confidence=0.9, bbox=bbox)], 128, 96)
    with pytest.raises(ValidationError):
        Detection(defect_type="solder_bridge", confidence=float("nan"), bbox=bbox)
