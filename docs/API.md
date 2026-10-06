# API contracts and authorization

Jira OAuth, site discovery, version-checked workspace destination selection and local disconnect are documented in [JIRA_CONNECTION.md](JIRA_CONNECTION.md). Exact Jira preview/create/update, receipts and reconciliation are documented in [JIRA_DELIVERY.md](JIRA_DELIVERY.md). Only the consenting owner in a configured private environment can deliver.

The web application uses same-origin `/api`. FastAPI serves an OpenAPI document at `/openapi.json` in local development. The database service commits before a successful response. Long-running indexing, extraction and publication return HTTP 202 plus a job ID; clients poll authorized job state.

## Authentication and roles

`POST /api/auth/login` accepts email and password and issues a configurable 12-hour HttpOnly session cookie plus a CSRF cookie. `POST /api/auth/logout` revokes the session. `GET /api/me` supplies account and integration capabilities; `GET /api/workspaces` supplies memberships. Public visitors use isolated, expiring sessions through `POST /api/demo/start`, never shared demo credentials. [USER_LIFECYCLE.md](USER_LIFECYCLE.md) defines the tested invitation, recovery, quota, export and erasure contracts.

Every session-authenticated mutation requires the exact configured Origin and `X-CSRF-Token`. A hashed expiring bearer token is an alternative for a single private workspace; membership, active user and authority generation are rechecked. Visitor bearer/MCP access is denied. There is no public private-account registration endpoint. Bootstrap creates the first owner; invited recipients accept their own membership and establish their own credentials. Password recovery invalidates prior sessions/tokens/jobs/Slack mappings and owner invitations by generation.

| Role | Permissions |
| --- | --- |
| Viewer | Read accessible workspace meetings, revisions, outcomes, directory and job status; search indexed evidence. |
| Editor | Viewer permissions plus import/edit permitted meetings, queue extraction, edit outcomes, confirm participants and prepare local previews. |
| Reviewer | Editor permissions plus archive meetings, approve outcomes and exact publication proposals, reconcile uncertain operations, view audit records. |
| Owner | Reviewer permissions plus manage members and roles. The last owner cannot be demoted. |

Restricted meetings are accessible to their creator and workspace owners/reviewers. Unauthorized resource reads return 404 to avoid disclosing existence; insufficient permission for a known operation returns 403. Roles are checked in application services, including the MCP adapter and worker.

## Workspace routes

`GET/POST /api/workspaces` list active memberships or create a workspace for an authenticated private user. Lists include `is_demo` and `expires_at`. Visitors receive three isolated department workspaces and cannot create more. Frozen/erased scopes are removed from ordinary access; pending-erasure privacy status/retry remains available to the owner. All routes below use prefix `/api/workspaces/{workspace_id}`.

`GET /integrations` returns a credential-free provider capability catalog. Common fields are `id`, `name`, `purpose` (`delivery` or `context`), `status`, `can_preview`, `can_publish`, and `description`. LinkedIn adds `can_draft`, `can_context` and `can_message:false`. Readiness reflects actual private authority, consent, workspace/destination binding, demo mode and role; it never implies a live product approval. Jira and Slack use the acting owner's connected account and verified destination. GitHub and supported LinkedIn publication retain their provider-specific guards. The catalog does not make provider requests. See [SLACK_DELIVERY.md](SLACK_DELIVERY.md), [SLACK_ACTIONS.md](SLACK_ACTIONS.md), [GITHUB_DELIVERY.md](GITHUB_DELIVERY.md) and [LINKEDIN_DELIVERY.md](LINKEDIN_DELIVERY.md).

`POST /meetings/{meeting_id}/export` prepares a local handoff and never publishes externally. The strict body is `{ "format": "json" | "markdown", "expected_revision": 1, "versions": { "<outcome UUID>": 2 }, "include_evidence": false }`. Between 1 and 30 selected versions are required. Every selected outcome must be approved and belong to the current transcript. A changed transcript, outcome version or approval returns 409; inaccessible meetings return 404. The response includes `filename`, `media_type`, `content`, and `snapshot_hash`. JSON uses a provider-independent `schema_version: 1` envelope with meeting/revision/department and reviewed outcomes. Calendar dates and confirmed owner names/responsibilities are retained. Evidence references are retained, while raw evidence text is opt-in.

| Method and path | Contract |
| --- | --- |
| GET `/members`; PATCH `/members/{user_id}` | Current private-owner member/role administration; retains an active owner. Legacy POST `/members` returns 409 directing callers to invitations. |
| GET/POST `/invitations`; DELETE `/invitations/{id}` | Owner-issued email/role-bound links, manual sharing, hashed expiring single-use acceptance. See lifecycle guide. |
| POST `/demo/load` | Visitor-only approved synthetic fixture ID; idempotently opens an indexed meeting, never arbitrary transcript text. |
| GET `/privacy`; GET `/privacy/export`; POST `/privacy/erase` | Owner export and exact password/name/version-confirmed erasure with pending freeze/resume. See lifecycle guide. |
| GET/POST `/participants` | List or explicitly add directory context; only the acting user can link their own application account. |
| GET `/meetings` | Paginated accessible meetings. |
| POST `/index` | Meeting slug, transcript, title, visibility, date, IANA timezone, optional expected version; creates a revision and index job. |
| POST `/upload` | Multipart UTF-8 `.txt`/`.md`, bounded to the configured byte limit. |
| GET/PATCH/DELETE `/meetings/{meeting_id}` | Read, rename with expected version, or soft archive. Archiving retains evidence/history and cancels queued work. |
| POST `/meetings/{meeting_id}/extract` | Queue extraction for the current revision; returns an existing pending extraction rather than duplicating it. |
| POST `/meetings/{meeting_id}/search` | `{ "q": "review checklist", "k": 5 }`; searches current indexed chunks, maximum 20 results. |
| PATCH `/meetings/{meeting_id}/outcomes/{item_id}` | Expected version plus changed review fields; approval requires owner/reviewer. |
| GET `/meetings/{meeting_id}/outcomes/{item_id}/history` | Immutable saved review payloads. |
| GET `/meetings/{meeting_id}/revisions/{number}` | Read-only historical transcript and associated outcomes. |
| POST `/meetings/{meeting_id}/mentions/{mention_id}/confirm` | Directory participant ID; same-workspace confirmation assigns matching drafts. |
| POST `/meetings/{meeting_id}/preview` | Repository, 1–30 approved current outcome IDs, optional evidence inclusion; stores exact proposal without external calls. |
| POST `/proposals/{proposal_id}/approve` | Exact 64-character payload hash; checks role, expiry, current versions, demo flag and destination allowlist. |
| GET `/jobs/{job_id}` | Authorized durable state, safe error code and result. |
| POST `/operations/{operation_id}/reconcile` | Owner/reviewer; read-only GitHub marker lookup for an uncertain operation. |
| GET `/summary` | Accessible outcome totals and pending review/owner counts for the workspace. |
| GET `/audit` | Bounded owner/reviewer audit metadata, newest first. |

Meeting slugs are stable readable identifiers within one workspace. Record IDs use generated UUID strings. Request bodies reject unknown fields, bound text/list lengths, and validate enums, dates, timezone and confidence. Transcript byte and chunk limits are additional service checks.

For example, after reading outcome version 3:

```json
{
  "expected_version": 3,
  "title": "Review the synthetic access checklist",
  "due_date": "2026-10-09",
  "status": "approved"
}
```

If another reviewer saved version 4 first, the request returns 409. The client should preserve its edit and load the new version for reconciliation, rather than silently overwriting it.

## Integrations and failures

`POST /api/integrations/linkedin/connect` starts configured self-account OIDC consent. The fixed callback is `GET /api/integrations/linkedin/callback`. `DELETE /api/integrations/linkedin` removes the acting user's stored minimum profile. Missing configuration returns a capability error and leaves the rest of the product usable.

Errors contain a safe message, location and request ID. Common statuses: 401 unauthenticated, 403 forbidden, 404 inaccessible/missing, 409 stale version/integrity conflict, 413 bounded body/upload exceeded, 422 invalid contract, 429 quota exceeded, 503 unavailable database/provider. Internal exception messages and input values are not echoed. Provider failure during a job is represented by job state and a safe error code.

Publication is intentionally guarded independently of outcome approval. Current demo mode prevents external writes even for an owner. Enabling provider credentials does not by itself authorize a user or agent to send data externally.
# Personal daily planning

All plan routes use the existing authenticated workspace principal and CSRF protection. Plans belong to the acting user, and list queries filter archived/restricted meetings. `GET /api/workspaces/{workspace_id}/plan?day=YYYY-MM-DD` returns bounded `entries` and unplanned approved action/follow-up `candidates`, with truncation flags. Candidate records include the expected `item_version`.

`POST /api/workspaces/{workspace_id}/meetings/{meeting_id}/outcomes/{item_id}/plan` accepts `expected_item_version`, `planned_on` (calendar date) and optional integer `priority` (1–3). Duplicate planning returns 409; move an existing entry using PATCH.

The same path supports PATCH with required `expected_version`, `expected_item_version`, `planned_on` and `state` (`planned`, `in_progress`, `blocked`, `done`), plus optional priority. Meeting/outcome locks serialize changes. A changed approved item must be explicitly reconfirmed with `state=planned`; superseded transcript outcomes cannot resume. DELETE removes only the acting user's entry from an accessible meeting, preserving the outcome. Viewer mutations return 403.

Review status and execution state are independent. Responses expose `stale` and `can_reconfirm`; stale entries may be removed without pretending an old transcript is current. Completing a plan never publishes an issue or marks an outcome reviewed.
# Experience V2 additions — October 5, 2026

See [Google Meet import and reviewed-calendar contract](GOOGLE_MEET_IMPORT.md) for the new read-only provider connection, latest-transcript exact-preview/save endpoints and bounded calendar DTO. Meeting summaries add `created_at`; the existing meetings list accepts a bounded literal `q` title/identifier search. These additions preserve existing authentication, workspace visibility, source revision and review contracts.
