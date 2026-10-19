# M2O study guides

## Purpose

These guides are for explaining M2O's trickiest backend subsystems on a whiteboard, in your own words. Much of M2O was written with AI tools. In an interview, "the AI wrote it" is not an answer. You need to say what each piece does, what breaks without it, and why it was built this way instead of another way.

Each guide is tied to the current source. Every `path:line` reference was checked against `origin/main` when the guide was written. If the code changes, the line numbers may drift; search for the quoted excerpt.

## How to use them

1. **Read.** Go through "In one sentence", "The problem it solves" and the diagram. Then open each `path:line` in "Walk through the code" next to the guide. Read the surrounding function, not just the excerpt.
2. **Quiz.** Answer each interview question out loud or on paper *before* opening its answer. The questions go from easy to hard. If you get one wrong, go back to the code step it depends on.
3. **Explain back.** Answer the three "Explain it back" prompts in your own words, without looking at the guide. These have no answers here on purpose; your written answers are drafts for the project's ADRs (architecture decision records).
4. **Draw it.** Redraw the diagram from memory on a whiteboard, then compare.

## Guides

| # | Guide | Core files |
| --- | --- | --- |
| 01 | [Job claiming and leases](01-job-claiming-and-leases.md) | `backend/app/worker.py`, `backend/app/models.py`, `backend/tests/test_privacy.py` |
| 02 | [Rate-limit identity](02-rate-limit-identity.md) | `backend/app/client_identity.py`, `backend/app/limits.py`, `backend/app/settings.py`, `backend/tests/test_client_identity.py` |
| 03 | [Migration lock and schema guard](03-migration-lock.md) | `backend/scripts/migrate.py`, `backend/migrations/env.py`, `backend/app/schema_compatibility.py`, `docs/OPERATIONS.md` |
| 04 | [Workspace erasure flow](04-erasure-flow.md) | `backend/app/services/privacy.py`, `backend/app/services/retention.py`, `backend/app/services/diagnostics.py`, `docs/USER_LIFECYCLE.md` |
| 05 | [Test database isolation and speed](05-test-database-isolation.md) | `backend/tests/conftest.py`, `backend/app/database.py`, `backend/tests/test_concurrency.py` |

Suggested order: 01 first, because 04 depends on it (erasure waits on the worker's lease recovery). 02 and 03 stand alone.

## Related project docs

- [OPERATIONS.md](../OPERATIONS.md): migrations, rollback policy, jobs and ambiguous publication.
- [USER_LIFECYCLE.md](../USER_LIFECYCLE.md): export, erasure, retention maintenance.
- [HOSTED_DEMO_RUNTIME.md](../HOSTED_DEMO_RUNTIME.md): Render/Neon runtime, including why the pooled Neon host is rejected.
- [SECURITY.md](../SECURITY.md): rate limits and proxy trust.
