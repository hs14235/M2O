# Public and private user lifecycle acceptance

Finishing scope approved by Hamza on October 4, 2026: isolated synthetic visitors, invited private onboarding, access expiry, recovery, and data handling. This is local implementation and verification. Deployment, provider writes, emailed invitations and other external communication require separate authorization.

## Journeys and acceptance gates

| Journey | Required observable behavior | Failure and integrity checks |
| --- | --- | --- |
| Start a public demo | A new visitor receives a private-to-that-visitor synthetic workspace and a bounded session. Department examples work without a shared password. | Two visitors cannot read or modify each other's workspace, meetings, people, plans, jobs or receipts. Global private mode does not elevate visitors. |
| Use the demo | Only trusted synthetic material is accepted. Server-enforced mutation/job quotas and admission capacity bound resource use. | Arbitrary transcripts, API-token creation, invitations, private workspace creation, OAuth, live publishing and operator destination metadata are denied. Cookies and any supported bearer path enforce the same authority. |
| Expire a demo | The UI explains expiry and offers a fresh isolated demo. Server expiry applies to both account and workspace. | Old sessions and tokens cannot regain access; queued work cannot act after expiry. Cleanup does not delete another visitor or a private workspace. |
| Invite a private collaborator | An authorized owner generates a scoped, expiring, single-use invitation with an explicit role. The owner shares it outside M2O. | Viewers/editors and visitors cannot issue invitations. Invalid, expired, revoked and consumed invitations fail. Concurrent acceptance cannot create multiple grants. |
| Accept an invitation | A new user can create an account from a valid invitation. An existing user signs in as the invited account before accepting. | Knowing an invitation token cannot reset an existing user's password or replace their account. Email, role and workspace are bound to the stored invitation. |
| Recover an account | An operator can create a short-lived account-bound recovery token using the local administration tool. The user consumes it once to change their own password. | No open registration or public recovery-token issuance; no email enumeration. Expired, reused and racing requests fail. Successful reset invalidates existing sessions/tokens and obsolete recovery links. No reset of unrelated users. |
| Export private workspace data | An authorized user receives only the data their role and scope allow, with source/review/progress/receipt provenance. | No password hashes, session/API tokens, OAuth state, encrypted grants, signing keys or other workspaces. Responses are not cached. |
| Erase data | An authorized owner explicitly confirms the target. Private content and connections are removed according to the documented policy. | Active operations are settled or blocked before erasure. Unknown provider effects retain only the minimum reconciliation tombstone; erasure must not authorize a resend or conceal an uncertain write. Other workspaces and shared accounts remain intact. |
| Operate retention | Expired synthetic workspaces and stale admission/auth records can be cleaned through a documented, bounded local operation. | Cleanup respects transactions, active work and exact targets; it is not a production database reset. Retention duration and operator responsibility are visible. |

## Ownership

- Phase 3 owns lifecycle models, additive migrations, HTTP/service authority, worker expiry, local administration tools and implementation tests.
- Phase 5 owns visitor/private entry, invite/recovery forms, expiry messages, administration and privacy screens, component and browser checks.
- Phase 4 checks provider credentials, destination metadata and durable receipt boundaries against lifecycle operations.
- The coordinator independently reviews and verifies the combined lifecycle, records observed results here, and checks the final local handoff.

## Verification record

Implementation is in progress. The coordinator's current independent HTTP acceptance increment passed seven tests against isolated PostgreSQL schemas (12.91 seconds):

```powershell
# From backend
.venv/Scripts/python.exe -m pytest -q tests/test_lifecycle_acceptance.py --postgres
```

Observed: two visitor identities have disjoint department workspaces; cross-visitor/private access fails; arbitrary text and private workspace creation are denied even when global demo mode is disabled; operator repository names are suppressed; expired sessions and queued jobs lose authority. A real API/worker journey also loads a fixture, extracts outcomes, approves an action, completes its personal plan and exports its exact reviewed JSON. Personal completion preserves approval/version; a stale export is rejected. Invitation, recovery, privacy, browser and combined acceptance gates remain pending. This is not a final release test report. Prior provider or frontend test counts do not satisfy those remaining gates.

The fifth HTTP regression confirms a token scoped to one workspace cannot inspect or erase another workspace owned by the same user. The target remains unchanged.

The two added private journeys use real HTTP and PostgreSQL: an owner issues an invitation, the recipient chooses credentials and explicitly signs in, exports their own account, resets through an operator-issued synthetic recovery link, loses the old session, cannot reuse the link, and anonymizes their own account without affecting the owner. Another journey indexes/extracts a private synthetic transcript through the worker, exports the workspace and erases its exact confirmed name/version while preserving the unrelated workspace. These passed; they do not replace browser acceptance.

Phase 5 reported four selected real-API visitor browser cases passing across a one-case run and a corrected three-case run. Observed journeys cover all departments, explicit participant confirmation, reviewed local export, saved personal progress, two-browser isolation, custom-upload denial, an empty no-action case, reduced motion, actual clip playback/loop/pause, and bubble layout/keyboard checks at the tested desktop/mobile widths. Real synthetic captures are saved in `docs/media/`; the coordinator inspected engineering review and People Operations daily-plan captures. This does not satisfy the private invitation/recovery/privacy browser gates.

The isolated browser runtime helper also passed a native Windows startup/readiness/shutdown smoke with real PostgreSQL and spawned API/worker processes. The longer visitor browser instance subsequently stopped cleanly and removed its own schema/credential fixture. This does not establish Linux container or hosted Render behavior.

## Usage-limit checkpoint — October 5

Phase 3's turn stopped at the account usage limit. Invitation/recovery/privacy models, migration, routes, services and tests are saved, but the final backend lifecycle acceptance and stable frontend handoff are unfinished. Phase 4 completed its current provider safety increment. Phase 5 completed visitor browser verification and is awaiting approval for its next command; private lifecycle UI is still dependent on the backend handoff.

The README now has a short Docker path, architecture, provider boundaries, actual screenshots and original video links; advanced commands moved to `LOCAL_DEVELOPMENT.md`. `USER_LIFECYCLE.md` is still pending from the backend phase, so its README link must be resolved before the final documentation check. The coordinator's Phase 6 responsibility is integrated acceptance and the local handoff, not new feature expansion or deployment. No shared runtime upgrade, provider write, commit, push or deployment occurred.

### Resumed verification — October 5

The backend lifecycle runbook `USER_LIFECYCLE.md` now exists and the README link resolves. Phase 3 reported 41 focused PostgreSQL checks, then corrected broader SQLite transaction/fixture issues and reported 327 native backend passes with 22 PostgreSQL-only skips. Its final full PostgreSQL suite is running. Phase 4's current six-file provider suite passed 135 PostgreSQL tests, including the actual consent/erasure adapter paths with controlled provider responses. A final own-grant disconnect permission correction is being checked separately. Phase 5 reported 77 frontend tests across 21 files, TypeScript and the production build passing.

A fresh isolated browser instance served the compiled frontend with real API/worker/PostgreSQL. Its dedicated synthetic recovery recipient avoided resetting the owner used by invitation/erasure cases. The four private browser cases and refreshed public captures were pending at this checkpoint. The final browser results below supersede that state.

### Actual local installation refresh — October 5

The previous interrupted refresh had not run. A corrected import-path precheck verified zero queued/running external-delivery jobs before any mutation. The existing local database was backed up to ignored `.runtime/backups`; API, worker and frontend were rebuilt, and Compose's migration dependency upgraded the existing volume from `20261003_04` to `20261004_10`. Private environment files and the database volume were preserved. Docker frontend type checking/build passed (59 modules); API/database health and web/worker running state were observed.

A real container smoke through `http://localhost:8080` passed: start an isolated People Operations demo, index/extract through the container worker, confirm synthetic participant matches, approve an action, complete its personal plan and export exact reviewed JSON. Five synthetic outcomes were returned; personal completion preserved approval/version. `/healthz` returned schema `20261004_10`. This establishes the refreshed local Compose path, not Render deployment or live provider delivery.

### Broader product boundary

The selected finishing scope is user lifecycle, its interface, documentation and local verification. LinkedIn's own-profile interface and draft/publishing backend are implemented, but `ShareStep` still directs LinkedIn selections to Connections: a dedicated post/outreach draft and publishing composer is not integrated. Do not describe the complete four-provider graphical delivery journey as finished. Live provider activation, Render deployment, representative model evaluation and hosted persistence/restore checks also remain separate gates.

### Final browser and packaging results — October 5

Phase 5 observed all four private-user browser cases passing in 18.3 seconds on fresh fixture B: new recipient activation/export/account erasure, existing recipient acceptance without password replacement, recovery/session revocation/replay rejection, and private transcript indexing/worker/export/confirmed workspace erasure. No provider mocks were used for those lifecycle cases; private recordings were disabled. All four public visitor cases passed in 51.6 seconds. All four staged workflow cases were verified across three initial passes and one corrected guided retry (41.7-second run); provider-facing UI responses in that suite are controlled synthetic responses, not live deliveries.

Ten public synthetic screenshots in `docs/media/` were refreshed October 5 and inspected. The current interface had a 77-test full frontend pass before the final visibility-key correction; its 13 affected tests, TypeScript and production build passed after the correction. Do not invent a fresh 79-test run.

Actual Docker asset inspection caught a packaging defect not present in the native test instance: `frontend/Dockerfile` omitted `public/`, and Nginx returned HTML for missing scene URLs. Phase 5 added the public directory copy and a `/scenes/` missing-file 404 rule. The coordinator rebuilt only the web service; Docker type checking/build passed. All three MP4 files and three WebP posters served from port 8080 now match their source SHA-256 bytes and expected MIME types; a nonexistent clip returns 404. The targeted actual-container browser check also passed (10.7-second run): authored playback/loop under CSP, pause preservation across department changes, and responsive/keyboard tools at the tested widths. No backend or database change was needed for that asset correction.

## Selected finishing milestone closed — October 5

Isolated visitors, invited private onboarding, expiry/revocation, operator-assisted recovery, scoped export/confirmed local erasure, retention safeguards, their frontend flows, README/setup documentation and current local Compose verification are implemented and locally verified. The temporary browser runtime exited cleanly and removed its own schema/credential fixture; the port-8080 app remains ready on schema `20261004_10`. The coordinator rechecked README local document/media references and whitespace on owned changes. No commits, pushes, PRs, deployment, provider writes or email delivery were performed.

This closes the lifecycle/README milestone requested by Hamza, not the broader release gates listed above. It does not turn unsupported LinkedIn lead messaging, a pending graphical publishing composer, undeployed Render configuration or unmeasured production/model behavior into completed functionality.

## Hosting boundary

The public Render runtime is a synthetic-only demonstration. Invited private onboarding is implemented for a separately configured private installation; it must not be advertised as durable hosted private use until persistence, backups, restore, origin, secure-cookie and provider callback checks have passed. Creating an invitation in the local application does not send it to anyone.

## Security references

Reviewed October 4, 2026: [OWASP password recovery](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) and [session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html). Recovery identifiers must be random, account-bound, expiring and single use; password reset invalidates existing sessions and outstanding recovery links. The current scope uses operator-assisted recovery and human-shared links, with no email transport or automatic sign-in after recovery.
