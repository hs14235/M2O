# Verification evidence

## Prepublication security review — October 5, 2026

A targeted independent read-only audit found no blocking authorization, workspace-isolation, credential-exposure or exact-delivery-approval flaw in the inspected paths. Two disjoint native runs produced **94 passed, four PostgreSQL-only skipped**: hosted/visitor/invitation/Google checks (64 passed, four skipped) and API/authentication/upload/privacy/publication checks (30 passed). Skipped checks are not concurrency evidence. This is scoped source and regression evidence, not a whole-system security certification or live-provider policy audit.

**Deployment gate:** the hosted launcher disables proxy headers while login, visitor admission, invitations and recovery budgets use `request.client.host`. A reverse proxy can put unrelated users in one quota bucket. Resolve the trusted-proxy/client-identity or deliberate global-budget policy and test spoofed headers and distinct visitors before hosting. This finding does not expose credentials or block publishing the source checkpoint.

Private environment/runtime paths were ignored and untracked. A heuristic source secret scan found only synthetic test fixtures; it does not establish historical secret absence. Live OAuth, provider delivery and Render behavior remain unverified.

## Experience V2 — October 5, 2026 (locally activated and verified)

This increment adds the four-destination shell, combined Review/Deliver stage, reviewed-outcome calendar, latest Google Meet transcript import and meeting search. It is locally activated and checked; it does not establish a live Google connection or deployed service. [Experience contract](EXPERIENCE_V2.md) and [Google import contracts](GOOGLE_MEET_IMPORT.md) define its boundaries.

| Check | Observed result | Boundary |
| --- | --- | --- |
| Backend owner's PostgreSQL regression | **396 passed** before the final visibility and provenance-cleanup corrections. | Real disposable schemas; synthetic provider HTTP responses. |
| Backend owner's final affected checks | **27 import/calendar passes** after both corrections; **45 provider/privacy/retention passes** after the cleanup correction. | Separate overlapping runs, not an aggregate count. |
| Coordinator's current PostgreSQL check | **27 passed in 33.10 seconds** for `test_google_meet.py` and `test_experience_calendar.py`. | Independent rerun of current source with real migrations, locks and constraints. |
| Local configuration/build | Compose validation passed; backend API, worker and migration images built. | Optional Google values wired from private root configuration; no new credentials supplied. |
| Disposable runtime | HTTP readiness reports schema **20261005_11**; real API/worker on a separate local port. | Own temporary PostgreSQL schema; existing installation unchanged. |
| Static media | Six department clips/posters matched local bytes and MIME types; missing file returned **404** on both disposable and refreshed Docker runtimes. | Actual HTTP bytes verified, not merely files present in the source tree. |
| Frontend components | **104 passed in 27 files**, 17.47 seconds; TypeScript and native/container production builds passed. | Current full run after calendar-to-review asynchronous selection regression was fixed. |
| Experience V2 browser | **3 passed in 25.9 seconds** on the disposable API/worker runtime. | Real indexing/extraction, explicit participant confirmation, five approved outcome kinds, dates/undated cluster, source-to-review navigation, legacy merged-stage URL, setup-required Google, repeated-title search and metadata. The third case uses explicitly synthetic Google responses for missing/processing/preview/exact restricted save and reopening the returned meeting. |
| Rendered/accessibility checks | Desktop 1440px and mobile 390px captures inspected; no horizontal overflow or violations in tested axe WCAG 2 A/AA and 2.1 AA checks. | Keyboard collapse/focus/reopen, persisted layout, calm/system reduced motion and confirmed-owner card checked; this is not whole-product WCAG certification. |
| Affected delivery workflow | **4 passed in 51.3 seconds** on the disposable runtime. | Synthetic Jira create/update approval and receipt recovery, local handoff/GitHub preview invalidation, department/personal-plan persistence and retained review history across transcript revisions. |
| Actual local activation | Backup saved; **20261004_10 → 20261005_11** migration completed; API healthy, web/worker running; Alembic check found no new upgrade operations. | Existing database volume and private configuration preserved. Zero pending external delivery jobs checked before refresh. |
| Docker visitor/browser acceptance | **4 passed in 41.9 seconds** on `localhost:8080`. | Real isolated visitor journeys across departments, exact local handoff/personal execution, cross-visitor denial, empty review, reduced motion, actual media playback/loop/pause and boundary-width reflow. |

The broader private invitation/recovery browser suite was not rerun after V2; its earlier lifecycle evidence remains dated below. Google provider responses in tests are synthetic, and live OAuth/transcript availability remains an external gate. No commits, pushes, live provider calls or deployment occurred during this increment.

## Current lifecycle and local application — October 5, 2026

These results supersede the older increment counts below for the implemented lifecycle and current local installation. They do not establish a deployed Render service, live provider authorization/delivery, complete LinkedIn publishing UI, or full accessibility certification. Exact journeys, commands and historical corrections are in [USER_LIFECYCLE_ACCEPTANCE.md](USER_LIFECYCLE_ACCEPTANCE.md).

| Layer | Observed result | Boundary |
| --- | --- | --- |
| Backend | Full PostgreSQL suite: **349 passed**, no skips, 351.59 seconds; native suite: **327 passed, 22 PostgreSQL-only skipped**. | Disposable schemas/data; full run preceded the last narrow own-grant disconnect correction. |
| Own-grant disconnect | **2 focused HTTP PostgreSQL passes**, plus **9 focused native provider passes**, after the full suite. | Signed-in self-removal, role demotion, removed membership, CSRF, other-user and revoked authority guards. |
| Independent lifecycle | **7 PostgreSQL HTTP acceptance tests passed**, 12.91 seconds. | Real visitor/private onboarding, recovery, export, erasure and worker paths with synthetic fixtures. |
| Frontend | Full **77-test** suite passed; **13 affected tests**, TypeScript and production build passed after the final preview-visibility correction. | No invented aggregate or fresh 79-test run. |
| Private browser | **4 passed**, 18.3 seconds, fresh fixture B. | Real API/worker/PostgreSQL; no provider mocks or private recordings. |
| Public browser | **4 passed**, 51.6 seconds; ten current public screenshots refreshed and inspected. | Isolated synthetic visitor scopes, department flows, motion, responsive tools and tested automated accessibility checks. |
| Staged workflow browser | Four cases verified across three initial passes and one corrected guided retry (41.7-second run). | Provider-facing UI responses are controlled synthetic responses; other application paths use the running API. |
| Actual Compose installation | Database backed up; images built; additive schema upgrade **20261003_04 → 20261004_10**; API/database health observed and web/worker running. | Existing database volume/private configuration preserved; zero pending external jobs checked before refresh. |
| Container business smoke | Actual port-8080 People Operations demo passed index/extract/participant confirmation/review/personal completion/exact JSON export. | Five synthetic outcomes; review approval/version survived personal completion. |
| Container media | Docker packaging corrected; all six clips/posters match source SHA-256 bytes and expected MIME types; missing media returns **404**. Actual-container playback/loop, pause and responsive tools also passed. | Tested local browser/CSP boundary; not hosted mobile performance measurement. |

Scoped Ruff/format/Pyright checks passed in the backend tracks and coordinator-owned runtime/acceptance files. No commits, pushes, PRs, external provider writes or deployment occurred. The README now has a short setup path, genuine screenshots, original video links and links to detailed lifecycle/development/operations guides.

The dedicated LinkedIn draft/publishing frontend remains outside the selected lifecycle finishing milestone; backend and own-profile UI availability must not be represented as a complete graphical publishing journey. Hosted availability/persistence, live app access and representative AI quality/performance measurements remain release gates.

## Jira reviewed delivery — October 3, 2026

This increment supersedes earlier Jira-unavailable/connection-only statements below. The full product release remains incomplete. Jira supports bounded issue-type/field discovery, exact stored create/update previews, owner approval, durable queued delivery, receipts, explicit retry after confirmed rejection, and read-only marker reconciliation. See JIRA_DELIVERY.md for field, authority and concurrency limitations.

- Full backend suite against real local PostgreSQL: **114 passed in 93.89 seconds**. Disposable per-test schemas execute all forward migrations. The 21 focused Jira delivery tests include simultaneous approval, browser-session CSRF, API → job → worker → receipt, exact POST/PUT, revoked owner access, stale source/destination/hash/expiry, changed remote issue, required-field validation, metadata pagination, uncertain-write prevention, explicit rejected retry, and reconciliation. Existing GitHub/OAuth/review/isolation tests remain intact.
- Frontend unit/component suite: **26 passed across 9 files**. New tests cover discovery, exact-hash approval, required unsupported-field blocking, stale preview removal and late response rejection. TypeScript passed. Ruff checks/formatting passed on affected Python files; full configured Pyright passed with zero errors/warnings using the project interpreter.
- Native production frontend build and Docker API/worker/migrate/web builds passed. Local Compose restart preserved existing data/volumes and kept demo mode enabled. Readiness returned `{"status":"ready","schema":"20261003_04"}`. Alembic check reported **No new upgrade operations detected**.
- Edge browser suite: **4 passed in 1.3 minutes**. Three existing application journeys use the actual local API. The added Jira journey uses actual sign-in/transcript/extraction/review, then intercepts provider-facing M2O endpoints with explicitly synthetic responses to test create/update controls, approval hash and receipt recovery. It does not prove live Jira connectivity. Real backend delivery is exercised separately through controlled HTTP transports and PostgreSQL tests.
- Axe reported zero violations in checked desktop/mobile Jira preview states and existing checked states; mobile horizontal overflow assertion passed. Desktop/mobile Jira screenshots were visually inspected. This remains a bounded accessibility check, not full WCAG certification. The Share page remains long on mobile; reducing its vertical review/configuration footprint belongs to the UX refinement phase.
- Initial verification failures were retained and investigated: native bundler sandbox access required approved execution; an incorrect pytest working directory was corrected; new fixture response/status expectations were corrected; the initial Jira browser selector used label text containing option text and timed out. Switching to the verified accessible combobox name made the complete rerun pass without removing assertions.
- Git diff whitespace checks passed with pre-existing line-ending warnings. No commits, pushes, remote CI, provider writes, credential activation or cloud deployment occurred. Local inference was not rebenchmarked; extraction tests run with deterministic rules/fallback and synthetic fixtures.

Assignee/reporter/user mappings, subtasks/parents, arbitrary plugin fields, workflow transitions, team-delegated publication and automatic synchronization remain unimplemented. Update timestamp preflight cannot eliminate a remote edit racing between read and PUT. The default demo blocks Jira and live account/product/permission behavior is still unverified. Slack, supported LinkedIn publishing, isolated visitor provisioning/invitations, authored video assets and the Render runtime remain release work.

## Jira connection foundation — October 3, 2026 (prior increment)

- Full PostgreSQL suite: **93 passed in 99.70 seconds**. Tests execute additive migration `20261003_03`, authenticated browser/API consent flow, CSRF, strict destination input, encrypted credential storage, state replay/expiry/cancellation, revoked membership, workspace separation, independently disconnected bindings, invalid resource URLs, scopes, stale destination versions, and hidden-prompt configuration preservation. Concurrent PostgreSQL tests prove one callback exchange and one rotating refresh for two simultaneous requests.
- Final frontend check: TypeScript passed; **22 tests across 8 files passed**. New connection components test destination verification/version payloads, demo restrictions, safe errors and disconnect. Native production build and Linux web/API/worker/migration builds passed.
- Final static checks: Pyright **0 errors/0 warnings**, Ruff passed, changed Python format checks passed. Final Alembic check: **No new upgrade operations detected**.
- Local rebuild preserved the existing database volume. The initial targeted rebuild omitted the separate migration image; the schema check caught the stale database revision. Rebuilt/recreated the migration runner and reran the drift check successfully. No table/data reset was used.
- Browser journeys: **3 passed in 1.2 minutes** using installed Edge and the ignored synthetic account, including the new Jira Connections setup heading/disabled-demo control and existing accessibility/mobile checks. Initial launch failed before testing because downloaded Chromium was missing; the rerun selected existing Edge. Initial native frontend verification was blocked by Windows sandbox/esbuild configuration reads; the approved rerun passed.
- Ollama was stopped during these browser journeys. They validate rules/fallback workflow behavior; they are not a fresh real-model extraction probe. The configured model remains Qwen2.5 1.5B; no replacement model was downloaded or selected.
- Provider credentials and responses in tests are synthetic. No real Jira/Slack/GitHub/LinkedIn request or external write was made. No credential was supplied to the private setup helper in the application environment, and demo mode remains enabled. Jira account connection and destination verification are implemented; issue field discovery, exact previews, delivery, Slack interactions, public isolation/invitations, cinematic video assets and Render deployment are still pending.
- No new dependency, lockfile update, commit, push, PR or cloud deployment occurred in this increment. Existing uncommitted work was retained.

## Department experience and daily planning — 2026-10-03

Implemented department-wide animated CSS scenes/themes, authorized department switching, persistent calm mode/system reduced motion, and PostgreSQL-backed personal execution plans. Scenes are original code-driven graphics, not video clips. Plan state does not change review status or ownership. Stale outcome/transcript versions prevent continuing work until appropriate review/reconfirmation.

- PostgreSQL full suite: **79 passed in 72.35 seconds**, including additive migration and five planning tests for persistence, expected versions, personal/workspace isolation, stale revisions, validation/viewer authority, and restricted/archived filtering.
- Frontend: TypeScript passed; **19 tests across 7 files passed**; native and Linux container production builds passed. Added themes/calm-mode and execution-plan component regressions.
- Python: changed-file Ruff lint/format passed; Pyright **0 errors/0 warnings**. Alembic check: **No new upgrade operations detected** after local migration.
- Local Compose rebuild/start passed, preserving the existing PostgreSQL volume and applying additive schema `20261003_02`.
- Final browser suite: **3 passed in 1.0 minute** using installed Edge and the ignored synthetic account. Covers department theme switching, calm persistence, system reduced motion, planning/completing an approved outcome across refresh, mobile layout, existing guided review/share and retained revision history. Axe checks passed in the tested states; this is not full accessibility certification.
- Initial browser run: **2 failed, 1 passed**, because whole-panel opacity transitions temporarily lowered text contrast. Removed text fades while retaining movement; rerun retained assertions and passed.
- Desktop department and mobile plan screenshots generated under ignored `frontend/test-results`; HR desktop and mobile planning screenshots inspected visually. These synthetic test screenshots are not publicly published assets.
- Slack manifest: JSON parsing and minimal `chat:write` scope assertion passed locally. Provider-side manifest validation/install and live provider requests were not executed.

The project-wide release remains incomplete: Jira/Slack delivery, LinkedIn posting/messaging, visitor-isolated demo provisioning, invitation activation, authored video assets and the Render-compatible runtime have not been implemented in this increment. `PUBLIC_DEMO_MODE` alone is not visitor isolation. Free-tier hosting constraints are documented in RENDER_PLAN.md. No external account/app was created, no Render deployment occurred, and no commit/push was performed.

## Guided workflow follow-up — 2026-10-03

Saved transcripts now allow viewers to use the Continue button while keeping transcript fields disabled. GitHub's publication status follows the actual destination capability, role, demo setting and repository permission instead of the demo setting alone.

TypeScript passed and all 15 frontend tests across 5 files passed, including regressions for these two behaviors. The first Vitest attempt could not load its configuration because Windows sandbox permissions denied ancestor-directory access; the permitted rerun passed. Git diff whitespace checks passed. Browser/container journeys and backend checks were not rerun for this frontend-only follow-up; the dated evidence below describes the earlier guided-workflow validation.

## Guided workflow verification — 2026-10-02

The frontend was changed from one long workbench to four URL-addressable steps: Transcript, People, Review and Share. The following results supersede the earlier suite counts for this local checkout:

| Check | Observed result | Scope |
| --- | --- | --- |
| Full PostgreSQL suite | 74 passed in 50.52 seconds | Includes local handoff authorization, stale revisions/approvals, opt-in evidence, date/owner serialization and the provider capability catalog. All row-lock tests ran. |
| Disposable SQLite suite | 71 passed, 3 skipped in 27.12 seconds | The three skipped tests require PostgreSQL and passed in the PostgreSQL run. |
| TypeScript and components | Type check passed; 13 tests passed across 5 files | Includes Back/Forward rejection, stable active outcome after approval, neutral handoff defaults and discarded late preview responses. |
| Python static checks | Ruff lint/format checks passed; Pyright 0 errors/0 warnings | Changed application/service/schema/test files and full application typing. |
| Linux container build/start | Passed | Existing local PostgreSQL volume retained; no schema migration was added in this pass. |
| Final guided browser journeys | 2 passed in 2.2 minutes | Installed Edge; all departments, local downloads, optional GitHub previews, real URLs, refresh/Back, unsaved guards, participant ambiguity and retained review history. |

Browser journeys cover all three department examples, separate page URLs, hidden GitHub controls until destination selection, one outcome on the Review page, reload of saved context, local download, exact GitHub preview invalidation, demo write blocking, ambiguous participant confirmation, rejected unsaved Back/workspace/outcome changes, and retained human review after a new transcript revision. Automated axe checks use WCAG 2 A/AA and WCAG 2.1 AA tags on login, each workflow step, the directory and the connections page, including mobile views. This is checked-page evidence, not complete WCAG certification.

Jira and Slack are explicitly unavailable in the catalog; no adapter or live provider verification is implied. LinkedIn remains locally tested with synthetic provider responses and awaits approved configuration. Page navigation uses the existing client renderer; server-generated HTML/SSR was not implemented.

Observed on 2026-10-01 in the isolated Windows worktree and its local Docker Compose project. All examples, accounts, meetings and provider responses used for validation were synthetic. This evidence describes local behavior; it is not a production certification.

## Automated checks

| Check | Observed result | Practical scope |
| --- | --- | --- |
| Full PostgreSQL backend suite | 66 passed in 37.49 seconds | Real migrations, constraints, transactions and row locks in randomly isolated test schemas. |
| Disposable SQLite backend suite | 63 passed, 3 skipped in 22.22 seconds | Fast adapter/business-rule regressions; the three PostgreSQL concurrency tests require PostgreSQL. |
| Python static checks | Pyright: 0 errors/0 warnings; Ruff checks passed; 61 files formatted | Application typing and Python source/tests/migrations/root scripts. |
| Python dependency consistency | No broken requirements | Installed native runtime/development environment. |
| Python runtime advisory audit | No known vulnerabilities found | Pinned runtime constraints applicable to the Windows audit environment; platform markers and optional AI dependencies limit scope. |
| Frontend type/component checks | TypeScript passed; 6 tests passed across 2 files | Review permissions, expected versions, retained edits on conflict, date hints, exact previews and invalidation. |
| Frontend advisory audit | 0 vulnerabilities | Full installed npm dependency tree after advisory fixes, including the esbuild override. |
| Production asset build | Passed natively and in the Linux web image | Lazy-loaded workspace views and same-origin API bundle. |
| Final browser/container journeys | 2 passed in 1.6 minutes | Installed Edge with local AI, keyboard focus, department examples, ambiguity, stale preview and retained review history. |
| Migration drift | No new upgrade operations detected | Alembic model/schema comparison against the local PostgreSQL schema. |
| Compose/configuration | YAML parsed; Compose config validation and build/start passed | Final local API, worker, web, database and optional Ollama configuration. |
| Readiness | HTTP 200 through web proxy, schema 20261001_01, CSP present | Actual running local web/API/database path. |

The PostgreSQL suite covers authentication/CSRF/logout, workspace isolation, viewer restrictions, restricted meetings, scoped token expiration, last-owner protection, upload/input bounds, safe database errors, complete REST and stdio MCP workflows, Unicode chunk boundaries, strict citations, extraction fallback/tail coverage, preserved review history, worker authority/leases, publication idempotency/exact payloads/closed issues/uncertain writes/reconciliation, and legacy import without changing the source.

The three concurrency tests establish that simultaneous workers claim distinct jobs, simultaneous reviewers cannot overwrite one expected version, and simultaneous OAuth callbacks consume state once. Signed synthetic RSA ID tokens exercise issuer/audience/nonce/expiry/subject validation; these tests make no LinkedIn requests.

Outcome-list verification proves two SQL queries load outcomes and evidence rather than one evidence query per outcome. Summary regression verifies that SQL aggregation excludes restricted meetings inaccessible to the acting viewer. This is query-behavior evidence, not a load benchmark.

## Real local inference

The native extraction probe and a separate session-authenticated API → PostgreSQL job → worker → Ollama probe both ran against the locally installed `qwen2.5:1.5b` model. The container probe processed 3/3 chunks in one batch and produced an action, decision and blocker in `mixed` mode. Its observed extraction time was 16,135.66 ms and external writes were zero.

The model initially omitted or misclassified explicitly labeled facts. The implemented literal-preservation guard produced the expected three types and surfaced `explicit_outcomes_preserved`/`explicit_type_corrected` warnings. That behavior is intentional: the model assists with interpretation, while literal facts and publication authority have deterministic checks. This small probe does not establish general extraction precision, recall, latency or safety.

The four-case lexical retrieval smoke evaluation returned recall@1 of 1.00, with the scope and limitations documented separately in `RETRIEVAL_EVALUATION.md`. Sentence Transformers semantic retrieval was not run.

## Browser and accessibility

Two Playwright journeys exercise the running containers with local AI enabled:

1. Sign in, import/index/extract the engineering, HR and finance examples, approve an outcome, inspect the exact proposal, invalidate selection, inspect history, and verify usable mobile layout.
2. Add two participants named Alex, handle ambiguity through explicit confirmation, prevent unsaved workspace navigation, save human review, replace the transcript and verify the earlier review remains readable.

The suite checks keyboard focus through the login form, mobile horizontal overflow, and axe WCAG 2 A/AA and 2.1 AA tags in login, directory and mobile workspace states. The observed checked states had zero axe violations. Desktop and mobile screenshots were generated under ignored `frontend/test-results` and inspected visually. This is not a full WCAG audit: broader keyboard/screen-reader, contrast/state, zoom and browser coverage still require review.

Initial browser failures exposed a mobile grid overflow and later malformed Unicode separators in the workbench. Those defects were corrected; successful reruns retain the assertions rather than weakening them.

## Backup and source review

A real PostgreSQL custom-format dump was restored into a newly created, separate local database. The restored schema revision and 55 synthetic outcomes matched the source at that point. The original application database and all existing data were retained. The dump and restored database remain private local artifacts; this is not off-host disaster recovery.

Git diff whitespace checks passed. A changed-file credential-pattern scan found no matching GitHub tokens, private-key blocks or AWS access keys. Ignored environment/account/backup files were kept outside tracked changes and container build contexts. Such a scan is one review aid, not proof that every possible secret format has been detected.

## Unexecuted or unverified boundaries

- GitHub Actions is configured locally; no remote CI run occurred.
- Live LinkedIn consent is unverified because no approved application/credentials exist. Arbitrary participant name lookup is not supported by ordinary OIDC access.
- GitHub provider tests use controlled HTTP responses. No issue, PR, commit, branch push or other remote write occurred.
- Public TLS/proxy/cookie behavior, production identity management, cloud infrastructure, monitoring/alerts, off-host backups, retention and disaster recovery were not deployed or verified.
- Optional semantic embedding dependencies/models, operating-system image vulnerability coverage and representative throughput/AI-quality benchmarks remain outside the verified scope.
- The optional native Windows PostgreSQL helper stopped at its binary check because the required binaries were unavailable. Docker Compose is the verified database setup; no native cluster was created.

The local application is usable and its critical integrity boundaries are tested. A public release still needs a separately authorized environment-specific deployment and verification plan.
