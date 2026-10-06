# Phase 3: Slack delivery and authorized meeting actions

Date: October 3, 2026, America/New_York.

Status: source-grounded implementation plan. This planning pass changes only this document. It does not implement Slack, change credentials or account settings, run provider writes, or establish deployment availability. Shared implementation changes require ownership assignment by the coordinating chat.

## Product and acceptance boundary

Deliver selected, currently approved meeting outcomes into an explicitly verified Slack channel; update a previous M2O message through a separately reviewed preview; let a linked, authorized Slack user capture a meeting or act on their own daily plan. Keep transcript/review authority, delivery status, and personal progress separate.

This phase implements the Slack portion of [M2O_IMPLEMENTATION_CONTRACT.md](M2O_IMPLEMENTATION_CONTRACT.md), including its numbered priority gates. It preserves the current modular FastAPI/API-worker/PostgreSQL structure and the agreed state ownership policy. It does not require an SSR migration or change local inference.

All department journeys use the same backend rules:

| Department | Useful delivery | Useful interaction | Privacy boundary |
| --- | --- | --- | --- |
| People Operations | Reviewed onboarding responsibilities and dates | Add an onboarding action to my plan; capture coordination notes | Exclude raw personnel evidence by default; explicit disclosure before any channel share. |
| Finance Control | Reviewed reconciliation follow-ups and control blockers | Record personal blocked/in-progress state; capture a follow-up meeting | No automatic disclosure of balances, account identifiers, or transcript quotations. |
| Engineering | Reviewed decisions, blockers and implementation actions | Add an action to my plan; update a prior handoff after review | No implicit GitHub/Jira status transition or account assignment. |

Permission to share a reviewed outcome is not permission to disclose all transcript evidence. Restricted meetings remain restricted inside M2O. Sharing their selected contents to Slack crosses that boundary and requires a destination-specific warning and explicit confirmation.

## Verified starting point

| Source | Observed behavior | Consequence |
| --- | --- | --- |
| `integrations/slack/manifest.json` | Bot scope `chat:write`; no slash commands or interactive endpoints; HTTP mode; token rotation disabled. | Manifest preparation exists. No interaction configuration or adapter is implemented. |
| `backend/app/settings.py` | Jira and LinkedIn settings; no Slack settings. | Add narrowly scoped private Slack configuration; never return credentials to the browser. |
| `backend/app/services/delivery.py` | Slack is `unavailable`, with preview/publish disabled. | Keep this truthful until implementation and configuration gates pass. |
| `backend/app/models.py` | Generic provider connection/destination/OAuth-state tables exist. Connection expiry is non-null; destination uses Jira-oriented project fields. | Do not fabricate Slack expiration or silently overload Jira fields. Coordinate an additive schema extension. |
| `backend/app/services/jira_delivery.py` | Stored exact preview/hash, owner-bound destination, revision checks, expiring approval and operation/job deduplication. | Reuse these product invariants, while retaining Slack-specific protocol and authorization rules. |
| `backend/app/worker.py` | Durable Jira write intent, lease recovery, uncertainty classification, no automatic resend. | Add a separate Slack job branch with the same external-effect discipline. |
| `backend/app/services/planning.py` | Personal entries are user-owned; current approved source and expected entry/item versions are required. | Slack personal actions must invoke this service as the mapped user rather than edit records independently. |
| `backend/app/auth.py` | Browser mutations require session, CSRF and exact origin; workspace role lookup is explicit. | Browser APIs retain these checks. Slack inbound requests need a separate signature boundary and must not impersonate a browser session. |
| `frontend/src/types.ts` | Basic integration catalog exposes preview/publish booleans, without separate action or update capabilities. | Add optional capabilities compatibly; do not treat one boolean as evidence that all Slack features work. |

Hamza reports an installed M2O app in M2O Sandbox, invited to `#m2o-demo`, and supplied its channel ID. That is account-setup context, not an API-verified channel, credential validation, successful delivery, or live callback test. No secret files were read in this planning pass.

Current upstream protocol facts:

- Sending uses `POST chat.postMessage`; updating uses `POST chat.update`, requires `chat:write`, and is limited to messages authored by the authenticated identity. M2O will further restrict updates to its stored bot receipts. Do not issue PUT to Slack simply because the operation is an update. [Slack send reference](https://docs.slack.dev/reference/methods/chat.postMessage/), [Slack update reference](https://docs.slack.dev/reference/methods/chat.update/).
- Destination metadata can be read with `conversations.info`, using scopes appropriate to the conversation type. [Conversation metadata](https://docs.slack.dev/reference/methods/conversations.info/).
- Slack Web API success is an explicitly validated `ok: true` response; HTTP 200 alone does not establish success. Internal/fatal errors can follow partial effects. [Send response and errors](https://docs.slack.dev/reference/methods/chat.postMessage/).
- Non-rotating Slack tokens have no expiry; rotating tokens expire and require persistence of each replacement refresh token. Enabling rotation is irreversible in Slack settings, so that account change requires separate human authorization. [Token rotation](https://docs.slack.dev/authentication/using-token-rotation/).

## Implementation milestones and shared dependencies

| Increment | Concrete result | Dependency / acceptance gate |
| --- | --- | --- |
| 3A Connection | Session-bound OAuth, encrypted bot credential, validated installation identity and verified channel | Shared schema/settings/routes integration and synthetic OAuth/revocation tests. |
| 3B Delivery | Exact selected-outcome create/update previews, approved jobs, durable receipts and read-only reconciliation | 3A; stale/duplicate/uncertain/concurrent cases pass with real PostgreSQL. |
| 3C Identity and inbound boundary | Browser-confirmed Slack identity mapping, raw-body signature validation, durable replay protection | Registered signed callbacks and measured acknowledgment path; no external account changes in this planning pass. |
| 3D Actions | Meeting-capture command/shortcut/modal and personal-plan controls | 3C plus current domain authorization/version checks; deployed reliability remains separately gated. |

Each increment has an independent readiness state. A connected bot is not an action-capable deployment. Delivery can work during a user-driven browser session even when a sleeping hosted service cannot reliably receive immediate Slack interactions.

## Recommended connection and data model

Recommended release scope: one Slack installation per connecting M2O owner and one selected Slack channel per owner/workspace binding. Members may separately link their own Slack identity for personal actions without receiving the owner's bot credential or publishing authority. Multiple channel bindings, installation-owner transfer, Enterprise Grid org-wide installs, GovSlack, Slack Connect/shared channels and direct-message destinations require their own authorization and tests; unsupported types receive a clear reason rather than being treated as ordinary channels.

Use existing `ProviderConnection`, `ProviderDestination` and `IntegrationOAuthState` for their shared responsibilities. Add Slack-specific extensions instead of renaming fields used by Jira:

| Record | Required shape and integrity |
| --- | --- |
| Connection expiry | Make `ProviderConnection.expires_at` nullable to represent a non-expiring token accurately; Jira still requires a real expiry and explicit guards. Review all callers and regression tests. No artificial far-future dates. |
| Slack account detail | Connection FK; validated app/team/bot identity; installing Slack user ID; token kind/rotation mode. Reject ambiguous duplicate active installations for the same app/team in this release instead of overwriting another owner's credentials. |
| Slack destination detail | Existing destination FK; bounded channel ID/name; conversation kind; verification time and bot membership. Preserve explicit `ProviderDestination.version`; no channel-name-only authorization. |
| Slack proposal | Workspace/meeting composite FK; actor; action; immutable destination snapshot and ordered outcome snapshots; exact request payload/hash; expiry and approved timestamp. |
| Slack operation | Proposal FK; unique delivery key; constrained `queued`, `sending`, `completed`, `failed`, `uncertain` state; safe result; intent/result timestamps. Preserve earlier attempts in job/audit history. |
| Slack user mapping | Workspace/user membership FK; installation/team and Slack user identity; confirmed/revoked state; monotonic version. Unique active mapping of a Slack identity within an M2O workspace. Mapping does not grant a role. |
| Link challenge | Hashed random challenge; browser session, workspace and user binding; intended installation; short expiry; pending Slack identity; consumed/confirmed timestamps. Return the challenge only to the initiating browser. |
| Interaction context | Opaque reference bound to installation/workspace/action/source versions; per-user modal contexts also bind mapped user and expected personal-plan version; expiry/consumption. No credential or transcript in button values. |
| Inbound receipt | Unique authenticated request fingerprint; minimal app/team/user/action metadata; safe acknowledgment; accepted/result timestamps. Persist only the minimum needed payload; encrypt any short-lived capability retained for a follow-up. |

Use composite scope constraints and indexes for workspace/meeting lookup, active mapping lookup, challenge expiry and operation history. Keep proposal/job/approval in one transaction and logical action/result/audit in one transaction. Global in-memory replay or rate-limit state alone is insufficient when API processes restart.

Parent-owned migration must extend the job-kind constraint for Slack and add the required tables/expiry change. Review generated SQL and lock impact, retain existing migrations, run upgrade against disposable PostgreSQL with existing Jira records, verify Alembic model agreement and rerun affected Jira tests. Do not apply it to a shared or deployed database in this planning pass.

## Proposed browser API contract

All workspace paths below are relative to `/api/workspaces/{workspace_id}`. Require browser session, CSRF/origin validation, active membership and runtime-validated bodies. Provider destinations and identities are loaded server-side; request parameters never choose arbitrary upstream hosts.

| Method/path | Request / response responsibility |
| --- | --- |
| POST `/integrations/slack/connect` | Owner-only; session-bound one-use OAuth state; return official authorization URL. Demo users cannot acquire private publisher credentials. |
| GET `/api/integrations/slack/callback` | Global callback, outside workspace prefix; validate code/state/current session and membership; fixed-host code exchange; validate returned team/app/bot/scopes; encrypt credential. Redirect only to a fixed M2O page. |
| GET `/integrations/slack` | Sanitized connection, destination, configured/reauthorization state and action/delivery capabilities. |
| POST `/integrations/slack/destination` | `channel_id`, strict `expected_version`; verify channel, team, bot membership and supported type through provider reads; version the binding. No auto-join. |
| DELETE `/integrations/slack` | Explicit local workspace disconnect; invalidate binding/contexts/queued authority. Distinguish this from external Slack uninstall or token revocation. |
| POST `/meetings/{meeting_id}/slack/preview` | Create/update input described below. Store exact preview; return hash, source/destination snapshots, expiry and safe rendered content. |
| POST `/slack/proposals/{proposal_id}/approve` | Exact `payload_hash`, strict `retry_rejected` default false; verify actor/current source/current binding/expiry and atomically create or reuse operation/job. |
| GET `/slack/operations/{operation_id}` | Acting publisher and meeting/workspace access required; return stored proposal and safe receipt. |
| GET `/meetings/{meeting_id}/slack/deliveries` | Bounded latest history belonging to the acting publisher; record action and message target. |
| POST `/slack/operations/{operation_id}/reconcile` | Strict candidate message timestamp for uncertain create, known target for update; fixed allowed channel read; compare exact M2O marker and identity; no resend. |
| POST `/integrations/slack/link-challenges` | Signed-in eligible member creates a short-lived challenge for the intended workspace/installation. |
| GET `/integrations/slack/link-challenges/{challenge_id}` | Initiating browser reads pending identity and expiry; another user/workspace receives 404. |
| POST `/integrations/slack/link-challenges/{challenge_id}/confirm` | Initiating browser explicitly confirms the signed Slack identity; activate mapping atomically. |
| DELETE `/integrations/slack/my-link` | Revoke acting user's mapping and outstanding personal-action contexts. |

Preview input:

```text
action: create | update
expected_revision: positive strict integer
versions: non-empty bounded map of outcome UUID -> positive strict integer
expected_destination_version: positive strict integer
include_evidence: strict boolean, default false
confirm_restricted_share: strict boolean, default false
target_operation_id: completed Slack operation UUID, required only for update
```

Limit a preview to 10 outcomes and one message initially. Reject excessive provider text/block lengths with a useful error; do not silently truncate reviewed content, split it into independently sent messages, or invent missing ownership. Current documented limits include 50 blocks per message, 100 per modal/Home tab, 3000 characters per section text object and 150 characters per header. Keep top-level text within M2O's explicit 4000-character budget and build a complete readable fallback for the chosen bounded message. Fresh message iterations require distinct block identifiers. Never expose caller-supplied arbitrary `blocks`, `channel`, mention syntax, webhook URL, bot identity or callback metadata as trusted request fields. [Block count limits](https://docs.slack.dev/reference/block-kit/blocks/), [Sections](https://docs.slack.dev/reference/block-kit/blocks/section-block/), [Headers](https://docs.slack.dev/reference/block-kit/blocks/header-block/).

Stored response shapes, subject to parent contract review:

```text
Proposal:
  id, action, payload_hash, expires_at, approved
  destination: id, connection_id, version, team_id, channel_id, channel_name
  snapshots: ordered list of item_id, version, revision_id
  target: null OR operation_id, channel_id, message_ts, observed_content_hash
  payload: exact provider request fields (text, blocks and explicit delivery options)

Operation receipt:
  operation_id, proposal_id, action
  state: queued | sending | completed | failed | uncertain
  result: null OR status, channel_id, message_ts, permalink?, safe_error?, retry_after?
  proposal: stored source/destination/hash/expiry snapshot where authorized
```

The earlier cross-chat draft used `id` for an operation. The recommended contract uses `operation_id` to match existing Jira receipt routes and avoid needless UI divergence; communicate this refinement before implementation. The generic catalog remains backward compatible. Slack's provider detail adds `can_create`, `can_update`, `can_reconcile`, `can_link`, `can_capture_meeting`, `can_change_my_plan`, `delivery_reasons` and `interaction_reasons`. Each operation also returns server-derived `can_reconcile` and `can_retry_rejected`; these depend on its actual state, current scope/grant and retained evidence, not just installation-level permissions. Default missing optional capabilities to false. The common frontend presentation adapter normalizes provider-native receipt shapes without changing existing Jira/GitHub storage or inventing a reconciliation capability for another provider.

Capability reasons must distinguish missing application configuration, missing connection, missing scopes, unverified destination, unsupported channel, demo authority, insufficient role, reauthorization required, unlinked user and unverified interaction availability. A credential's presence does not establish that Slack currently accepts it.

## Exact delivery and update behavior

1. Read and lock current meeting scope/source, selected approved outcomes, publisher authority and current destination. Include versions and opt-in disclosure choices in a canonical hash.
2. Build bounded plain-text/Block Kit content from reviewed fields, with a readable top-level accessibility fallback. Use plain-text nodes for user text; escape any intentional formatting. Disable link/media unfurls and uncontrolled mention parsing. A participant name is not a Slack user mention without separate explicit confirmation.
3. Show the exact channel, create/update action, selected content, evidence disclosure and update target before approval. Expire previews after 30 minutes; edits, destination changes, disconnection and transcript replacement invalidate them.
4. Approval deduplicates by workspace, verified installation/channel, ordered outcome/version set, action and update target. Identical approval returns the existing operation. Different content against an existing logical delivery requires explicit new-version review; an uncertain operation cannot be bypassed through a new preview.
5. Worker rechecks active publisher, membership, source, binding and lease; records durable write intent; then crosses the provider boundary once. No database lock ordering copied from Jira without reviewing Slack credential refresh behavior.
6. For update, require a completed M2O receipt from this workspace/installation/channel. Read the exact message, verify bot identity and prior M2O marker, and bind a canonical content hash into preview. Recheck before `chat.update`. A changed/missing message blocks the update. No arbitrary message timestamp supplied by the browser can establish ownership.
7. Slack does not provide an atomic compare-and-swap for this ordinary message update. A remote change can race after the read; disclose the overwrite/race limit. Changing a shared Slack message never changes anybody's personal plan.
8. Validate `ok: true`, expected channel and bounded timestamp. Store the provider receipt before any optional permalink read. Failure to obtain a permalink does not turn a confirmed send into a retryable failure. Validate any displayed permalink host/path; never fetch arbitrary provider-returned URLs.

M2O will embed a deterministic non-sensitive delivery marker in an authored context block, bound to the stored exact proposal. Validate that the marker survives real Slack serialization before claiming automatic reconciliation. It is correlation evidence, not a cryptographic guarantee of current message content or an exactly-once provider guarantee. Do not assume an undocumented `client_msg_id` behavior or message metadata support will provide idempotency.

Reconciliation reads only a user-specified candidate timestamp in the already allowed channel, not unrestricted workspace history. The read must validate exact timestamp, bot/app identity, marker and approved content representation. A missing/mismatched message remains uncertain; absence is not proof that a delayed create never happened. Preserve a separate operator investigation path after credential revocation or lost access.

Retrieve a single message with bounded `conversations.history` parameters and verify the returned timestamp. History access requires conversation-appropriate scopes. Internal customer-built apps retain different limits from commercially distributed non-Marketplace apps; do not assume the same quota for every installation. Read-only retries honor bounded provider `Retry-After` without blocking a request thread or polling entire history. [Single-message retrieval and distribution-dependent rates](https://docs.slack.dev/reference/methods/conversations.history/), [Rate limits](https://docs.slack.dev/apis/web-api/rate-limits/).

| Observed result | M2O classification | Next action |
| --- | --- | --- |
| Valid provider-confirmed success | `completed` | Display persistent receipt; personal progress remains unchanged. |
| Explicit known validation/auth/permission rejection | `failed`, `rejected` | Correct configuration/content; explicitly approve an identical current retry or create a newly reviewed version where allowed. |
| Confirmed 429 with valid delay | `failed`, `rejected`, safe retry delay | Honor delay; require explicit retry for a write in this increment. No hidden repeated send. |
| Timeout, transport loss, internal/fatal error, server failure, malformed success, unexpected redirect/status | `uncertain` | No automatic resend; verify receipt through reads. Unknown error classifications fail closed. |
| Worker recovered after intent or ownership of lease lost | `uncertain` | No second write. A late response cannot overwrite a newer recovery state. |
| Failure proven before provider write intent | `failed`, `not_sent` | Explain source/configuration issue; retry only after current approval checks. |

## Verified user mapping and signed inbound requests

Use two dedicated global POST endpoints: `/api/integrations/slack/commands` and `/api/integrations/slack/interactions`. They do not use browser cookies or CSRF dependencies. They authenticate the raw request through Slack's signing secret and then load the mapped M2O principal from persisted scope. Every internal action still checks active user, current membership/role and meeting visibility.

Inbound protocol:

1. Bound the raw body and accepted content type before parsing. Verify timestamp skew within five minutes, HMAC over Slack's exact raw body/version/timestamp, and constant-time signature equality. Reject malformed/duplicate headers and mismatched application/team identity. Never trust a posted verification token or username instead of signature verification. [Slack request verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/).
2. Parse only supported command/interaction types through strict bounded schemas. Treat text, button values, `private_metadata`, URLs and display names as untrusted. Limit and validate transcript modal content against existing meeting rules. Use persisted context references to recover workspace and versions.
3. Deduplicate the authenticated request durably; retries return the saved acknowledgment. Also deduplicate logical domain actions, so a second click or changed retry envelope cannot apply a state transition twice. Expiring signatures alone do not prevent replay inside the acceptance window.
4. Complete a small bounded database transaction and return an acknowledgment within three seconds. Database overload/unavailability must not return a misleading accepted acknowledgment for lost work. No AI extraction, embedding, provider-history scan or normal delivery write on the acknowledgment path.
5. Treat `response_url` as a short-lived bearer capability. Prefer an immediate ephemeral acknowledgment or existing fixed-host bot method for follow-ups. If retaining a response URL becomes necessary, encrypt it, expire it, redact it and validate Slack's supported exact host/path rules; never send to a caller-chosen arbitrary URL. [Slack interaction responses](https://docs.slack.dev/interactivity/handling-user-interaction/).

Mapping ceremony:

- Signed-in M2O member creates a random, hashed, five-minute link challenge tied to their current browser session, user, workspace and selected installation.
- Member invokes `/m2o link <challenge>` from Slack. A valid signed request records the pending Slack team/user identity, once; it does not immediately activate a mapping.
- The initiating M2O browser shows that pending identity and requires explicit confirmation. Do not match by transcript name, email string, Slack display name or directory similarity. Consume and bind the challenge atomically.
- Reject expired/session-replaced challenges, identity collisions and challenges from another installation. Unlink, workspace removal, disabled user, installation disconnect and role changes revoke the relevant authority.
- For a user linked to several M2O workspaces, select an explicit authorized workspace. Do not default to the first membership or infer workspace from channel naming.

Use installation OAuth's verified `authed_user.id` only as that consenting installer's identity. It does not identify all channel members or authorize actions on their behalf. User mapping remains separate from confirmed meeting participant context.

## Meeting, modal and personal-plan actions

| Surface | Action | Authorization and result |
| --- | --- | --- |
| `/m2o help` | Show concise supported actions and connection guidance | No private meeting/plan data; ephemeral acknowledgment. |
| `/m2o link` | Record pending browser-issued identity challenge | Signed identity and challenge ceremony above; no role escalation. |
| `/m2o meeting` or global Capture meeting shortcut | Open title/transcript/date/timezone capture modal | Linked active owner/reviewer/editor; explicit authorized workspace and restricted visibility by default. Persist through `MeetingService.index` only after submission. |
| Message shortcut Capture meeting context | Prefill editable notes from the selected visible message | Explicit user opt-in; message text is not a complete meeting transcript; no automatic history import or extraction claim. |
| Delivered action button Add to my plan | Open personal confirmation modal for planned date/priority | Current approved action/follow-up, meeting access and mapped owner/reviewer/editor; invoke `PlanningService.add` as that user. |
| `/m2o plan` | Show acting user's selected-day plan privately | Linked current workspace member; bounded results, no another-user plan access. |
| Personal plan controls | Start, block or complete my own entry | Per-user context includes expected entry/item/review versions; invoke `PlanningService.patch`. Duplicate submission returns previous result. |
| Open in M2O | Navigate to meeting review/plan | Fixed application-origin link; login and authorization still apply. No capability-bearing secret in URL. |

Capture does not automatically approve outcomes or deliver them. New transcript indexing/extraction uses existing jobs, review and participant confirmation. Finance/HR content remains user-authored and access-controlled. Slack modal limitations may require longer transcripts to continue in M2O; explain the limit rather than silently truncate input.

Opening a modal requires spending a single-use trigger before its three-second expiry. It cannot sit in the ordinary job queue. Use a separately bounded immediate modal-open path with no inference/history work; record an intent to prevent duplicate trigger exchange, cap the upstream timeout and test the total ingress-to-modal latency. If this path cannot meet its deadline, acknowledge with a safe M2O link and truthful failure feedback. Modal submissions can acknowledge valid input or return bounded validation errors, then persist/enqueue authorized work. [Trigger lifetime and interaction timing](https://docs.slack.dev/interactivity/handling-user-interaction/), [Modal opening](https://docs.slack.dev/reference/methods/views.open/), [Slash commands](https://docs.slack.dev/interactivity/implementing-slash-commands/).

Do not change the shared channel message to show one user's personal completion; other members have independent plans. Personal action confirmation must be ephemeral or private to the mapped user. No reaction-based completion, implicit external status synchronization, external issue reassignment or delivery approval from an unlinked Slack click.

## Configuration and hosting gates

Recommended public-channel scope set for the complete 3A-3D increment: `chat:write`, `channels:read`, `channels:history`, `commands`. Private-channel support adds `groups:read` and `groups:history` only when explicitly selected, documented and tested. No `chat:write.public`, auto-join, user-email read, user impersonation, unrestricted history import or reaction/event subscriptions are needed for these initial actions. Review manifest schema and exact scope grants during implementation; changed scopes require reinstall/consent in the human-owned Slack app.

Private configuration includes Slack client ID, client secret and signing secret, plus the existing provider encryption key. OAuth callback derives from the configured real application origin. Inbound commands/interactions require an actual Slack-reachable HTTPS endpoint; an OAuth browser callback on localhost does not make the local API reachable by Slack. Do not invent a Render domain or expose local transcripts through an unapproved tunnel.

Configuration ownership remains human: create/update app settings, accept grants, install/reinstall and register actual callbacks only after explicit authorization. This phase prepares the adapter, helper and local validation; a successful live synthetic send/update/action needs separately authorized tests to the identified sandbox/channel.

Render Free currently sleeps idle web services and may take about a minute to wake; it offers no free standalone worker and no persistent disk, and its free PostgreSQL is time-limited. Therefore the requested free hosted budget does not support a reliable claim of always-on Slack interactions. Keep outbound delivery enabled only in a verified runtime, and show an independent interaction capability reason. [Render Free limits](https://render.com/docs/free).

Recommended free-demo behavior: browser-led wakeup and reviewed outbound delivery, plus honest interaction availability messaging. Demonstrate signed commands/modals on an explicitly authorized reachable local/test environment, or later choose an authorized always-on ingress/runtime. A future independent ingress must durably hand off authenticated work and preserve domain authorization; merely returning 200 at the edge does not process or save the action. Socket Mode still needs an awake process and does not remove this deployment constraint. No keepalive workaround or paid infrastructure is assumed.

## Narrow file ownership and parallel coordination

This chat owns only `docs/PHASE_3_SLACK_PLAN.md` in the current parallel planning pass. No implementation, manifest, environment, dependency, lockfile, migration or shared documentation files are changed here.

Suggested exclusive Slack implementation files after coordinator assignment:

- `backend/app/slack.py`: fixed-host OAuth/account protocol and sanitized connection/destination discovery.
- `backend/app/slack_delivery.py`: message construction, message reads, post/update protocol and error classification.
- `backend/app/slack_interactions.py`: signatures, bounded ingress schemas and modal protocol.
- `backend/app/services/slack_delivery.py`: exact preview/approval/receipt/reconciliation product rules.
- `backend/app/services/slack_actions.py`: mapping/context/replay rules and authorized calls into existing meeting/planning services.
- `backend/tests/test_slack.py`, `test_slack_delivery.py`, `test_slack_interactions.py`: synthetic transport and real database coverage.
- `scripts/configure_slack.py`: secret-safe local setup modeled on the existing Jira helper, preserving unrelated entries and encryption key.
- `frontend/src/components/SlackConnection.tsx`, `SlackPublisher.tsx` and focused component tests: assign to one frontend implementer after Phase 5 agrees presentation and accessibility boundaries.

Coordinator-owned edits require one writer at a time: `models.py`, `schemas.py`, `settings.py`, `main.py`, `worker.py`, catalog service, migrations, environment examples, Compose/runtime wiring, `frontend/src/types.ts`, common API/Share/Integrations/job UI, shared CSS/E2E files and README/API/operations/validation documentation. Prefer new modular routers over expanding a single route file where this can be done without unrelated refactoring; parent decides registration ownership.

Phase 4 owns GitHub/LinkedIn planning. Phase 5 owns experience/release planning. They received the initial proposal/receipt shapes and action constraints. Publish refinements through the coordinator rather than simultaneously editing common contracts. Do not claim UI readiness, provider sends or migrations completed from these plan documents.

## Verification plan and release evidence

| Layer | Required cases |
| --- | --- |
| Protocol unit tests | HMAC raw bytes, timestamp bounds, constant-time comparison boundary; malformed/missing headers, encoding/form/JSON bounds; Block Kit length/plain-text handling; mention/unfurl behavior; known rejection versus internal/fatal/unknown errors; safe permalink validation. |
| OAuth/account integration | Current session/state/role/demo checks; wrong team/app/bot and insufficient scopes; consumed/expired state; credential AAD isolation; non-expiring versus rotating tokens; refresh concurrency; disconnect/revocation invalidates current authority. |
| PostgreSQL delivery integration | Atomic preview/approval/job; duplicate concurrent approval; changed transcript/item/binding; rejected retry; timeout/5xx/malformed success uncertainty; crash after intent; recovered lease; no write after role revocation; read-only reconciliation; no provider update of arbitrary message; changed remote message blocks update. |
| PostgreSQL mapping/action integration | Challenge browser/session/team/workspace identity, replay and collisions; mapping removal; cross-workspace and restricted-meeting denial; only acting user's plan; stale plan/item version; two clicks/submissions apply once; audit/result transaction; capture creates ordinary indexed meeting without automatic review or send. |
| Ingress reliability | Authenticated request ack under three seconds in warm measured environment; duplicate request returns saved ack; slow/unavailable DB not falsely accepted; modal trigger exchange deadline and duplicate prevention; bounded acknowledgment under worker/inference load. |
| Frontend | Unconfigured/connected/missing-scope states; evidence disclosure off by default; explicit restricted share; exact action/channel/target preview; expiry/edit/unmount invalidation; approve disabled while pending; persistent receipt/history; rejected retry versus uncertain reconcile; personal action feedback; readable mobile and keyboard paths. |
| End-to-end | Synthetic HR/Finance/Engineering review -> channel preview -> queued delivery -> receipt; previous message -> explicit update -> receipt; linked editor -> capture modal -> transcript/index -> normal review; mapped user's plan transition leaves shared outcome and external issue state unchanged. |
| Regression | Existing Jira/GitHub/review/planning/authentication suites, typed frontend/backend checks, targeted lint/build, migration upgrade/model agreement. Source-only mocks cannot establish real provider acceptance or deployed timing. |

Use fake Slack transport and synthetic fixtures; do not send test requests with operator credentials. Locally generated signed requests prove the M2O signature/action boundary, not Slack's live callback registration. Measure ingress acknowledgment and modal opening separately, including failure paths. Existing test totals are historical evidence for the earlier Jira phase, not a Slack result.

Phase 3 completion requires executed evidence for connection/delivery and actions, honest unsupported-scope/runtime limits, integrated accessible UI, documented recovery and no implicit synchronization. Live installation/consent, sandbox sends/updates/actions and hosted cold-start behavior remain explicitly labeled until separately authorized and observed.

## Implementation handoff

Start with parent agreement on the nullable connection expiry and additive Slack account/destination tables, plus final shared capability/receipt types. Then assign dedicated files for 3A-3B while Phase 5 prepares the focused presentation and Phase 4 continues its provider work. Implement 3C-3D after the connection and ownership boundaries pass focused tests. Preserve all existing dirty/untracked work and publish no commits or external effects without Hamza's permission.
