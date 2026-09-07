# Foundation architecture decisions

The full target remains the source architecture. This document records M1 choices.

```text
Local client -> FastAPI -> normalized PNG in filesystem
                       -> SQL inspection + queued event (one transaction)

Separate worker -> SQL conditional lease claim -> demo detector -> decision/report contract
                -> fenced completion + audit event (one transaction)

Local client -> status / history / image / report
```

SQLite is the single-machine default. Compose uses PostgreSQL through the same SQLAlchemy
repository. Explicit Alembic migrations run outside API startup to avoid concurrent DDL.
The report is persisted atomically in the inspection row; no second report object can become
inconsistent with completion. Separate model/detection/user tables follow their real features.

The database queue exercises durable asynchronous behavior without cloud services; it is not an
SQS emulator. Claims use conditional `UPDATE ... RETURNING`; an unexpired processing row is
ineligible. A random token and unexpired lease are required for completion/failure. Crashed
workers become eligible after expiry; exhausted jobs transition to `FAILED`. Retries use
exponential delay, with no retry of completed jobs. Events commit with state transitions.

The demo worker is fast and does not renew leases. Longer model execution needs lease/visibility
renewal before enabling a real adapter. SQL failures roll back transitions; the poller backs off
and retries. A stored image can be orphaned by a crash between filesystem write and SQL commit;
ordinary database failures trigger cleanup. Scheduled reconciliation is required in M4. There is
no claim of an atomic transaction across independent storage systems.

Storage keys are server-generated, path-contained and written via atomic rename. Images are
decoded, bounded, oriented and re-encoded with metadata stripped before storage. Filesystem
access is private to the local environment; the image endpoint filters by local owner.
No user-supplied URL is fetched. Production ingestion needs S3, Cognito and hardened egress.

The detector contract receives a decoded image and returns validated pixel-coordinate boxes.
The only configurable implementation is `DemoDetector`. The provisional decision policy retains
confidence >= 0.70, labels >= 0.90 high confidence, and rejects invalid/out-of-bounds geometry.
These values follow illustrative scope examples and are not calibrated. Model integration must
add class thresholds, artifact identity, quality checks, compatibility checks and held-out evaluation.

Structured application logs include request/inspection correlation. API Prometheus labels use
route templates so UUIDs do not create unbounded series. Inference/queue telemetry is subsequent work.

Implementation references:

- [FastAPI upload handling](https://fastapi.tiangolo.com/tutorial/request-files/)
- [SQLAlchemy conditional updates](https://docs.sqlalchemy.org/en/20/tutorial/data_update.html)
- [Pillow image validation](https://pillow.readthedocs.io/en/stable/reference/Image.html)
