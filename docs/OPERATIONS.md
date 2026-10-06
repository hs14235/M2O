# Local operation, migrations and recovery

## Runtime and startup

Compose project `meeting-to-tasks-e2db` runs PostgreSQL 17, a one-shot migration service, FastAPI, a durable worker, Nginx/React and optional Ollama. Web and database ports bind only to loopback. Generated configuration contains a random database password and is ignored. Do not print `docker compose config` without `--quiet`, since expanded configuration contains secrets.

From the root, `docker compose config --quiet` validates configuration. `docker compose up -d --build web worker` starts the database, waits for its health, applies the migration, and starts application services. API `/healthz` establishes process liveness; `/readyz` verifies the database/schema. Nginx exposes `/healthz` by proxying to the API's `/readyz`, so `http://localhost:8080/healthz` verifies readiness through the web service.

`docker compose ps` shows local state. Application logs are structured JSON; inspect bounded tails with `docker compose logs --tail 100 api worker`. They intentionally omit transcript and exception values. Ollama may log its own runtime information. Do not collect or upload logs externally without checking their contents and obtaining authorization.

To pause containers without removing data, use `docker compose stop`. Named volumes retain the application database and downloaded model. Removing volumes or deleting databases is a separate destructive operation requiring explicit authorization; it is not a normal test cleanup step.

## Migrations

`20261003_02_daily_plan.py` adds personal plan entries, unique user/outcome references, foreign keys, execution-state/value constraints and a user/date index. It preserves existing transcript, outcome and publication tables. The additive migration passed isolated PostgreSQL suite runs and local Compose startup; Alembic reported no model/schema drift afterward. Apply it before serving the new daily-plan page. Its downgrade is blocked to avoid deleting plan data; recovery requires a reviewed forward change or restore.

`backend/migrations/versions/20261001_01_workspace_outcomes.py` defines the initial PostgreSQL schema. `python -m scripts.migrate` retries initial database connectivity, acquires a PostgreSQL advisory lock, and upgrades Alembic to head. The API checks the expected schema rather than creating tables at startup.

The migration does not alter the previous SQLite file. It was executed against the local PostgreSQL database and independently against disposable test schemas. `python -m alembic check` found no model/schema upgrade differences. Downgrade is intentionally blocked because dropping this foundation would delete state; recovery uses a tested backup or a reviewed forward migration.

For later schema changes, create the smallest additive migration, inspect SQL/locking/backfill implications, test representative data and plan compatible rollout order. Do not rewrite an applied migration. Production execution requires the actual target, backup, release and rollback plan to be verified first.

## Legacy SQLite import

The importer opens SQLite in read-only/query-only mode. Default operation validates without importing:

```powershell
cd backend
.\.venv\Scripts\python.exe -m scripts.import_legacy PATH_TO_PRIVATE_SQLITE_COPY --workspace WORKSPACE_UUID --actor OWNER_UUID
```

The capitalized arguments are values from the actual local source and authorized destination, not real production identifiers. Validation rejects invalid confidence and citations instead of guessing source positions. To import the validated source, explicitly add `--apply`. The actor must own the destination. Conflicting meeting slugs stop the transaction; existing meetings are never overwritten. Import is atomic and preserves original human wording, old evidence text and publication metadata. It never replays GitHub writes. An imported outcome with a matching recorded successful publication cannot be previewed for the same destination; inspect its audit record first.

Tests prove the original SQLite file's byte hash is unchanged and index-eight evidence is preserved. No user-provided legacy database was imported during this revamp.

## Backups and restore verification

From the root, `python scripts/backup_local.py` runs a PostgreSQL custom-format dump into ignored `.runtime/backups`. Adding `--verify-restore` creates a fresh random `mtt_restore_...` database, restores the dump without overwriting an existing database, and checks the migration revision and outcome count. The helper retains the restored database for inspection and never drops an existing target.

A restore drill was executed locally: revision `20261001_01` and 55 synthetic outcomes were restored successfully at that point in testing. Later tests added further synthetic data. This proves one local backup/restore path, not off-host disaster recovery, point-in-time recovery, backup encryption or a recovery-time objective.

## Jobs and ambiguous publication

Jobs expose queued/running/completed/failed state, coverage/results and safe error codes. A claim sets a 90-second lease with a 20-second heartbeat. Expired computation leases are recoverable up to three claims. Before saving, the worker checks that its lease, membership and transcript are still current. To diagnose a stuck job, first inspect worker health, model reachability, job lease and safe error code. Do not manually change a job to queued merely to make a test pass.

Publication persists intent before a network write. If a POST response is unknown, the operation becomes uncertain. A reviewer can use the UI's reconciliation action, which searches GitHub markers using GET only and updates local state when found. If no issue is found, the operation remains uncertain; it is not safe to resend automatically. An operator must inspect the destination and explicitly authorize any further action. A provider rejection preserves the reviewed payload and reports failure rather than removing labels or assignees.

## Deployment conditions

The supplied Compose environment is development-only. It has no public domain, TLS endpoint, external database, cloud account or production secret values. A deployment preparation must provide a separate configuration with `APP_ENVIRONMENT=production`, an actual HTTPS `APP_ORIGIN`, secure cookies, explicit proxy policy, protected database credentials, allowed provider destinations, retention and backup ownership, health/worker monitoring and capacity evidence.

The GitHub Actions workflow verifies backend checks, frontend checks and a synthetic container/browser journey. It has read-only repository permissions and no deployment or publication job. It is configured locally and has not executed on GitHub. Container images use version tags, not a managed digest/update policy; establish image scanning and controlled updates before a public release.

No commits, pushes, pull requests, issues, deployments or infrastructure mutations were performed outside the isolated local runtime. Preparing these files does not authorize an external action.
