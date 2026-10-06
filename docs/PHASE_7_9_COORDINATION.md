# Phases 7–9: release planning and decision gates

Requested October 5, 2026. This is planning authorization, not approval of new integrations, application changes, purchases or deployments.

## Baseline

Repository: `hs14235/M2O`; reviewed checkpoint: `ddfca8251ff37f31ef3f175ca1d50da42833ed6c`, published to `main`. The authoritative implementation checkout is the coordinator's `e2db` worktree. New project chats start in the primary checkout, which may still have an older revision; they must read the authoritative source without resetting or overwriting their checkout.

The current application is client-rendered React/Vite, FastAPI API and worker, PostgreSQL/Alembic, isolated synthetic visitors and separate invited private use. Hosted demo configuration uses deterministic rules/hash retrieval; optional local Ollama is a separate path. Render deployment and live provider behavior remain unverified. Preserve the dated evidence in VALIDATION.md.

## Planning ownership

| Phase | Chat ID | Planning document in the primary checkout | Responsibility |
| --- | --- | --- | --- |
| 7 | `01a10e97-c88b-7e12-9f27-33b0f6095943` | `docs/PHASE_7_FRONTEND_DX_PLAN.md` | Frontend maintainability, recovery states, accessibility, motion/performance, browser CI and developer onboarding |
| 8 | `01a10e9a-5a8f-7222-a39f-350aff024e15` | `docs/PHASE_8_BACKEND_DEPLOYMENT_PLAN.md` | Proxy trust, backend security, provider boundaries, CI/CD, containers and deployment/rollback |
| 9 | `01a10e9a-d48d-73f2-9db7-06a0f83a62c3` | `docs/PHASE_9_DATA_OPERATIONS_COST_PLAN.md` | Transactions/concurrency, migrations, retention/restore, observability, monitoring and free/paid cost scenarios |

Coordinator: `01a0f867-346c-7b13-9b97-85f432594979`. Compact planning messages between these chats are authorized. Each chat may write only its own plan; none owns shared implementation files yet. The old phase chats need not resume implementation for this planning pass.

## First release gate

The October 5 audit found that proxy headers are disabled while several admission/authentication quotas use the direct peer IP. Behind an ingress proxy, visitors can share quotas. Phase 8 must establish the actual ingress contract and recommend a narrowly trusted attribution policy or deliberate shared admission policy. Never enable arbitrary forwarding-header trust. Require distinct-client, forged-header, direct-peer, NAT/IPv6 and multi-process tests as appropriate to the chosen design.

## Integration due diligence

Every candidate must state the user problem, existing capability gap, data leaving M2O, retention and redaction, credentials/scopes, current official free limits and paid triggers, maintenance cost, failure behavior, exit strategy, simpler alternative and verification plan. Price claims need dated primary sources. Recommendations are not accepted decisions. No service accounts, credentials, source uploads, dependency installation or cloud resources are authorized by a research recommendation.

The default budget remains Render Free for a bounded synthetic demo. Durable private hosting needs a separate database/backup/cost decision. Local AI must not silently become a cloud AI service. Transcript content and credentials must not enter diagnostic telemetry by default. Audit history and operational diagnostics have different responsibilities.

## Sequence before implementation

1. Inspect current source and report verified capabilities, concrete gaps and uncertainties.
2. Research a bounded set of relevant options and coordinate frontend/API/data contracts.
3. Consolidate required release gates and optional enhancements, with explicit file ownership and dependency order.
4. Give Hamza source links, tradeoffs and a short due-diligence checklist for proposed stitching.
5. Record selected decisions and implementation authorization before changing behavior or dependencies.
6. Implement the smallest coherent increments; verify failure, security, consistency and recovery paths.
7. Recheck exact deployment target, configuration, database ownership and rollback before external actions. Earlier publication does not authorize pushing future planning or implementation commits automatically.

Plans must distinguish local verification from hosted CI, target-platform testing and live provider activation. No invented latency, capacity, compliance or availability claims.

## Phase 7 implementation handoff — October 6

The coordinator verified Hamza's direct Phase 7 message, "Let's initiate phase 7." Phase 7 subsequently created local `codex/m2o-phase7` in the Desktop checkout from exact checkpoint `ddfca82`, preserving its planning documents. Frontend implementation and focused regression evidence belong to that branch; the coordinator's e2db branch retains the root planning/skills work. No frontend file overlap existed at handoff. Do not attribute Phase 7 branch tests to the running e2db installation. Integration, commits, merges and remote publication require their own reviewed action scope and applicable human authorization. First increment targets async/read-recovery/duplicate-click behavior without new versions/vendors or backend contract changes.

## Phase 9 implementation handoff — October 6

The coordinator verified Hamza's direct Phase 9 message, "Let's start phase 9." Phase 9 reports an isolated local `codex/m2o-phase9` branch based on `ddfca82`. Its first scope is local read-only aggregate diagnostics, retention preview/count accuracy and expired-temporary-record handling, privacy-safe logs and affected PostgreSQL regressions/runbooks. Phase 8 retains proxy/schema/migration/worker-health ownership. Both chats were notified that `main.py` request-log template/import changes are a shared hunk requiring coordination. No private runtime cleanup, new telemetry vendor or external publication follows from this handoff. Evidence remains branch-specific until reviewed integration and activation.
