# Phase 8: backend security, CI/CD and deployment plan

Requested October 5, 2026; prepared October 6, 2026, America/New_York. Official research was performed for the requested October 5 baseline and carried into this document across the date change. Recheck prices and platform behavior at implementation and deployment approval.

**Planning only. Recommendations below are not accepted implementation decisions. No application changes, dependency installation, provider calls, credentials/settings changes, provisioning, commit, push or deployment occurred.**

## 1. Recommendation and provenance

Recommend a bounded public synthetic demonstration first, using the existing client-rendered React/Vite, FastAPI, supervised worker and dedicated PostgreSQL runtime. Preserve Render Free and disclose sleep and temporary persistence. Gate invited private use separately on durable storage, recovery ownership, real-data permission and actual provider consent/delivery evidence.

This is sequencing, not removal of Jira, Slack, GitHub or supported LinkedIn requirements. A synthetic demo can pass its narrow release gate while the complete private product still has unfinished activation/UI/operational gates. The dedicated LinkedIn draft/publishing frontend remains pending.

| Accepted/source-confirmed | Proposed or unknown |
| --- | --- |
| Render Free selected; synthetic public demo first | Exact database/lifetime, region, service/account/origin and cost ceiling remain unknown |
| React/Vite client rendering; API and worker; PostgreSQL/Alembic | No SSR migration recommended |
| Hosted deterministic hash/rules; optional LOCAL Ollama separate | No cloud AI substitution or model superiority claim |
| Confirmed participants, immutable/current revisions, exact delivery previews/approval | Client-identity policy, schema compatibility and worker-progress contract need approval |
| Visitor isolation and invited private scope, uncertain-write handling | Hosted/live behavior remains unverified |
| Provider status and personal-plan progress have separate owners | Automatic provider synchronization is not proposed here |

**Writable planning checkout:** C:/Users/hamex/Desktop/meeting-to-tasks/meeting-to-tasks, clean main at 8beac1b49f373cbc5c7e56fd7c9b27bb9d9039b8 before this work. It was not reset.

**Authoritative inspected source:** C:/Users/hamex/.codex/worktrees/e2db/meeting-to-tasks, codex/m2o-revamp at ddfca8251ff37f31ef3f175ca1d50da42833ed6c. Initially clean; later coordinator-created planning/skill files were preserved. Coordinator identifies the checkpoint as published on [M2O main](https://github.com/hs14235/M2O). This pass did not retrieve hosted Actions or verify current remote head.

**Only authored file:** docs/PHASE_8_BACKEND_DEPLOYMENT_PLAN.md in the writable checkout. Relative implementation references below refer to the authoritative checkpoint, not the older writable checkout. Portable source example: [hosted launcher at reviewed checkpoint](https://github.com/hs14235/M2O/blob/ddfca8251ff37f31ef3f175ca1d50da42833ed6c/backend/scripts/serve_demo.py).

Read AGENTS.md, M2O_IMPLEMENTATION_CONTRACT, README, VALIDATION, SECURITY, HOSTED_DEMO_RUNTIME, RENDER_PLAN, OPERATIONS and narrowly relevant code. Newly created m2o-backend and m2o-deploy-security skills were reviewed read-only. No actionable blocking instruction gap was found for “fix proxy quotas and deploy free demo”; they require current authorization, exact targets, ingress evidence and relevant regressions. No skill was edited.

## 2. Source evidence and its limits

| File / location | Confirmed evidence | Limit |
| --- | --- | --- |
| backend/scripts/serve_demo.py:12, 59, 72, 100 | Synthetic config guard, forward migration before launch, API/worker supervision, bounded child termination | No hung-worker detector or hosted Linux shutdown acceptance |
| serve_demo.py:123; backend/Dockerfile | --no-proxy-headers in both Uvicorn entry points | Hosted client attribution unresolved |
| frontend/nginx.conf | Host/proto forwarding, no explicit canonical client-IP contract | Compose proxy is not evidence of trusted Render identity |
| app/main.py:240, 333; lifecycle_routes.py:87, 100, 108, 124 | Auth/admission/invitation/recovery budgets use request.client.host | Shared proxy-peer buckets |
| app/limits.py:15; models.py:483 | Hash-keyed PostgreSQL RateBucket with row locks/first-insert collision handling | Shared storage does not prove correct identity/fairness |
| app/main.py:87, 221, 226 | Startup checks connectivity; /healthz alive; /readyz DB/revision query | Neither compares revision with expected head or verifies worker progress |
| app/worker.py:91, 118, 162 | SKIP LOCKED, ownership fencing, 90-second lease, 20-second renewals, three claims | Not hosted recovery/availability evidence |
| auth.py:43; access_policy.py; services/lifecycle.py | Hashes, expiry, CSRF/Origin, scope and authority generation | Local password foundation is not enterprise security/compliance |
| provider_credentials.py | AES-GCM, associated provider/account/user data, v1 prefix | Single key; rotation/keyring/recovery procedure not implemented |
| hosted.py:13, 25, 38 | Static containment, SPA document fallback, missing assets error, separate API/static headers | Hosted image needs checks beyond Compose |
| .github/workflows/verify.yml | Backend PG/static/audits, frontend checks, Compose/browser; contents:read; no deploy job | Configured workflow is not an observed hosted green run |
| Dockerfile.render; render.yaml | Non-root single Free Docker service, manual deployment, private config placeholders | No deployed service/database/origin |

VALIDATION records an October 5 scoped audit: **94 native passes, four PostgreSQL-only skips**, and no blocking auth/isolation flaw in inspected paths. It also records **396 PostgreSQL passes before final narrow corrections**, affected reruns, **104 frontend tests** and local browser/container evidence. These dated, overlapping records are not a fresh aggregate. **No application tests ran during this planning pass.**

Documentation corrections to include in an authorized increment:

1. OPERATIONS says API startup checks expected schema; current lifespan calls check_database() and readiness only reads version_num. Presence of Alembic state is not compatibility.
2. RENDER_PLAN describes the shared supervisor conditionally although it is implemented locally; change to “implemented locally, hosted acceptance outstanding.”
3. SECURITY’s original OIDC discussion needs a link to separate LinkedIn publishing code/pending UI, without broadening OIDC claims.
4. Retention and recovery procedures must describe actual hosted scheduling/maintenance access; a helper or frozen scope is not automatic deletion.
5. Historical “not implemented” and “CI not executed” paragraphs are dated evidence. Refresh only after observing the current revision/environment.

## 3. FIRST release blocker: proxy identity and quotas

### Diagnosis

**Confirmed:** affected endpoints consume budgets from the socket peer while both launchers disable proxy-header processing.

**Source-supported inference:** a hosting proxy can place unrelated clients into the same bucket; multiple proxy peers can also fragment a client budget. This threatens admission availability/fairness. It is not an observed live attack or authentication bypass.

| Current source budget | Existing regression baseline |
| --- | --- |
| login-ip | 30 / default 300 seconds |
| login-account | 10 / default 300 seconds |
| visitor-ip | 10 / 3,600 seconds |
| invitation inspect / accept | 30 / 15 per default window |
| recovery request / reset | 10 each per default window |

These values are not measured hosted capacity. PostgreSQL already shares counters across processes. Redis does not fix the wrong key and has no demonstrated requirement here.

### Official ingress evidence

- Render’s [PocketBase guide](https://render.com/articles/host-pocketbase-on-render) describes Cloudflare → Render load balancer public ingress. It says CF-Connecting-IP is overwritten by the edge and warns that caller-controlled leftmost X-Forwarded-For is unsafe. Its private-service case needs a separately protected forwarding boundary.
- Render’s [DDoS guide](https://render.com/articles/how-render-handles-ddos-attacks) broadly recommends XFF without a complete chain/trusted-peer policy. Treat the more specific guidance above as the starting point; do not select the first entry.
- [Render web services](https://render.com/docs/web-services) says the application port is not directly public and TLS terminates at the load balancer. This does not prove every internal caller is trusted.
- [Cloudflare headers](https://developers.cloudflare.com/fundamentals/reference/http-headers/) documents Worker-subrequest and IPv6/Pseudo-IPv4 variations. Extra customer CDN/Worker paths change the analysis.
- [Uvicorn settings](https://uvicorn.dev/settings/) defines proxy-header processing restricted by forwarded-allow-ips; “*” trusts everything. No runtime regression of the pinned installed version ran here.

**Evidence gap:** actual route/custom-domain/CDN topology, immediate peers/CIDRs, duplicate/header order behavior, internal/direct reachability and ingress changes remain unverified. No static Render ingress CIDR/fixed hop count is known from this research. Outbound service IPs are not inbound trust identities.

### Recommended A: narrowly scoped canonical client identity

Propose one small server-side helper for quota identity, retaining the raw peer for trust evaluation. Avoid globally mutating request.client, scheme or Host merely to fix a budget.

| Runtime profile | Policy | Required proof |
| --- | --- | --- |
| Native/direct | Valid canonical socket peer; ignore forwarding headers | Known direct listener |
| Owned Nginx | Proxy strips/replaces caller identity; API trusts only its protected path | Verified peers/network and overwrite regression |
| Render Free public edge | Single canonical CF-Connecting-IP only in the explicitly enabled profile | Proved edge overwrite and absence of bypass/direct/internal ingress |
| Private/multiple proxies | Separate authenticated/protected forwarding contract | Verified callers, network and hop policy; no inherited Free assumption |

A header name is not authentication. The Render profile is conditional on target proof, not a generic trust policy. If internal/direct callers can reach the listener, exclude/authenticate them or handle them as untrusted. “All private IPs” is not an acceptable trust list.

Before coding, specify:

1. Missing, duplicated, invalid or ambiguous trusted identity must yield safe rejection or a deliberate bounded fallback, never unlimited new buckets.
2. Parse bounded IP literals with a standard parser; canonicalize IPv4/IPv6. Explicitly test mapped IPv6 equivalence, brackets/ports, zone IDs and pseudo-IP behavior; reject unsupported syntax instead of guessing.
3. Ignore XFF/Forwarded/X-Real-IP/True-Client-IP and proto/host substitutions unless their exact contract is separately established.
4. If XFF is necessary, process a bounded chain from the immediate trusted peer toward the first untrusted hop. No fixed hop count where paths vary.
5. Network identity is coarse. Preserve account/principal/workspace and storage/job caps plus global resource controls. NAT fairness and IPv6 address rotation remain limitations.
6. Keep budget keys hashed. Keyed hashing/retention changes require their own reviewed schema/privacy decision.
7. Health probes must not consume admission budgets; database quota failure must not bypass authentication.

### Alternative B: explicit global admission

If trusted attribution cannot be established, propose a deliberately named global synthetic admission budget with existing principal/workspace limits. Do not call shared peer-IP buckets visitor-specific quotas.

This avoids header spoof dependence but lets one caller exhaust public admission. Hamza must accept the availability tradeoff and Phase 7 must disclose truthful cooldown. Preserve login-account protections; pick global thresholds from capacity measurements. Browser IDs/cookies are not sufficient abuse identities because callers can recreate them.

**Avoid:** forwarded-allow-ips="*", first XFF entry, universally trusted CF headers, process-memory counters, blindly raising limits, adding a customer CDN solely to fix attribution.

### Required regression contract

| Family | Assertion |
| --- | --- |
| Spoofed forwarding | XFF/Forwarded/X-Real-IP/CF header, duplicates/mixed case cannot choose arbitrary keys |
| Direct untrusted peer | Forged identity ignored/rejected; edge profile cannot activate on direct path |
| Two clients / one edge | Independent keys under A; explicit shared semantics under B |
| One client / multiple edge peers | No per-peer budget multiplication |
| Multiple proxies | Supported chains correct; shortened/unsupported paths cannot bypass |
| NAT | Principals remain isolated; shared network fairness is truthful |
| IPv6 | Equivalent forms do not multiply budgets; malformed/mapped/pseudo cases explicit |
| Authentication | Account cap retained; Origin/CSRF denied; recovery remains non-enumerating |
| Multi-process PG | Concurrent insert, rollover and exhaustion have one shared counter, no lost update |
| Saturation/outage | Safe 429/503; no authentication fail-open; cheap probes unaffected |

**Target proof before public launch:** separately authorize a synthetic validation deployment, then send probes from two controlled networks with forged headers, test actual platform/custom-domain paths and approved internal callers, compare canonical keys without returning raw headers/IPs publicly. Use protected temporary diagnostics with minimum retention; no public echo endpoint. Record date/topology/release/test evidence and revalidate after ingress changes.

## 4. Threat model and boundaries

~~~mermaid
flowchart LR
 B[React browser] --> E[Verified TLS edge / owned Nginx]
 E --> A[Hosted static + FastAPI]
 A --> D[(Dedicated PostgreSQL)]
 W[Supervised or private worker] --> D
 W -. private only .-> L[LOCAL Ollama]
 W -. exact approved delivery .-> P[Jira / Slack / GitHub / LinkedIn]
 A -. authorized private import .-> G[Google Meet]
 O[Operator migrations / recovery / restore] --> D
 A --> T[Allowlisted diagnostics]
 W --> T
~~~

Public synthetic hosting has no live L/P/G activation. Static serving does not authorize users. DB owns source/review/authority/jobs/receipts; providers own external status; personal progress remains M2O-owned. Diagnostic telemetry is distinct from audit history.

| Threat / affected asset | Existing control | Release check |
| --- | --- | --- |
| CSRF, session replay, credential stuffing | Argon2, hashes/expiry, exact Origin/CSRF, auth generation | Actual HTTPS cookies, budgets, expired/revoked auth |
| Cross-user/workspace/restricted source exposure | Server-derived authority, 404 non-disclosure, composite provenance | Negative HTTP/browser access tests |
| Prompt grants tools or invents owners | Validation, explicit confirmation and review | Malicious synthetic transcript cannot authorize writes/identities |
| Stale review or substituted delivery | Versions/hashes/source/destination approval | Simultaneous approval, changed grant/source, atomic enqueue failures |
| Ambiguous POST or revoked worker authority | Persistent intent, lease/authority checks, uncertain receipts | Crash checkpoints and no blind resend |
| DB/log leak of provider access | AES-GCM associated data, safe output | Key recovery/rotation, encrypted backup access |
| Spoofed IP/Host/proto | TrustedHost/exact origin, disabled broad trust | Verified section 3 policy |
| Oversized upload/traversal/stored XSS | UTF-8/text bounds, containment, React text, CSP | Stream/chunked body bounds, final image MIME/cache/security |
| Malicious CI/action or accidental deploy | contents:read, no deploy job, ignored config | Immutable pins, no-secret PRs, safe failure artifacts |
| Data expiry/restore revives erased authority | Freeze/erasure/tombstones, local restore helper | Current restore with deletion replay and paused effects |

### Secrets, cookies, TLS, origins and CSP

- Synthetic DB/operator access must be separate from private installations. No shared public password; use isolated visitor flow.
- Current hosted secret rejection list omits GOOGLE_MEET_CLIENT_ID/SECRET added later. Existing private/demo/encryption guards still block Google activation: this is an **exhaustiveness gap in the credential-free contract**, not a confirmed provider bypass. Propose tested complete credential inventory/allowlist.
- Keep actual DATABASE_URL/APP_ORIGIN in the authorized platform secret mechanism. Never print expanded config; no backend .env/runtime links/backups in build context. No VITE_* secret because frontend assets expose it.
- Preserve host-only HttpOnly/Secure/SameSite=Lax session cookie; readable mtt_csrf is intentional for header verification. Verify issuance, expiry, logout/recovery clearing on actual HTTPS.
- Managed TLS does not authenticate forwarding headers. Keep APP_ORIGIN and cookie Secure explicit. Prefer existing same-origin topology over adding separate API/frontend origins.
- Environment-specific allowed hosts must match actual traffic/health probes. Existing lists include local/test aliases; review production necessity, preserve test/local profiles and never wildcard.
- Exact CORS origin is not authorization. Cookie mutations retain CSRF/Origin; scoped bearer/MCP authority is separate.
- Preserve API no-store, no-referrer, static CSP, asset 404 and immutable hashed caching. hosted.py includes media-src; Nginx uses default-src fallback. Test both paths.
- Hosted static HSTS and API headers differ. Verify actual edge response policy before adding preload/includeSubDomains; do not claim uniform HSTS.
- Verify DB transport/CA settings for actual internal/external connection without printing its URL. Never bypass certificate checks.
- Single-key AES-GCM cannot be rotated by simply changing env. Private rotation needs inventory, reviewed dual-key/re-encryption or deliberate reconnect, protected recovery material, and rollback checks for stale/revoked secrets.

## 5. Provider scope, consent and effect safety

These are existing core integrations; account setup reports are not verified access. No live activation is implied.

| Capability | Current scope/credential boundary | Private activation gate |
| --- | --- | --- |
| Jira issue create/update | read:jira-work, write:jira-work, offline_access; encrypted rotating grants; owner delivery | Actual app distribution/3LO consent, site/project fields, refresh/revocation |
| Slack M2O post/update; separately gated actions | chat:write, channels:read, channels:history, commands; bot/client/signing secrets | Earlier minimal manifest is insufficient; channel membership, own-message update, signed callback |
| GitHub issues | Destination/operator token, minimum issue permission and allowlist | Exact repo/token access; no invented OAuth onboarding |
| LinkedIn self profile | openid profile; optional email discarded; OIDC tokens discarded | Product/callback/consenting member; no arbitrary lookup/identity verification |
| LinkedIn member post | Separate openid profile w_member_social publishing grant/version | Approved product/API/consent/policy/Page, dedicated UI; no lead messaging |
| Google Meet existing transcript import | meetings.space.readonly; encrypted renewable grant | Sensitive-scope distribution, authorized existing transcript; no recording/Drive/Calendar |

Primary references: [Atlassian 3LO](https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/), [Jira scopes](https://developer.atlassian.com/cloud/jira/platform/scopes-for-oauth-2-3LO-and-forge-apps/), [Slack methods](https://docs.slack.dev/reference/methods/), [LinkedIn OIDC](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2), [LinkedIn sharing](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin), [Meet authorization](https://developers.google.com/workspace/meet/api/guides/authenticate-authorize). Recheck exact method/API/version policies at activation.

Private acceptance order:

1. Confirm operator app ownership/distribution, callback, data disclosure/retention and allowed destination. Users consent; they do not supply operator client secrets.
2. Controlled HTTP + PG tests for session-bound state/nonce where relevant, replay/expiry/cancel, callback and refresh races, issuer/audience/signature, expiry and scope.
3. Verify encrypted storage, grant disconnect/rotation/revocation and scope visibility. Distinguish local disconnect from provider revocation: Google currently returns remote_consent_revoked=false.
4. Confirm source/participant/review versions and exact destination/payload hash. Recheck current authority before effects; raw evidence opt-in and restricted disclosure affirmative.
5. Persist intent before write. Timeout/abort/crash retains uncertainty; reconcile through supported reads. Empty search is not proof of no write.
6. Verify receipt against actual result. Provider status never automatically changes review or personal completion.

Jira preflight and Slack content hashes cannot remove the race after remote read. LinkedIn unsupported reconciliation cannot borrow GitHub marker semantics. Preserve limitations.

[Slack verification](https://api.slack.com/docs/verifying-requests-from-slack) requires raw-body signature/timestamp checks; [interaction handling](https://api.slack.com/interactivity/handling) requires acknowledgement within three seconds. Sleeping Free cannot promise that deadline. Keep actions disabled there; prove an awake private endpoint first.

No new email service selected. Owners manually share invitation links; recovery is operator-assisted identity verification and one-time private token. Free recovery cannot assume SSH/one-off access or use a new public admin endpoint as a shortcut.

## 6. Shared error and readiness contract with Phase 7

Preserve safe message/request_id/status; propose additive stable safe codes, operation identity and retry-after only when supported by real server state. Never echo submitted fields, OAuth values, raw provider responses or connection URLs.

| State | Server duty | Frontend acceptance |
| --- | --- | --- |
| 401 | Expired/revoked authority, no protected data | Clear protected scope/re-auth; private draft retention needs privacy decision |
| 404 | Non-disclosing inaccessible/removed | No cross-workspace fallback/existence inference |
| 409 | Stale source/version/approval/provider conflict | Preserve input; refresh/re-review, no silent overwrite |
| 422 | Bounded safe validation | Retain fields/actionable errors |
| 429 | Correct budget; cooldown from expiry | Server Retry-After only; no invented countdown/resubmission |
| 503 | Defined dependency/schema/worker/overload failure | Bounded GET recovery/manual wake |
| Accepted job | Identity/state survive failed refresh | Failed read is not failed write; scoped receipt recovery |
| Unknown write | Durable uncertain/reconciliation | Never retry mutation on timeout/abort/navigation/re-auth |

Phase 7 reports accepted writes and subsequent reads can share a UI error path, and polling stops on read error. Address this through a small contract, not broad API replacement. Request cancellation cannot undo a committed write.

Current meanings differ:

- Direct/hosted /healthz: API liveness. Hosted /readyz: DB/Alembic read.
- Compose Nginx /healthz forwards API /readyz.
- Neither proves worker progress, live provider access or successful delivery.

Propose expected-schema comparison plus co-located worker-progress readiness with startup/wake grace and bounded cheap checks. Separate private worker health should be monitored independently; define queue-dependent degraded capabilities rather than taking all API routes down for optional provider outage. Idle worker needs a process heartbeat independent of job leases.

No provider calls, large scans or destination/secret disclosure in readiness. Safe capabilities may disclose synthetic/rules mode and unavailable live integrations. Phase 8 owns server semantics, Phase 9 progress/metric storage, Phase 7 recovery/display.

## 7. Supervisor, workers and migration lifecycle

Keep modular API/worker/shared PG. The single public container is a budget adaptation, not a microservices mandate. No measured need for Kafka/Celery/Redis/Kubernetes/Render Workflows.

Current supervisor starts after validation/migration, fails on either child exit and stops siblings. SIGTERM/SIGINT terminates children with shared ten-second grace then kill/reap. Worker loop has no explicit drain; lease code alone is not Linux/Render shutdown proof.

Required final hosted-image drills:

1. Bad config/migration failure stops before user traffic; diagnostics remain safe.
2. Worker zero/nonzero exit stops API; API exit stops worker; no orphans.
3. Alive-but-stalled worker degrades progress/readiness; idle healthy worker remains visible.
4. SIGTERM during idle/request/index/extract/receipt: bounded cleanup, no false success.
5. SIGKILL after claim/commit: only current lease/authority/source can commit; computation recovers safely.
6. Private controlled-provider crashes before send, after intent, after remote success before receipt, after receipt: no blind resend.
7. DB loss/restart, pool exhaustion and sleep/wake: safe unavailable state, current schema/visitor expiry, truthful queue recovery.
8. Frozen/erased workspace with a running job whose lease expired during sleep/crash: prove wake/recovery settles revoked work and allows authorized purge completion without provider effects. services/privacy.py returns pending_erasure while any job remains running, regardless of lease expiry. Do not manually requeue/relabel ambiguous provider work or claim storage erasure from access expiry alone. Coordinate bounded maintenance and pending-erasure visibility with Phase 9.

Propose private worker drain: stop new claims, finish only within allowed deadline, retain durable intents/leases. Never classify interrupted remote effects as safely retryable solely because shutdown began.

[Render deploys](https://render.com/docs/deploys) documents SIGTERM followed by shutdown delay (default 30 seconds) before forced kill. Align actual service, supervisor, Uvicorn and worker deadlines; increasing a timeout is not verification.

### Schema compatibility

scripts.migrate checks connectivity and takes a PostgreSQL advisory lock before Alembic upgrade. It serializes runners; it does not guarantee compatibility with an old serving instance.

- Test fresh DB and upgrade from checkpoint with representative synthetic rows; inspect SQL/locks/backfill. Keep additive applied migrations immutable.
- Define accepted schema revision/range per release and check startup/readiness against it.
- Test old/new API/worker overlap and old/new job payload compatibility.
- Bound lock/connect/statement waits after target evidence. Current blocking advisory lock can wait indefinitely.
- Budget lock and Alembic connections plus old/new serving overlap; Phase 9 owns pool/reserve calculation.
- scripts.migrate holds a connection for its advisory lock while migrations/env.py obtains another from the same cached engine. With max_overflow=0, DB_POOL_SIZE=1 can starve migration startup. Test the minimum supported pool explicitly; the current Render setting is 2, not a capacity guarantee. If a later external database offers transaction pooling, verify a direct/session-compatible migration endpoint rather than assuming session advisory locks survive pooled routing.
- Free lacks paid preDeployCommand; preserve fail-before-serve startup migration or another supported strategy. [Render deploy documentation](https://render.com/docs/deploys) specifies paid pre-deploy availability.
- App rollback does not reverse DB. Destructive downgrades are blocked intentionally. Prefer compatible rollback/forward fix; restore only into specifically authorized target with backup/tombstone/authority plan.
- Acceptance must include older database/new application rejection and prior application/new additive database compatibility. Use an explicit supported-revision range for rolling releases where appropriate, rather than unconditionally demanding exact head equality.

## 8. Container and dependency hardening

Present: non-root UID 10001, frontend build stage, npm lock, pinned Python constraints, synthetic mode without model dependencies, .dockerignore private/runtime exclusions.

Required incremental review:

- Exercise Dockerfile.render itself, not only Compose.
- Pin verified maintained base digests and full action SHAs; current Python/Node/Postgres tags are mutable. Schedule controlled refreshes; invent no digest.
- Check constraint completeness, including direct SQLAlchemy, resolution/pip check and optional AI boundary. Hash-verified dependencies can be considered later; no unrequested lockfile rewrite.
- Scan final OS packages as well as Python/npm. Existing package audits leave base-image gaps.
- Inspect image history/files/build context with synthetic secret canaries; never print real discoveries.
- Test required temp writes/listeners and least privilege. Read-only FS/cap-drop/no-new-privileges need actual platform support and regressions; Dockerfile alone cannot enforce every host option.
- Measure CPU/memory/concurrency with Argon2, uploads, vector work and media. Cheap price does not prove fit.
- Triage vulnerability severity/fix/reachability; exceptions require reason/owner/expiry. Do not blanket-ignore findings to pass.

[GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use) recommends full-length SHA pinning and least privilege. Immutable pins still need maintenance/source review.

## 9. CI/CD and release promotion

verify.yml configures Ubuntu/Python 3.13/Node 22/Postgres 17, migrations/drift, PG pytest, Ruff/Pyright/pip audit, frontend type/test/build/audit and Compose/browser; no deploy job. Its local presence is not hosted run evidence.

Narrow gaps:

1. Final hosted-image build/start/Linux signals/worker recovery.
2. Proxy/auth/NAT/IPv6/two-process budget regression.
3. Expected schema and progress freshness.
4. Accepted-write/read-recovery contract tests.
5. Safe failure artifacts: current bounded API/worker logs need bootstrap/third-party error redaction review; no env, DB dumps or browser storage upload.
6. Pins, timeouts, exact run provenance; ubuntu-latest is not byte-identical reproducibility.

Keep configured checks. Mark unavailable scans unavailable, not clean. All CI fixtures remain synthetic. Untrusted PRs receive no provider/deploy secrets; no privileged pull_request_target checkout shortcut.

Promotion sequence:

1. Hamza approves selected decisions and local implementation scope.
2. Small increments receive focused then broader affected checks/docs. No automatic commit/push.
3. Record candidate SHA, affected full PG/frontend/browser results, final hosted build/image inputs, schema compatibility and dated scans.
4. If publication authorized, retrieve hosted Actions **for exact SHA**, run URL/jobs/skips/failures/artifacts; earlier green/badge insufficient.
5. Prepare secret-free release manifest: source/image/schema/mode, actual approved targets, prior compatible deploy, config names, ceiling/owners.
6. Keep autoDeployTrigger off. Manual deployment requires exact repo/branch/account/service/DB/origin/scope/cost authorization. Do not add deploy hooks to verify jobs.
7. Authorized synthetic ingress/TLS/cookie/static/readiness/worker/cold-start validation precedes public launch.
8. Record observations; private/live activation is a separate gate.

Exact source is not necessarily exact image with mutable bases/resolution/platform rebuild. Initial source deployment must record actual build provenance. Prebuilt immutable registry promotion can follow only if its upload/credentials are separately justified and approved.

| Gate | Evidence | Owner |
| --- | --- | --- |
| G0 decisions | Identity policy, synthetic lifetime/DB/targets/budget/privacy | Hamza/coordinator |
| G1 integrity | Proxy/auth/visitor/CSRF/revision/uncertainty regressions | Phase 8 |
| G2 runtime/data | Fresh/upgrade/drift/pools, two-process quotas, stalled worker/recovery/signals | Phase 8 + 9 |
| G3 journeys | Visitor, five kinds, people, review, plan/export, errors/mobile/motion | Phase 7 |
| G4 candidate | Current affected full checks, image review, exact provenance, rollback rehearsal | Coordinator |
| G5 target | Actual ingress/HTTPS/cookies, measured cold/warm resources | Authorized deployment owner |
| G6 private | Durable restore/tombstones, awake callback, recovery, data consent, live grants | Authorized private operator |

Existing workflow/guide commands are future validation procedures, not observed results from this document-only pass.

## 10. Operations, Free constraints and rollback

[Render Free](https://render.com/docs/free) documents 15-minute idle sleep, about a minute to wake, 750 monthly workspace running hours, ephemeral files, one service instance, no Free worker/shell/one-off jobs/persistent disk. Free Postgres is 1 GB, expires after 30 days with 14-day upgrade grace, and has no managed backups/pooling. Only two recent previous Free deploys are rollback targets. Treat this as temporary synthetic hosting with an expiry owner, not durable private persistence. No synthetic keep-alive probes are recommended.

API/worker sleep together; jobs wait for wake. Media/monitoring traffic consumes resources; diagnostic probing must not become an unintentional sleep-prevention scheme.

Stop promotion for identity spoofing, cross-scope disclosure, incompatible schema, falsely healthy stalled worker, lost uncertainty, exposed private data/secrets, or actual memory/startup failure.

| Event | Safe owner action |
| --- | --- |
| Wake/idle sleep | Truthful state, bounded reads; no repeated mutations |
| Bad build/start/migration | Do not promote; inspect safe evidence, never fake schema |
| DB outage/expiry | Stop DB-dependent work; approved expiry/restore procedure |
| Hung/exited worker | Degrade progress; stop claims/restart under authorized scope; fenced leases |
| Unknown provider effect | Freeze resends, receipt/read reconciliation or approved human inspection |
| Secret exposure | Stop propagation/effects; authorized revoke/rotate; safe incident evidence |
| Restore after erasure | Replay tombstones/authority invalidation before access/effects |
| Resource/spend exhaustion | Approved controls; no silent paid upgrade |

Application rollback: prove prior code accepts current schema/jobs; inspect active effects/intents; pause new effects where needed; select actual approved prior deploy; verify secret/key/privacy freshness and readiness; rerun critical synthetic smoke. Never roll back review/audit/receipt truth.

[Render rollback docs](https://render.com/docs/rollbacks) describes reuse of prior build/config and environment-variable/group behavior. Old env can reappear: check revoked credentials/keys/privacy explicitly. Platform app rollback does not reverse external DB/provider effects. Mutable image tags are not reliable rollback artifacts.

Free maintenance cannot assume SSH. Propose local authorized protected DB maintenance or documented startup/redeploy repair; never expose public administration to compensate. Private paid maintenance path is separately approved.

Name release, DB expiry/restore, recovery/identity, provider revocation and advisory owners. A solo owner can hold all roles, but procedures belong in runbooks.

## 11. Bounded integration due diligence

No new SaaS telemetry vendor, broker, identity platform or cloud model is selected. Phase 9 owns fuller monitoring/storage costs. Each candidate below includes adding nothing as an alternative.

### A. Render existing web/Postgres hosting

**Recommendation:** selected Free for temporary synthetic; evaluate awake/durable paid private stack separately.

- **Benefit/gap:** shareable demo and real ingress/TLS evidence; local tests cannot provide hosted proof.
- **Data/retention/privacy:** source/static assets for platform build, synthetic DB records, IP/HTTP metadata and safe logs. Private hosting additionally stores authorized real content/grants and delivers reviewed payloads; separate consent. Verify actual platform build/log/backup access/retention/residency. Hosting certification does not certify M2O.
- **Auth/secrets:** actual operator access, dedicated DATABASE_URL/exact APP_ORIGIN; later deploy credential only if narrowly approved. No provider secret in public demo.
- **Limits/paid trigger:** section 10; durability and awake callback requirements trigger a new decision.
- **Costs:** [Render pricing](https://render.com/pricing) lists $7/mo 0.5c-512mb web/worker, $6/mo 0.1c-256mb Postgres compute, storage $0.30/GB/mo. Arithmetic floor: co-located awake API/worker $13 + storage; separate awake web/worker $20 + storage, excluding egress/backup/monitoring/tax/higher capacity. Not a measured fit or approved ceiling.
- **Workspace:** [new plans](https://render.com/docs/new-workspace-plans) says Hobby $0, 5 GB included bandwidth then $0.15/GB and 500 pipeline minutes. Actual account may be legacy; verify separately. Do not use historical legacy DB pricing for a new DB.
- **Burden/failure/exit:** named owner for manifests/expiry/incidents/bills; PostgreSQL export/restore and portable Docker/ASGI enable exit, requiring current restore proof.
- **Compatibility:** existing wrapper fits Docker web service; worker shares sleep; no inference replacement.
- **Private-runtime condition:** serve_demo deliberately rejects private mode and credentials. The co-located paid figure is hypothetical topology arithmetic, not an available private launcher. Private co-location requires separately reviewed supervision/configuration; separate awake API/worker is the preferred private operations proposal.
- **Add nothing/validation:** local demo stays $0 hosting but no public URL. For hosting, G1–G5 plus actual usage/retention review. No resource created.

### B. Existing GitHub Actions; optional CodeQL

**Recommendation:** strengthen exact-revision workflow; CodeQL is an additional signal after runtime blockers, not permission to change repository settings.

- **Benefit/gap:** shared deterministic checks; CodeQL covers some code/workflow patterns beyond tests/lint but not business authority or runtime proof.
- **Data/privacy/retention:** code checked out on hosted runner; logs and approved SARIF/artifacts in GitHub under actual visibility/retention. Synthetic fixtures only; inspect artifacts. No new upload during planning.
- **Auth:** contents:read existing; separate scan upload may need security-events permission. Verify version/docs; no deploy/provider secrets in PR checks.
- **Cost:** [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) says standard hosted runners free for public repositories; private GitHub Free includes 2,000 minutes/month and 500 MB artifacts; larger runners/storage have separate charges. [CodeQL](https://docs.github.com/en/code-security/concepts/code-scanning/codeql/codeql-code-scanning) applies to public and qualifying paid private org repositories. Recheck entitlement if visibility changes; no invented private quote.
- **Burden/failure/exit:** pins/query updates, finding triage; outage is unavailable evidence, not clean scan. Local checks remain; optional scan removable.
- **Compatibility:** Python/JS/TS; verify Python 3.13/dependency scanner support.
- **Add nothing/validation:** keep current workflow with documented gaps. Test synthetic finding, safe artifacts, fork/no-secret behavior and exact-SHA provenance. No setting changed.

### C. Trivy local/CI final-image scan

**Recommendation:** candidate for OS/image gap; no app runtime dependency. Approve/pin a verified release first.

- **Benefit/gap:** pip-audit/npm audit do not exhaustively review image OS packages/configuration.
- **Data/privacy:** inspect local image/archive; keep reports local. DB/registry downloads are outbound metadata, not permission to upload image/source. Reports can expose paths/secret findings; sanitize before publication.
- **Telemetry/retention:** [network docs](https://trivy.dev/docs/latest/guide/advanced/air-gap/) and [telemetry](https://trivy.dev/docs/latest/guide/advanced/telemetry/) describe checks. Proposed use disables telemetry/version checks; controlled DB downloads remain necessary. Offline requires a verified dated DB. Local report retention explicit.
- **Auth/cost:** Aqua-maintained [Apache-2.0 CLI](https://github.com/aquasecurity/trivy/blob/main/LICENSE), no SaaS license fee. Private registry credentials, if selected, pull-only. Costs are CI/storage/cache/operator time; enterprise scanner not selected.
- **Burden/failure/exit:** check official release/advisories and verify artifact/signature before install; pinned scanner/DB date; unavailable DB means unavailable result. Severity/fix/EOL triage and expiring exceptions. JSON/SBOM reports ease replacement.
- **Compatibility:** exact final Linux image/package inventory, not just repo.
- **Add nothing/validation:** package audits/manual base review retain OS gap. Approved vulnerable fixture and synthetic canary prove detection, safe report and disabled telemetry. Nothing installed/scanned.

### D. OpenTelemetry Python/FastAPI

**Recommendation:** defer remote exporter/vendor until safe logs/aggregate metrics leave a demonstrated request→queue→worker diagnosis gap.

- **Benefit/gap:** current JSON request fields/worker job errors lack full async causality. Transitive opentelemetry-api in constraints is not configured SDK/exporter.
- **Data/privacy:** route template, safe code/status/duration/release/bounded correlation only. No query/body/transcript/outcome/SQL params/provider payload/cookies/tokens/email/IP/exception values; never put job payload in baggage.
- **Retention/auth/cost:** [Python SDK](https://opentelemetry.io/docs/languages/python/) is open-source; local CPU/memory/disk only, no selected ingestion subscription. Remote endpoint/token/retention/residency and paid trigger remain undecided; no fabricated allowance.
- **Burden/failure/exit:** version/cardinality/sampling owner; bounded nonblocking export must not affect transactions. Disable instrument/export without losing safe logs; standard OTLP preserves choice.
- **Compatibility:** [instrumentation](https://opentelemetry.io/docs/languages/python/instrumentation/) distinguishes API/SDK; [FastAPI library](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/fastapi/fastapi.html) supports exclusion/hooks/header sanitation. Verify pinned FastAPI/Starlette/HTTPX/SQLAlchemy and worker handoff.
- **Add nothing:** existing safe logs/aggregate metrics first is recommended.
- **Validation:** synthetic secret canaries, excluded health/OAuth, exporter outage/full buffer, measured overhead; no high-cardinality metrics from request/job IDs. No dependency/exporter adopted.

## 12. Proposed ownership, sequencing and acceptance

Ownership is proposed, not permission for concurrent shared edits. Planning chats own only their own docs.

| Shared area | Proposed author | Review dependency |
| --- | --- | --- |
| Identity helper/main/lifecycle/limits + regressions | Phase 8 | Phase 9 PG counters; Phase 7 cooldown |
| auth/settings/provider config/credentials | Phase 8 | Coordinator/provider review |
| hosted/supervisor/Dockerfiles/render.yaml | Phase 8 | Phase 9 data/progress/cost; Phase 7 serving |
| frontend/nginx.conf | One coordinator-designated author | Phase 8 ingress + Phase 7 CSP/media/cache |
| verify.yml | One release/coordinator author | Phase 7 browser, Phase 8 hosted/security, Phase 9 PG/restore |
| database/models/migrations/retention/restore/progress store | Phase 9 | Phase 8 compatibility/revocation |
| worker.py | One increment owner designated first | Phase 8 effects/drain; Phase 9 leases/progress |
| frontend API/error/read recovery | Phase 7 | Phase 8 semantics |
| README/VALIDATION/SECURITY/OPERATIONS/HOSTED_RUNTIME | Coordinator consolidation | Owners supply dated scope/results |

Order:

1. Decision packet: synthetic DB/lifetime, ingress policy, private cost threshold and candidate tool selection.
2. Contracts/tests/ownership: identity, stable errors, schema, progress.
3. Small backend change: identity + credential-guard completeness; focused then affected PG regressions.
4. Runtime/data: schema/pools/progress, signal/lease/crash drills.
5. Frontend: accepted-write/read distinction, bounded read recovery, non-disclosure/mode truth; affected browsers.
6. Candidate checks: final hosted Linux path, current affected acceptance, scans/safe artifacts; optional tools only if approved.
7. Review manifest/runbook: exact target/spend/rollback/expiry/owners.
8. Authorized synthetic target validation then bounded public launch.
9. Separate private pilot: durable restore/deletion, identity/awake callbacks, live access one provider at a time.

**Public blockers:** unresolved identity or shared-cap decision; schema incompatibility not signaled; hung-worker visibility; current final-image start/shutdown/recovery; actual ingress/HTTPS/cookies; dedicated DB lifetime/owner; exact candidate CI/build provenance; no secrets in image/config.

**Private additionally:** authorized real-data policy, protected durable backups/current restore, tombstone/authority restoration, recovery/revocation owner, awake callbacks, approved apps/scopes/destinations and controlled live delivery, completed supported UI journeys.

**Optional:** CodeQL, rich OTel/remote backend, registry automation, managed identity/email, Redis, SSR, Kafka/Kubernetes. These need a stated threshold; none fixes wrong quota identity.

## 13. Due diligence and open decisions

For each candidate Hamza selects:

- Read current official limits and actual account terms; split workspace/compute/storage/usage.
- Identify data leaving M2O, access/retention/deletion/residency and telemetry exclusions.
- Verify app owner/scopes/consent/callback/refresh/revocation/rotation; setup is not capability.
- Name upgrades/alerts/expiry/recovery/billing owner and tested exit/export path.
- Choose failure/acceptance tests and usage/spend stop conditions.
- Approve concrete local work first; publication/settings/provisioning/deploy/live effects remain separate exact-target authorization.

Questions materially affecting implementation:

1. May public synthetic history expire with the Free DB, or must it persist? Durability changes the DB decision first.
2. For private hosting, what monthly ceiling/downtime/data-loss tolerance is acceptable? No budget assumed.
3. Standard Render route only, or custom-domain/customer CDN/Worker? Extra paths change trust proof.
4. If identity remains unverifiable, accept a disclosed shared admission cap or wait for public launch?
5. Who owns verified account recovery, provider revocation, restore and expiry? Are manual flows acceptable?
6. Which tools merit a local spike: image scanning, CodeQL, tracing? Adding nothing to telemetry is valid.
7. Which real-data classes/organizations, if any, are authorized for private pilot? Department examples/branding are not permission/compliance.

Unknowns: actual target/account/region/origin/ingress, exact hosted CI, live callback/product grants, final-image memory/cold-start evidence, maintenance access, current restore/tombstone drills, retention/spend/owners and local model CPU quality/latency. Integrated graphics is the usable hardware assumption.

**This phase is complete when the plan and evidence gaps are reviewable. Implementation, service adoption, publication, target verification and provider activation remain separate authorized work.**
