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
