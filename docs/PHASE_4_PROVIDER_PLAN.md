# Phase 4: GitHub delivery alignment and LinkedIn capabilities

October 4 implementation update: this remains the historical planning baseline. Current provider behavior and limitations are in [GitHub delivery](GITHUB_DELIVERY.md), [LinkedIn drafts/publication](LINKEDIN_DELIVERY.md) and [provider review](PHASE_4_PROVIDER_REVIEW.md). Versioned GitHub workspace binding/receipts and separate LinkedIn drafts/consent/worker routes are now implemented and synthetically tested. Live activation and cross-phase release gates remain separate.

Prepared October 3, 2026 for the parallel Phase 3 Slack and Phase 5 experience planning pass. **Status: source-grounded plan, not an implementation or live activation report.** Only this document is owned by the Phase 4 planning chat. Shared implementation files remain unchanged by this pass.

Read with [the implementation contract](M2O_IMPLEMENTATION_CONTRACT.md), [integration inventory](INTEGRATIONS.md), [Jira delivery contract](JIRA_DELIVERY.md), and [validation history](VALIDATION.md). The coordinating chat assigns shared files and additive migrations before implementation starts.

## 1. Actual capability inventory

| Capability | Current source behavior | Evidence and limits |
| --- | --- | --- |
| GitHub preparation | Select current approved outcomes, generate issue title/body/labels/optional assignee, omit evidence by default, include a duplicate marker, store exact payloads and snapshots for 30 minutes. | `backend/app/services/issues.py`, `schemas.py`, `models.py`. Browser request supplies IDs, not expected outcome versions; the server snapshots the current versions. |
| GitHub authorization | Editors can prepare; owners/reviewers approve. Demo blocks publication. A backend operator token and global repository allow-list enable writes. | `settings.py`, `IssueService.approve`, `worker.publish`. This is not user OAuth, a GitHub App installation flow, or a per-workspace destination binding. |
| GitHub delivery | Persist operation/job; worker rechecks membership, meeting visibility and reviewed versions; persist write intent; bounded issue scan includes closed issues; ambiguous writes are not resent. | `github.py`, `worker.py`, `tests/test_publication.py`. External HTTP responses are synthetic in the existing test evidence. |
| GitHub receipts | Job results include per-issue status/URL; a POST reconciliation endpoint searches markers. | `main.py`, `Workbench.tsx`. No dedicated GitHub GET operation or per-meeting delivery-history route exists. Job state alone cannot describe a partially delivered batch. |
| GitHub presentation | Share defaults to local handoff, exposes GitHub after destination selection, displays exact JSON and hash, and invalidates changed/expired or late previews. | `Publisher.tsx`, `ShareStep.tsx`, `Publisher.test.tsx`. No GitHub update UI/API, persistent receipt history, connection selection or status synchronization is implemented. |
| LinkedIn account context | Session-bound, expiring, single-use state and nonce; RS256 signature, issuer, audience, expiry and subject checks; retain only subject and selected name fields. | `linkedin.py`, `LinkedInProfile`, `OAuthState`, `tests/test_linkedin.py`. Access/refresh/ID tokens and email are discarded. `identity_verified` is explicitly false. |
| LinkedIn configuration | OIDC scopes are restricted to `openid profile` with optional `email`. Connect/disconnect routes are personal account routes. | `settings.py`, `main.py`. Changing the scope setting to `w_member_social` currently fails validation and cannot enable posting. |
| LinkedIn presentation | Connections offers own-profile context, explicit disconnect, and explanatory setup text. Catalog entry has `purpose=context`, no delivery preview/publication. | `Integrations.tsx`, `services/delivery.py`, `types.ts`. No post/message drafting, posting adapter, publishable token, receipt or automatic participant mapping exists. |
| Provider storage groundwork | `ProviderConnection`, `ProviderDestination`, `IntegrationOAuthState`, and AES-GCM credential sealing exist for Jira. Provider names already include all four providers. | `models.py`, `provider_credentials.py`. Destination fields are currently Jira-oriented and the binding cardinality is one per workspace/connection. Generic names do not establish a working LinkedIn or GitHub adapter. |

Existing validation history reports 114 backend tests and 26 frontend tests after Jira delivery. Those checks were **not rerun in this documentation pass**. The inventory above is confirmed from current source; live provider credentials, grants and permissions were not inspected or exercised.

## 2. Common product and security invariants

Every provider must keep M2O review, provider delivery and personal execution separate. Sending an issue or post does not mark the daily plan done. Provider workflow state cannot approve a meeting revision.

The delivery sequence is: approved source versions → selected destination/action → editable preparation → stored exact preview → affirmative approval of that hash → persistent operation/job → provider result/receipt. A changed outcome, transcript, destination, author, visibility, evidence policy or prepared text requires another preview. Recheck current authority and credential/destination generation immediately before the HTTP write.

Preparation can be available without provider credentials. Publication must have truthful readiness and independently satisfy workspace role, meeting visibility, provider permission and account ownership. Workspace ownership does not authorize publishing as another person's LinkedIn account. Provider tokens, signed tokens and private account identifiers do not belong in browser payloads, logs or downloadable handoffs.

No shared rendering migration is proposed here. Focused URLs, readable previews, calm mode and stale-response protection work with the current client renderer. The rendering decision remains a separate documented decision.

## 3. GitHub implementation slices

### G1: Align the existing create journey and receipts

- Retain the existing preview/approve/reconcile routes and their response fields. Do not rename `Publisher`, `PublicationProposal`, `PublicationOperation`, or persisted job kind `publish` just for consistency with another adapter.
- Add read-only, workspace/meeting-authorized GET operation and per-meeting history routes. Return bounded receipt rows with issue position/outcome/version, result status, number and verified URL; do not return tokens, private credentials or internal exception text. Preserve partial batch results after reload.
- Present preparation, stored preview, approval and receipt as focused steps. Human-readable title/body/labels/assignees are primary; exact JSON and hash remain inspectable. Approval sends only the stored proposal ID/hash, never a regenerated payload.
- Use server capability data for allowed destinations. Distinguish a local preview from a repository enabled for publication. The placeholder example repository must never be described as a connected destination.
- Poll operation state only while pending; abort/read-sequence guard on meeting/workspace/destination changes. An approval whose response is lost can still be found in persistent history. A job marked completed with `operation.state=uncertain` must display uncertainty.
- Show each batch outcome's result. Created/existing are delivery successes; rejected is a confirmed refusal; uncertain needs investigation; an absent result means not attempted, not delivered. No global celebration may imply every selected issue succeeded.
- Keep existing input compatibility while adding a strict expected-version preparation contract for the new UI, preferably a provider-specific route/schema rather than making legacy clients silently incompatible. Specify and test how absent expectations in the retained route are handled before enabling private multiuser delivery.

### G2: Explicit workspace destinations and adapter hardening

Important before invited private workspaces: a global token/allow-list is an operator-controlled bridge shared across every workspace. Add an explicit workspace repository binding with an audited owner action and a generation/version. The global allow-list remains an outer operator limit; it is not sufficient workspace authorization by itself. Bind preview/approval/worker/reconciliation to the selected workspace destination. Show the verified destination's audience/visibility and require explicit external disclosure confirmation for a restricted meeting. Evidence opt-in alone does not authorize sharing the outcome body. Roll out with a migration/backfill plan; do not automatically bind every repository to every workspace.

GitHub Apps are a future credential mechanism when separate customer installations are required. A private, bounded demonstration can retain an operator-managed fine-grained token with restricted repositories while workspace bindings are enforced. GitHub documents Issues write permission for creation; publication can trigger notifications. [GitHub issue API](https://docs.github.com/en/rest/issues/issues#create-an-issue).

Source-confirmed hardening items to implement and test:

1. `GitHubAdapter.record` currently accepts any `https://github.com/` URL and any Python `int` issue number. Require a positive, non-boolean number and an HTTPS receipt matching the expected owner/repository/issue number. Require the documented create success status; malformed success remains uncertain.
2. `find_marker` rejects multiple matches on one page but returns the first matching page immediately. Duplicates on later pages are not detected. Either complete a bounded scan before establishing uniqueness or report a bounded matching receipt without claiming uniqueness. A scan limit/permission error cannot justify a new POST.
3. Distinguish permission rejection from actual rate limiting: current code labels every 403 as a rate limit. Respect safe provider retry metadata for reads; never automatically replay a potentially accepted write.
4. Bind stored payload integrity, proposal workspace/meeting, approval principal and destination generation at worker execution. Verify the hash from stored content. Add concurrent PostgreSQL approvals across distinct proposals of the same delivery intent; preserve one operation/job through a unique delivery key and serialized checks.
5. Introduce provider-specific bounded request/scan budgets. The existing scan can fetch up to 100 pages for each issue while holding the meeting lock. Preserve correctness first, then measure database lock duration, request count and rate-limit behavior before changing duplicate detection.
6. Define explicit retry only for a proven rejected write, with renewed validation and audit. Existing repeated approvals return the original operation and do not retry. Never provide a generic resend button for uncertain writes.

The current pinned GitHub API version remains supported according to the official version table; a version upgrade is not a prerequisite for this phase. [GitHub API versions](https://docs.github.com/en/rest/about-the-rest-api/api-versions).

GitHub issue update remains a separately scoped addition: verified existing issue identity, remote change detection, exact overwrite preview and PATCH semantics. Aligning the present create journey must not be represented as implementing update or workflow synchronization.

## 4. LinkedIn product and scope boundaries

| User-facing action | Required access | Planned behavior and current external dependency |
| --- | --- | --- |
| Connect my basic profile | Sign In with LinkedIn using OpenID Connect; `openid profile` | Preserve current minimal context flow. `email` is optional and unnecessary here. Human still confirms transcript participants. |
| Prepare a post or outreach draft | No LinkedIn API grant for local text preparation | User-selected approved outcomes → editable M2O draft → local copy/download. Label it as a draft; no recipient lookup or automatic send. |
| Publish a text post as me | Approved Share on LinkedIn product, actual `w_member_social` grant, current member-owned token and validated author | Separate publishing consent/storage; exact public text/author/visibility preview; explicit publication. Currently missing app/Page/policy/grant activation and implementation. |
| Read recent member posts for reconciliation | `r_member_social`, restricted approved access | Do not infer this grant from posting permission. Without usable reads, keep an uncertain write unresolved and prevent resend. |
| Publish as an organization | Appropriate organization grant and authenticated Page role | Not supported by the initial member-post adapter. Associating a Page to an app is not authority to post as it. |
| Send a LinkedIn message | Approved partner Messages API and applicable agreement | Not available through OIDC or ordinary posting consent. Local editable outreach drafts remain useful; API messaging is externally blocked and a separate implementation. |
| Enrich arbitrary transcript names | Applicable limited-access APIs and data/storage rights | Not supported. Retain user-supplied directory context, provenance, confirmed mappings and permitted profile links. No scraping workaround. |

OIDC supplies the consenting member's lite profile and explicitly is not identity verification. It provides no arbitrary participant career-history lookup. [LinkedIn OIDC](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2).

The self-service Share product grants `w_member_social`. Its older guide still shows `ugcPosts`; the current Posts API states that it replaces that API. Use the current documented text-post contract and a supported pinned version, then verify actual app eligibility when activation becomes possible. Do not claim an approved product or successful live call from the documentation alone. [Share product](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin), [current Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api).

The ordinary Profile API and Messages API have restricted access. Message sending also requires an affirmative member action on an editable draft. Nothing in the current grants establishes these capabilities. [Profile API](https://learn.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api), [Messages API](https://learn.microsoft.com/en-us/linkedin/shared/integrations/communications/messages).

Programmatic refresh is documented for approved Marketing Developer Platform partners. Default to reconnect-on-expiry for a self-service member connection; persist provider-supplied expiry rather than inventing a lifetime or assuming `offline_access`. [Refresh tokens](https://learn.microsoft.com/en-us/linkedin/shared/authentication/programmatic-refresh-tokens).

## 5. LinkedIn implementation slices

### L1: Useful local drafting without a provider write

Implement a small deterministic preparation service. It consumes only explicitly selected current approved outcome versions; no new inference dependency is needed. Start with an empty editable composer and user-selected source details, rather than automatically converting an internal HR or finance task into a public post. Raw transcript evidence and participant details are omitted by default. Keep all local drafts inside the authorized workspace/meeting boundary.

Support a public-post draft and a private outreach-text draft. Both allow editing, source inspection, bounded text and local copy/download. An outreach draft has an explicitly user-supplied recipient description/link and no automatically resolved person or send action. Copying text does not create an external-delivery receipt and must not be reported as posted/sent.

Use revision/version expectations on save/preparation; an edited source can leave a retained draft readable but stale and ineligible for publication until renewed review. Persist draft version and source snapshots, not a hidden mutable payload that approval later reads. Exact server schemas/length limits are assigned with the shared schema owner; document M2O limits separately from provider limits.

Department journeys: People Operations can draft a deliberately non-confidential onboarding initiative announcement; Finance can draft an authorized public process-improvement note without amounts or personnel details; Engineering can draft an approved release/demo progress note. Every public disclosure is human-selected and reviewed. These examples do not establish that automated sanitization makes real meeting data safe to publish.

### L2: Separate member publishing consent and credentials

Keep the existing OIDC adapter's token-discard policy. Add a separate posting-purpose OAuth flow and credential adapter; do not silently widen the existing OIDC scope validator. Session, workspace, current membership, purpose, state, nonce where OIDC is used, expiry and one-time callback consumption must be enforced. Distinct purpose/state storage prevents an OIDC callback from consuming a publishing approval.

Reuse authenticated credential sealing for a member-owned publishing connection only after inspecting the existing provider schema. Persist actual granted scopes, token expiry and credential generation; remove encrypted credentials on disconnect and mark pending proposals stale. Validate grants from the provider response/introspection; a requested scope or operator setting is not proof of consent. Introspection reports token activity, client binding and grants. [Token introspection](https://learn.microsoft.com/en-us/linkedin/shared/authentication/token-introspection).

Derive the publishing author from the authenticated provider account and the documented identifier contract, never from a browser-supplied person URN. OIDC subjects are application-bound; explicitly test their use with the chosen posting API/app. Do not assume cross-app identifiers or public profile URLs are posting identities. If author compatibility cannot be established from permitted APIs, readiness remains blocked.

M2O authorization recommendation: editors may prepare drafts; owners/reviewers may approve publication only using their own current member grant and authorized meeting. Team-delegated posting is not implicit. Confirm this role policy during coordinated implementation, while preserving Jira's existing owner-only policy.

### L3: Exact text-post preview, job and receipt

Initial publishable subset: one text-only post from one explicit user action, as the connected member, with a clearly presented public audience. Organization posts, media uploads, comments, post edits, scheduled posts and messages remain distinct additions. Do not infer supported visibility enums from the older UGC guide; expose only the contract verified for the selected Posts API.

Store the exact provider body and API version, author/connection generation, selected source versions, disclosure acknowledgment and expiry before approval. Show public text, audience, source summary and author prominently. Confirm disclosure separately from approving an internal outcome; the approval button must explicitly say it publishes to LinkedIn.

Approval and operation/job insertion share a transaction. Use a unique intent key for the same workspace/author/source/draft version so repeated approvals or concurrent identical proposals cannot enqueue duplicates. Store write intent before the network call; recheck grant, current authority, snapshots and credential generation before sending. Never allow approval to add text or change visibility.

A verified success returns the provider post URN from the documented success response and records it. Validate any constructed permalink from that identifier; if no permalink is established, display a receipt without inventing one. Timeouts, 5xx, malformed success or a recovered sending lease remain uncertain. Confirmed rejections may have a separately approved retry policy. A read permission cannot be assumed; manual investigation does not automatically mark an uncertain operation confirmed or permit resend.

## 6. Proposed API and UI contracts

These shapes are **proposals**, not currently available endpoints. Preserve existing GitHub/Jira shapes and add a frontend view adapter rather than forcing a simultaneous persistence rewrite.

### Capability presentation

Retain provider `id`, `name`, existing legacy `purpose/status/can_preview/can_publish`, and description. Add a per-action collection when coordinated with the shared type owner:

```typescript
type ActionReadiness = {
  action: "context" | "draft_post" | "draft_outreach" | "create_issue" | "publish_post";
  state: "ready" | "preview_only" | "needs_configuration" | "needs_connection"
       | "needs_permission" | "reauthorization_required" | "unsupported";
  can_prepare: boolean;
  can_publish: boolean;
  blockers: { code: string; message: string }[];
};
```

Scope these capabilities to the actual principal/workspace. A connected LinkedIn context account can coexist with posting setup required and local drafting ready. Legacy `purpose=context` must not hide its drafting action; a connected badge must not imply all actions are enabled. The common type owner can widen actions for Jira/Slack without adding unsupported buttons.

### Proposal and receipt view models

```typescript
type DeliveryPreviewView = {
  id: string;
  provider: "github" | "jira" | "slack" | "linkedin";
  action: "create" | "update";
  destination: { id: string; version: number; label: string };
  sources: { item_id: string; version: number; revision_id: string }[];
  payloads: Record<string, unknown>[];
  payload_hash: string;
  expires_at: string;
  approved: boolean;
};

type DeliveryReceiptView = {
  operation_id: string;
  proposal_id: string;
  provider: DeliveryPreviewView["provider"];
  state: "queued" | "sending" | "completed" | "failed" | "uncertain";
  results: {
    source_ids: string[];
    status: "created" | "updated" | "existing" | "rejected" | "uncertain" | "not_attempted";
    resource_label?: string;
    url?: string;
    error_code?: string;
  }[];
  can_reconcile: boolean;
  can_retry_rejected: boolean;
};
```

GitHub maps existing `would_create` to preview `payloads`; its `repo` becomes a destination label. Jira's single `snapshot/payload/result` maps to singleton arrays. Slack's proposed snapshots/message result maps to the same presentation, with team/channel/timestamp retained in its native typed response. LinkedIn member/post identifiers stay in its authorized native receipt, not in the capability catalog. Never invent a persisted destination version for the existing GitHub implementation; its normalized view needs the real binding introduced in G2 or an explicitly distinct legacy destination type.

The UI displays proposed `can_reconcile` only if the backend can perform permitted reads for that provider and operation. User certainty is not a boolean inferred from a URL. A missing result for a later batch item is rendered as not attempted without changing stored provider state.

### Candidate routes for implementation review

Within `/api/workspaces/{workspace_id}`:

- GitHub: retain existing preview/approve/reconcile; add `GET /operations/{operation_id}` and `GET /meetings/{meeting_id}/deliveries/github`, each enforcing meeting access.
- LinkedIn drafts: meeting-scoped create/read/update with strict expected draft/source versions and authorized visibility; optional local export. Route naming is assigned with the shared API owner.
- LinkedIn posting: dedicated connection/status/consent/disconnect routes, meeting-scoped exact preview, proposal approval, operation read/history. These are separate from existing personal OIDC routes.

Use strict runtime schemas, uniform sanitized errors, CSRF/origin controls on browser mutations, bounded pagination and UUID validation. Cross-workspace/restricted objects return the existing non-disclosing not-found contract. Reading a global member connection never authorizes reading another workspace's meeting.

## 7. Parallel ownership and implementation handoffs

| Owner | Planning ownership now | Candidate implementation responsibility after assignment |
| --- | --- | --- |
| Phase 4 provider chat | This file only | GitHub adapter/service hardening and dedicated LinkedIn draft/publishing adapter/service/test files. |
| Phase 3 Slack chat | `PHASE_3_SLACK_PLAN.md` | Slack protocol, consent/destination/user mapping, verified commands and message delivery. |
| Phase 5 experience chat | `PHASE_5_EXPERIENCE_PLAN.md` | Focused Share subpages, common receipt presentation, department visuals, calm/reduced motion and mobile journeys. |
| Coordinating chat | Cross-phase contracts and assignments | `main.py`, `models.py`, `schemas.py`, `worker.py`, migration sequence, settings/examples, catalog, shared frontend types and integration wiring. |

Provider plans agree on stored exact previews, destination/source versions, durable intent, uncertainty and separate personal execution. Shared files are edited by one assigned owner at a time. No simultaneous migrations or schema/worker rewrites. Provider UI components (`Publisher`, new LinkedIn composer, `Integrations`, `ShareStep`) are assigned explicitly after the UX structure is reviewed. Do not update shared manifests, CI, lockfiles or private configuration as a side effect of planning.

Coordination received from Phase 3: use `operation_id` consistently for receipt responses, retain native Slack capability details, and require updates to reference a completed M2O receipt with a remote content snapshot. Slack interaction and delivery readiness must be separate. Phase 3 also proposes nullable provider expiry for legitimately non-expiring Slack tokens; the shared schema owner must preserve explicit expiry requirements/tests for Jira and LinkedIn. LinkedIn publishing still requires an actual provider-supplied token expiry; null must not become a permission bypass.

## 8. Focused verification and acceptance

| Area | Required checks |
| --- | --- |
| GitHub protocol | Exact POST/status/body; expected receipt repository/number; malformed success; 403 permissions versus rate limits; timeout/5xx; markers in closed issues; duplicate matches across pages; pagination cap; no resend after ambiguous result/recovered intent. |
| GitHub authorization | Wrong workspace/restricted meeting/viewer; revoked role/token/repository binding; stale destination/outcome/transcript; stored hash mutation; concurrent repeated/distinct same-intent approvals in PostgreSQL; allow-list changes between approval and worker. |
| GitHub UI | Draft versus enabled destination; preview/readable details; evidence opt-in; late responses; expiry/source changes; reload history; partial batch; uncertainty and reconciliation; double approval cannot enqueue twice; no daily-plan state change. |
| LinkedIn OIDC regression | Retain signed claim/session/nonce/state replay tests, minimum profile retention and disconnect; context-only account does not gain post permission or auto-confirm people. |
| LinkedIn drafting | Strict length/type/expected versions; source isolation; no transcript/private-field auto-inclusion; local copy failure shown honestly; editable draft retention; stale source blocks publish. |
| LinkedIn consent/credentials | Requested versus actual grants; missing publishing scope; no refresh-token assumption; active/client-bound introspection; expired/revoked token; encrypted account binding; single-use state; mismatched account/author; disconnect generation invalidates pending writes. |
| LinkedIn delivery | Exact body/version/author/audience; separate disclosure approval; repeated and concurrent intents; revalidation before worker write; 201 with valid post identifier; rejected/rate-limited responses; timeout/5xx/malformed success/crash remain uncertain; absent read scope blocks automatic reconciliation and resend. |
| Provider-independent journeys | Hiring-team synthetic demo cannot connect/write externally; authorized private contributor drafts → own-account reviewer approves → receipt survives refresh; editor cannot publish as another user; delivery leaves personal-plan progress unchanged. |
| UI and release | Keyboard/focus/status announcements, calm/system reduced motion, accessible contrast, mobile non-overflow and focused page length; existing Jira/GitHub/local journeys continue; full affected tests/static checks after focused checks; no claim of live activation from transport mocks. |

Provider HTTP tests use controlled transports and synthetic tokens. Database races use disposable PostgreSQL data; migrations use additive reviewed SQL. Live activation testing requires separately authorized destinations and exact writes. Public Page/policy creation, developer-product approvals and deployment are human/external actions, not outcomes of local testing.

## 9. Release gates and remaining dependencies

Locally implementable now: GitHub receipt/readiness alignment and hardening, explicit destination policy, LinkedIn local drafts, tested separate publishing credentials/protocol and truthful disabled states. These should not wait for an API approval to begin.

Externally required for live LinkedIn publication: actual administered Page/app association, public privacy policy/contact/data retention behavior, requested product approval, actual member consent/grants, verified author compatibility, actual HTTPS callback when hosted, and an explicitly authorized publish test. There is no verified app grant today. Lead messaging and arbitrary enrichment remain restricted capabilities rather than implied parts of posting.

Render Free does not establish durable worker availability, persistence or inference capacity. Receipts and privacy lifecycle depend on a durable database/recovery plan; interactive deadlines remain a Phase 3/hosting concern. No hosting resource is created by this plan.

Completion for Phase 4 means demonstrated GitHub preparation-to-receipt recovery and meaningful LinkedIn drafting/context with locally tested, permission-gated publishing behavior. The overall release must separately report whether LinkedIn is live activated, locally implemented but blocked, or deliberately draft-only; none of those labels is interchangeable.
