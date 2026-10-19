---
name: m2o-postgresql
description: Plan, implement and verify M2O PostgreSQL models, Alembic migrations, transactions, queues and recovery with explicit data-consistency and rollout evidence. Use for M2O data-layer changes or database diagnosis.
---

# M2O PostgreSQL changes

Locate the repository root, inspect revision/status and read AGENTS.md plus docs/M2O_IMPLEMENTATION_CONTRACT.md. All paths are repository-relative. Read affected relationships in backend/app/models.py, database.py, the existing migration chain and service/worker callers. Verify commands in docs/OPERATIONS.md against current scripts.

Start with the invariant: identify source truth, immutable review history, personal execution, provider state and receipts. Keep their lifecycles distinct. Inspect foreign keys, uniqueness/check constraints, indexes, cascade/erasure behavior and version guards. Application prechecks alone do not prevent races.

For jobs/delivery, trace claim/lease, authority, proposal hash, receipt and uncertainty. Explain lock order and simultaneous requests. Provider HTTP and database commits are not one atomic transaction.

Prefer additive compatible migrations. Review operations/SQL for locks, defaults/backfills, nulls, duplicates and mixed-version API/worker compatibility. Define rollout order and recovery before executing. Never rewrite applied migrations or silently drop data. Application rollback is not database rollback; a forward correction or verified restore may be required. Destructive work needs exact-target permission.

PostgreSQL is required outside isolated tests. SQLite passes do not prove migration, row-lock or concurrency behavior. Inspect backend/tests/conftest.py: --postgres creates and removes its own random schema in the configured database. Verify a local/disposable test target privately; never run it on production/private organizational data.

Run affected tests with --postgres and include representative upgrade data/races when required. Check Alembic head/model drift in a disposable migrated target; alembic check alone does not prove migration safety. Do not broaden production privileges for tests.

Budget pool connections across API, workers, migrations and monitoring. Measure representative query counts/plans before adding indexes/caching. EXPLAIN ANALYZE executes its statement; use disposable data and avoid mutating statements without authorization. Label performance targets as proposed until measured.

Before selecting a transaction pooler, verify advisory-lock and migration/backup connection semantics. Use an appropriate direct database endpoint for session-locked migrations and dumps; inspect whether the migration entry point holds one connection while Alembic opens another. Account for that in pool sizing rather than assuming pool size one is sufficient.

A restore can resurrect revoked grants, deleted data and queued delivery jobs. Plan how to reapply the latest off-backup erasure/revocation decisions and quarantine restored jobs/grants until reconciliation. Restored state must not automatically authorize replay of external effects.

For shared migrations verify actual target, authorization, backup ownership, restore evidence and compatibility. Backups contain sensitive data and stay private. Address retention/erasure in exports/backups separately. Report exact upgrade/restore results, concurrency evidence and unverified hosting limits. No automatic database reset, volume deletion, provisioning or history rewrite follows from this skill.
