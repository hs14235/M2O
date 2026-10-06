# Latest Google Meet transcript import

October 5, 2026. Implementation is local and configurable. Hamza has reported no Google Cloud OAuth application and no generated Meet transcripts. No live consent, Google account setup or transcript fetch has been performed.

## Capability and limits

M2O reads the latest conference accessible to the consenting Google account, ordered by Google's default descending conference **start time**. This is the latest accessible meeting, not necessarily the meeting with the latest end time. An active latest meeting returns a pending message. A missing transcript returns a no-transcript message. M2O never silently imports an older meeting.

Import reads existing structured **Meet API transcript entries**. It does not generate speech transcription, join meetings, record audio, retrieve Drive documents, create meetings or manage Google Calendar. API entries can differ from the generated or edited Google Docs transcript, including interleaved speech. Conference/entry data is available for 30 days after the conference ends. Transcription must already have been enabled with an eligible account, administrative settings and meeting access.

Sources: [conference listing](https://developers.google.com/workspace/meet/api/reference/rest/v2/conferenceRecords/list), [Meet artifacts and retention](https://developers.google.com/workspace/meet/api/guides/artifacts), [transcription availability](https://support.google.com/meet/answer/12849897).

## Explicit user flow

1. An invited private owner, reviewer or editor connects their own Google account from a signed-in browser. Visitors cannot connect or import, independently of the global demo flag.
2. Import latest meeting performs bounded, read-only Google requests. All transcript sessions must be `FILE_GENERATED` under M2O's conservative completed-artifact policy. It collects every page of every session and participants, validates resource ancestry, speaker references and timestamps, then orders speech chronologically. Missing, processing, denied, expired, malformed, oversized, incomplete and timed-out results never become a successful partial transcript.
3. A 15-minute preview shows text, conference timestamps, all transcript resource IDs and the source format. Speaker labels have sanitized delimiters and stable resource suffixes; imported people remain **unconfirmed**. Google identity does not confirm a workspace participant.
4. Explicit Save submits the preview ID and exact payload hash with a chosen title/identifier and access choice. Imports default to **restricted**; `visibility: "workspace"` requires an explicit selection. M2O queues its existing index job, creates participant mentions, and continues normal extraction, people confirmation and outcome review. Reusing an existing import preserves its access setting.
5. Repeating the same source/text in the same workspace returns the existing meeting/job without advancing its version. Another title/identifier does not create a duplicate. A changed source or an independently replaced local revision returns 409; replacement requires the existing explicit transcript/review flow. Archived or erased meetings are never revived automatically.

The preview route has a 25-second overall asynchronous deadline, below the current proxy's 30-second read timeout. Bulk reads have a 20-second deadline; each Google HTTP request has a 10-second timeout. A maximum of 50 pages per list, 50 transcript sessions, 5,000 entries and 500 participants applies, together with existing byte/chunk limits. Exceeding a bound fails the whole preview. This deliberately favors an honest error over partial extraction; unusually large meetings may need the ordinary text-upload path. Import attempts are bounded to ten per actor/workspace/hour.

## Operator setup, when account prerequisites exist

Do not send secrets through chat. Creating an application, accepting policies, changing accounts and enabling Google Cloud services require the account holder's explicit action.

1. In an actual Google Cloud project, enable Google Meet REST API. Configure the OAuth consent screen with the actual M2O name, support contact, public privacy policy and appropriate testing audience/test users. No production domain or public policy URL is assumed here.
2. Add only `https://www.googleapis.com/auth/meetings.space.readonly`. This sensitive scope reads existing accessible conferences. `meetings.space.created` is insufficient for arbitrary previously held meetings. No Drive or Google Calendar scope is needed for this feature.
3. Create an OAuth **Web application** client. Register the exact callback `${APP_ORIGIN}/api/integrations/google-meet/callback` using the real configured origin. For a local origin of `http://localhost:8080`, the callback is `http://localhost:8080/api/integrations/google-meet/callback`. Hosted use requires the actual HTTPS origin; the local callback does not activate hosted consent.
4. Store `GOOGLE_MEET_CLIENT_ID`, `GOOGLE_MEET_CLIENT_SECRET` and the existing `PROVIDER_ENCRYPTION_KEY` privately in the selected runtime. Preserve the encryption key used by existing integrations. Never replace it merely to configure Google. The settings default to empty credentials and return `setup_required: true` until configured. Native backend settings read `backend/.env`; Compose passes these optional values from the root private `.env` to the API, worker and migration services. The example files contain blank values, not credentials.
5. Apply migration `20261005_11` through the repository's reviewed backup/migration procedure, recreate the appropriate runtime to load configuration, and connect through M2O. Do not paste Google's generated authorization URLs into the application.
6. Enable transcription in an eligible test meeting, allow its artifacts to finish generating, then test preview and explicit save. A Google connection alone cannot manufacture a missing transcript.

Google external OAuth apps in Testing can have seven-day refresh-token expiration for this scope. Expired or revoked consent becomes `reauthorization_required`; reconnect is a normal recovery action. Production consent/scope verification requirements depend on the actual app audience and must be assessed before public activation.

Sources: [Meet authentication/scopes](https://developers.google.com/workspace/meet/api/guides/authenticate-authorize), [Google web-server OAuth](https://developers.google.com/identity/protocols/oauth2/web-server), [OAuth token expiration](https://developers.google.com/identity/protocols/oauth2).

## HTTP contract

`ROOT = /api/workspaces/{workspace_id}`. Standard authentication, workspace lifetime, roles and browser CSRF rules apply.

| Request | Result |
| --- | --- |
| `GET ROOT/integrations/google-meet` | `configured`, `state`, `can_import`, `setup_required`, `source_format`, `transcription_required` |
| `POST ROOT/integrations/google-meet/connect` | Browser-only consent `url` |
| `GET /api/integrations/google-meet/callback` | Validates one-use browser-bound state, stores narrow encrypted grant, redirects to workspace connections |
| `DELETE ROOT/integrations/google-meet` or `DELETE /api/integrations/google-meet` | Removes the caller's local grant/previews across their bindings; `remote_consent_revoked: false` |
| `POST ROOT/imports/google-meet/preview` with `{}` | `preview_id`, `payload_hash`, `transcript`, `source`, `participants`, `expires_at`; `Cache-Control: no-store` |
| `POST ROOT/imports/google-meet/{preview_id}/save` with `{payload_hash,title,meeting_id,visibility?}` | 202 normal index response plus `import_id`, `reused`; visibility defaults to restricted, accepts only restricted/workspace; same-source replay returns actual existing meeting/job |

The meeting detail DTO adds `import_source`, containing public-to-that-meeting source provenance, original revision ID and `current`; no grant, secret, access token or connection generation is exposed.

## Persistence, revocation and maintenance

Credential encryption uses the existing provider/account-bound AES-GCM storage. Refresh is serialized under account/workspace/connection locks and preserves an omitted refresh token only within the same generation. Bulk fetch releases those locks. The returned text becomes a stored preview only after fresh account generation, membership, workspace lifetime and connection-generation checks; Save checks them again and recomputes the exact payload fingerprint. Disconnect/reconnect invalidates previews. A known revoked refresh clears credentials and rotates generation.

The short OAuth exchange/refresh may hold authority locks during its bounded network request; bulk transcript retrieval does not. PostgreSQL authority paths set two-second lock and five-second statement limits. Cancellation during credential refresh can require reconnect; no read is retried blindly.

Migration 11 adds consent generation, expiring previews and unique workspace/conference provenance. It does not rewrite transcripts or existing approvals. Concurrent saves serialize on workspace authority and retain database uniqueness as the final guard. Downgrade refuses automatic data loss.

Workspace erasure deletes previews/provenance before transcript revisions, then removes unused associated credentials while preserving grants associated with another active workspace. Account erasure deletes own previews and clears own credentials; collaborators' shared meeting text/provenance follows the existing collaborative-retention policy. The bounded operator retention command removes expired previews. Browser expiration alone is not scheduled deletion; run retention according to the operator runbook. Disconnect removes local consent only; users can revoke Google's own authorization separately in their Google account.

## Reviewed calendar contract

`GET ROOT/calendar?start=YYYY-MM-DD&end=YYYY-MM-DD&meeting_id=optional&include_unscheduled=true&limit=100&offset=0` returns `entries` and `next_offset`. Dates are inclusive, ordered, and at most 93 days; limit is 1–200 and offset 0–10,000.

Each entry includes `item_id`, `meeting_id`, `meeting_title`, `title`, `kind`, `item_version`, `meeting_version`, `revision_number`, `review_status`, `due_date`, `due_hint`, `scheduled`, `owner_name`, `owner_confirmed`, and `personal_plan`. All five current approved outcome kinds appear. Explicit `due_date` alone places an item on the calendar. Undated items remain undated with their literal hint. Only a confirmed workspace participant supplies the owner name; otherwise it is `Unassigned`. `personal_plan` is the caller's own `{id,state,planned_on,version,reviewed_version,stale}` or null; its date/state never substitutes for a due date or changes shared review/provider status.

Restricted meetings use the existing creator/owner/reviewer visibility rule. An inaccessible selected meeting returns 404. Old revisions, draft/dismissed outcomes and archived meetings are excluded. Pagination order is stable by due date, meeting ID and outcome ID for an unchanged dataset; edits can change page contents, so reload after review changes.

Meeting summaries now include `created_at`. `GET ROOT/meetings?q=...` searches title/slug on the server with a bounded 200-character literal query, escaping SQL wildcard characters. Same-title records remain distinct by identifier and creation timestamp.

## Local verification evidence

October 5, 2026, this backend track observed:

- Full PostgreSQL backend regression run: **396 passed in 516.25 seconds**. That run began before the final import-visibility and provenance-cleanup corrections.
- Current focused import/calendar PostgreSQL suite after those corrections: **27 passed in 41.37 seconds**, including actual HTTP preview/save, explicit workspace visibility versus restricted default, paginated multi-session retrieval, malformed resources, authority changes during fetch, exact hash/source/version checks, read timeout without partial persistence, revoked/renewable consent, browser state/CSRF, visitor denial, visibility/date/calendar boundaries and concurrent duplicate saves returning one meeting/job.
- Focused Google/provider/privacy/retention PostgreSQL checks after provenance cleanup: **45 passed in 84.55 seconds**. This includes erasure after a destination binding has been removed; remaining active associations preserve shared grants.
- Native focused suite before the final visibility/cleanup corrections: **26 passed, one PostgreSQL-only concurrency test skipped**. This is complementary isolated-test evidence, not PostgreSQL replacement.
- Full backend Pyright reported zero errors; scoped Ruff/format and `git diff --check` passed, with existing CRLF conversion warnings only.

Provider responses are synthetic `httpx.MockTransport` data; PostgreSQL tests use disposable schemas and real migrations/locks. These results do not demonstrate live Google access, hosted deployment or frontend browser completion. No Google account/app creation, live consent/read, private environment change, shared runtime migration/restart, commit, push or deployment was performed by this track.
