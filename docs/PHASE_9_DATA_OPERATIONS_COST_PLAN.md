# Phase 9: data consistency, operations, observability and cost

Planning baseline: October 5, 2026. Completed October 6, 2026, America/New_York, during the overnight planning session. Official service research was retrieved October 5–6; prices and limits must be checked again before an approved purchase or deployment.

**Status: planning only.** No application implementation, schema execution, dependency installation, service provisioning, account changes, credentials, live provider calls, commits, pushes or deployment are authorized by this document. Recommendations below are proposals for Hamza and the coordinator to review.

**Recommendation:** release the bounded synthetic demo first, after its specific deployment gates pass. Keep invited real-data use local until a separately approved durable database, backup, operator and awake runtime exist. Retain PostgreSQL as the source of persistent truth and the existing job queue. Add a small operational measurement contract before choosing a telemetry vendor or changing queue architecture.

## 1. Provenance and decision boundaries

The writable checkout is `C:/Users/hamex/Desktop/meeting-to-tasks/meeting-to-tasks`, on `main` at `8beac1b49f373cbc5c7e56fd7c9b27bb9d9039b8`, initially clean. It predates the reviewed M2O implementation. This document is its only Phase 9 write.

The authoritative inspected source is `C:/Users/hamex/.codex/worktrees/e2db/meeting-to-tasks`, branch `codex/m2o-revamp`, at `ddfca8251ff37f31ef3f175ca1d50da42833ed6c`, initially clean. Coordinator-authored skills and planning files appeared there later and were read without editing. All implementation file references below refer to that checkpoint/worktree, rather than the older writable checkout. The supplied publication checkpoint was not independently audited on GitHub in this planning turn.

| Accepted decision or observed fact | Consequence for this plan |
| --- | --- |
| Render Free selected; public synthetic demo first | No always-on or durable-private promise for Free. The database choice remains open. |
| React/Vite client rendering; FastAPI API plus worker; PostgreSQL/Alembic | Preserve these boundaries. No SSR, broker, auth-provider or cloud-model migration follows from this plan. |
| Public visitors are isolated and use hash retrieval/rules extraction | No real transcripts, model inference or live grants in the public database. Display the actual mode. |
| Private local inference remains optional Ollama | Integrated GPU only; no accelerated model-capacity assumption. A cloud process cannot reach a laptop's localhost. |
| M2O personal progress and provider status have separate owners | A delivered or closed issue must not automatically finish/reopen a personal plan. |
| Exact current review/version/payload approval, confirmed participants, revoked authority and uncertainty are mandatory | Cost and reliability changes must preserve these invariants. |
| No public deployment or live integration verification | Local/synthetic evidence cannot establish provider access, hosted recovery, security certification or capacity. |

The October 5 targeted audit recorded 94 native passes and four PostgreSQL-only skips, with no blocking auth/isolation flaw in inspected paths. Those skips are not row-lock evidence. `docs/VALIDATION.md` also records older broad PostgreSQL and subsequent affected runs; their counts overlap and must not be added together or called a fresh complete checkpoint run. No tests were run for this planning document.

## 2. Evidence map and concrete gaps

| Source | Confirmed behavior | Planning implication |
| --- | --- | --- |
| `AGENTS.md`; `docs/M2O_IMPLEMENTATION_CONTRACT.md` | Review, delivery and personal execution are distinct; all supported provider requirements remain in scope | Keep one canonical contract, with provider-specific capabilities. No implicit synchronization. |
| `backend/app/models.py` | Composite source/workspace foreign keys; review-version uniqueness; plan uniqueness; destination/version records; unique operation keys; visitor/admission/lifecycle state | Preserve database enforcement and inspect service checks separately. Different provider models are not automatically identical. |
| `backend/app/services/review.py` | Meeting/item locks, current transcript check, expected-version conditional update, immutable review snapshot in the transaction | Concurrency tests must demonstrate one accepted update and a meaningful conflict, without overwriting the losing edit. |
| `backend/app/services/issues.py`; provider delivery services | Stored exact proposals, expiry/hash/source/destination checks; operation and job persistence | Approval plus durable queue intent must remain atomic. Provider HTTP cannot join that transaction. |
| `backend/app/worker.py:91`; `:162`; `:566` | `FOR UPDATE SKIP LOCKED`, 90-second lease, 20-second renewal, three-claim limit, authority rereads, idle polling every second | Measure lease failures and idle database activity. Free serverless compute cannot be estimated from user traffic alone. |
| `backend/app/database.py`; `settings.py`; `render.yaml` | Bounded SQLAlchemy pools, pre-ping, no overflow; ordinary default pool 5 and timeout 10 seconds; demo Blueprint pool 2 | API and worker have distinct process pools. Migration/backup connections add to the budget. |
| `backend/scripts/migrate.py`; `backend/migrations/env.py` | Session advisory lock held on one connection; Alembic normally acquires another; forward chain ends at `20261005_11` | Use a direct endpoint for migration, reserve at least the observed two simultaneous slots, and do not set this runner's pool to one. |
| `backend/app/main.py:227` | `/readyz` queries connectivity and returns the stored Alembic revision; it does not compare against the code's supported schema | `docs/OPERATIONS.md` overstates an expected-schema guard. Define/test compatibility readiness before hosted release. |
| `backend/app/observability.py`; `main.py:158` | JSON allowlist omits bodies/exception values, but `path` is `request.url.path`; logs include request/job IDs | Raw paths can contain identifiers or attacker-controlled text. Template paths before exporting; audit every logger/transport. |
| `backend/app/services/privacy.py`; `retention.py` | Freeze before waiting, pending-erasure status/retry, minimal tombstones, known-effect retention, unresolved-effect preservation | Expiry is immediate access revocation, not immediate storage erasure. Restores must not reactivate deleted data or grants. |
| `scripts/backup_local.py` | Local Compose dump; optional new-database restore checks schema revision/outcome count | Useful foundation; not portable hosted backup automation, encryption, off-host recovery or a current full restore drill. |
| `docs/HOSTED_DEMO_RUNTIME.md`; `serve_demo.py`; `render.yaml` | Synthetic-only supervisor, startup migration, coupled API/worker shutdown; no automatic deploy; no database resource declared | Native tests do not verify Linux signals, resource fit or Render behavior. Hung worker health is still a gate. |

Credential-guard parity also needs an explicit regression: the current `serve_demo.demo_environment` denylist names Jira/Slack/GitHub/LinkedIn credentials and the shared encryption key, but omits `GOOGLE_MEET_CLIENT_ID` and `GOOGLE_MEET_CLIENT_SECRET`. This is a configuration-boundary gap to review with Phase 8, not a confirmed visitor/provider-write bypass. Public runtime acceptance must reject every current private provider credential family, including Google, rather than relying on a historical list.

Priority interpretation: these are release-planning findings, not claims that every gap is an exploitable vulnerability. The proxy rate-limit issue is an explicit public deployment gate. Missing hosted recovery, retention ownership and durable storage are private-use gates. Index and external telemetry choices are conditional improvements.

## 3. Data and concurrency contract to freeze before implementation

| State/invariant | Authority/enforcement | Required regression evidence |
| --- | --- | --- |
| Meeting and immutable transcript revisions | M2O; scoped relationships and current revision | Old chunks/reviews remain attributable; replacing transcript cannot reuse old extraction/review/delivery approval. |
| Evidence citations | Database composite item/chunk revision relationships plus service validation | Cross-revision and cross-workspace citations fail. No fallback to the first chunk for malformed source references. |
| Confirmed owner/participant | M2O directory and explicit confirmation | Ambiguous name is never silently mapped to an account or external assignee. |
| Human review | M2O expected version, permitted transitions, immutable `WorkItemRevision` | Simultaneous edits produce one success/one conflict; edited approved content requires proper renewed review. |
| Personal execution | M2O `PlanEntry`, unique user/item and version/reviewed-version checks | Another person's plan cannot be exported/edited; provider closure and delivery do not mutate it. |
| Provider destination/grant | Acting member-owned connection plus workspace binding and current versions/generation | Disconnect, changed scope/destination, reset or role revocation blocks stale jobs after commits/awaits. |
| Delivery proposal | Exact payload/hash, source snapshots, current destination, expiry and affirmative approval | No hidden title/body/labels/assignee substitution or extra evidence disclosure. |
| Durable operation/job | Unique proposal/operation key and same-transaction enqueue | Duplicate approval returns existing intent or meaningful conflict. Crash between flush/commit cannot orphan a committed operation. |
| Worker authority | Lease token plus active account/auth generation/membership/workspace/current source | Lost lease, frozen scope and reset generation cannot commit/send as if still authorized. |
| External effect | Provider-confirmed receipt or preserved uncertainty | Marker or HTTP success alone is insufficient where exact returned content must be compared. Never blindly resend an ambiguous effect. |
| Erasure | M2O owner/version/password boundary, committed freeze, bounded cleanup | Pending state remains reachable. Collaborators' other workspaces/grants survive. Remote content deletion is never implied. |

Current uniqueness prevents several duplicate intents, but it is not an end-to-end exactly-once guarantee. GitHub operations use a distinct model and do not share every state check present in Jira/Slack/LinkedIn. A future consistency increment may add narrowly justified constraints after checking existing values; do not mechanically unify schemas or rename existing fields.

The computation sequence is `claim → computation outside its save transaction → reacquire owned job → reread authority/source → save → settle`. Test crashes before save, after save and during renewal. Recovered computation can run again; its output must remain constrained by current state.

The external delivery sequence is `approved proposal + queued operation/job commit → current-authority checks → durable sending/uncertain intent commit → provider request → exact receipt save`. Test the ambiguous window where the provider accepted a write but M2O lost its response or the receipt commit failed. A restored or reclaimed sending operation must retain uncertainty even when its local job is failed. Do not reset it to queued to obtain a green status.

Preserve actual existing lock order. Document it per path before changing worker/provider/lifecycle locks; identify user/membership/workspace, meeting/item, connection/destination, proposal/operation and job acquisitions and every commit/await. Some provider paths deliberately reacquire locks after intent commits. “Move all network calls outside transactions” is too broad to apply without rebuilding authority/reconciliation evidence. Measure lock duration and pool occupancy first. PostgreSQL lock semantics and deadlock avoidance are described in [PostgreSQL 17 explicit locking](https://www.postgresql.org/docs/17/explicit-locking.html).

## 4. Future synchronization ownership and conflicts

Synchronization is proposed future work, not the next demo blocker. Jira, Slack, GitHub and supported LinkedIn product breadth remains required; this section does not drop providers. Start with a read-only external-status observation when a supported provider, granted read scope and user need justify it.

| Field/state | Owner | Incoming event policy | Explicit outgoing policy |
| --- | --- | --- | --- |
| Transcript/evidence/review approval | M2O | Ignore provider attempts to alter it; retain only permitted audit facts | Export only exact reviewed proposal after approval. |
| Personal plan progress | M2O acting user | External status appears separately with source/freshness | Any supported provider transition requires a new explicit action, expected versions and authority. |
| Provider issue workflow/status | Provider | Observe without completing/reopening M2O plan | Provider-specific supported transitions; no generic status translation guessed from names. |
| Title/body/assignees after publication | Provider resource plus last approved M2O snapshot | Remote edit becomes a conflict, not a silent overwrite | Show current remote baseline and precise diff, then approve a new supported update. |
| Slack action | Authenticated authorized instruction to M2O | Validate signature/replay/team/app/user mapping and current generation; reaction alone is insufficient | No automatic outbound progress notification unless separately accepted and authorized. |
| LinkedIn post state | Member/provider capability | If read permission is unavailable, show unknown and preserve uncertainty | Never assume reconciliation or messaging from OIDC/publishing permission. |

Future event envelope must define provider, opaque event ID, resource reference, supported action, provider version/order information, received time, authorized workspace binding and safe payload schema. Process authenticated events with a unique inbox key in the same transaction as local observation/version updates. Duplicates are acknowledged without another effect. Out-of-order events cannot regress an observation. If the provider lacks a monotonic version, re-read current provider state under authorized read access; do not invent ordering from arrival time.

Store observed-at and provider-updated-at separately. Stale/revoked access displays stale/unknown, not success. Conflicting local and external edits require a reviewable choice. Reconciliation uses provider reads only where supported and granted. Absence in a bounded search is not proof of no write. Tombstones and erasure suppression stop delayed events from recreating erased content. No event broker, webhook connector or automation platform supplies these rules automatically.

Acceptance before synchronization: duplicate/out-of-order events, concurrent human edits, wrong workspace/team, revoked mapping/grant, unsupported transition, source version change, callback after erasure and timeout after remote success. Do not implement implicit bidirectional completion.

## 5. Migrations, deployment compatibility and recovery

Keep applied migrations unchanged. The existing sequence includes additive lifecycle/import tables and check-constraint expansions; several downgrades deliberately refuse destructive reversal. “Mostly additive” does not establish lock-free or rolling-release compatibility.

Recommended future sequence:

1. Specify the invariant, smallest model change and all current callers. Identify existing rows, null/default/backfill needs, unique-key duplicates, cascade behavior and operator privilege requirements.
2. Review generated operations/SQL in a disposable PostgreSQL target. Record lock types/duration, table rewrite risk, representative row counts and interrupted backfill handling. Any destructive change remains separately gated.
3. Prefer expand → compatible application/worker change → bounded backfill → constraint validation → later contract cleanup. Only split migrations when the measured locking/data need justifies it.
4. Test fresh install and upgrades from supported revisions with representative synthetic historical rows, jobs, encrypted dummy grants, proposals, pending erasure and tombstones. `alembic check` detects drift; it does not prove upgrade safety.
5. Define supported schema range per release and test old API/worker with new schema, and new code with old schema. `/readyz` should reject an unsupported schema safely; strict equality is not automatically suitable for a compatible rolling release.
6. Apply once under a verified direct connection/advisory lock, before incompatible API/worker traffic. Preserve automatic-deploy-off until explicitly authorized CI/deployment review.
7. Record application artifact/revision, schema revision, backup time and recovery owner. Release only after affected/full PostgreSQL and target-runtime gates pass.

Pool compatibility is a specific database-choice gate: the current runner holds `pg_advisory_lock` on one connection while Alembic obtains another. A one-slot pool can exhaust locally; a transaction pooler does not preserve session-level advisory-lock ownership across transactions. Use a direct connection for migrations and dumps, with separately reviewed runtime pooling. Neon documents these distinctions in its [official connection-pooling documentation source](https://github.com/neondatabase/website/blob/main/content/docs/connect/connection-pooling.md). This does not justify installing PgBouncer now.

Application rollback and database rollback are different. Reverting the image is valid only if its code is compatible with the already-applied schema. Prefer a reviewed forward fix. Restore is a separate incident action into a verified fresh target; it can lose new writes and undo revocation/erasure unless the recovery procedure below is followed. No reset, fake migration, applied-migration rewrite or destructive downgrade is part of normal release handling.

## 6. Measurements before indexes, pooling or a new queue

Start on disposable PostgreSQL using the actual version/driver, fixture sizes and configured runtime. Record build/schema/DB version, process count, pool size, workload shape, data volume and cold/warm state alongside results. The local PostgreSQL 17 Compose setup is evidence for that setup, not the newest managed service default.

| Question | Existing evidence/path | Measurement and possible response |
| --- | --- | --- |
| Are reads doing N+1 queries? | Review list batches evidence; dated validation proves two queries for that path | Recheck affected list/calendar/history/export query counts. Fix a demonstrated extra query before caching. |
| Is job claiming scanning many rows? | `ix_job_claim(state, available_at, created_at)`; OR for expired running leases | On realistic synthetic queue distributions inspect `EXPLAIN (ANALYZE, BUFFERS)` and rows scanned/lock waits. Consider separate queued/expired-lease partial indexes only if justified. |
| Are recent meeting/plan reads efficient? | `ix_meeting_recent`, `ix_plan_day`, `ix_item_queue` | Measure filters/order/keyset pagination and actual relation sizes. A work-item revision/order index may help a measured path; do not add it by intuition alone. |
| Is retention getting slower? | Visitor expiry and tombstone deadline indexes; bounded batches | Measure per-table candidates, lock waits and purge duration at retained visitor budget. Foreign-key cascade work can dominate selection time. |
| Are connections exhausted? | Per-process pool, no overflow, timeout | Track checked-out connections, checkout wait/timeout and DB active/idle-in-transaction/wait classes. Increase pools only after DB and transaction evidence. |
| Is the DB kept awake when idle? | Worker checks for work every second; pre-ping/readiness add activity | Measure queries/minute and managed CU-hours/active time, including empty queue. Future bounded polling/backoff/wake design must preserve latency/recovery and platform rules. |
| Is a provider await holding locks? | Existing transaction/authority code | Measure slow controlled provider responses plus reset/demotion/erasure overlap. Preserve correctness before shortening transactions. |
| Is storage growing unexpectedly? | Transcript text, chunks, embedding JSON, immutable reviews, job results, previews and audit tables | Measure each table/index/TOAST size, rows/day, export size and backup/WAL growth. Do not estimate only raw transcript bytes. |

`EXPLAIN ANALYZE` executes the statement. Use synthetic disposable data for benchmark queries; never run a mutating statement or expose raw SQL with transcript literals for convenience. Use [PostgreSQL's EXPLAIN guidance](https://www.postgresql.org/docs/17/using-explain.html). `pg_stat_statements` is an optional later diagnostic if supported and explicitly justified; normalized statements can still disclose schema/literals and must not be exported indiscriminately.

Connection budget formula: `sum(API processes × pool) + sum(worker processes × pool) + migration concurrent connections + backup/retention/diagnostic connections + operator reserve ≤ reviewed database allowance`. Pools are maxima, not constantly occupied connections. The current demo has pool 2 in each API/worker process, so its runtime maximum is 4; the migration normally runs before those children and needs its own two connections. Ordinary one-API/one-worker defaults sum to 10. Deployment overlap, heartbeat thread work, extra workers and restore tooling change the budget. A hypothetical two-API/two-worker setup at pool 5 has 20 runtime slots before reserve; that is arithmetic, not a capacity target.

Do not replace the PostgreSQL queue with Redis/Kafka/Celery to look more distributed. The current transactional queue supports review/intent atomicity. A change requires measured contention, latency or availability needs and a new outbox/inbox, deduplication, retry and reconciliation contract. Free ephemeral key-value storage is unsuitable as the sole durable intent store.

## 7. Retention, export and erasure policy

| Data class | Implemented boundary | Proposed operational policy / unresolved decision |
| --- | --- | --- |
| Visitors and demo workspaces | Default two-hour access, 100 active/500 retained visitors, 200 mutations/12 jobs; expiry revokes access | Prove measured resource fit and cleanup lag. Keep disclosures clear; these quotas are not capacity guarantees. |
| Expired visitor storage | Bounded operator purge, protects unexpected shared/private membership and retains pending effects | Define authorized execution schedule, batch budget and owner. Free sleeping runtime cannot promise continuous cleanup. Admission should fail truthfully when retained budget is full. |
| Private transcripts/chunks/evidence/reviews | Retained until owning workspace lifecycle action; archive is reversible | Hamza must approve a retention purpose/window. Do not delete chunks alone while reviews still cite them. Any meeting-level retention feature needs scoped dependency design/tests first. |
| Personal plans/profile | Account-owned export/anonymization; other people's plans excluded | Retain while account active under approved policy. Account erasure must preserve collaborators' shared history correctly. |
| Provider credentials | Backend AES-GCM account-bound ciphertext; disconnect/account/scope rules | Ciphertext is still sensitive. Private backup access and encryption-key recovery are separate from DB storage. Never put key and backup in a public artifact. |
| OAuth/import/link/security records | Expiring records; retention apply cleans selected classes; visitor removal clears more | Inventory every class. Current generic maintenance does not delete expired ordinary `OAuthState`, `IntegrationOAuthState`, invitations or API-token rows in its per-table expiry loop. Plan safe bounded pruning if needed; expiry already blocks access. |
| Proposals, job results and diagnostic data | Explicit workspace erase removes content; no general private-content TTL demonstrated | Measure size and choose explicit retention. A proposal expiry prevents approval; it does not erase approved payload text from storage. |
| Known delivery tombstones | Default minimum 90 days, minimal hashes/resource coordinates | Treat as accountability metadata, with restricted access. Final configurable/legal purpose is an operator decision, not a compliance claim. |
| Sending/uncertain tombstones | Excluded from automatic deletion until explicit resolution/accepted uncertainty | Never shorten retention to hide ambiguity. Store operator decision/time; `accepted_unknown` is not “not sent.” Preserve only minimum facts, no resend body. |
| Product audit | Accountable actions/scope/provenance, separate from diagnostic JSON logs | Define role access/retention and redacted export; do not stream raw audit details to a telemetry vendor. |
| Downloads and backups | Export `no-store`; downloaded files and dumps may contain sensitive data | Local erasure cannot recall downloads, rewrite old backups or delete remote provider content. Explain those boundaries before private use. |

The current maintenance dry run reports visitor/tombstone counts, while apply additionally prunes certain temporary security tables. Improve preview completeness before an operator relies on it for shared-environment removal: report all eligible table classes, protected/pending counts and bounded totals without exposing row contents. Maximum `limit=100` is per selected class/batch, not a universal transaction-row or byte cap. A purge can remove substantial dependent data; measure it.

`purge_workspace` returns pending while any job row is still `running`, even if its lease time has expired. Prove that wake/recovery settles revoked/frozen expired jobs and allows the purge to finish, including after repeated sleep/crash. Do not manually relabel a potentially ambiguous provider job to bypass this guard. An asleep worker is not evidence that storage erasure completed.

Proposed private diagnostic retention: 7 days initially; extend only for a clear operational need. Vendor defaults may retain longer. Public demo data should be purged after expiry and worker settlement under the agreed maintenance cadence, with observed maximum lag recorded. A proposed 24-hour cleanup objective is not implemented or guaranteed. Private content windows remain undecided; do not silently choose a destructive default.

Exports must retain existing owner/browser scope, no-store, version/source evidence and sanitization. The workspace browser limit is two million stored transcript characters; larger administrative backups are sensitive privileged operations, not a normal user download. Pending erase remains status/retry accessible through its known ID. Monitoring may count pending work but must never bypass freeze or publish to settle it.

## 8. Backup, restore and operator lifecycle

RPO means how much recent committed work may be lost; RTO means time to usable recovery. Neither is currently measured for hosted M2O.

| Environment | Proposed target | Evidence required before promising it |
| --- | --- | --- |
| Public synthetic demo | No durable personal-history promise; recreate from fixtures. Proposed recovery within one operator day | Fresh database/bootstrap/visitor smoke and actual hosted cold-start/expiry procedure; no continuously staffed support claim. |
| Small invited private installation | Initial proposed RPO ≤24 hours and RTO ≤4 operator hours | Approved encrypted off-host daily dump plus protected erasure/revocation ledger, current full restore drill, measured restore/integrity time and available operator. These targets require Hamza's acceptance. |
| Future higher-stakes private service | Tighter RPO/RTO only after workload/impact review | Approved PITR window, independent recovery/access/key management, measured drills and staffing. No automatic SLA or HA claim. |

Managed recovery supplements an independently recoverable export. Render paid Hobby provides a three-day PITR window and Pro seven days; recovery creates another instance for validation, and current documented restore points cannot be within ten minutes of now. Free has no managed recovery; operators can make a logical dump before expiry. [Render recovery/backups](https://render.com/docs/postgresql-backups).

Proposed restore drill, using synthetic data first:

1. Verify source/target/environment privately, obtain exact-target action authorization, freeze new mutations and pause all provider side effects. Preserve current operation/erasure/revocation records and incident metadata without secrets.
2. Select an authenticated backup with timestamp, content hash, PostgreSQL major version, schema revision and tested tool version. Restore into a new isolated database; never overwrite the live database as a first step.
3. Keep restored API inaccessible to users and worker/provider sends disabled. A pre-write backup may contain a queued delivery whose external effect happened later. Quarantine queued/running/sending/uncertain operations until current receipts are reconciled; no automatic replay.
4. Reapply the latest erasure freezes/purges and account/grant/session revocations from a separately protected, current ledger. The ledger is a proposed missing recovery artifact, not something the current backup helper already maintains. Reapply all changes since the backup, including scope-binding changes. If records are incomplete, default to blocked authority and manual investigation.
5. Verify migration compatibility, composite/unique constraints, review history/source attribution, exact proposal hashes, plan isolation, pending-erasure accessibility and visitor expiry. Count every critical table class; one outcome count is inadequate.
6. Verify old sessions/tokens/invites cannot return, provider ciphertext is usable only when allowed with independently held key, and callbacks cannot resurrect deleted state. Reconnect consent if safe recovery cannot prove a grant's current authority.
7. Test API, worker lease recovery and browser critical journeys against the isolated target with controlled provider transports. Record actual elapsed times and latest recoverable commit.
8. Obtain separately authorized cutover to the verified target, retain the original for reversible diagnosis under its retention policy, and resume only reviewed authority/jobs. Later deletion of the old target is separately destructive.

Proposed encrypted logical-dump retention: seven daily copies, one pre-migration copy until acceptance and the approved recovery window. This is a proposal, not a configured backup policy; reconcile it with provider PITR, deletion commitments and available protected storage. Keep backup secrets/encryption keys and provider grant keys independently recoverable with least privilege. The current helper does not create roles, export platform secrets or prove key recovery. A chosen off-host service needs its own approval, region/retention/cost review; an existing encrypted removable/off-machine location can be evaluated without adding a cloud vendor.

Operator ownership, to name before private hosting: Hamza or an explicitly designated operator owns billing/expiry/backup, identity verification for manual recovery, grant/key access, maintenance, restore, incident acknowledgment and dependency updates. Do not fabricate another recipient or send any alert now. Hobby's single infrastructure seat differs from M2O's invited application users; adding a second platform operator may require another workspace plan.

## 9. Minimal privacy-safe observability contract

Start with one question per signal: “Is the API available?”, “Is the worker making progress?”, “Is storage/admission close to a limit?”, “Did a delivery become uncertain?”, “Can an operator recover?” Existing liveness, JSON logs and local diagnostics are the baseline; no vendor is essential for defining these answers.

| Signal | Safe dimensions and measurement | Operator action / initial proposed alert |
| --- | --- | --- |
| Request warm latency and 5xx | Fixed route template/method/status class; bounded histograms; include early rejection paths | Diagnose API/DB separately. Alert >5% 5xx over 10 minutes with ≥20 requests; revise after baseline. Low-volume one-off failures remain visible. |
| User-visible cold-start delay | Synthetic planned session timing from first navigation through first usable API response | Distinguish Render sleep from warm regressions and DB resume. No continuous probes to keep Free awake. |
| Job queue age | Counts/oldest age per finite job kind/state, no workspace labels | Awake rules-demo candidate: oldest queued >2 minutes. Free asleep backlog is expected and separately labeled; private inference threshold requires CPU measurements. |
| Lease health and worker progress | Renewal failures, expired-running count, claim/recovery/attempt-limit counters, safe process heartbeat | Awake worker heartbeat stale >90 seconds or repeated lease failure warrants investigation. Heartbeat freshness alone does not establish successful processing. |
| External delivery uncertainty | Aggregate provider/state counts and newly-uncertain event code | Any new uncertainty needs visible operator review, with deduplicated reminder. Never alert-trigger an automatic resend. Public credential-free demo should have zero external publication jobs. |
| Pool pressure | Each finite process role: checked-out/capacity, wait histogram, timeout count | Investigate sustained >80% checked-out or any recurring timeout; preserve migration/operator reserve. Do not blindly enlarge pool. |
| DB activity/storage | Aggregate connections/wait classes, relation size, database total, growth rate and available limit | Warning at 70% storage/quota, action at 85%; stop admission before exhaustion. These thresholds are proposed, not vendor capacity guarantees. |
| Visitor budgets/cleanup | Active/retained counts, admission rejection reason, expired/pending/protected counts and maintenance age | Review at 70/85% selected budget, protected visitor or maintenance missing >24h candidate. Access expiry is immediate even if cleanup sleeps. |
| Backup/recovery | Last completed backup time, verification age, safe outcome/schema/build code | Private proposed backup age >24h requires action; fail closed on an unverifiable restore ledger. No dump bodies in telemetry. |
| Deployment/expiry/billing | Build/schema compatibility, DB expiry days, usage against approved budget | Plan expiry at creation; alerts at agreed lead times; cost review at 70/85% of actual approved ceiling. No dollar ceiling has been chosen. |

Proposed log event schema: timestamp, finite event name, build ID, environment, process role, fixed route template, method, status, duration, safe error code and random request correlation ID. Authorized local operator diagnostics may resolve an opaque job/operation ID to database records; IDs are not metric labels, and external export needs a documented justification. Do not expose workspace/user IDs, names/emails, meeting title/slug, raw URLs/path/query/hash/referrer, transcript/chunks, request/response bodies, headers/cookies/tokens/codes, SQL parameters, provider payload/hash/response, grant ciphertext, stack locals or uploaded attachments. Request and job IDs are pseudonymous operational references, not proof of anonymity.

The existing formatter's arbitrary `record.getMessage()` and raw request path need a stricter event/template contract before external export. Review Uvicorn/proxy/library/model logs as well as the application logger. A safe application formatter cannot scrub an independent access logger or telemetry SDK. Synthetic canary tests must include content in a path, query, OAuth body, headers, exceptions, provider result and nested payload, then inspect actual emitted bytes.

Trace adoption is optional after metrics/logs answer initial questions. If needed, trace request → database query category → durable job correlation → worker stage → provider operation using bounded span attributes. Link a queued job to the originating request rather than inventing one continuous span across sleep. Do not propagate credentials, private IDs or arbitrary baggage to providers. Database spans contain query category, not submitted SQL/values. Proposed successful-trace sample 1%, error traces only if scrubbed, capped bytes/queue and short drop-on-failure buffering; those are initial proposals, not installed settings.

Telemetry failure must not block review, commit, lease renewal or delivery receipt saving. Fail locally, count dropped diagnostics and bound memory; do not persist a private offline event queue without a new retention requirement. Diagnostics do not replace product audit or minimal delivery tombstones, and telemetry deletion cannot claim remote business content was erased.

Phase 7 proposes a native redacted support envelope first and Sentry error-only as an optional separate choice. Prefer one vendor initially; do not add both Sentry and Grafana merely because they have free tiers. No replay, DOM/console breadcrumbs, profiling, AI log assistant or source-map/source upload is part of this recommendation. Browser event scrubbing does not eliminate source IP disclosure at the transport layer. Phase 7 owns the Sentry pricing/data-collection research; Phase 9 owns shared retention and cost assumptions.

## 10. Bounded hosting and integration shortlist

Every external option below is **researchable, not approved**. No accounts/resources, subscriptions, alerts or telemetry uploads were created. Dollar figures are USD list prices excluding tax, FX, domain purchase, private backup storage, exceptional traffic, model compute and operator time. A vendor's certifications or marketing language are not M2O compliance/capacity evidence.

### 10.1 Render: selected platform, database still a decision

Official limits: Free web sleeps after 15 idle minutes and takes about a minute to resume; ephemeral disk, 750 pooled monthly hours and no free dedicated worker. Free PostgreSQL is 1 GB, expires after 30 days, becomes inaccessible at expiry and is deleted after a 14-day upgrade grace period; no managed backup or managed pooling. External DB traffic can also encounter Render Free's service-initiated traffic restrictions. [Render Free](https://render.com/docs/free).

Current Hobby is $0 workspace fee, 5 GB included egress and 500 standard build minutes. Pro is $25/month flat. Additional bandwidth is $0.15/GB and standard pipeline increments $5/1,000 minutes; prices apply separately from service compute. These updated plans replaced older bandwidth/seat assumptions. [Render workspace pricing update](https://render.com/changelog/updated-plans-for-render-workspaces), [pricing](https://render.com/pricing).

Current small paid compute: web or worker `0.5c-512mb` $7/month; larger `1c-2g` web/worker $25/month. PostgreSQL `0.1c-256mb` $6/month; `0.5c-1g` $19/month. Expandable storage $0.30/GB-month. New IDs correspond to legacy Starter/Standard/Basic names; no configuration rename is needed for this planning turn. [Compute plan mapping](https://render.com/docs/compute-plans), [Render's current small-stack cost example](https://render.com/articles/production-rails-hosting-guide), [pricing](https://render.com/pricing).

- **Benefit / existing-code gap:** hosted recruiter access and, separately, durable private availability. Compose/local backup does not supply hosted ingress, billing, recovery or operational ownership.
- **Data/privacy:** database receives stored transcripts/evidence/reviews and grant ciphertext in private use; demo only synthetic records plus account/session metadata. Logs/builds contain application source/configuration; deployment implies an explicitly authorized source artifact transfer. Choose real region, restrict database external access and review backup/log retention. No encryption-at-rest/compliance claim is inferred.
- **Authentication/secrets:** operator platform account with least privilege/MFA; private DB credentials/backend key; no frontend platform token. Provider app secrets remain backend-only. Infrastructure roles and application memberships are separate.
- **Failure/maintenance/exit:** idle/restart/expiry/storage/credit exhaustion can stop the demo. Keep bootstrap/export/cold-start instructions and portable `pg_dump`/restore. Paid services still need measured worker health, controlled dependencies and backup drills. Use manual deploy/rollback with compatible schema.
- **Validation:** full disposable PG regressions, target Linux startup/signals/lease recovery, measured memory/CPU/storage, actual HTTPS cookies/Origin/proxy budgets, expiry transition, dump/restore and billing inspection after separately authorized deployment.
- **Add nothing alternative:** keep the current local Compose product and share approved synthetic screenshots/video evidence. This preserves local inference and avoids a new hosted data boundary.

### 10.2 Neon: strongest free external PostgreSQL candidate to research

The October 2 official update raises Free storage to **1 GB/project**; it lists 100 CU-hours/project/month, 10 branches and a six-hour restore window. Older September documentation still says 0.5 GB, so the discrepancy must be confirmed in the actual account before adoption. [Neon October 2 update](https://neon.com/blog/neon-free-plan-1-gb-per-project). The official documentation source gives 5 GB/project Free egress, five-minute idle suspension, and paid restore-history/transfer rules. [Neon plans source](https://github.com/neondatabase/website/blob/main/content/docs/introduction/plans.md).

Launch compute is $0.106/CU-hour and storage $0.35/GB-month; no monthly minimum is stated in the updated usage-pricing explanation. Restore history is a separate $0.20/GB-month of retained changes; additional branches/egress can bill. Older blog tables contain superseded compute/free allowances. [Compute price change](https://neon.com/blog/major-compute-price-reduction-on-neon), [usage/restore pricing](https://neon.com/blog/new-usage-based-pricing), [current pricing](https://neon.com/pricing).

- **Benefit / gap:** avoids Render's fixed 30-day Free DB expiry for a continuing synthetic demo; existing code does not supply cloud database persistence. It does not create an always-awake worker, durable private recovery program or live AI.
- **Compatibility:** retain SQLAlchemy/psycopg/Alembic and application auth. Direct connection initially is plausible within measured small pool limits. Transaction-pooled endpoint needs prepared-statement/transaction/isolation tests; migration/dump must use direct endpoint. Do not adopt Neon Auth/functions/storage/AI gateway by association.
- **Data/privacy/auth:** same sensitive SQL data as above over an external TLS connection; separate synthetic/private projects and approved region. Password/least-privilege DB roles stay backend-side, with direct migration privilege separately controlled. Branches copy private data; never use production-data branches for public CI or exploratory agents.
- **Cost trap:** current empty-queue polling can keep database compute active. At an explicitly hypothetical fixed 0.25 CU, 100 CU-hours permits 400 active hours; a continuously awake 31-day worker implies 744 × 0.25 = 186 CU-hours. This is an inference from polling and billing units, not a measured Neon bill. Free supervisor sleep may reduce usage, but visitors/health checks/polling can keep it warm. Measure before calling it indefinitely zero-cost.
- **Failure/maintenance/exit:** compute/quota exhaustion, suspend/resume delays, external-network suspension and separate-platform incidents. Bounded retries must preserve no-blind-replay delivery. Keep independent logical exports; migrate to standard PostgreSQL without proprietary auth/data APIs. Paid compute ceiling/notification policies and backup retention require review.
- **Validation / add nothing:** synthetic migrations/constraints/races/leases/restores, cold resume, idle CU consumption and egress, deliberate quota outage. Alternative remains a disclosed 30-day Render demo or local PostgreSQL; no external DB is required for local development.

### 10.3 Supabase: alternative if its broader platform is independently useful

Free database is 500 MB, 5 GB egress and two active projects; inactive projects pause after a week. Pro starts at $25/month, includes 8 GB database disk and daily backups retained seven days; compute/add-ons/extra projects can increase cost. [Supabase pricing](https://supabase.com/pricing). Free requires operator exports for off-site backup; seven-day PITR is approximately $100/month extra and also needs at least Small compute, so it is unsuitable as a casual “included backup” assumption. [Supabase backups](https://supabase.com/docs/guides/platform/backups).

- **Benefit / gap:** managed PostgreSQL with an account's potential future storage/auth needs. M2O already has auth, database queue and provider boundaries, so a broad platform rewrite has no demonstrated benefit now; lower Free DB capacity makes it a secondary candidate.
- **Compatibility:** connect via psycopg to a dedicated application schema/role. Inspect direct IPv4/IPv6/session-pooler availability and region routing for the actual service; transaction pooling has separate compatibility needs. Ensure M2O tables are not accidentally available via a public data API. Do not replace auth generations, invitations or worker checks with a frontend key.
- **Data/auth/privacy:** stored SQL/private backups/grant ciphertext; project account and DB roles, no service/admin key in React. Verify exposed schemas/privileges/TLS and relevant retention/deletion policy. Other Supabase APIs remain unused.
- **Failure/maintenance/exit:** pause/quota/connection/path differences and another control plane. Preserve standard SQL migrations and portable exports; provider-specific schemas/roles require restore review. Larger/subscribed compute or PITR is a separately approved cost.
- **Validation / add nothing:** same PG migration/concurrency/restore suite plus actual network/pooler/exposed-schema test and paused-project recovery. Existing local or Render database avoids the extra platform entirely.

### 10.4 Grafana Cloud: optional aggregate metrics and sanitized logs

Free lists 10,000 active metric series, 50 GB/month logs and 50 GB/month traces, with 14-day retention. Pro starts $19/month plus usage; metric overage starts $6.50/1,000 series, with product-specific ingest/retention charges. These generous limits are not an appropriate default collection target. [Grafana pricing](https://grafana.com/pricing/).

- **Benefit / gap:** cross-restart operational history, aggregate dashboards and alerts. Current JSON logs and health routes lack queue-age/pool/storage trends; vendor alone cannot add those measurements.
- **Data/privacy:** export only allowlisted operational events/aggregates; retain no transcript, user data or audit payload. Choose approved region, retention/deletion and account access. Disable optional AI assistants, profiling/replay and broad automatic instrumentation in this proposal.
- **Auth:** stack-scoped write token, only `metrics:write`, `logs:write`, and optional `traces:write`; no admin permissions in runtime. Separate read/operator account and rotate/revoke ingest tokens. [Grafana access policies](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/security-and-access/authentication-and-permissions/access-policies/).
- **Cost/maintenance/failure/exit:** cardinality, trace volume, network egress and collector memory/CPU dominate accidental cost. Start below 1,000 planned metric series with measured payload budget. Exporter errors drop bounded diagnostics without blocking product operations. Preserve standard structured logs/OTel-compatible signals and portable dashboards; remove exporter/rotate token to exit.
- **Validation / add nothing:** inspect canary network bytes, token scope, unavailable exporter, queue/memory overhead and sample/retention caps on synthetic data. Native logs plus a local safe aggregate diagnostic command remain a valid first release baseline. Decide between this and Phase 7's error-only Sentry option before installing anything.

### 10.5 UptimeRobot: optional external availability, only for awake hosting

Free lists 50 monitors at five-minute intervals. The current Solo 10-monitor option shows $10/month monthly or $9/month billed annually ($108/year), with 60-second checks. Earlier official comparison pages cite different prices; use the current plan quote before subscribing. [UptimeRobot pricing](https://uptimerobot.com/pricing/).

- **Benefit / gap:** detect public endpoint failure independently of the application's process. `/healthz` alone is not a remote observer or worker check.
- **Data/auth/privacy:** send only the approved public health URL/status and operator alert contact; no login, cookies, workspace path, transcript or provider secret. Platform requests reveal service IP/timing; inspect incident retention/privacy terms before acceptance. A bare public health probe needs no application token; a monitor API token is operator-only if later automation is authorized.
- **Failure/cost/maintenance/exit:** false positives during DB/deploy incidents, expected maintenance and cold starts require explicit policy. Notification recipients/channel scope must be approved. Vendor outage does not stop M2O; exit by disabling/removing monitor after approval.
- **Compatibility/validation:** use a minimal truthful readiness response on paid awake hosting; two-stage API readiness plus worker-progress observation is required internally. Test one planned synthetic outage and recovery, notify only authorized recipient, and deduplicate alerts.
- **Free warning / add nothing:** five-minute probes prevent 15-minute Free sleep and can consume hours/DB compute. Do not use this monitor to defeat Free sleep. For the Free demo use platform health/lifecycle plus planned human cold-start checks and disclosed availability; do not promise 24/7 uptime.

## 11. Comparable operating scenarios

Figures are calculated planning examples, not accepted budgets, actual account quotes or capacity evidence. Every scenario requires the release gates for its intended data class. A paid service removes specific Free limitations; it does not establish adequate RAM, throughput or security.

| Scenario | Components / monthly example | Conditions and billing triggers |
| --- | --- | --- |
| A: bounded no-cost public demo | Render Free synthetic API+worker supervisor + Free Render PG: $0 within allowances | Explicit ≤30-day DB term, synthetic history disposable, no live provider/AI, no keep-alive. Expiry/1 GB, 750 hours, egress/build and admission budgets can suspend it. |
| A2: continuing free-db candidate | Same Render Free runtime + Neon Free: $0 only within both plans | Not yet accepted. Idle polling, DB compute/egress, TLS/direct migration, dual cold starts and Render external-traffic policy must be measured; no guarantee of permanent no cost. |
| B: smallest paid co-located private candidate | Paid 512 MB web containing separately designed private API+worker + $6 PG + 1 GB storage: $7 + $6 + $0.30 = **$13.30** | New private supervisor/config is required: current synthetic launcher deliberately rejects private credentials. 512 MB joint fit unproven. Shared failure/redeploy; no hosted Ollama in this figure. Add approved backup storage/traffic. |
| C: recommended private topology to evaluate | Paid 512 MB API/web $7 + paid 512 MB worker $7 + smallest PG $6 + 1 GB storage $0.30 = **$20.30** | Awake endpoint/job lifecycle, measured memory/DB capacity, protected daily off-host export plus PITR/restore, separately approved private credentials. Static frontend serving/same origin needs Phase 7/8 review. No promised inference service. |
| C2: external paid DB comparison | Same $14 API+worker + Neon Launch at hypothetical 0.25 CU awake for 744h and 1 GB: $14 + $19.716 + $0.35 = **$34.07** | Before history ($0.20 × retained-change GB-month), network/branches/backups. Current polling favors awake estimate. If measured activity is lower, bill can be lower; do not assume suspension savings. |
| C3: Supabase alternative | Same $14 API+worker + Supabase Pro one-project baseline $25 = **$39** | Review compute credits/add-ons and actual endpoint. Seven-day daily backups differ from PITR; no automatic $100 PITR purchase. Auth/storage/realtime rewrite excluded. |
| D: measured growth example | 2 GB API $25 + 2 GB worker $25 + 1 GB PG compute $19 + 5 GB storage $1.50 = **$70.50** | No proven user/meeting capacity. Add workspace Pro only if its needed features justify +$25; optional Grafana Pro adds ≥$19 plus usage. Extra instances/staging/backups/egress remain additional. |

Scenario C is the recommended topology for future durable hosted private review; B is a smaller-cost alternative under measured resource fit and accepted coupled recovery. Neither replaces the already usable local private Compose/Ollama route. Public/private databases, credentials and deployment configurations must remain separate. A private hosted rules-only mode must be labeled honestly; a secure local-inference bridge is an additional architecture/authorization project, not a localhost URL change or an unpriced free tunnel.

Cost worksheet before approval: number and size of API/worker instances, database compute/storage/active hours/history, staging/recovery instances, build minutes, egress including media/telemetry/backups, domains, monitoring seats/add-ons, protected backup storage, model compute and recurring operator time. Alert ceilings need an actual approved monthly budget; email notifications alone are not hard caps. Render build spend limits can stop builds without eliminating other resource charges. DB storage growth cannot be assumed reversible. Review dashboard billable units monthly and before changing limits/autoscaling or adding a payment method.

Do not create rotating free accounts/databases or heartbeat traffic to circumvent service limits. When a required Free limit is exhausted, stop admission/service use truthfully or present a reviewed paid/exit transition.

## 12. Temporary Free PostgreSQL expiry transition

At creation, operator records actual creation/expiry date, account/database reference, data class and decision deadline privately. Do not infer those identifiers from this document.

- Proposed day 21: review continuing demo need, storage, visitor retention and migration choice. Inspect/export only minimum synthetic state and test a fresh restore. Reminder scheduling is not installed here.
- Proposed day 25: obtain the concrete paid upgrade, external migration or demo-closure decision. Do not wait for the 30-day inaccessible state to decide how to dump.
- Proposed day 28: execute only the approved transition, verify visitor/database readiness, label history portability/reset policy and record rollback/source retention. Keep new admission off during an incomplete cutover.
- At day 30 expiration: show truthful service unavailability/expiry, preserve known recovery options; the upgrade grace period is not functioning database access or an SLA.
- If closure is chosen: retain approved minimum synthetic evidence/export under a defined policy, then request exact-target destructive resource cleanup separately. Do not silently recreate a database and promise old accounts/history survived.

Moving a private database is a different gated procedure: pause mutations/provider sends, take verified dump plus current erasure/revocation ledger, restore fresh target, test schema/current authority and all critical boundaries, reconcile effects, obtain cutover approval, and retain the source until measured acceptance. Changing an environment variable alone is insufficient.

## 13. Cross-phase ownership and order

The coordinator owns assignment and integration of shared files after Hamza reviews the plans. Ownership below is proposed implementation responsibility; nobody edits these files during planning.

| Work/file family | Proposed owner | Coordination/review |
| --- | --- | --- |
| Frontend receipt/expiry/cold-start/error/support views; optional client errors | Phase 7 | Consume canonical server capability/state/freshness fields; Phase 9 reviews retention/telemetry; Phase 8 reviews API/auth. |
| API/proxy/health/supervisor, worker behavior, delivery/security contracts and CI/deploy runtime | Phase 8 | Phase 9 reviews transaction/lease/pool/quota/restore; coordinator assigns exact shared edits. |
| Database models/migrations, measured indexes, retention/export/recovery ledger and operation consistency | Phase 9 implementation owner, when assigned | One migration owner at a time; provider/lifecycle owners review; coordinator integrates. |
| `models.py`, `settings.py`, `main.py`, `worker.py`, `database.py`, migrations, `compose.yaml`, `render.yaml`, Dockerfiles, CI and common contracts | Coordinator-controlled shared files | Explicit file/section ownership and reviewed handoffs; no concurrent broad edits or automatic formatter. |
| Operational docs/diagnostic schema and pricing assumptions | Phase 9 | Phase 7/8 verify deployment/UI interpretation; dated evidence replaces recommendations only after observation. |

Recommended dependency order:

1. Coordinator consolidates plans, accepted decisions and blockers; Hamza reviews vendor/data/budget questions. Preserve current checkpoint and working files.
2. Phase 8 defines trusted ingress or deliberate global admission, supported-schema checks and worker-progress contract. Phase 9 freezes invariants, quota/pool/retention/restore assumptions. Phase 7 consumes those contracts in recovery/receipt/expiry UX.
3. Implement smallest authorized gates with synthetic fixtures and PostgreSQL evidence: proxy identity, telemetry redaction/templates, worker visibility, complete retention preview, current restore safety. No vendor required yet.
4. Rebuild final changed Linux runtime; run affected/full PostgreSQL, focused browser journeys and redaction/failure recovery. Record exact revision and evidence. No cherry-pick/commit/deploy implied.
5. Select/approve concrete synthetic database/address/account; verify actual billing plan and deploy only after separate exact-target authorization. Measure sleep/wake/queues/resource/expiry and media egress on target.
6. Keep private hosting gated until retention/backup/key/operator/restore decisions and current drills pass; activate each live provider separately through approved scopes and exact synthetic/private test boundaries. Dedicated LinkedIn publishing UX remains a Phase 7 release item.
7. Measure operating pain before optional external metrics/errors/uptime, synchronization or queue replacement. Reassess after real observations rather than assigning a speculative scale milestone.

## 14. Acceptance matrix and release gates

| Stage | Required acceptance | Evidence/owner |
| --- | --- | --- |
| Planning complete | One Phase 9 document, source checkpoint, dated official shortlist, unresolved decisions, ownership/order | This document; no runtime tests or service activation claimed. |
| Data implementation candidate | Fresh/representative migration chain, drift, unique/composite constraints; review/approval/job/lease/reset/erasure races; no blind replay | Real disposable PostgreSQL, synthetic providers; Phase 9 + Phase 8. SQLite-only is insufficient. |
| Diagnostic candidate | Canary content absent in all output channels; bounded metric labels/bytes; exporter-down and pool/worker failure behavior | Actual emitted local/network bytes using controlled transports; Phase 7/8/9. |
| Recovery candidate | Current-head isolated full restore, ledger reapplication, revoked authority denial, quarantined delivery, pending erasure, key recovery | Measured drill, source/schema/build/time and approved target; Phase 9/operator. |
| Public release candidate | Trusted client identity/global quotas, sleep/wake jobs, migration compatibility, process exits/hung worker, actual TLS/Origin/cookies, visitor isolation/budgets/cleanup and no provider credentials | Final local Linux evidence then separately authorized Render target checks; Phase 8 coordinator with Phase 7 UX. |
| Private release candidate | Durable storage, permitted-data/retention policy, encrypted off-host recovery, operator/key ownership, awake endpoint, measured capacity, live consent gates | Private deployment review; no promise before concrete approval and observation. |
| Optional integration accepted | Need/gap, transmitted data, scopes, current prices/limits, caps, exporter failure, ownership and exit verified | Concrete integration review before any account/upload/notification/install. |

Public blockers: proxy/client budget policy; supported-schema and actual target supervisor/job lifecycle; truthful sleep/expiry/mode UX; selected dedicated synthetic DB and expiry ownership; resource/visitor/storage limits measured; safe diagnostic paths and content disclosure audit.

Private blockers: everything relevant above plus permitted real-data handling, durable database/approved retention, backup/restore/ledger/key and operator evidence, awake provider ingress/worker, actual granted products/scopes, and measured inference route if promised. A provider that lacks read reconciliation retains uncertainty visibly.

Optional enhancements: hosted telemetry service, error-only client SDK, uptime on paid services, measured index/queue tuning, read-only external status observation, event synchronization and new brokers/caches. Optional status does not waive a required safety invariant if the feature is later enabled.

## 15. Maintenance and developer experience

Proposed cadence after authorization: daily private backup/retention health review, weekly queue/storage/usage/admission and unresolved receipt review, monthly pricing/billing/dependency update review, restore drill before first private release and after material schema/recovery changes, plus a quarterly routine drill if private hosting continues. Actual staffing/availability must be accepted; no automation or notification was installed.

Keep updates narrow: verify official package/driver/image advisories and supported provider API versions, compare lockfile/digest changes, run focused/full affected checks, test upgrade/rollback compatibility and preserve prior artifacts. Do not batch unrelated dependencies or rely on an old clean advisory scan as current evidence. The worker and privacy invariants are regression gates for each release.

Developer diagnostic flow: reproduce in local Compose/disposable PG with synthetic fixture → record build/schema and safe request ID → locate structured event/safe code → inspect finite aggregate queue/lease/pool/storage state → reproduce boundary with controlled provider/model response → fix smallest cause → rerun meaningful regression → document observed result. No real transcript, full `.env`, expanded Compose configuration, DSN, dump, credential, recovery link or raw provider log belongs in support chat.

Proposed support envelope is user-reviewed before export: build/schema versions, environment type, fixed page/route identifier, safe code/status, operation state and bounded timing. It is opt-in, local first, with content preview and no automatic upload. CLI commands must verify target privately and show aggregate results; dry-run and destructive apply remain distinct. Backend `--postgres` tests create/drop only their own random schema, so point them at a verified disposable database with required privilege, never a private or production organizational database.

The reviewed `skills/m2o-postgresql/SKILL.md` and `skills/m2o-observability-cost/SKILL.md` already require state ownership, disposable PG evidence, safe diagnostics/current vendor research and explicit external authorization. Recommended instruction refinements sent to the coordinator: direct migration/dump endpoint and two-connection runner budget; idle polling/CU-hour checks; raw-path/all-logger redaction; restored authority/erasure/delivery quarantine. Those skill files were not edited by Phase 9.

## 16. Due diligence Hamza can complete before implementation

- Choose public demo duration and loss-of-history disclosure. Is a disclosed 30-day Render database sufficient, or is continuing synthetic history worth a Neon compatibility/usage experiment?
- Choose whether any real data will leave the local machine in this release. Identify permitted data, region, consent/purpose and owners; no vendor certificate answers those product questions.
- State an actual monthly ceiling and whether overages/payment-method billing are allowed. Review compute, egress/media, builds, storage/PITR, backup, staging and monitoring line items rather than just a headline price.
- Name primary/backup operator and acceptable support availability. Confirm manual recovery identity verification, infrastructure seat access, key custody and incident acknowledgment.
- Accept or revise proposed RPO/RTO and backup retention. Demonstrate that encryption keys and latest erasure/revocation ledger survive the same incident as the database.
- Inspect current vendor console limits and contradictions: Neon October 2 1 GB update versus older 0.5 GB docs; Render current plan versus older bandwidth articles; uptime monthly versus annual commitment. Save a non-sensitive dated quote, not credentials.
- For each proposed telemetry tool, approve exact payload/region/retention/deletion, scopes/token location, sampling/cardinality, buffer/drop behavior, receiver and exit. Prefer native diagnostics if no unanswered operating question remains.
- Decide between Phase 7's optional error-only Sentry and Phase 9's aggregate Grafana candidate based on the actual support need. Any source-map/source upload, browser replay, remote alerts or live provider integration requires its own explicit scope.
- Confirm synthetic/private database and configuration separation, direct migration/dump connection, runtime pool budget and measured idle worker cost. A free tier or large connection count is not a benchmark.
- Review the final combined Phase 7/8/9 file ownership and acceptance evidence before authorizing implementation. Approve deployment/provisioning/provider tests separately once exact targets and reviewable artifacts exist.

Unresolved: actual hosting account/region/origin/database, billing ceiling, real workload/storage growth, target Linux/Render memory and cold-start results, private inference transport/capacity, retention/backup/key/ledger destination, maintenance staffing, vendor retention/deletion terms for the selected account, current full release-candidate rerun and live provider grant behavior. These remain unknown rather than invented production details.
