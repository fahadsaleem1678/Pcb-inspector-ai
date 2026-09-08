# Implementation verification

Verified locally on 2026-09-07 with Windows, Python 3.12.14, and the dependency versions
recorded in `requirements.lock`.

| Check | Result |
| --- | --- |
| `python -m pytest -q` | 56 passed |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | 36 files formatted |
| `python -m mypy` | Passed; 13 source files checked in strict mode |
| `python -m alembic upgrade head` | Passed |
| `python -m alembic check` | No schema differences |
| `python -m pip check` | No broken requirements |
| `python scripts/smoke.py` | Passed: real HTTP API and separate worker, persisted report after API restart |
| `docker compose config --quiet` | Passed |
| Container build/runtime and PostgreSQL execution | Not run locally: Docker Desktop Linux engine is stopped |
| GitHub Actions | Workflow authored; not remotely executed |

Tests cover image byte/pixel/dimension limits, malformed/animated content, metadata removal,
orientation, filesystem containment, upload/status/results/history/download, owner filtering,
migration-backed storage, failure cleanup, events, concurrent claims, lease expiry/fencing,
retry delays, exhausted/crashed jobs and provisional decision thresholds.

The separate-process smoke test used an isolated SQLite database and filesystem, then cleaned
its processes and temporary files. Its last output is saved in the gitignored
`.runtime/last-smoke-result.json`. No trained model or real inference quality was tested.

Two dependency deprecation warnings were emitted by Starlette's test client: legacy HTTPX
integration and an AnyIO BlockingPortal alias. They do not fail these checks; revisit the
test-client dependency upgrade before a future dependency refresh.

The workflow includes a PostgreSQL service smoke test and a container build to run once the
repository is hosted on GitHub. Public deployment, Cognito, S3/SQS, actual model evaluation,
browser acceptance and production load/security tests remain later milestone gates.

## Local product and dataset preparation

Frontend production build and ESLint passed. Three component/hook tests passed. All eight browser scenarios passed in a complete desktop/mobile run after the authentication changes. Axe reported no violations in tested empty/completed
desktop and mobile states. The in-app browser connection failed; local Playwright Chromium
was used instead. Browser tests cover real upload/worker/report flow, download, reload, history,
errors, keyboard access and bounding-box geometry during zoom.

Dataset regression tests cover usage/evidence gates, checksums, annotations, dimensions,
duplicate bytes/pixels, likely visual leakage, class coverage and grouped split determinism.
No external dataset or trained model is included. Test detector outputs are synthetic fixtures.

Node 24.19.0 and the frontend lockfile were used. Frontend container/Compose and CI integration
are authored; Docker runtime and hosted CI verification remain pending.

## Authentication verification

The suite includes 21 additional Cognito checks using ephemeral RSA keys and mocked HTTPS JWKS.
Valid access tokens, key caching/rotation, malformed signatures/headers/claims, expiry, missing
scopes, resource audience, identity-service outage and cross-user isolation are covered.
Local development remains the default. No real Cognito pool or browser login has been exercised.

Windows launcher cleanup now stops owned process trees; the smoke test also verifies the old API no longer accepts connections before restart.


## Dataset acquisition and scope revision — 2026-09-08

- Acquired the original PCB-Defect V1 and MIXED V4 archives; both SHA-256 values match
  Mendeley metadata. URLs, versions and hashes are recorded in data/source-lock.json.
- Re-ran scripts/audit_dataset_archives.py against all 1,971 images and 5,640 annotation rows.
  Reproduced counts, geometry statistics, issues and filename-family leakage candidates.
- PCB-Defect: 230 images / 1,704 boxes; no structural issues or exact duplicates; ten images
  exceed the API's 20 MP limit. Group independence and annotation completeness are not proven.
- MIXED: 1,741 images / 3,936 rows; class-name mapping absent; four filename families span
  splits. No exact duplicates found. Training eligibility remains false for both sources.
- Visually reviewed 12 annotated images from each archive and PCB-IND's manuscript class table.
  These are exploratory reviews, not expert relabeling or statistically representative sampling.
- Checksum mismatch probe rejected an unexpected archive before ZIP processing.
- Python lint and formatting passed across the repository. Specification links, JSON parsing
  and six-class source-to-canonical mapping checks passed; git diff --check passed.
- No runtime/API/frontend behavior changed; service tests were not rerun for this data/docs slice.
- PCB-IND's Zenodo page/API returned HTTP 403. Its repository and manuscript disagree on label
  IDs/names; no PCB-IND archive, weights, training-ready manifest or trained model was produced.
- Compact measured reports are in data/audits/2026-09-08; raw data and visual artifacts remain
  ignored by Git. Dataset V1 specification records the accepted surface scope and remaining gates.


## Frozen PCB-Defect research manifest — 2026-09-08

- Reviewed first/middle/last images from all 22 original-name families and all 30 cross-family
  aHash/pHash candidates. Recorded five different-layout decisions and 25 conservative merges,
  yielding 13 transitive provenance/layout groups. Physical board IDs remain author-unverified.
- Built the immutable six-class release from unchanged source image bytes: 165/32/33 images,
  1,230/232/242 annotations and 9/2/2 groups across train/validation/test.
- All six classes are present in every split. Full 230-image manifest validation at the explicit
  40 MP offline limit passes with no errors/review findings. API/default limits remain 20 MP.
- Rebuilt the release with identical bytes. Manifest SHA-256:
  31bc9c3df24a42dae1b577ea7082a4c0906fd26a5fb4ecf095af2853d43b26b4.
- All 61 Python tests passed, including five new preparation/boundary regressions; Python lint,
  formatting and strict source typing passed. Frontend behavior did not change.
- Release provenance, review decisions and validation are committed under data/releases/pcb-defect-v1.
  Native images, license evidence copy and review thumbnails remain ignored by Git.
- This is research-baseline readiness, not production suitability: holdouts contain only two
  conservative groups each; no clean-board negatives, external camera set, expert annotation
  completeness certification or trained model is included.


## Offline ML baseline workflow — 2026-09-08

- Installed matched torch 2.13.0+cpu / torchvision 0.28.0+cpu in separate .venv-ml, with
  pycocotools 2.0.11, numpy 2.5.3 and mlflow-skinny 3.16.0. Resolved ML pins are recorded.
- CPU resize and 1024-pixel/256-overlap tile smoke training completed with finite losses,
  checkpoint artifacts and local SQLite MLflow tracking. Each used two optimizer steps and
  two validation boards; AP was zero, not evidence of useful inspection accuracy.
- Resize checkpoint reload reproduced predictions and per-class metrics exactly; MLflow
  run status was FINISHED. No held-out test evaluation or pretrained weight download occurred.
- 65 service/data tests passed without ML dependencies. Eleven optional ML contract tests
  passed for geometry, split isolation, source/evidence integrity, COCO edge cases, model
  initialization and smoke/test-set protection. Dependency consistency checks passed.
- Lint, formatting and strict source typing passed before final documentation updates.
- Optional CPU CI is authored; hosted execution has not been verified in this slice.
- Website inference remains explicitly demo-only. All research checkpoints remain ineligible
  for deployment; no clean-board negative or external camera evaluation is claimed.


### Full-data CPU baseline and final failure guard

- One clean-revision c461519 scratch epoch completed: 165 train images/steps, 32 validation
  images, 320.15 seconds including validation. Mean training loss 0.6585; every class had
  zero AP50/AP50:95/AR100. The checkpoint is not a usable detector and remains unpromoted.
- Full checkpoint reload reproduced all validation predictions and per-class metrics exactly;
  the local MLflow run is FINISHED. Held-out test data were not evaluated.
- Compact reproducible evidence is committed in ml/evidence/cpu-resize-epoch1.json. Model
  weights and full local logs remain ignored under ml/runs/cpu-resize-epoch1.
- Added a regression rejecting evaluation when artifact logging fails after a completion
  summary is written; all four model-contract tests passed after that fix (12 ML checks overall,
  including the four lightweight view/preflight checks also in the 65-test service suite).
- Final lint/format checks passed. Hosted CI and GPU execution remain unverified.

### Pretrained initialization support

- Reviewed the official COCO_V1 artifact provenance and separate weight/data terms for local
  research; public distribution approval remains unresolved (ml/PRETRAINED.md).
- Initial download matched publisher prefix; full SHA-256 is pinned for every subsequent
  acquisition and training load. Training/evaluation do not implicitly download weights.
- All 280 transferred tensors matched an official pretrained factory model with six trainable
  backbone stages. The predictor was replaced with six classes plus background.
- Fourteen ML checks passed, including corrupt-weight rejection before deserialization and
  offline frozen-normalization checkpoint reload; repository lint and formatting passed.
- Real-data COCO smoke fine-tuning completed with finite loss. Checkpoint reload reproduced
  all validation predictions and per-class metrics exactly; smoke AP remained zero.
- Five-epoch full-data experiment is documented separately when complete. The web detector
  remains demo-only; no hosted CI, CUDA execution or public-model qualification is claimed.
