# PCB Inspector AI

A portfolio application for AI-assisted PCB surface inspection. Upload an image, follow
background processing, explore defect boxes, and download a JSON report. React provides
the interface; FastAPI, PostgreSQL and a separate Python worker handle inspections.

The optional nine-class research model achieved **45.97% AP50** on 256 unreviewed validation
images. This is a detection benchmark, not an accuracy percentage. Predictions are
experimental and never certify a board as defect-free. Default local mode runs the workflow
without a model. Training is stopped; the unfinished 640-pixel experiment is not used.

## Quick start

Requires Python 3.12+, Node 24 and pnpm 11. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -c requirements.lock -e ".[dev]"
pnpm --dir frontend install --frozen-lockfile
.venv\Scripts\python.exe scripts/dev.py
```

Open [localhost:5173](http://127.0.0.1:5173). The command applies migrations and starts the
API, worker and frontend. Ctrl+C stops them. SQLite and uploaded images persist under
ignored `.runtime/`. On Linux/macOS, use `.venv/bin/python`.

For containers, start Docker's Linux engine and run `docker compose up --build`.
This local stack includes PostgreSQL, migrations, API, worker and frontend; it is not the
public deployment configuration.

## Trained model and hosting

- [Model setup, benchmark and research tools](ml/README.md)
- [Vercel + Supabase + AWS deployment](docs/portfolio-deployment.md)
- [Cognito login configuration](docs/authentication.md)
- [API contract](docs/api.md)
- [S3/SQS configuration and recovery](docs/cloud-integrations.md)

Public portfolio mode requires Cognito user isolation. Model checkpoints and datasets are
not committed. The deployment package is prepared; live cloud acceptance is still pending.

## Checks

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m mypy
.venv\Scripts\python.exe scripts/smoke.py
pnpm --dir frontend lint
pnpm --dir frontend build
pnpm --dir frontend test
pnpm --dir frontend test:e2e
pnpm --dir frontend test:auth
```

Install Chromium once with `pnpm --dir frontend exec playwright install chromium`.
See [frontend development](frontend/README.md) for API type generation and browser tests.
CI checks Windows/Linux services, PostgreSQL, containers and frontend behavior.

## Repository structure

| Directory | Purpose |
| --- | --- |
| `src/pcb_inspector/` | API, authentication, storage, job lifecycle and inference |
| `frontend/` | React application and browser tests |
| `migrations/` | Versioned database schema |
| `deploy/` | AWS portfolio containers and HTTPS gateway |
| `tests/` | Service and integration tests |
| `ml/` | Offline research tools, tests and current model evidence |
| `data/` | Dataset schemas, source records and frozen research manifest |
| `scripts/` | Local development, smoke checks and dataset preparation |
