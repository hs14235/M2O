# Slack identity, meeting capture and personal actions

The action boundary is implemented behind `SLACK_INTERACTIONS_ENABLED=false`. Enabling it requires private client/signing/encryption configuration, `SLACK_APP_ID`, private mode and an awake reachable endpoint. Tests use synthetic requests; no Slack callback registration, real account linking, messages or modal calls were performed.

## Linking requires confirmation on both sides

1. In the signed-in M2O browser, select a connected workspace installation and request a link challenge.
2. The browser receives a one-use `/m2o link CODE` command with a five-minute lifetime. Only the code hash is stored.
3. Run it in the specified Slack team. Its signed request records the pending Slack member ID; it does not activate the mapping.
4. Return to the same browser session, inspect the team and pending member ID, and explicitly confirm that member.

The resulting mapping binds the M2O user, workspace, Slack installation/member, installation generation and identity version. An existing member cannot be claimed by another M2O user in that workspace. Editors and reviewers can link for personal actions; this does not grant the owner's bot-installation or publication authority. Revoked membership, disabled users, a changed role or installation generation invalidate action authority. Unlinking invalidates modal contexts. Names, email strings, transcript mentions and reactions never create an identity mapping.

## Current interactions

| Entry point | Result |
| --- | --- |
| `/m2o help` | Ephemeral usage guidance. |
| `/m2o link CODE` | Pending browser confirmation only. |
| `/m2o meeting` | A private capture form for title, transcript/notes, date and IANA timezone. |
| Global “Capture a meeting in M2O” shortcut | Opens the same capture form. |
| Message shortcut | Prefills editable text from the explicitly selected message; it does not download recording/file content or read arbitrary channel history. |
| `/m2o plan [YYYY-MM-DD]` | Opens the linked user's current approved actions and personal plan for that date. |

When a Slack member links multiple M2O workspaces in one team, the command must include the desired workspace UUID. Shortcuts refuse to choose one implicitly in that case. This is a supported but less polished path for the experience phase to refine; it is not permission to default to another workspace.

Capture submissions create a new **restricted** meeting and queue existing indexing work. They never automatically approve outcomes, publish content or infer a transcript from audio. Text is limited to 3000 characters in the Slack form. Larger transcripts use M2O's normal transcript step. Users continue participant confirmation, extraction and review in M2O.

Personal-plan forms freeze selectable source versions and existing plan versions. Submission uses `PlanningService` to add or update only the mapped user's state, date and priority. Stale or unapproved outcomes, stale plans and another user's form are rejected. Completing this form leaves review approval and Jira/GitHub/Slack/LinkedIn delivery state separate.

## Request and replay boundary

The two public inbound endpoints are `POST /api/integrations/slack/commands` and `POST /api/integrations/slack/interactions`. Their authority is the verified Slack signature plus an explicit stored identity; they do not use browser cookies as authorization.

- A 64 KiB raw-body bound is enforced before form decoding. Form fields cannot be duplicated.
- HMAC-SHA256 checks the original body bytes and timestamp with constant-time comparison. Duplicate signature headers and requests outside a five-minute window are rejected. The configured app and returned team must match a stored installation. Documented shortcut payloads may omit `api_app_id`; the signing secret and configured app ID establish that application boundary. See [request signatures](https://docs.slack.dev/authentication/verifying-requests-from-slack/) and [shortcut payloads](https://docs.slack.dev/reference/interaction-payloads/shortcuts-interaction-payload/).
- A ten-minute durable request receipt returns the prior acknowledgement for identical valid retries. Personalized modal contexts are one-use, identity/version-bound and expire in ten minutes. A differently signed retry of a consumed context also returns its acknowledgement without executing again.
- A successful capture/plan acknowledgement follows the database commit. Database failures do not claim accepted changes. Outbound `response_url` fields are ignored; modal calls use only Slack's fixed API host.
- Owner user and membership locks precede installation-generation locks, matching reconnection. A PostgreSQL regression forces a reconnect to overlap an action and verifies the old mapping is rejected. Inbound PostgreSQL statements and lock waits have bounded timeouts; this is not a general claim that all future cross-account lock graphs are deadlock-free.

## Timing and hosting limitations

Slack requires an acknowledgement within three seconds, and a trigger expires quickly. The warm HTTP help test checks a sub-three-second response in the test environment. Modal requests use a 1.5-second HTTP timeout; inbound PostgreSQL statement and lock limits reduce stalls. These per-operation limits do **not** prove an overall three-second production budget under pool contention, multiple slow queries or network latency. See [handling interactions](https://docs.slack.dev/interactivity/handling-user-interaction/).

Sleeping Render Free services cannot meet that promise reliably: cold starts, database availability and network latency remain release constraints. Keep the gate disabled there until an appropriate awake topology and end-to-end timing tests establish availability. See [Render Free limitations](https://render.com/docs/free).

## Browser API

Routes are relative to `/api/workspaces/{workspace_id}` and retain browser session and CSRF requirements:

| Method and route | Body / response |
| --- | --- |
| `GET /integrations/slack/actions` | `enabled`, `can_link`, installed teams and the current user's mapping status. |
| `POST /integrations/slack/link` | `{connection_id}` → challenge ID, command, team and expiry. |
| `GET /integrations/slack/link/{challenge_id}` | The pending member ID for the original browser's unexpired challenge. |
| `POST /integrations/slack/link/confirm` | `{challenge_id, slack_user_id}` → current installation/mapping status. |
| `DELETE /integrations/slack/link/{connection_id}` | Removes only the current user's mapping and pending challenges for that installation/workspace. |

Raw link commands, credentials and request bodies must not enter logs or shared documentation. Secrets remain in private backend configuration. The manifest generator includes separate global/message shortcut IDs and explicitly supplied callback URLs; updating/installing it remains a human account action.
