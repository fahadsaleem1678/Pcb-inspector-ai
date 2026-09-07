# PCB Inspector AI

An asynchronous platform for AI-assisted visual PCB inspection, being implemented from
[the production architecture](PCB_Inspector_AI_Production_Architecture.md).

**Current milestone: local web application and dataset preparation tools.** React provides
image upload/preview, automatic progress, zoomable images, history and JSON reports. The
detector remains explicitly a demo: processed images return `is_demo: true`,
`overall_result: NOT_EVALUATED`, and no detections. Managed browser login, a trained detector,
PCB/quality classifiers, S3/SQS and cloud deployment remain later milestones.

Read the [implementation plan](docs/implementation-plan.md) for milestones, acceptance gates,
decisions and remaining work. [Dataset notes](data/README.md) record the class/usage issues to
resolve before selecting training data.

## Start the complete application

The workspace already has Python and frontend dependencies installed:

```powershell
.\.venv\Scripts\python.exe scripts/dev.py
```

Open [the inspection workspace](http://127.0.0.1:5173). The command applies migrations and
starts the API, separate demo worker and React dev server. Ctrl+C stops all three. Use
`--api-port` and `--web-port` if the defaults are occupied.

For a fresh checkout, install Python dependencies below, install Node 24 and pnpm 11, then run
`pnpm install --frozen-lockfile` in `frontend/` before running `scripts/dev.py`.
The frontend uses a same-origin API proxy. See [frontend setup](frontend/README.md) for checks
and [dataset preparation](ml/README.md) for manifest validation.

## Run the backend separately

Python 3.12+ is required. From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements.lock -e '.[dev]'
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn pcb_inspector.api:create_app --factory --host 127.0.0.1 --port 8000
```

In a second terminal, from the same directory:

```powershell
.\.venv\Scripts\python.exe -m pcb_inspector.worker
```

Open [interactive API documentation](http://127.0.0.1:8000/docs). Use
`POST /api/v1/inspections/upload`, select a JPEG or PNG, and execute. Copy the returned UUID
into the status, results, image or report endpoint. The API creates a durable queued record;
the separate worker processes it. Stop/restart either process without losing saved jobs.

On macOS/Linux, use `.venv/bin/python` in place of `.\.venv\Scripts\python.exe`, and
`cp .env.example .env`. The example matches the local defaults; skip the copy command if you
already have configuration. SQLite data and sanitized images live under the gitignored
`.runtime/` directory. Run migrations before starting API/worker.

For this workspace, a Python virtual environment has already been created. If Python is not on
PATH, the Codex bundled Python can create it; the existing `.venv` commands work directly.

## Docker Compose

Start Docker Desktop's Linux engine, then:

```sh
docker compose up --build
```

Compose starts PostgreSQL, applies the migration once, and runs independent API, worker and
frontend containers. Open the UI on port 5173; API and worker share a local object volume. The API binds only to `127.0.0.1:8000`; PostgreSQL
has no published port. The included database password is for this isolated development stack.
`docker compose down` retains named volumes. S3/SQS and Cognito replace local adapters in M4.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe scripts/smoke.py
```

The smoke test launches a real HTTP API, submits a generated image, executes a separate worker,
downloads a report, restarts the API and verifies persistence. It cleans its temporary SQLite
database, images and child processes and writes `.runtime/last-smoke-result.json`. Set
`PCB_SMOKE_DATABASE_URL` only for a disposable CI PostgreSQL database; this applies migrations
and inserts one demo inspection, without dropping or truncating existing data. See
[verification](docs/verification.md) for local results.

`requirements.lock` pins the tested dependency set, including development dependencies. Use
it as a constraint with `-c`; the container installs only runtime dependencies selected by the
project. GitHub Actions checks Windows and Linux, runs a separate PostgreSQL smoke job, and
builds both containers, and runs frontend/browser checks with API-type drift detection. No workflow deploys resources yet.

## Code map

| Path | Responsibility |
| --- | --- |
| `src/pcb_inspector/api.py` | HTTP, upload limit, local identity, OpenAPI, health and metrics |
| `src/pcb_inspector/images.py` | Content decoding, size limits and normalization |
| `src/pcb_inspector/repository.py` | Transactional job lifecycle, leases, retries, events and history |
| `src/pcb_inspector/worker.py` | Separate worker process and report persistence |
| `src/pcb_inspector/inference.py` | Detector contract and provisional decision policy |
| `src/pcb_inspector/storage.py` | Object-store contract and atomic local file adapter |
| `migrations/` | Explicit versioned database schema |
| `tests/` | API, image handling and worker lifecycle regression coverage |

See [API contract](docs/api.md) and [architecture decisions](docs/architecture.md).

Optional backend Cognito token verification is implemented; see [authentication configuration](docs/authentication.md). Browser login remains a subsequent step.
