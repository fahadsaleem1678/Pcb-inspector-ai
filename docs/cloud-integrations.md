# S3 storage, transactional outbox and SQS workers

Implemented for opt-in integration testing on 2026-09-14. Local database/filesystem mode
remains the default. Configuration still rejects production/staging environments and real
detectors. This implementation does not provision AWS resources or qualify the model.

## Submission and delivery

1. The API validates and normalizes an image, then writes it to a private S3 namespace.
2. One database transaction creates the inspection, its audit event and the submission
   outbox record. A rolled-back transaction cannot leave a publishable outbox record.
3. A separate outbox publisher leases pending records and sends their event/inspection IDs
   to standard SQS. It marks publication only after SendMessage succeeds. Send failures
   back off; crashes and ambiguous acknowledgements can resend the same event.
4. An SQS worker resolves the event against the database. Neither paths nor owner IDs come
   from queue messages. The database lease/token controls ownership and result writes.
5. During processing, a background heartbeat renews the database lease and SQS visibility.
   A renewal failure prevents that worker from committing an unfinished result. Expired or
   superseded database tokens cannot commit. Already committed completion remains authoritative.
6. Only a durable COMPLETED record permits message acknowledgement. Redelivery of a completed
   event acknowledges it without another inference. Active duplicates are not acknowledged.
   Retriable failures retain the message and apply the database's retry delay. Failed jobs,
   unknown events and malformed messages remain available for native SQS DLQ redrive.

Delivery and inference attempts are at least once, not exactly once. Database fencing allows
one committed completion per processing cycle. Explicit operator retries create a new cycle.
Upload requests do not yet accept an idempotency key: after an uncertain POST, inspect history
before retrying, because resubmission creates a separate inspection. Browser code does not
silently replay uploads.

AWS documents that receipt handles identify delivery attempts and that standard messages
can be delivered again after deletion. See [DeleteMessage](https://docs.aws.amazon.com/boto3/latest/reference/services/sqs/client/delete_message.html)
and [ChangeMessageVisibility](https://docs.aws.amazon.com/boto3/latest/reference/services/sqs/client/change_message_visibility.html).

## Configure an authorized integration environment

Use an existing private bucket, standard source queue with a configured DLQ, and a disposable
or reviewed database. Public access is not enabled by this configuration.

```dotenv
PCB_ENVIRONMENT=local
PCB_DETECTOR=demo
PCB_STORAGE_BACKEND=s3
PCB_QUEUE_BACKEND=sqs
PCB_AWS_REGION=us-east-1
PCB_S3_BUCKET=your-private-bucket
PCB_S3_PREFIX=pcb-inspector
PCB_SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789012/pcb-inspections
PCB_LEASE_SECONDS=120
PCB_SQS_VISIBILITY_SECONDS=120
PCB_OUTBOX_LEASE_SECONDS=120
# Optional explicit KMS key; otherwise requests specify SSE-S3 AES256 encryption:
# PCB_S3_KMS_KEY_ID=your-key-arn
```

SQS requires S3 storage, a standard HTTPS queue URL in the selected region, and a database
lease of at least 30 seconds. Publisher/worker startup checks the source queue's redrive
policy: the DLQ must be a different standard queue in the same account/region, and its
maxReceiveCount must be at least PCB_MAX_ATTEMPTS + 2. Use a larger margin for duplicate
traffic, long retry delays and restarts. Receipt counts and inference attempts differ.

Use the SDK credential chain locally and distinct task roles when deployed. Do not place
credentials in repository files or frontend variables. The SDK uses bounded connection/read
timeouts and three total attempts. No arbitrary custom endpoints or bucket/queue creation
are included. IAM/bucket/KMS policies still need live review.

Run migration before starting the processes:

```powershell
.venv\Scripts\python.exe -m alembic upgrade head
# Separate terminals/processes with the same database, namespace and queue configuration:
.venv\Scripts\python.exe -m uvicorn pcb_inspector.api:create_app --factory --host 127.0.0.1 --port 8000
.venv\Scripts\python.exe -m pcb_inspector.outbox
.venv\Scripts\python.exe -m pcb_inspector.worker
```

Publisher and worker each support --once. A worker receive can long-poll for 20 seconds.
The API accepts uploads while SQS is unavailable: the database outbox retains publication
intent. /ready checks the schema and object store, not publisher liveness or queue backlog.

Migration 0002 preserves existing jobs as database-queue jobs. Database workers cannot claim
SQS jobs. Do not simply switch an existing local database to S3: its older image keys still
refer to filesystem objects. Use a fresh integration database or a separately verified
object migration before changing storage. Downgrade refuses any database containing SQS
inspection records to avoid discarding delivery intent.

## Private objects and reconciliation

The API checks ownership before fetching image bytes. Both API and worker use the same
ObjectStore interface. S3 keys are namespace-bound, writes specify encryption and SHA256,
and reads enforce size limits and verify stored SHA256 metadata. Downloads remain bearer-
authenticated API responses; no public ACLs, token URLs or presigned upload bypass are added.
See [S3 PutObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/put_object.html).

The API intentionally retains uploaded objects after uncertain database commits. Deleting
immediately could remove an image belonging to an already committed inspection. A failed or
interrupted write/transaction can leave an orphan; record retention and operational cleanup
remain necessary. The audit command only lists old unreferenced upload candidates:

```powershell
.venv\Scripts\python.exe -m pcb_inspector.storage_audit --min-age-hours 24
```

It scans only the uploads namespace, skips recent objects and checks all inspection owners.
It never deletes objects. Concurrent submissions can change references after a scan: before
any separately approved cleanup, pause submissions and recheck database references. Versioned
bucket noncurrent versions and health-probe retention need separate lifecycle rules. The audit
does not certify that a candidate is safe to delete.

## Failure recovery and DLQ

After diagnosing and fixing a failed inspection, an operator with database access can request
an explicit retry. Do not run this command automatically on every failed event:

```powershell
.venv\Scripts\python.exe -m pcb_inspector.outbox --redrive INSPECTION_UUID
```

This atomically resets a FAILED SQS job's attempt budget, reopens its existing outbox event,
and records inspection_redrive_requested. Concurrent requests cannot reset it twice; a
COMPLETED/PROCESSING/QUEUED job is rejected. Historical failure/audit events are retained.
The publisher resends the event. Delayed/old deliveries remain protected by database fencing.
This command does not move or purge SQS DLQ messages; inspect and clean those separately after
verifying recovery. Poison/unknown events require operator diagnosis and cannot claim other jobs.

Watch oldest unpublished outbox age, send failures, database queue age, expired leases,
source/DLQ depth and retention. A message reaching the DLQ/retention limit can leave an
unprocessed database job, so queue/database reconciliation and alerts are required for live
operations. Automatic DLQ consumption and dashboard/alert provisioning are not implemented.

Suggested least-privilege boundaries: API S3 Put/Get (Delete only for its readiness prefix),
worker S3 Get and source SQS Receive/Delete/ChangeMessageVisibility/GetQueueAttributes,
publisher source SQS Send/GetQueueAttributes. The operator audit additionally needs scoped
S3 ListBucket. KMS use adds the corresponding key permissions. Keep buckets private and
validate these policies with the actual deployment roles.

## Verification and remaining acceptance

Local tests use real SDK request-model stubs, an in-memory S3/queue simulator and real SQLite
transactions/migrations. They cover encryption/checksum/bounds/ownership, atomic outbox
creation, concurrent leasing, publisher failure/crash, duplicate/poison delivery, receipt
acknowledgement loss, heartbeat renewal/loss, retry exhaustion, explicit redrive, migration
compatibility and read-only orphan candidates. These are not live AWS acceptance tests.

CI's PostgreSQL job now runs cloud/worker tests in a unique disposable schema per test via
PCB_TEST_DATABASE_URL. Use only a disposable database for that setting; test schemas are
removed after each test. The local Docker engine was unavailable, so PostgreSQL verification
of this change and fresh remote CI remain pending.

Next acceptance work: a live authorized S3/SQS/Cognito environment, queue-policy/IAM/KMS checks,
kill/restart and retention/DLQ drills, storage migration if needed, alerts, rate limiting,
load/capacity testing, backups/restore, and staging deployment. Expert labels, negatives,
external-camera evaluation and an approved detector remain independent release gates.
