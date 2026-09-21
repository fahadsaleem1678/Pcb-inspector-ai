# Portfolio deployment: Vercel + Supabase + AWS

This deployment demonstrates the completed model. No further training is required.
Predictions remain experimental, with `NOT_EVALUATED` board disposition even when boxes
are displayed. AP50 45.97% is a research benchmark, not 45.97% accuracy. Nine source
classes are preserved. The 0.25 display threshold is not a calibrated pass/fail threshold.

## Service layout

- Vercel: React static frontend, root directory `frontend`.
- Supabase: PostgreSQL only. Disable the Supabase Data API for this project before applying
  migrations: the backend owns authorization and these tables have no browser RLS policies.
  Never expose a database password or service-role key to Vercel/browser code.
- AWS EC2: API and one CPU model worker, Caddy HTTPS gateway, using the provided Compose file.
  Start with an x86 Linux instance with at least 4 GiB RAM; verify resource use under load.
- AWS S3: private uploaded images, accessed only through the authenticated API.
- AWS Cognito: existing authorization-code/PKCE login. Supabase Auth is not integrated.
- Database-backed job queue: avoids needing SQS for the initial single-server portfolio.

Browser requests go directly to the HTTPS API via `VITE_API_ORIGIN`, with exact-origin
CORS and bearer tokens. No Vercel Function handles image uploads or model inference.
Cognito authentication and per-owner repository access remain mandatory in portfolio mode.

## Configuration sequence

1. Create a Supabase project. Disable its Data API. Copy the **session pooler** connection
   string from Connect (port 5432 for a long-lived backend with IPv4). Use
   `postgresql+psycopg://` and append `?sslmode=require`; URL-encode the password.
   Use the provider CA and `sslmode=verify-full` where configured. Keep API/worker connection
   counts within the selected Supabase plan. Migrations need schema-creation privileges.
2. Configure a private S3 bucket with Block Public Access. Attach a least-privilege EC2 role
   permitting GetObject/PutObject/DeleteObject in the configured prefix, including health probes.
   Do not provide AWS access keys in the image. For containers, configure IMDSv2 access with
   the appropriate hop limit and test role credential resolution from inside the container.
3. Configure Cognito's public app client with **no client secret**, authorization code grant,
   `openid profile` scopes, callback `https://YOUR-SITE/auth/callback`, logout
   `https://YOUR-SITE/`. See [authentication](authentication.md). Keep signups controlled until
   live acceptance and abuse controls have been verified.
4. Point an API hostname (for example `api.your-domain.com`) to the EC2 server. Allow public
   80/443; do not publish API port 8000 or database ports. Use restricted administration access.
5. Copy `deploy/.env.portfolio.example` to `deploy/.env.portfolio` on the server and replace
   all placeholders. This file is ignored by Git and Docker build context. Set the exact
   production Vercel origin in `PCB_CORS_ORIGINS`; no wildcard preview origins.
6. Transfer the completed checkpoint privately to its expected path:
   `ml/runs/dspcbsd-nineclass-research-3968steps-001/final-research.pt`.
   SHA256: `1427332c3633582f34f1262ebbfaf3c832a411118412bcb2a359df8149c3c87e`.
   The file is intentionally not in Git or container images. The worker rejects any other
   bytes before deserialization and never downloads pretrained weights. Make it readable by
   container UID 10001. Preserve dataset/pretrained-weight attribution and source-use records;
   do not publish source training images or checkpoint downloads without checking their terms.
7. From the repository root on EC2, run:

   ```sh
   docker compose -f deploy/compose.portfolio.yml config --quiet
   docker compose -f deploy/compose.portfolio.yml up --build -d
   docker compose -f deploy/compose.portfolio.yml logs --tail=50 api worker gateway
   ```

   Migrations must complete before API/worker start. The gateway obtains TLS for the configured
   hostname. Container builds and live cloud acceptance remain to be run on the target host.
8. In Vercel import the repository with root `frontend`, Vite preset, and these public build vars:

   ```text
   VITE_API_ORIGIN=https://api.your-domain.com
   VITE_AUTH_MODE=cognito
   VITE_COGNITO_USER_POOL_ID=REGION_POOL
   VITE_COGNITO_CLIENT_ID=PUBLIC_CLIENT_ID
   VITE_COGNITO_DOMAIN=https://YOUR_COGNITO_DOMAIN
   VITE_COGNITO_REDIRECT_URI=https://YOUR-SITE/auth/callback
   VITE_COGNITO_LOGOUT_URI=https://YOUR-SITE/
   VITE_COGNITO_SCOPES=openid profile
   ```

   Redeploy when build variables change. Configure exact callback/logout/CORS origins after
   the Vercel production URL is known. Never put secrets in `VITE_*` variables.

## Acceptance before sharing the URL

Use two different Cognito users: upload a board, wait for worker completion, inspect boxes,
download image/report, sign out and verify the other user cannot access the first user's
inspection by ID. Confirm reports show the pinned model, experimental flag, and no board
acceptance claim. Try invalid/oversized images; verify API/worker restart recovery and S3
private access. Test callback reload, token renewal and logout on the actual public domains.
Add request rate limits/quotas at the chosen ingress before enabling unrestricted signup;
the current code bounds individual uploads but not total per-user storage or queue usage.
Use your own PCB photo initially. Public dataset samples are not bundled pending reuse review.

Set AWS budget alerts before running continuously. Credits are finite; EC2, storage, egress
and public IPv4 usage can consume them. This package has not created any cloud resources.
Stop with `docker compose -f deploy/compose.portfolio.yml down`; this does not delete cloud
storage or stop the EC2 instance. Retain backups and explicitly manage cloud resources.

## Local model preview

Use the existing ML environment, which contains the tested torch/torchvision versions:

```powershell
$env:PCB_DETECTOR="research"
$env:PCB_RESEARCH_CHECKPOINT="ml/runs/dspcbsd-nineclass-research-3968steps-001/final-research.pt"
.venv-ml\Scripts\python.exe scripts/dev.py
```

Default local mode still supports the no-model workflow; no training is launched by this command.

## Provider references checked 2026-09-21

- [Vercel function body limits](https://vercel.com/kb/guide/how-to-bypass-vercel-body-size-limit-serverless-functions)
- [Supabase connection and pooler terminology](https://supabase.com/docs/guides/troubleshooting/supavisor-and-connection-terminology-explained-9pr_ZO)
- [AWS EC2 Free Tier credits](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html)
- [AWS public IPv4 pricing](https://aws.amazon.com/vpc/pricing/)
