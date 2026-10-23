# Hosted synthetic demo runtime

This runtime is prepared locally for the selected Render Free demonstration. It is not deployed, and its existence does not establish release readiness. Private transcripts and provider credentials belong in the separate private installation.

## Components and lifecycle

`Dockerfile.render` builds the React frontend and installs the existing backend requirements. The resulting image runs as user 10001. Its build context excludes private environment files, local databases, credentials, runtime files and dependency directories.

`python -m scripts.serve_demo` validates the synthetic-only configuration, normalizes a Render PostgreSQL URL for the installed psycopg driver, and runs the existing advisory-locked forward migration entry point. An unsuccessful migration prevents startup. It then starts one Uvicorn API process and one queue worker. If either child exits, the supervisor stops the other and fails the container. SIGTERM/SIGINT stops both children with a bounded grace period; unfinished queue work is handled by the existing lease/recovery rules. This is process supervision, not proof that a hung worker is healthy.

`app.hosted:create_app` serves the compiled frontend and forwards `/api/*`, `/healthz`, and `/readyz` unchanged to FastAPI. Document deep links receive the application shell; missing assets and unknown API routes remain errors. Static pages carry a same-origin CSP and security headers. Vite assets use immutable caching; HTML and media revalidate. API responses retain their own no-store policy. This remains client-rendered React, not SSR.

## Configuration boundary

`render.yaml` declares one free Docker web service (decided October 11, 2026). Deploys are continuous but gated: `autoDeployTrigger: checksPass` deploys `main` only after its GitHub checks pass. The database is a dedicated free Neon Postgres project, because Render allows one free Postgres per workspace and that one serves Trainline. Neon's free plan is permanent, includes 100 CU-hours a month (running out suspends compute until the next billing period), and suspends compute after 5 idle minutes. The keep-warm workflow keeps the Render service awake, so the demo itself must leave Neon idle (October 18, 2026): Render's health check and keep-warm call `/healthz`, which does not query the database; the worker's idle polling backs off from 1 second to `WORKER_IDLE_POLL_MAX` (1800 seconds here, default 1 elsewhere); and committing a job touches a supervisor-owned wake file (`WORKER_WAKE_FILE`, next to the worker health file) that starts the worker within about a second. `/readyz` still checks the database and schema at startup and for Compose. The cost is that Render no longer notices a database failure after startup; restarting would not fix one. Expired visitors count against the demo's retained budget (`VISITOR_RETAINED_LIMIT`, 500) until purged, so the hosted worker runs the bounded retention cleanup (`WORKER_RETENTION_INTERVAL`, 600 seconds; up to 100 records per class) at startup, after a job and after a wake, never as an extra database wake-up. The operator enters Neon's **direct** connection string as `DATABASE_URL` privately in Render; it never appears in source. The launcher rejects Neon's pooled (`-pooler`) host, because migrations hold a session advisory lock that a transaction pooler can silently drop. The launcher takes the public origin from Render's `RENDER_EXTERNAL_URL` unless `APP_ORIGIN` is set explicitly, for example for a custom domain. Do not reuse a private workspace database.

The startup guard requires `PUBLIC_DEMO_MODE=true`, hash retrieval and an empty `OLLAMA_MODEL`. It rejects provider client credentials, signing secrets, operator tokens and the provider encryption key. Production secure cookies are enforced. A deployment must use the server-enforced isolated visitor flow, never a publicly shared test-account password.

No email delivery, provider publishing, OAuth activation or account creation on a third-party service occurs merely by building this image. No credential appears in `render.yaml`; Render generates the database password and injects the connection string at runtime.

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

Render Free PostgreSQL has a limited lifetime and no managed backups. Durable invited private use requires an explicit database/backup/restore decision. No local container check proves hosted availability, retention or recovery.

## What a visitor sees

Decision (Hamza, October 22, 2026): the demo looks like a working private installation. There is no in-app demo notice; the landing page's "Explore the isolated demo" entry is where a visitor chooses the demo. This replaces the earlier rule that the demo must disclose its temporary nature and synthetic-data boundary inside the app. The boundary itself is unchanged: every transcript is an approved synthetic fixture, custom text and uploads are refused by the API, external delivery is unavailable, and a session expires after `VISITOR_HOURS`.

Each new visitor session gets one workspace per department, each with its people already in the directory and three meetings already listed and indexed by the worker: the department's own meeting, the launch stand-up made from a recording (its audio plays on the Transcript step), and a check-in with no outcomes. Preloading spends none of the visitor's job budget. Sessions started before this change have empty workspaces until they expire.

References: [Render Free](https://render.com/docs/free), [Blueprint fields](https://render.com/docs/blueprint-spec), [web-service ports and health checks](https://render.com/docs/web-services).
