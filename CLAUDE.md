@AGENTS.md

# Working in this repository

## Verify before claiming

Run the checks CI runs for the area you changed, and report what passed or failed.

- Backend (from `backend`): `python -m ruff check app scripts tests migrations ../scripts`, `python -m ruff format --check app scripts tests migrations ../scripts`, `python -m scripts.check_types`, `python -m pytest -q`. Add `--postgres` when the change touches SQL, locking, migrations or the worker; SQLite does not prove PostgreSQL behavior.
- Frontend (from `frontend`): `npm run format:check && npm run typecheck && npm test && npm run build`.
- Migrations: `python -m scripts.migrate` then `python -m alembic check` (no model drift). A new migration must also downgrade.
- Browser journeys: `python scripts/run_e2e.py` against the Compose stack.

## Habits that have paid off here

- **Failing test first** for bugs. The NULL-lease bug (`lease_until < now()` never matches NULL) was found by a crash-drill test written to fail.
- **Formatting-only changes:** prove they change no behavior with `npx prettier --debug-check` or by comparing syntax trees, and list the commit in `.git-blame-ignore-revs`.
- **Measure, don't assume.** Extraction quality changes are scored with `python -m scripts.evaluate_extraction`; transcription with `python -m scripts.evaluate_transcription`. Record numbers with their date and machine.
- **Prefer widely used patterns** (idempotency keys, outbox, provider-documented OAuth flows) and say so when something is custom.

## Boundaries

- Never read or print `.env` files, `.runtime/*.json` or connection strings; `.claude/settings.json` denies them.
- The public demo stays synthetic and credential-free (`backend/scripts/serve_demo.py` enforces this).
- Planning history lives in `docs/archive/` and is not current documentation.
