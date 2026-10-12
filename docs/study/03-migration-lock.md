# 03 — Migration lock and schema guard

## In one sentence

`scripts/migrate.py` takes a PostgreSQL session advisory lock with a bounded try-lock loop, runs Alembic on that same connection so it never needs a second pooled connection, and releases the lock explicitly; separately, the API, `/readyz` and the worker refuse to run unless the database is at exactly the migration head the release was built with.

## The problem it solves

Every deploy runs `python -m scripts.migrate` before starting the app. Several things can go wrong:

- **Two migrators at once.** Two containers starting together (a rolling deploy, a restart during a deploy, Compose plus a manual run) both see the schema at revision N and both try to apply N+1. One fails halfway on "table already exists", or both partially succeed and the version table is inconsistent.
- **Waiting forever.** If one migrator hangs while holding the lock, a naive `pg_advisory_lock` in the next one blocks with no timeout, and the deploy hangs with no clear error.
- **Deadlocking your own pool.** The hosted demo runs with `DB_POOL_SIZE=2` (`render.yaml:29`) and `max_overflow=0` (`backend/app/database.py:33`). If the lock is held on one pooled connection and Alembic asks the pool for another, a pool of 1 can never give it one: the process waits on itself until `pool_timeout`.
- **A pooler that loses the lock.** Through PgBouncer in transaction mode (Neon's `-pooler` hosts), consecutive statements can run on different server connections. The lock you took may not be held by the connection that runs the migration, and the unlock may go to a connection that never had it.
- **Old code on a new schema (and vice versa).** If a release starts against a schema it was not tested with, queries can fail at random places at runtime, or worse, succeed while writing wrong data.

## Core flow

```mermaid
sequenceDiagram
    participant M as migrate.py
    participant Pool as SQLAlchemy pool
    participant PG as PostgreSQL
    participant A as Alembic (env.py)
    participant App as API / worker

    M->>Pool: connect() (one connection: "lock")
    loop until acquired or MIGRATION_LOCK_TIMEOUT (default 30s)
        M->>PG: SELECT pg_try_advisory_lock(674198234)
        M->>PG: COMMIT (don't sit idle in transaction)
        Note over M: sleep 0.1s if not acquired
    end
    M->>A: command.upgrade(config with attributes["connection"]=lock)
    A->>PG: BEGIN; DDL...; UPDATE alembic_version (same connection)
    M->>PG: COMMIT
    M->>PG: (finally) ROLLBACK if still in txn; SELECT pg_advisory_unlock(674198234); COMMIT
    M->>Pool: return connection
    App->>PG: startup check_schema(): current heads == script heads?
    alt mismatch
        App-->>App: 503 schema_incompatible, refuse to start / not ready
    end
```

## Walk through the code

**1. One connection, used as the lock holder.** `backend/scripts/migrate.py:15`

```python
def main():
    check_database()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with get_engine().connect() as lock:
        if lock.dialect.name == "postgresql":
            deadline = time.monotonic() + settings.migration_lock_timeout
```

`check_database` (`backend/app/database.py:61`) retries a `SELECT 1` with backoff so a database that's still starting doesn't fail the deploy. Then the script checks out exactly one connection and calls it `lock`. Everything that follows (locking, migrating, unlocking) happens on it. On SQLite (tests only) there is no locking; advisory locks are PostgreSQL-specific.

**2. Try-lock with a deadline, committing between tries.** `backend/scripts/migrate.py:21`

```python
            while True:
                acquired = lock.execute(text("SELECT pg_try_advisory_lock(674198234)")).scalar_one()
                # Session locks survive commit; don't leave an idle transaction
                # while waiting, or make Alembic borrow a second pool connection.
                lock.commit()
                if acquired:
```

An advisory lock is a lock on an arbitrary number (here `674198234`) that Postgres keeps for you but that means nothing to Postgres itself; all participants just agree to use the same number. `pg_try_advisory_lock` returns `true`/`false` immediately instead of blocking. The loop retries every 0.1 s until `migration_lock_timeout` (default 30 s, range 1-300, `backend/app/settings.py:40`) and then raises a 503 "Migration lock is temporarily unavailable" (`backend/scripts/migrate.py:29`).

This is a **session-level** lock: it belongs to the database connection and survives `COMMIT`. That's why it is safe to commit right after taking it. Committing matters because SQLAlchemy 2.x (the repo pins 2.1.1, `backend/requirements.txt:8`) auto-begins a transaction on `execute`; without the commit the connection would sit "idle in transaction" for the whole wait. Open idle transactions are something operators monitor as a leak (diagnostics counts them, `backend/app/services/diagnostics.py:141`), and they can trip a server-side `idle_in_transaction_session_timeout`, which would kill the session and fail the deploy. (A **transaction-level** lock, `pg_advisory_xact_lock`, would be released by that commit.)

**3. Hand Alembic the lock-holding connection.** `backend/scripts/migrate.py:31`

```python
        try:
            config.attributes["connection"] = lock
            command.upgrade(config, "head")
            lock.commit()
            print("Schema is at the current migration.")
```

`config.attributes` is Alembic's official way to pass objects into `env.py`. On the other side, `backend/migrations/env.py:9`:

```python
def run():
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        context.configure(connection=supplied, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
```

Only if no connection was supplied (e.g. running `alembic` by hand) does `env.py` open its own (`backend/migrations/env.py:16`). Two reasons this matters. First, **pool budget**: with `max_overflow=0`, the pool can't grow, so a second checkout while holding the first could wait on itself. `backend/tests/test_phase8_runtime.py:167` runs `migrate.main()` twice against an engine with `pool_size=1, max_overflow=0, pool_timeout=1` to prove it never needs a second connection. Second, **correctness**: the session that holds the lock is the session doing the DDL, so the lock really covers the migration.

PostgreSQL DDL is transactional, so the migration either fully commits or fully rolls back. `backend/tests/test_phase8_runtime.py:225` makes the upgrade create a table and then raise; afterwards the table does not exist and an independent session can take the lock.

**4. Always release, on success or failure.** `backend/scripts/migrate.py:36`

```python
        finally:
            if lock.dialect.name == "postgresql":
                if lock.in_transaction():
                    lock.rollback()
                lock.execute(text("SELECT pg_advisory_unlock(674198234)"))
                lock.commit()
```

Leaving the `with` block returns the connection to the pool; it does **not** close it. A session lock lives as long as the server session, so without an explicit unlock the lock would stay held by a pooled connection and the next migrator would time out. The rollback first clears a failed transaction, because an aborted transaction rejects every statement including the unlock. Note the timeout path (`raise` at line 29) is before the `try`, so a process that never acquired the lock never tries to unlock it. `backend/tests/test_phase8_runtime.py:248` checks that a timed-out migrator leaves the other owner's lock intact.

**5. Reject transaction poolers before migrating.** `backend/scripts/serve_demo.py:112`

```python
    # Migrations hold a session advisory lock; a transaction pooler can move statements
    # to other server connections and silently drop it. Neon marks pooled hosts "-pooler".
    if "-pooler." in (urlsplit(database).hostname or ""):
        raise ValueError("Use the database's direct connection string, not its pooled one")
```

A transaction-mode pooler (PgBouncer, Neon's pooled endpoint) gives your client a server connection only for the duration of one transaction. Step 2 commits right after locking, so the next statement can land on a different server connection that does not hold the lock. The migration then runs unprotected, and the unlock goes to a connection that never held the lock (it returns `false` and the real lock leaks onto a server connection that other clients will reuse). The hosted launcher refuses the `-pooler` hostname up front; `docs/HOSTED_DEMO_RUNTIME.md:15` records that the operator must use Neon's direct connection string.

**6. The exact-head schema guard.** `backend/app/schema_compatibility.py:15`

```python
@lru_cache(maxsize=1)
def supported_revisions() -> frozenset[str]:
    # No arbitrary environment override. Expand this policy only with tested
    # old/new binary + schema compatibility when a later release requires it.
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    return frozenset(ScriptDirectory.from_config(config).get_heads())
```

The release knows its own migration heads from the migration scripts it ships with. `require_schema` (`backend/app/schema_compatibility.py:23`) reads the database's current heads from `alembic_version` and raises a 503 `schema_incompatible` unless they match exactly (an empty table also fails). It is called on API startup (`backend/app/main.py:92`), on every `/readyz` (`backend/app/main.py:239`) and on worker startup (`backend/app/worker.py:592`). So a process with the wrong schema either won't start or reports not-ready, rather than failing in the middle of a request.

**7. What the guard means for rollback.** `docs/OPERATIONS.md:25`

> After a migration has run, rollback therefore means a forward fix or a verified restore, never redeploying the previous image.

Because the check is "exactly equal", not "at least", the previous image sees an unknown newer head and refuses to start. The policy calls this fail-closed rule acceptable for the disposable synthetic demo, and says that before invited private use the project should move to one-release overlap: migrations only add in one release and remove in a later one, and the supported set includes the previous head once that compatibility is tested. The migrations' downgrades are also blocked to avoid deleting data (`docs/OPERATIONS.md:17`, `docs/OPERATIONS.md:21`).

## What breaks without each piece

| Mechanism | Failure it prevents |
| --- | --- |
| Advisory lock around `upgrade` | Two deploys apply the same migration concurrently; one fails mid-way or the version table is wrong. |
| `pg_try_advisory_lock` + deadline | A stuck migrator makes every later deploy hang with no error. |
| `commit()` after each try | The waiting connection sits idle in transaction for up to the whole timeout, looking like a leak and risking a server-side idle-transaction kill. |
| Alembic reuses the lock connection | With a pool of 1-2 and no overflow, the migrator waits on itself; or the DDL runs on a session that doesn't hold the lock. |
| Transactional DDL | A failed migration leaves a half-applied schema. |
| `rollback()` then explicit `pg_advisory_unlock` in `finally` | The lock stays held on a pooled connection after a failure; the next deploy times out. |
| Reject `-pooler` hosts | Lock and migration run on different server connections; the lock silently stops protecting anything. |
| Exact-head check at startup/readiness/worker | Old code runs against a new schema (or new code against an old one) and fails or corrupts data at runtime. |

## Trade-offs and alternatives

**Session lock vs transaction lock.** `pg_advisory_xact_lock` is released automatically at commit or rollback, so it can't leak, and it works through a transaction pooler as long as everything happens in one transaction. The cost: the lock lasts only one transaction, so a migration that needs several transactions (for example `CREATE INDEX CONCURRENTLY`, which can't run inside a transaction block) would run partly unprotected, and the code couldn't commit while waiting. The session lock covers the whole run but must be released by hand, and requires a direct (non-pooled) connection.

**Advisory lock vs "only one migrator".** You could rely on the platform running migrations exactly once (a release phase, a Kubernetes Job). That works until someone runs it by hand or a deploy is retried. The lock is cheap insurance and also protects local Compose, where a one-shot migration service runs on every `up`.

**Lock timeout of 30 s.** Long enough for normal small migrations, short enough that a stuck lock fails the deploy visibly. If migrations grow (large backfills), you'd raise `MIGRATION_LOCK_TIMEOUT` (allowed up to 300) or, better, move long backfills out of the deploy-blocking migration.

**Exact-head vs compatible range.** Exact-head is simple and safe: the only tested combination is allowed. It makes rollback a forward fix or restore, and it means every deploy has a short window where old instances fail readiness against the new schema. A compatible range (expand/contract migrations, "N and N-1 both supported") allows zero-downtime deploys and image rollback, but each pair must actually be tested, which is why the code says not to expand the set without that testing (`backend/app/schema_compatibility.py:17`).

## Interview questions

**1. What is a PostgreSQL advisory lock, and why use one for migrations instead of a table lock?**

<details><summary>Answer</summary>

It is a lock on an application-chosen number that Postgres tracks but does not attach to any table or row; it only means something because every participant agrees on the number (`674198234`). A migration touches many tables and creates new ones, so there is no single table to lock, and locking real tables would block the app. An advisory lock serializes migrators without touching application data.
</details>

**2. What is the difference between a session-level and a transaction-level advisory lock?**

<details><summary>Answer</summary>

A session-level lock (`pg_advisory_lock`, `pg_try_advisory_lock`) is held until explicitly unlocked or the server session ends, and survives commits. A transaction-level lock (`pg_advisory_xact_lock`) is released automatically at the end of the current transaction and can't be unlocked manually. M2O uses session level so it can commit while waiting and cover the whole Alembic run, which means it must unlock explicitly in `finally`.
</details>

**3. Why does `migrate.py` use `pg_try_advisory_lock` in a loop instead of `pg_advisory_lock`?**

<details><summary>Answer</summary>

`pg_advisory_lock` blocks until the lock is free, with no timeout of its own; if another migrator is stuck, this deploy hangs forever. The try-lock loop polls every 0.1 s and gives up after `migration_lock_timeout` (default 30 s) with a clear 503 error. It also lets the script commit between attempts so the connection isn't idle in transaction while waiting.
</details>

**4. Why must Alembic use the same connection that holds the lock? Give two reasons.**

<details><summary>Answer</summary>

Correctness: the lock should be held by the session doing the work; if Alembic opened its own connection, the DDL would run in a session unrelated to the lock. Resources: the engine has `max_overflow=0` and the hosted pool is 2; holding one connection while asking for another can exhaust the pool and make the process wait on itself until `pool_timeout`. The pool-size-1 test runs `migrate.main()` twice to prove only one connection is needed.
</details>

**5. Why does the hosted launcher reject Neon's `-pooler` hostname?**

<details><summary>Answer</summary>

A transaction-mode pooler assigns a server connection per transaction. `migrate.py` takes a session lock, commits, then migrates and unlocks in later transactions, which can land on different server connections. The lock is then held by a backend that isn't running the migration, so two migrators can run at once; and the unlock goes to a backend that never held it, leaking the real lock onto a pooled server connection. Using the direct connection string guarantees one client connection is one server session.
</details>

**6. A release with migration N+1 is deployed and has a bug. The team wants to redeploy the previous image. What happens, and what should they do instead?**

<details><summary>Answer</summary>

The previous image's `supported_revisions()` is `{N}`, the database reports `{N+1}`, so `check_schema` raises `schema_incompatible`: the API fails at startup, `/readyz` returns 503, and the worker exits. Downgrades are blocked as well. Per `docs/OPERATIONS.md:25`, they should ship a forward fix (a new release on top of N+1), or restore a verified backup taken before the migration and redeploy the old image against it, accepting data loss since the backup. To make image rollback possible in future, adopt expand/contract migrations and support {N, N+1} once that pairing is tested.
</details>

## Explain it back

1. Explain, with a timeline of two containers starting at the same moment, what the advisory lock prevents and what each container prints or raises.
2. Explain to an operator why they must use the direct Neon connection string, without using the word "PgBouncer".
3. Defend or argue against the exact-head schema guard for M2O today, and describe what you would change before real private users depend on it.
