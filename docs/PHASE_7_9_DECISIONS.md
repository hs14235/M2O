# Phases 7–9: consolidated review checklist

October 6, 2026. All three planning documents are complete and copied into the coordinator's M2O worktree with matching SHA-256 hashes. They inspect checkpoint `ddfca82`; they do not establish implemented fixes, live provider behavior or a Render deployment.

## Read in this order

1. [Phase 8 deployment and security](PHASE_8_BACKEND_DEPLOYMENT_PLAN.md): public release gates and proxy decision.
2. [Phase 9 data, operations and cost](PHASE_9_DATA_OPERATIONS_COST_PLAN.md): persistence, recovery, monitoring and cost assumptions.
3. [Phase 7 frontend and developer experience](PHASE_7_FRONTEND_DX_PLAN.md): user-facing recovery, acceptance, performance and remaining provider interface.

## Proposed first implementation batch

These are recommendations awaiting accepted decisions and implementation scope.

| Area | Planning finding | Acceptance needed |
| --- | --- | --- |
| Proxy quotas | Direct peer IP can collapse visitors into one budget | Verified target ingress/header contract; spoofed/direct/multi-client cases; deliberate NAT/global-cap behavior |
| Synthetic startup guard | Google client credentials are omitted from the hosted credential denylist; not a confirmed visitor bypass | Reject every configured private provider credential family in public runtime regression tests |
| Schema/readiness | Reporting a migration revision does not establish supported app/schema compatibility or worker health | Older-schema rejection, supported additive rollback range, supervisor/recovery and readiness tests |
| Migration connections | Advisory-lock connection is held while Alembic obtains another | Explicit connection budget; direct/session-compatible endpoint if a pooler is proposed |
| User recovery | Source-level async/read recovery and duplicate-click concerns | Synthetic regressions, meaningful next actions, preserved approval/version boundaries |
| Private-user CI | Lifecycle browser cases need a dedicated fixture; demo-only CI is insufficient | Disposable invitation/recovery/private-access CI lane before private hosted release |
| Erasure after interrupted jobs | Purge can remain pending while a revoked job is still marked running, even after lease expiry | Sleep/crash drill proving safe revoked-job settlement and eventual purge; no blind requeue of uncertain provider effects and no erasure claim from access expiry |

## Accepted Phase 7 direction

Hamza's October 6 message in the Phase 7 chat accepts its direction with this rendering correction: use SSG or ISR for static pages, and SSR only for personalized or dynamic data. The coordinator verified the actual user message before recording it. Use SSG for release-authored public content; justify ISR only where independent public refresh is needed. SSR is eligible for personalized/dynamic routes, not compulsory for every authenticated screen. Define cache isolation and freshness tests before selecting a runtime. Current source remains client-rendered; no renderer migration or new service has been implemented.

## Remaining decisions and due diligence

- Preserve the cinematic department experience and accessible calm/agenda alternatives while following the accepted rendering policy above. Select implementation boundaries/runtime without assuming that acceptance authorizes a dependency or hosting purchase.
- Choose the intended lifespan of a zero-cost synthetic demo and a database expiry/reset/transition policy. Durable private hosting is a separate budget and recovery decision.
- Start with existing safe diagnostics or select one justified error/metrics tool after reviewing actual SDK defaults, outbound fields, retention, billing and source-map/replay behavior. No tool has been adopted.
- Review idle-worker database polling before assuming serverless compute suspension or no-cost operation. User traffic alone does not determine database activity.
- Define backup ownership and restore quarantine. Restoring old data must not revive revoked access, erased content or old delivery jobs without reconciliation.
- Review the dedicated LinkedIn publishing interface and supported product consent as separate feature/activation work; do not imply unrestricted lead messaging or transcript-name lookup.

## Release separation

The temporary public synthetic release tolerates documented sleep and temporary data. Invited private use additionally needs durable storage, privacy/retention ownership, recovery evidence and live provider consent verification. A public demo pass does not satisfy private-use gates.

The long plans contain dated official source links and candidate prices, not a selected monthly bill. Recheck limits and assumptions immediately before a purchase or deployment. No new service, dependency, account, runtime telemetry export, paid upgrade, automatic deployment, commit or push is authorized merely by completing these plans.

Future implementation should use the relevant skills listed in AGENTS.md, allocate shared files before parallel edits, and update validation with actual commands, revision and environment. See [coordination contract](PHASE_7_9_COORDINATION.md).
