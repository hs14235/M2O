# Hosted synthetic demo runtime

This runtime is prepared locally for the selected Render Free demonstration. It is not deployed, and its existence does not establish release readiness. Private transcripts and provider credentials belong in the separate private installation.

## Components and lifecycle

`Dockerfile.render` builds the React frontend and installs the existing backend requirements. The resulting image runs as user 10001. Its build context excludes private environment files, local databases, credentials, runtime files and dependency directories.

`python -m scripts.serve_demo` validates the synthetic-only configuration, normalizes a Render PostgreSQL URL for the installed psycopg driver, and runs the existing advisory-locked forward migration entry point. An unsuccessful migration prevents startup. It then starts one Uvicorn API process and one queue worker. If either child exits, the supervisor stops the other and fails the container. SIGTERM/SIGINT stops both children with a bounded grace period; unfinished queue work is handled by the existing lease/recovery rules. This is process supervision, not proof that a hung worker is healthy.

`app.hosted:create_app` serves the compiled frontend and forwards `/api/*`, `/healthz`, and `/readyz` unchanged to FastAPI. Document deep links receive the application shell; missing assets and unknown API routes remain errors. Static pages carry a same-origin CSP and security headers. Vite assets use immutable caching; HTML and media revalidate. API responses retain their own no-store policy. This remains client-rendered React, not SSR.

## Configuration boundary

`render.yaml` declares one free Docker web service with automatic deployments disabled. It deliberately does not create a database or fabricate a deployment address. Before any separately authorized deployment, supply the actual `DATABASE_URL` and exact HTTPS `APP_ORIGIN` through Render's private environment settings. The selected database must be dedicated to the synthetic demo; do not reuse a private workspace database.

The startup guard requires `PUBLIC_DEMO_MODE=true`, hash retrieval and an empty `OLLAMA_MODEL`. It rejects provider client credentials, signing secrets, operator tokens and the provider encryption key. Production secure cookies are enforced. A deployment must use the server-enforced isolated visitor flow, never a publicly shared test-account password.

No email delivery, provider publishing, OAuth activation or account creation on a third-party service occurs merely by building this image. The `sync: false` entries require the operator to provide actual values rather than putting credentials in source.

## Local verification

From `backend`:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_hosted_runtime.py
.venv/Scripts/python.exe -m ruff check app/hosted.py scripts/serve_demo.py tests/test_hosted_runtime.py
.venv/Scripts/python.exe -m pyright app/hosted.py --pythonpath .venv/Scripts/python.exe
```

From the repository root, the image build is:

```powershell
docker build -f Dockerfile.render -t m2o-render-demo:local .
```

The image still needs a disposable PostgreSQL startup/shutdown/recovery check after the current schema and frontend increment stabilizes. Native tests alone do not verify Linux signal behavior or Render startup. Render-hosted cold starts, resource usage and database recovery must be measured after an explicitly authorized deployment.

## Hosting limitations

The API and worker sleep together when the free web service sleeps. The worker resumes processing when the service wakes; there is no always-on delivery promise. Slack interactive actions remain unavailable in this credential-free demo. A private live installation needs an awake endpoint and appropriate credentials.

Render Free PostgreSQL has a limited lifetime and no managed backups. The demo must disclose its temporary nature and synthetic-data boundary. Durable invited private use requires an explicit database/backup/restore decision. No local container check proves hosted availability, retention or recovery.

References: [Render Free](https://render.com/docs/free), [Blueprint fields](https://render.com/docs/blueprint-spec), [web-service ports and health checks](https://render.com/docs/web-services).
