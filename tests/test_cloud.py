import base64
import hashlib
import io
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from pcb_inspector.api import create_app
from pcb_inspector.config import Settings
from pcb_inspector.database import Inspection, InspectionEvent, SubmissionOutbox
from pcb_inspector.outbox import Outbox, Publisher
from pcb_inspector.queue import Delivery, SQSQueue
from pcb_inspector.sqs_worker import Heartbeat, SQSWorker
from pcb_inspector.storage import S3ObjectStore
from pcb_inspector.worker import Worker


@pytest.fixture
def cloud(settings):
    return Settings(
        **{
            **settings.model_dump(),
            "storage_backend": "s3",
            "queue_backend": "sqs",
            "aws_region": "us-east-1",
            "s3_bucket": "test-pcb-bucket",
            "sqs_queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/pcb",
        },
        _env_file=None,
    )


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(("put", kwargs))
        self.objects[kwargs["Key"]] = kwargs

    def get_object(self, **kwargs):
        self.calls.append(("get", kwargs))
        if kwargs["Key"] not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        item = self.objects[kwargs["Key"]]
        return {
            "Body": io.BytesIO(item["Body"]),
            "ContentLength": len(item["Body"]),
            "Metadata": item["Metadata"],
        }

    def delete_object(self, **kwargs):
        self.calls.append(("delete", kwargs))
        self.objects.pop(kwargs["Key"], None)


class FakeQueue:
    def __init__(self, settings):
        self.settings = settings
        self.messages = []
        self.sent = []
        self.deleted = []
        self.renewed = []
        self.fail_send = False
        self.fail_renew = False
        self.fail_delete = False

    def send(self, event_id, inspection_id):
        if self.fail_send:
            raise TimeoutError("uncertain publish")
        body = json.dumps({"version": 1, "event_id": event_id, "inspection_id": inspection_id})
        self.sent.append(body)
        self.messages.append(Delivery(str(uuid4()), body))

    def receive(self):
        return self.messages.pop(0) if self.messages else None

    def renew(self, delivery, seconds=None):
        if self.fail_renew:
            raise TimeoutError("visibility renewal failed")
        self.renewed.append((delivery.receipt, seconds))

    def delete(self, delivery):
        if self.fail_delete:
            raise TimeoutError("ack failed")
        self.deleted.append(delivery.receipt)


@pytest.fixture
def cloud_app(cloud, monkeypatch):
    sdk = MemoryS3()
    monkeypatch.setattr("pcb_inspector.aws.aws_client", lambda service, settings: sdk)
    app = create_app(cloud)
    with TestClient(app) as client:
        yield app, client, sdk


def submit(cloud_app, png):
    app, client, _ = cloud_app
    response = client.post("/api/v1/inspections/upload", files={"file": ("pcb.png", png)})
    assert response.status_code == 202
    job_id = response.json()["inspection_id"]
    with Session(app.state.repository.engine) as session:
        event = session.scalar(
            select(SubmissionOutbox).where(SubmissionOutbox.inspection_id == job_id)
        )
    return job_id, event


def deliver(queue, event):
    queue.send(event.id, event.inspection_id)
    return queue.messages[-1]


@pytest.mark.parametrize(
    "changes",
    [
        {"aws_region": None},
        {"s3_bucket": None},
        {"storage_backend": "local"},
        {"s3_prefix": "../escape"},
        {"s3_prefix": "/root"},
        {"s3_prefix": "a//b"},
        {"sqs_queue_url": "http://127.0.0.1/queue"},
        {"sqs_queue_url": "https://sqs.eu-west-1.amazonaws.com/123456789012/pcb"},
        {"sqs_queue_url": "https://sqs.us-east-1.amazonaws.com/123456789012/pcb.fifo"},
        {"lease_seconds": 1},
        {"sqs_visibility_seconds": 43201},
        {"environment": "production"},
        {"detector": "real"},
    ],
)
def test_cloud_settings_fail_closed(cloud, changes):
    with pytest.raises(ValidationError):
        Settings(**{**cloud.model_dump(), **changes}, _env_file=None)


def test_s3_sdk_contract(cloud):
    client = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    store = S3ObjectStore(client, cloud)
    content = b"test"
    digest = hashlib.sha256(content).digest()
    body = io.BytesIO(content)
    with Stubber(client) as stub:
        stub.add_response(
            "put_object",
            {},
            {
                "Bucket": cloud.s3_bucket,
                "Key": "pcb-inspector/uploads/a.png",
                "Body": content,
                "ContentType": "image/png",
                "ChecksumSHA256": base64.b64encode(digest).decode(),
                "Metadata": {"sha256": digest.hex()},
                "ServerSideEncryption": "AES256",
            },
        )
        stub.add_response(
            "get_object",
            {"Body": body, "ContentLength": 4, "Metadata": {"sha256": digest.hex()}},
            {"Bucket": cloud.s3_bucket, "Key": "pcb-inspector/uploads/a.png"},
        )
        stub.add_response(
            "delete_object", {}, {"Bucket": cloud.s3_bucket, "Key": "pcb-inspector/uploads/a.png"}
        )
        store.put("uploads/a.png", content)
        assert store.get("uploads/a.png") == content
        assert body.closed
        store.delete("uploads/a.png")
        stub.assert_no_pending_responses()


@pytest.mark.parametrize(
    "key", ["", "/absolute", "../escape", "a/../b", "a//b", "a\\b", "x" * 1025]
)
def test_s3_key_containment(cloud, key):
    sdk = MemoryS3()
    with pytest.raises(ValueError):
        S3ObjectStore(sdk, cloud).put(key, b"x")
    assert sdk.calls == []


def test_s3_kms_corruption_bounds_and_missing(cloud):
    sdk = MemoryS3()
    store = S3ObjectStore(sdk, cloud.model_copy(update={"s3_kms_key_id": "test-key"}))
    store.put("a", b"original")
    item = sdk.objects["pcb-inspector/a"]
    assert item["SSEKMSKeyId"] == "test-key" and item["ServerSideEncryption"] == "aws:kms"
    item["Body"] = b"tampered"
    with pytest.raises(ValueError, match="checksum"):
        store.get("a")
    store.max_bytes = 1
    with pytest.raises(ValueError, match="size limit"):
        store.get("a")
    with pytest.raises(ValueError, match="size limit"):
        store.put("b", b"large")
    with pytest.raises(FileNotFoundError):
        store.get("missing")


def test_s3_access_denied_is_not_missing(cloud):
    client = boto3.client(
        "s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    with Stubber(client) as stub:
        stub.add_client_error("get_object", service_error_code="AccessDenied")
        with pytest.raises(ClientError):
            S3ObjectStore(client, cloud).get("private.png")


def test_submission_transaction_and_s3_owned_delivery(cloud_app, cloud, png, monkeypatch):
    app, client, sdk = cloud_app
    job_id, event = submit(cloud_app, png)
    repo = app.state.repository
    assert event is not None and event.published_at is None
    assert repo.get(job_id, cloud.local_user_id).queue_backend == "sqs"
    assert client.get(f"/api/v1/inspections/{job_id}/image").status_code == 200
    other = cloud.model_copy(update={"local_user_id": "another-user"})
    before = len(sdk.calls)
    with TestClient(create_app(other)) as other_client:
        assert other_client.get(f"/api/v1/inspections/{job_id}/image").status_code == 404
    assert len(sdk.calls) == before  # Ownership checked before touching S3.
    assert repo.claim(cloud.model_copy(update={"queue_backend": "database"})) is None
    with pytest.raises(ValueError, match="message-bound"):
        repo.claim(cloud)

    def fail(*args, **kwargs):
        raise RuntimeError("transaction failure")

    monkeypatch.setattr(repo, "_event", fail)
    with pytest.raises(RuntimeError):
        repo.create(str(uuid4()), "owner", "new.png", 128, 96, "request", queue_backend="sqs")
    with Session(repo.engine) as session:
        assert session.scalar(select(func.count()).select_from(Inspection)) == 1
        assert session.scalar(select(func.count()).select_from(SubmissionOutbox)) == 1


def test_commit_acknowledgement_loss_keeps_referenced_image(cloud_app, cloud, png, monkeypatch):
    app, _, sdk = cloud_app
    original = app.state.repository.create

    def commit_then_error(*args, **kwargs):
        original(*args, **kwargs)
        raise TimeoutError("commit acknowledgement lost")

    monkeypatch.setattr(app.state.repository, "create", commit_then_error)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert (
            client.post("/api/v1/inspections/upload", files={"file": ("pcb.png", png)}).status_code
            == 500
        )
    jobs = app.state.repository.history(cloud.local_user_id, 10, 0)
    assert len(jobs) == 1
    assert app.state.storage.get(jobs[0].image_key)
    assert not any(call[0] == "delete" for call in sdk.calls)


def test_outbox_exclusion_expiry_backoff_and_fencing(cloud_app, cloud, png):
    app, _, _ = cloud_app
    submit(cloud_app, png)
    outbox = Outbox(app.state.repository.engine, cloud)
    now = time.time() + 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: outbox.claim(now), range(4)))
    first = next(event for event in claims if event is not None)
    assert sum(event is not None for event in claims) == 1
    assert outbox.claim(now + 1) is None
    second = outbox.claim(now + cloud.outbox_lease_seconds)
    assert second.attempts == 2 and second.lease_token != first.lease_token
    assert not outbox.finish(first, published=True, now=now + cloud.outbox_lease_seconds)
    assert outbox.finish(second, published=False, now=now + cloud.outbox_lease_seconds)
    assert outbox.claim(now + cloud.outbox_lease_seconds + 3) is None
    retry = outbox.claim(now + cloud.outbox_lease_seconds + 4)
    assert retry.attempts == 3
    assert outbox.finish(retry, published=True, now=now + cloud.outbox_lease_seconds + 5)
    assert outbox.claim(now + 1000) is None


def test_publish_failure_retries_and_crash_resends_same_identity(cloud_app, cloud, png):
    app, _, _ = cloud_app
    _, event = submit(cloud_app, png)
    outbox = Outbox(app.state.repository.engine, cloud)
    queue = FakeQueue(cloud)
    publisher = Publisher(outbox, queue)
    queue.fail_send = True
    assert publisher.run_once()
    assert not publisher.run_once()
    with Session(outbox.engine) as session, session.begin():
        session.execute(update(SubmissionOutbox).values(available_at=0))
    queue.fail_send = False
    claimed = outbox.claim()
    queue.send(claimed.id, claimed.inspection_id)  # Process dies before marking publication.
    with Session(outbox.engine) as session, session.begin():
        session.execute(update(SubmissionOutbox).values(lease_until=0))
    assert publisher.run_once()
    assert len(queue.sent) == 2 and queue.sent[0] == queue.sent[1]
    assert json.loads(queue.sent[0])["event_id"] == event.id


def test_sqs_worker_duplicate_ack_loss_and_exactly_one_result(cloud_app, cloud, png):
    app, client, _ = cloud_app
    job_id, event = submit(cloud_app, png)
    queue = FakeQueue(cloud)
    worker = SQSWorker(Worker(app.state.repository, app.state.storage, cloud), queue)
    deliver(queue, event)
    queue.fail_delete = True
    with pytest.raises(TimeoutError):
        worker.run_once()
    assert client.get(f"/api/v1/inspections/{job_id}").json()["status"] == "COMPLETED"
    queue.fail_delete = False
    receipt = deliver(queue, event).receipt
    assert worker.run_once()
    assert queue.deleted == [receipt]
    with Session(app.state.repository.engine) as session:
        events = list(
            session.scalars(
                select(InspectionEvent).where(InspectionEvent.event_type == "inspection_completed")
            )
        )
        assert len(events) == 1
    assert app.state.repository.get(job_id, cloud.local_user_id).attempts == 1


def test_duplicate_while_processing_not_acknowledged(cloud_app, cloud, png):
    app, _, _ = cloud_app
    job_id, event = submit(cloud_app, png)
    repo = app.state.repository
    repo.claim(cloud, inspection_id=job_id)
    queue = FakeQueue(cloud)
    deliver(queue, event)
    assert SQSWorker(Worker(repo, app.state.storage, cloud), queue).run_once()
    assert queue.deleted == []
    assert repo.get(job_id, cloud.local_user_id).attempts == 1


def test_worker_retry_and_terminal_failure_retained_for_dlq(cloud_app, cloud, png):
    app, _, _ = cloud_app
    job_id, event = submit(cloud_app, png)
    repo = app.state.repository
    app.state.storage.delete(repo.get(job_id, cloud.local_user_id).image_key)
    queue = FakeQueue(cloud)
    worker = SQSWorker(Worker(repo, app.state.storage, cloud), queue)
    for _ in range(cloud.max_attempts + 1):
        deliver(queue, event)
        assert worker.run_once()
    assert repo.get(job_id, cloud.local_user_id).status == "FAILED"
    assert repo.get(job_id, cloud.local_user_id).attempts == cloud.max_attempts
    assert queue.deleted == []


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        "{}",
        '"hello"',
        "x" * 1025,
        json.dumps({"version": True, "event_id": str(uuid4()), "inspection_id": str(uuid4())}),
        json.dumps(
            {
                "version": 1,
                "event_id": str(uuid4()),
                "inspection_id": str(uuid4()),
                "image_key": "evil",
            }
        ),
        json.dumps({"version": 1, "event_id": str(uuid4()), "inspection_id": str(uuid4())}),
    ],
)
def test_poison_and_unknown_events_cannot_claim_jobs(cloud_app, cloud, png, body):
    app, _, _ = cloud_app
    job_id, _ = submit(cloud_app, png)
    queue = FakeQueue(cloud)
    queue.messages.append(Delivery("poison", body))
    assert SQSWorker(Worker(app.state.repository, app.state.storage, cloud), queue).run_once()
    assert queue.deleted == []
    assert app.state.repository.get(job_id, cloud.local_user_id).attempts == 0


def test_heartbeat_loss_blocks_completion_and_expired_renewal(cloud_app, cloud, png):
    app, _, _ = cloud_app
    job_id, event = submit(cloud_app, png)
    queue = FakeQueue(cloud)
    worker = Worker(app.state.repository, app.state.storage, cloud)
    job = worker.repository.claim(cloud, inspection_id=job_id)
    delivery = deliver(queue, event)
    heartbeat = Heartbeat(worker, queue, delivery, job)
    assert heartbeat.pulse()
    queue.fail_renew = True
    assert not heartbeat.pulse()
    worker.process(job, can_commit=lambda: not heartbeat.lost.is_set())
    assert worker.repository.get(job_id, cloud.local_user_id).status == "PROCESSING"
    future = time.time() + cloud.lease_seconds + 1
    assert not worker.repository.renew(job, cloud, now=future)
    replacement = worker.repository.claim(cloud, future, inspection_id=job_id)
    assert replacement.lease_token != job.lease_token
    assert not worker.repository.renew(job, cloud, now=future + 1)


def test_live_heartbeat_extends_lease_during_processing(cloud_app, cloud, png, monkeypatch):
    app, _, _ = cloud_app
    job_id, event = submit(cloud_app, png)
    queue = FakeQueue(cloud)
    renewed = threading.Event()
    original = queue.renew

    def renewal(delivery, seconds=None):
        original(delivery, seconds)
        if len(queue.renewed) >= 2:
            renewed.set()

    queue.renew = renewal
    original_init = Heartbeat.__init__

    def fast_interval(self, *args):
        original_init(self, *args)
        self.interval = 0.01

    monkeypatch.setattr(Heartbeat, "__init__", fast_interval)

    class SlowDetector:
        version = "test-only"
        is_demo = True

        def predict(self, image):
            assert renewed.wait(3), "background heartbeat did not run"
            return []

    deliver(queue, event)
    worker = Worker(app.state.repository, app.state.storage, cloud, SlowDetector())
    assert SQSWorker(worker, queue).run_once()
    assert renewed.is_set() and len(queue.deleted) == 1
    assert app.state.repository.get(job_id, cloud.local_user_id).status == "COMPLETED"


def test_sqs_sdk_contract_and_dlq_validation(cloud):
    client = boto3.client(
        "sqs", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test"
    )
    queue = SQSQueue(client, cloud)
    event, job = str(uuid4()), str(uuid4())
    body = json.dumps({"version": 1, "event_id": event, "inspection_id": job})
    with Stubber(client) as stub:
        stub.add_response(
            "get_queue_attributes",
            {
                "Attributes": {
                    "QueueArn": "arn:aws:sqs:us-east-1:123456789012:pcb",
                    "RedrivePolicy": json.dumps(
                        {
                            "deadLetterTargetArn": "arn:aws:sqs:us-east-1:123456789012:pcb-dlq",
                            "maxReceiveCount": "10",
                        }
                    ),
                }
            },
        )
        stub.add_response(
            "send_message", {"MessageId": "sent"}, {"QueueUrl": queue.url, "MessageBody": body}
        )
        stub.add_response(
            "receive_message",
            {"Messages": [{"ReceiptHandle": "receipt", "Body": body}]},
            {
                "QueueUrl": queue.url,
                "MaxNumberOfMessages": 1,
                "WaitTimeSeconds": 20,
                "VisibilityTimeout": 120,
            },
        )
        stub.add_response(
            "change_message_visibility",
            {},
            {"QueueUrl": queue.url, "ReceiptHandle": "receipt", "VisibilityTimeout": 120},
        )
        stub.add_response("delete_message", {}, {"QueueUrl": queue.url, "ReceiptHandle": "receipt"})
        queue.validate()
        queue.send(event, job)
        delivery = queue.receive()
        assert delivery.identities() == (event, job)
        queue.renew(delivery)
        queue.delete(delivery)
        stub.assert_no_pending_responses()


@pytest.mark.parametrize(
    "policy",
    [
        {},
        {"deadLetterTargetArn": "bad", "maxReceiveCount": 10},
        {"deadLetterTargetArn": "arn:aws:sqs:us-east-1:123456789012:pcb-dlq", "maxReceiveCount": 2},
        {
            "deadLetterTargetArn": "arn:aws:sqs:eu-west-1:123456789012:pcb-dlq",
            "maxReceiveCount": 10,
        },
    ],
)
def test_missing_or_invalid_redrive_policy_blocks_startup(cloud, policy):
    class SDK:
        def get_queue_attributes(self, **kwargs):
            return {
                "Attributes": {
                    "QueueArn": "arn:aws:sqs:us-east-1:123456789012:pcb",
                    "RedrivePolicy": json.dumps(policy),
                }
            }

    with pytest.raises(ValueError):
        SQSQueue(SDK(), cloud).validate()


def test_explicit_redrive_is_atomic_and_duplicate_safe(cloud_app, cloud, png):
    app, _, _ = cloud_app
    job_id, event = submit(cloud_app, png)
    repo = app.state.repository
    queue = FakeQueue(cloud)
    broken = Worker(repo, app.state.storage, cloud.model_copy(update={"max_attempts": 1}))
    job = repo.claim(broken.settings, inspection_id=job_id)
    assert repo.fail(job, broken.settings)
    outbox = Outbox(repo.engine, cloud)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: outbox.redrive(job_id), range(2)))
    assert sum(results) == 1
    assert repo.get(job_id, cloud.local_user_id).attempts == 0
    assert Publisher(outbox, queue).run_once()
    deliver(queue, event)  # Old receipt/redrive duplicates are still safe.
    worker = SQSWorker(Worker(repo, app.state.storage, cloud), queue)
    assert worker.run_once() and worker.run_once()
    assert repo.get(job_id, cloud.local_user_id).status == "COMPLETED"
    assert repo.get(job_id, cloud.local_user_id).attempts == 1
    assert not outbox.redrive(job_id)
    with Session(repo.engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(InspectionEvent)
                .where(InspectionEvent.event_type == "inspection_redrive_requested")
            )
            == 1
        )


def test_orphan_audit_excludes_referenced_and_recent_objects(cloud_app, cloud, png):
    from pcb_inspector.storage_audit import audit

    app, _, sdk = cloud_app
    job_id, _ = submit(cloud_app, png)
    job = app.state.repository.get(job_id, cloud.local_user_id)
    now = time.time()
    records = [
        (job.image_key, now - 100000),
        ("uploads/orphan/original.png", now - 100000),
        ("uploads/inflight/original.png", now),
    ]
    before = list(sdk.calls)
    result = audit(app.state.repository.engine, records, now=now)
    assert result["candidates"] == [
        {"image_key": "uploads/orphan/original.png", "modified_at": now - 100000}
    ]
    assert result["read_only"] and not result["deletion_approved"]
    assert sdk.calls == before
    with pytest.raises(ValueError):
        audit(app.state.repository.engine, records, min_age_seconds=0)


def test_retry_wait_does_not_consume_attempts(cloud_app, cloud, png):
    app, _, _ = cloud_app
    job_id, event = submit(cloud_app, png)
    repo = app.state.repository
    delayed = cloud.model_copy(update={"retry_delay_seconds": 300})
    job = repo.claim(delayed, inspection_id=job_id)
    repo.fail(job, delayed)
    queue = FakeQueue(delayed)
    deliver(queue, event)
    assert SQSWorker(Worker(repo, app.state.storage, delayed), queue).run_once()
    assert queue.deleted == []
    assert repo.get(job_id, cloud.local_user_id).attempts == 1


def test_heartbeat_initial_failure_never_runs_inference(cloud_app, cloud, png):
    app, _, _ = cloud_app
    job_id, event = submit(cloud_app, png)
    queue = FakeQueue(cloud)
    queue.fail_renew = True
    deliver(queue, event)
    worker = Worker(app.state.repository, app.state.storage, cloud)
    assert SQSWorker(worker, queue).run_once()
    assert app.state.repository.get(job_id, cloud.local_user_id).status == "PROCESSING"
    assert queue.deleted == []


def test_expired_final_sqs_attempt_becomes_failed_for_dlq(cloud_app, cloud, png):
    app, _, _ = cloud_app
    job_id, event = submit(cloud_app, png)
    repo = app.state.repository
    single = cloud.model_copy(update={"max_attempts": 1})
    repo.claim(single, inspection_id=job_id)
    with Session(repo.engine) as session, session.begin():
        session.execute(update(Inspection).where(Inspection.id == job_id).values(lease_until=0))
    queue = FakeQueue(single)
    deliver(queue, event)
    assert SQSWorker(Worker(repo, app.state.storage, single), queue).run_once()
    assert repo.get(job_id, cloud.local_user_id).error_code == "RETRY_LIMIT_EXCEEDED"
    assert queue.deleted == []


def test_migration_preserves_existing_jobs_and_refuses_unsafe_downgrade(settings):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text

    from pcb_inspector.database import make_engine

    config = Config("alembic.ini")
    command.downgrade(config, "0001")
    engine = make_engine(settings.database_url)
    try:
        job_id = str(uuid4())
        with engine.begin() as connection:
            connection.execute(
                text("""INSERT INTO inspections
                (id, owner_id, image_key, width, height, status, created_at, available_at, attempts)
                VALUES (:id, 'owner', 'old.png', 128, 96, 'QUEUED', 1, 1, 0)"""),
                {"id": job_id},
            )
        command.upgrade(config, "head")
        with engine.begin() as connection:
            assert (
                connection.execute(text("SELECT queue_backend FROM inspections")).scalar()
                == "database"
            )
            connection.execute(text("UPDATE inspections SET queue_backend = 'sqs'"))
        with pytest.raises(RuntimeError, match="Cannot downgrade"):
            command.downgrade(config, "0001")
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == "0002"
            )
    finally:
        engine.dispose()
