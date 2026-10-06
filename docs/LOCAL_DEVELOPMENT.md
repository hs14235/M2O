# Local development and verification

The [README](../README.md) contains the shortest Docker path. This guide covers optional AI, native processes and verification. Commands below are PowerShell; `npm.cmd` avoids Windows execution-policy issues with `npm.ps1`.

## Optional local AI

The default empty model setting uses deterministic rules. Enable the existing local Ollama service only when you want private local inference:

```powershell
# Repository root
docker compose --profile ai up -d ollama
docker compose exec -T ollama ollama pull qwen2.5:1.5b
python scripts/configure_local_ai.py
docker compose --profile ai up -d api worker
```

The helper explicitly changes the model and Ollama endpoint keys in private local configuration. The current baseline is Qwen2.5 1.5B; replacing it requires representative synthetic extraction and CPU latency evaluation. A model name or generic benchmark is not M2O quality evidence.

Extraction processes bounded transcript chunks in batches and validates model output against actual source UUIDs. Explicit labels retain literal facts through deterministic rules. The interface reports `ollama`, `rules` or `mixed`, coverage and warnings. Visitors use approved synthetic material and deterministic extraction even if a private installation has a model configured.

Optional semantic embeddings require `backend/requirements-ai.txt` and an available embedding model. The default hash provider needs no model download and stores vectors in PostgreSQL. Do not assume semantic retrieval was verified by the hash-provider tests.

## Native development

Run the root configuration helper once and start the Compose database:

```powershell
docker compose up -d db
```

From `backend`, create the Python 3.13 environment and start the API:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
.venv/Scripts/python.exe -m scripts.migrate
.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

In a second backend terminal:

```powershell
.venv/Scripts/python.exe -m app.worker
```

From `frontend`:

```powershell
npm.cmd ci --ignore-scripts
npm.cmd run dev
```

Vite proxies `/api` to port 8000; its configured browser origin is `http://localhost:5173`. Compose uses port 8080. Generated `backend/.env` points native Python at the loopback PostgreSQL port. Native and container workers share the queue when they use the same database: stop the container worker if you need to debug every job in the native process.

## Checks

From `backend`:

```powershell
.venv/Scripts/python.exe -m ruff check app scripts tests migrations
.venv/Scripts/python.exe -m ruff format --check app scripts tests migrations
.venv/Scripts/python.exe -m pyright app --pythonpath .venv/Scripts/python.exe
.venv/Scripts/python.exe -m pytest -q --postgres
.venv/Scripts/python.exe -m alembic check
.venv/Scripts/python.exe -m scripts.evaluate_retrieval
.venv/Scripts/python.exe -m pip_audit -r constraints.txt --no-deps --disable-pip --progress-spinner off
```

PostgreSQL tests create UUID-named isolated schemas and remove only the schemas they created. Without `--postgres`, most tests use disposable SQLite files; that does not prove PostgreSQL locking behavior. `alembic check` inspects the configured database, so run current migrations before checking it. See [validation](VALIDATION.md) for observed results rather than assuming these commands have passed on your machine.

From `frontend`:

```powershell
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
npm.cmd audit
npx.cmd playwright install chromium
```

For the existing authenticated browser suite, prepare the generated synthetic account with `python -m scripts.bootstrap_demo` from `backend`, then run `python scripts/run_e2e.py` from the repository root. Credentials stay in ignored local files and the child process environment. These tests create synthetic meetings; controlled provider responses are not live provider verification.

The lifecycle browser runtime helper isolates a real API and worker in a disposable PostgreSQL schema and serves the current built frontend:

```powershell
# From backend, after npm.cmd run build in frontend
.venv/Scripts/python.exe -m scripts.lifecycle_browser_runtime --port 19080 --seconds 1200 --fixture-file .runtime/lifecycle-browser.json
```

Its synthetic owner credentials are saved only in the new ignored fixture file. On exit it stops only its child processes, removes only its UUID-named schema and deletes that credential fixture. The shared port-8080 installation and private workspace data are unaffected. Browser evidence must identify which runtime was exercised.

The helper accepts only a loopback PostgreSQL connection and a new `.json` fixture path. A separate synthetic editor account and single-use recovery link are included for browser recovery checks. To request early shutdown without killing unrelated processes, create the same-basename `.stop` file next to the fixture (for this example, `.runtime/lifecycle-browser.stop`); the helper removes its control file during cleanup. Private logs remain under `.runtime`; do not share them without inspection.

To check actual local container inference after enabling AI, run `backend/.venv/Scripts/python.exe scripts/verify_container_ai.py` from the root. The public hosted demo intentionally has no model or provider credentials.

## Same-Wi-Fi phone demo

The normal Compose app binds to localhost. To test on a phone without exposing the private installation, the isolated runtime helper has a synthetic-only LAN mode. Confirm the computer's current Wi-Fi IPv4 address; do not use a VPN or WSL adapter address. Replace `WIFI_IPV4` below with that actual private address.

```powershell
# From backend; frontend must already be built
.venv/Scripts/python.exe -m scripts.lifecycle_browser_runtime --phone-demo --host WIFI_IPV4 --port 19081 --seconds 3600 --fixture-file .runtime/phone-demo.json
```

Open the URL printed by the helper in the phone's browser and select **Explore the isolated demo**. Keep both devices on the same Wi-Fi and the computer awake. The helper binds only the selected private IPv4 address, creates its own temporary PostgreSQL schema, seeds no private accounts, clears provider credentials and disables live publishing/local model inference. It sets the preview's exact origin without editing the desktop configuration. Private acceptance fixtures remain loopback-only.

The preview ends automatically after the requested lifetime and removes only its own schema/fixture. Create `.runtime/phone-demo.stop` to end this example early. Windows firewall or VPN LAN-blocking settings may still prevent a phone connection; a successful computer-side HTTP probe does not prove phone reachability. This helper does not alter firewall rules or deploy a public site. Use only synthetic examples in the preview.

Binding guard tests (`tests/test_phone_preview.py`) passed nine cases; scoped Ruff and Pyright passed. The October 5 live preview was checked from the computer for readiness/schema, homepage, MP4 delivery, visitor-only capabilities and fixture indexing through the worker. Physical phone interaction still requires the user to open the link.

## Optional local MCP

The stdio adapter requires an expiring workspace-scoped `MCP_API_TOKEN`. Bootstrap can write a fresh token to a private file with `--mcp-token-file .runtime/mcp-token.env`. Add it privately to the process environment or ignored backend configuration; never put it in source-controlled Codex settings.

From `backend`, run `python -m app.mcp_server`. MCP calls use the same application authority as the API. Publication is an external write that requires explicit approval. This is local stdio, not an unauthenticated network server.
