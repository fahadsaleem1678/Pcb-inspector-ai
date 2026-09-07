# Implementation verification

Verified locally on 2026-09-07 with Windows, Python 3.12.14, and the dependency versions
recorded in `requirements.lock`.

| Check | Result |
| --- | --- |
| `python -m pytest -q` | 35 passed |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | 32 files formatted |
| `python -m mypy` | Passed; 12 source files checked in strict mode |
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

Frontend production build and ESLint passed. Three component/hook tests passed. Eight browser
scenarios passed across desktop/mobile, with the final overlay assertion verified separately
after accounting for its two-pixel outline. Axe reported no violations in tested empty/completed
desktop and mobile states. The in-app browser connection failed; local Playwright Chromium
was used instead. Browser tests cover real upload/worker/report flow, download, reload, history,
errors, keyboard access and bounding-box geometry during zoom.

Dataset regression tests cover usage/evidence gates, checksums, annotations, dimensions,
duplicate bytes/pixels, likely visual leakage, class coverage and grouped split determinism.
No external dataset or trained model is included. Test detector outputs are synthetic fixtures.

Node 24.19.0 and the frontend lockfile were used. Frontend container/Compose and CI integration
are authored; Docker runtime and hosted CI verification remain pending.
