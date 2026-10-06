---
name: m2o-backend
description: Implement, debug or review M2O FastAPI services, jobs and provider adapters while preserving workspace authority, revision integrity and exact delivery approval. Use for M2O backend changes, not unrelated APIs or database-only migrations.
---

# M2O backend integrity

Locate the actual repository root and inspect revision/status. Read AGENTS.md and docs/M2O_IMPLEMENTATION_CONTRACT.md. All paths here are repository-relative even when installed globally. A saved project's checkout may lag another worktree; verify the authoritative source without resetting either.

Trace the affected route → schema → service → transaction/job → adapter → receipt. Start with backend/app/access_policy.py, auth.py and services/common.py for authority; schemas.py for contracts; the relevant delivery service, adapter and worker.py for effects. Use docs/API.md and the relevant provider guide as maps, then verify source.

Preserve these boundaries:
- Derive workspace/user/meeting authority on the server using existing policies. Hidden controls do not authorize access. Visitors and restricted meetings need their existing guards.
- Preserve immutable transcript/review revisions, explicit participant confirmation, expected versions and source evidence. Suggestions are drafts, not confirmed identity or approval.
- Keep review, exact destination/payload delivery approval, provider status and personal progress separate.
- Enqueue jobs atomically with required business state. Revalidate current actor/grant/scope authority before effects. Revocation and stale previews must stop writes.
- Preserve receipts and uncertain-write states. A submission timeout is not permission to resend; verify each provider's idempotency/reconciliation support.
- Keep credentials in the authenticated-encryption boundary. Do not log transcripts, credentials, OAuth codes or sensitive provider responses.

Implement the smallest coherent correction; keep protocols in adapters and business rules in services. Add affected authorization, stale-version, duplicate, revocation and ambiguous-write tests. Use controlled provider transports; live writes require explicit authorization.

From backend, run relevant pytest files with .venv/Scripts/python.exe -m pytest -q. Use --postgres for lock/transaction evidence after reading conftest.py and verifying disposable-capable local/test infrastructure without printing its connection string. Fixtures create and remove random schemas; never target production/private real data. Run configured Ruff and Pyright for changed code.

For new dependencies/capabilities, present official support, scopes, disclosure, maintenance/cost and existing-code alternatives for the user's requested due diligence before adoption. Skill invocation grants no external writes, commits, pushes or deployment. Update affected contracts and dated validation evidence; distinguish mocks/local results from hosted/live behavior.
