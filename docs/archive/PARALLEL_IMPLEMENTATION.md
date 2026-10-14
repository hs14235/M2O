# Coordinated implementation — October 3, 2026

## Current closure — October 5, 2026

The selected user-lifecycle/README finishing milestone is closed locally. Phase 3 handed off the verified backend lifecycle, migrations, privacy/retention tools and contracts; Phase 4 closed provider grant/erasure/receipt guards; Phase 5 closed invited/private and isolated/public interfaces, current screenshots, staged browser journeys and actual-container media verification. See `USER_LIFECYCLE_ACCEPTANCE.md` and the current section of `VALIDATION.md` for exact non-aggregated results and historical deltas.

The coordinator backed up and refreshed the actual port-8080 Compose app to schema `20261004_10`, preserved its volume/private configuration, verified a real People Operations review/plan/export flow, corrected the missing-public-media Docker packaging with Phase 5, and checked six served asset hashes/MIME types plus missing-file 404. The final actual-container browser playback/CSP test passed. Temporary synthetic browser runtimes cleaned their own schemas/credential fixtures; the local app remains running. No commits, pushes, PRs, deployment or provider writes occurred.

Future work starts from this checkpoint rather than stale in-progress paragraphs below. A dedicated LinkedIn draft/publishing composer, live provider grants, Render deployment/persistence/recovery and representative model/hosted performance measurements remain broader product/release gates. They were not silently counted as complete in the lifecycle milestone.

Hamza authorized execution of the three phase plans, with inspection and refinement before dependent changes. Local implementation and verification are authorized. Commits, pushes, deployment, account changes and live provider publication require separate explicit permission.

## Ownership

| Track | Owns | Integration rule |
| --- | --- | --- |
| Phase 3 Slack | Shared backend models, schemas, settings, routes, worker, provider catalog, forward migrations; Slack adapter/services/tests and setup manifest/docs | Integrates explicit additive requests from Phase 4. Preserves existing contracts and verifies migration compatibility. |
| Phase 4 providers | GitHub/LinkedIn-specific backend adapters, services, tests and provider documentation | Requests shared changes from Phase 3; supplies verified readiness, preview and receipt contracts to Phase 5. |
| Phase 5 experience | Frontend components, navigation, types/API client, styles, assets and frontend tests | Sole frontend editor. Integrates actual backend capabilities; no synthetic success or premature availability in product UI. |
| Coordinating chat | Cross-track inspection, contract review, verification scheduling, release evidence and isolated hosted demo runtime (`Dockerfile.render`, `render.yaml`, root `.dockerignore`, `app/hosted.py`, `scripts/serve_demo.py`, focused runtime tests/runbook) | Reviews changes before dependent integration. Does not independently edit another track's owned surfaces. |

Each track inspects existing work and peer contracts before changing dependent code. Database and provider mutation tests use disposable synthetic fixtures. Mutation-bearing browser tests against a shared account run serially. Existing dirty files and credentials are preserved.

## Experience refinement

The main workflow remains explicit and sequential. A contextual bubble at the right edge offers helpful secondary navigation only where relevant. It may indicate upcoming choices without representing a pending save, approval or successful delivery.

- A labeled native button opens a compact navigation disclosure. Hover/focus may alter its decorative shape; neither executes an action.
- Links and actions use ordinary labels and semantics. Keyboard and touch have the same capabilities; Escape closes the disclosure and returns focus when appropriate.
- Hidden options are absent from keyboard navigation. Closing does not discard form drafts or approved previews.
- The panel must not cover evidence, approval controls or essential mobile content. Pages without useful secondary options omit it.
- Calm mode and system reduced motion retain a static, clear control. Decorative transitions do not delay navigation or writes.
- Motion uses bounded transforms/opacity; no perpetual full-screen animation or unmeasured dependency additions.
- Duplicate clicks, refreshes and Back/Forward navigation retain server-authoritative state. Animation never retries an external write.

Primary implementation references: [W3C disclosure navigation](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/), [MDN Popover API](https://developer.mozilla.org/en-US/docs/Web/API/Popover_API/Using), [animation performance](https://web.dev/articles/animations-and-performance). These inform semantics and performance; they do not establish that M2O has passed accessibility or performance verification.

## Integration gates

1. Inspect baseline, refine the affected contract and communicate the dependency.
2. Implement the smallest complete increment in owned files.
3. Run focused failure-path and regression checks, then inspect the result.
4. Integrate dependent backend/frontend work only against the implemented contract.
5. Run affected PostgreSQL, type, component and browser checks; record observed evidence and unresolved failures.

Review approval, personal execution and external status remain separate. Credentials stay server-side. Exact previews, current authority, source/destination versions, durable write intent and uncertain-result handling remain mandatory.

Public visitor isolation, invitations, privacy lifecycle, durable hosted persistence and Render runtime limits remain release gates even when individual provider features work locally. Sleeping free hosting cannot be advertised as reliable immediate Slack interaction availability.

## October 4 verification checkpoint

- Coordinator independently ran GitHub adapter/destination/publication tests: 58 passed, 1 PostgreSQL-only concurrency test skipped. The focused PostgreSQL rerun stalled on a test's open rejection transaction blocking its own worker. The coordinator interrupted that run; Phase 4 fixed the test by releasing the transaction before starting the worker. A fresh PostgreSQL pass is required.
- Coordinator independently ran signed Slack action tests: 15 passed, 1 PostgreSQL-only replay/row-lock test skipped. Phase 3 is running its broader PostgreSQL checks and reviewing reconnect/action lock ordering.
- Coordinator authored the isolated hosted demo runtime: 18 native tests passed, scoped Ruff check/format passed, hosted wrapper Pyright reported zero errors. Linux container build/startup/shutdown and hosted resource measurements remain unverified.
- Phase 5 reported 32 component tests and TypeScript passing before subsequent Share changes. Original department clips/posters are saved; final mounting, current checks and rendered browser verification remain pending.
- LinkedIn drafts/publishing services and shared tables/routes are being implemented with synthetic tests. Product approval, a public privacy-policy address and live activation remain separate external dependencies.

This checkpoint is not a full-suite pass or release-completion claim. Current increment results supersede earlier capability inventories only for the behavior they actually verify. Shared runtime migration, account changes and provider writes have not occurred in this coordination increment.

## Token-efficient continuation

Hamza requested efficient token use across all phase chats on October 4. Search before narrow reads; do not reload unchanged files or whole chat turns. Coordinate actionable deltas only: changed contracts/files, new observed verification, unresolved blocker and next dependency. Run focused tests while changing an increment, then the affected broad suite once stable. Do not repeat unchanged passing checks or poll unchanged status frequently. Preserve security, failure-path and PostgreSQL concurrency verification.

Current continuation references:

- `CROSS_PHASE_REVIEW.md`: all-feature ranked research/revision gates; peer detail in `PHASE_3_REVIEW_FINDINGS.md` and provider/experience reports as they land.
- Phase 3: shared backend owner; signed Slack lock ordering, authoritative rereads and attempt-limit receipt handling corrected with reported PostgreSQL checks. Next increment is isolated visitors/expiry/quotas, then safe invitation/recovery/privacy contracts.
- Phase 4: GitHub/LinkedIn owner; reported focused PostgreSQL run 53 passed. Exact marker/content and GitHub 201 field verification are being corrected before shared worker integration. LinkedIn synthetic modules/routes exist; live product consent remains unverified.
- Phase 5: exclusive frontend owner; reported TypeScript, 43 component tests and production build passing before new focused fixes. Correcting heuristic score/mode wording, scene reset, medium-width bubble overlap and late preview navigation. Serialized browser slot remains to be granted after the next stable increment.
- Coordinator: hosted runtime native tests 18 passed, scoped Ruff/Pyright passed, Dockerfile.render build passed. `.dockerignore` now also excludes npm cache. Linux container startup/shutdown/recovery and final current integrated build are pending; no runtime schema upgrade has occurred.

Keep compaction summaries short and distinguish independently observed checks from peer reports. No commits, pushes, deployment, provider writes or external account actions are authorized.
