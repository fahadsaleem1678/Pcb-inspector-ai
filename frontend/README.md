# Inspection workspace

React + TypeScript + Vite. Uses the FastAPI-generated contract in `src/generated/api.d.ts`.
The UI is an engineering workspace with native CSS, restrained green accents and local system
fonts; no remote fonts/assets or marketing design-system dependency is required.

## Development

Install Node 24 and pnpm 11, then run `pnpm install --frozen-lockfile` here. From the project
root, run the existing Python environment with `python scripts/dev.py` to start all three
services. Alternatively run API and worker as in the root README and run `pnpm dev` here.
Open [the local workspace](http://127.0.0.1:5173).

The Vite proxy forwards same-origin `/api` calls to port 8000. Set `PCB_API_PROXY` in the
frontend process environment to use a different local backend. No permissive CORS is needed.
Local Compose uses `nginx.conf`; Vercel uses `VITE_API_ORIGIN` for the HTTPS API.
See [deployment](../docs/portfolio-deployment.md) for exact-origin CORS and hosting.

Capabilities: file selection/drop, local preview, bounded uploads, status polling with timeout,
backoff and cancellation, report download, paginated history, deep links, image zoom and
coordinate-correct selectable boxes. Demo mode never renders a successful processing state as
a defect pass. Experimental trained-model findings are supported; reports identify the model and its limits.

## Checks

```sh
pnpm run lint
pnpm run build
pnpm test
pnpm exec playwright install chromium
pnpm run test:e2e
pnpm run test:auth
```

Browser tests start an isolated database/API/worker on port 8011 and frontend on port 5174.
Ports must be free. Tests check desktop and mobile workflows, download, history, reload,
errors, keyboard access and axe accessibility. Generated board imagery is a software fixture,
not a training dataset. Screenshots/traces stay in the gitignored `test-results/` directory.

To update API types after a backend schema change:

```sh
# From project root, using the Python virtual environment:
python scripts/export_openapi.py
# From frontend/:
pnpm run generate:api
```

Commit both `openapi.json` and `src/generated/api.d.ts`. CI regenerates them and rejects drift.
The server OpenAPI response model remains authoritative. Client upload hints use the default
10 MiB cap; server-side configured size/dimension limits are always enforced.

Local mode is single-user development. Opt-in Cognito browser login, renewal/logout and
bearer-protected images/downloads are implemented; see [authentication setup](../docs/authentication.md).
Copy `.env.example` to `.env.local` for public browser settings. Tokens stay in memory, so a
page reload requires another hosted sign-in. Live AWS acceptance remains pending.

The separate auth browser suite uses port 5175 and mock provider/API responses; no AWS
account is contacted. It verifies PKCE and auth failure paths on desktop and mobile, writing
artifacts to `auth-test-results/`. Live cloud deployment acceptance remains pending.
