# Implementation plan

Source of scope: `PCB_Inspector_AI_Production_Architecture.md`, with the accepted V1
surface-defect revision in [Dataset V1 specification](dataset-v1-spec.md).
Started: 2026-09-07. The workspace initially contained only that document.

## Delivery approach

Deliver testable milestones in dependency order. The source's week estimates are planning
guidance, not committed dates. Begin with asynchronous processing so later model integration
does not require moving inference out of API requests. Production completion still requires
all of the source document's user and engineering acceptance criteria.

Decisions for the first iteration:

- Python 3.12, FastAPI, SQLAlchemy 2, Alembic; React/TypeScript follows the backend contract.
- One Python package with distinct API and worker entry points and containers. Shared contracts
  live in `src/pcb_inspector` rather than being copied between service directories.
- SQLite and filesystem storage for a zero-service local run; PostgreSQL in Docker Compose.
- A transactional database job queue for the local milestone. SQS and an outbox arrive in M4;
  neither an in-memory queue nor request background tasks are used as durable infrastructure.
- Only an explicitly labeled demo detector initially. It emits no fabricated defects and
  always returns `NOT_EVALUATED`; successful processing never means a board passed inspection.
- Local single-user development only. Configuration refuses non-local environments until
  authentication and production storage/queue integrations are implemented.
- ECS/Fargate first for staging. EKS follows an explicit operational/portfolio need and a
  resource budget; no cloud resources are provisioned during foundation work.
- URL ingestion follows authentication and a tested SSRF threat model. No arbitrary fetch
  endpoint is exposed in the foundation.

## Milestones and acceptance gates

| Milestone | Scope | Acceptance gate | Dependencies |
| --- | --- | --- | --- |
| M1 â€” Backend foundation | Package, config, migration, image validation, storage, durable jobs, API, separate demo worker, events, metrics, CI, Compose | Upload â†’ queued â†’ worker â†’ persisted demo report; restart persistence, invalid uploads, lease recovery and duplicate ownership tests pass | None |
| M2 â€” Local product | React/TypeScript upload, polling, image viewer with coordinate-correct overlays, errors, history, JSON report download, accessibility | Browser test of complete workflow; responsive desktop/mobile layouts; demo mode is visibly labeled | M1 |
| M3 â€” Data and real inference | Inventory/licenses, taxonomy decision, grouped splits, duplicate/annotation validation, DVC manifest, quality checks, YOLO baseline, MLflow evaluation, detector adapter | Reproducible held-out evaluation with per-class AP/recall, latency, artifact hash and label map; thresholds justified by validation data | Dataset permission and class coverage; M1 contract |
| M4 â€” Production service integrations | Cognito JWT verification, owner isolation, S3 adapters/presigned uploads, SQS/outbox, visibility renewal, idempotent completion, DLQ/redrive, controlled URL ingestion | PostgreSQL/S3/SQS integration tests; auth/SSRF tests; worker crash, redelivery, publish-failure and ownership tests | M1; M2 auth UI |
| M5 â€” AWS staging | Terraform VPC/IAM/KMS/S3/RDS/SQS/ECR/Cognito/ALB/ECS/CloudFront/WAF/secrets, OIDC deployment, immutable images, backups and retention | Reviewed plan, staging smoke test, migration/rollback and restore drill, budget alerts | M2â€“M4; account/region/domain/budget |
| M6 â€” Operations and MLOps | Prometheus/Grafana, CloudWatch, tracing, SLOs, model registry approval, drift baselines, retraining/evaluation pipeline; EKS only if justified | Actionable failure alerts, model rollback demo, promotion gate rejects regressions, drift validation | M3â€“M5 |
| M7 â€” Release validation | Security review, load tests, capacity tuning, documentation, demo and final acceptance audit | All section 34 acceptance criteria demonstrated with real authorized model and deployed services | M1â€“M6 |

M3 dataset research can proceed alongside M2 implementation. M4 can use a deterministic test
detector while training proceeds, but public inspection requires the M3 model gate.

## M1 implementation checklist

- [x] Package structure and project-local environment.
- [x] Typed settings and response contracts with explicit demo/result semantics.
- [x] Alembic initial migration; persistent inspection and audit-event records.
- [x] JPEG/PNG decoding, upload byte/pixel/dimension bounds, EXIF normalization and metadata removal.
- [x] Filesystem object store with atomic writes and path containment.
- [x] Job claims with expiring leases and fencing tokens, bounded retries and terminal failure.
- [x] Separate worker, demo detector interface, provisional decision policy.
- [x] Upload/status/results/history/image/report endpoints; request IDs and health/metrics.
- [x] Local launch instructions, Docker Compose and CI checks.
- [x] Local verification recorded in `docs/verification.md`: 27 tests, lint, formatting, strict typing, migrations, dependencies and separate-process smoke passed; Compose configuration valid. Container/PostgreSQL execution remains pending Docker availability.

M1's database stores the versioned report as JSON alongside searchable job metadata; normalized
detections/models/users/api_usage tables are introduced with the corresponding real-model/auth
features. Audit events are already separate and transactional with state changes.

## Data/model gate

The user selected surface-defect inspection for V1 on 2026-09-07/08; assembly inspection
moves to V2. PCB-Defect is acquired with six verified classes. PCB-IND remains the intended
industrial source, but its paper and repository disagree on class IDs/names and its Zenodo
archive could not be accessed here. MIXED is acquired but excluded pending label-map and
lineage review. See [Dataset V1 specification](dataset-v1-spec.md) for measured findings,
the nine-class roadmap, the six-class baseline and the frozen-split release gates.

Before training: approve intended usage, retain license evidence and source revision, inspect
annotations, group splits by physical board/template/acquisition, check near duplicates across
splits, reserve a held-out test set, and document absent classes. No accuracy promise precedes
measurement. The demo decision policy is not a calibrated manufacturing rule.

## Production gates and remaining decisions

1. Dataset rights and taxonomy coverage; model/framework distribution terms before selecting weights.
2. Real-image resolution, board types, expected traffic and retention requirements.
3. AWS account, region, domain and monthly budget before any infrastructure apply.
4. Cognito and tenant isolation before public access; fail closed on invalid issuer/audience/token use.
5. URL ingestion: DNS/IP validation at connection time, redirects revalidated, metadata/private
   ranges blocked for IPv4/IPv6, bounded download/decode, restrictive egress and timeout tests.
6. SQL/S3/SQS are not a shared transaction: implement an outbox and orphan reconciliation.
7. Worker visibility renewal and fencing must protect slow model inference and stale workers.
8. Product results describe visible findings only, never electrical/functional certification.

## M2 â€” Local product: implemented

- [x] React/TypeScript/Vite application using generated FastAPI OpenAPI types.
- [x] File selection and drop, image preview, validation errors and submission state.
- [x] Automatic polling with cancellation, terminal-state handling and retry/backoff.
- [x] Image zoom, coordinate-correct region overlays and keyboard selection.
- [x] Demo-aware report panel, JSON download and image/model metadata.
- [x] Paginated history, reopen/deep links and browser navigation.
- [x] Responsive desktop/mobile layout and automated accessibility checks.
- [x] Local combined launcher, frontend Docker image/Compose service and CI.
- [x] M2 verification recorded in `docs/verification.md`: build/lint, 3 component tests and desktop/mobile workflow/accessibility/overlay checks passed.

## M3 â€” Preparation started

- [x] Strict dataset manifest/schema with provenance, license evidence/review and purposes.
- [x] Checksum, decode/dimension, annotation, class coverage and group-leakage checks.
- [x] Exact byte/pixel duplicates and coarse visual similarity review findings.
- [x] Deterministic group splitting utility and frozen-test-set guidance.
- [x] CLI/report exit codes and regression tests.
- [x] Surface-defect V1 scope and explicit six-class baseline mapping.
- [x] Two original archives acquired, checksums verified and structural/image audit recorded.
- [x] Conservative family/layout groups and frozen six-class research manifest, with passing integrity validation.
- [ ] Independent annotation-completeness review, clean-board negatives and external camera holdout.
- [ ] PCB-IND release acquired and conflicting label dictionaries reconciled.
- [x] Optional seeded Torchvision CPU/CUDA research trainer, resize/tile views, COCO per-class/group evaluation and local MLflow logging.
- [x] Real-data CPU resize/tile smoke runs and checkpoint reload verification.
- [x] First full-data scratch epoch and recorded validation evidence; zero AP, not promoted.
- [x] Explicit checksum-pinned COCO initialization, normalization-preserving reload and provenance review for local research.
- [x] Five-epoch pretrained experiment, best-epoch reload and auditable evidence export; quality remains inadequate.
- [x] Fixed-checkpoint validation comparison of 320/640 resolution and 1536-pixel tiles; changed transforms reduced AP50:95.
- [x] One-epoch 640-pixel training pilot and exact checkpoint reload; AP50 8.2584%, AP50:95 1.7542%, still research-only.
- [x] Five-epoch 640-pixel run, exact pilot/reload parity and fixed-threshold error diagnostics; AP50 38.1599%, AP50:95 13.5267%, still research-only.
- [x] Local validation review with original-coordinate overlays, exported notes and six-case mouse-bite inspection.
- [x] Corrected empty-tile training and one-epoch tile pilot, exact reload and error comparison; AP50 63.1950%, AP50:95 24.7772%, still research-only.
- [x] Selectable false-positive review, overlap contexts, separate prediction notes and seven high-score visual cases.
- [x] Exact optimizer-step budgeting, endpoint-only selection, strict schedule evidence checks and real CPU partial-pass smoke/reload.
- [x] Execute and compare the prespecified 1,053-step whole-board control; exact reload, AP50:95 15.5973%, tile advantage 9.1799 points.
- [x] Bound review-note import, immutable adjudication history and separate validation-label correction candidates.
- [ ] Meaningful trained baseline/YOLO or RT-DETR comparison, DVC data versioning and calibrated quality classifier.
- [ ] Calibrated thresholds and approved real detector artifact.

Assembly inspection is deferred to V2. The six-class research manifest is frozen and passes
integrity gates; no calibrated production model has been produced. The original architecture
remains historical context where its taxonomy differs from the accepted V1 specification.

## M4 â€” Identity and browser integration implemented locally

- [x] Optional Cognito access-token signature and issuer/client/expiry validation.
- [x] Signing-key cache/rotation, bounded retrieval and fail-closed authentication errors.
- [x] Verified owner filtering on uploads and all inspection read endpoints.
- [x] Optional scope/resource-audience enforcement and identity endpoint.
- [x] Synthetic signed-token and cross-user regression coverage.
- [x] Managed browser login with PKCE/session renewal/logout, protected images/downloads and mock browser acceptance.
- [ ] Live Cognito signup/login/renewal/logout and two-user ownership acceptance.
- [x] Opt-in S3 adapter, transactional outbox, SQS delivery, visibility renewal and fenced completion.
- [x] Native DLQ policy checks, explicit audited failed-job retry and read-only orphan candidate audit.
- [ ] Live S3/SQS/PostgreSQL acceptance, IAM/KMS/policy checks and operational recovery/alerts.
- [ ] Safe URL ingestion with SSRF controls.

## Next implementation slice

PCB-Defect research release 1.0.0 is frozen: 165 train / 32 validation / 33 test images;
13 conservative groups, all six classes in every split, no validator findings. See
[data release notes](../data/releases/pcb-defect-v1/README.md). The offline [baseline pipeline](../ml/BASELINE.md) now provides reproducible training/evaluation.
The [corrected tile pilot](../ml/evidence/coco-tiles1536-rpn0-epoch1.md) completed 1,053 steps
with exact checkpoint reload: AP50 63.1950%, AP50:95 24.7772%, AR100 40.0831%. At diagnostic
score 0.25, misses fell from 131 to 46 but false positives rose from 162 to 548. No real model
is approved. Local review now has a generated package for this checkpoint as well as the control.
The [false-positive review](../ml/evidence/coco-tiles1536-rpn0-fp-review.md) is now implemented,
with seven selected regions inspected. At score 0.25, duplicates account for 41/548 false
positives; 492 have partial or no overlap. Annotation completeness still needs expert review.
Explicit optimizer-step budgeting and the [1,053-step whole-board control](../ml/evidence/coco-resize640-rpn0-steps1053.md)
are complete, with exact reload and one endpoint selection opportunity. Control AP50 is
45.8523%, AP50:95 15.5973%, AR100 26.6494%; the tile pilot retains a 9.1799-point AP50:95 lead.
At score 0.25, tiles detect 49 more labels with 280 more false positives. This comparison
matches updates and RPN filtering, but compute, board/label exposure and clipping still differ.
The prescribed experiment sequence stops here; no further expensive experiment is launched.
Keep the existing frozen release intact until expert label review establishes any correction.
An approved surface-model API contract follows model qualification. PCB-IND acquisition and label-map reconciliation remain separate follow-up work.
Annotation-completeness review, negative examples and an external camera holdout are still
required before making broad product claims.

Review import/adjudication/candidate tooling is implemented: see [review workflow](../ml/ADJUDICATION.md).
Next, obtain human review observations, resolve disagreements, and independently validate any
proposed release. No actual label correction or expert approval has been recorded.

Cognito browser integration and mock acceptance are implemented: see [authentication setup](authentication.md).
Live Cognito acceptance awaits configured infrastructure/accounts. The S3/outbox/SQS service
slice is implemented with local failure-oriented tests; see [cloud integration guide](cloud-integrations.md).
Next validate the deployment roles, queue/DLQ policies, migrations and crash/recovery behavior
against an authorized integration environment. PostgreSQL cloud/worker tests were added to CI;
the local Docker engine is stopped and fresh remote CI has not run. Complete monitoring,
retention/reconciliation, load and staging acceptance before enabling public deployment.
No cloud deployment is needed for annotation review.
