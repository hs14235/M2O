# Slack reviewed delivery

This increment implements an owner-managed bot installation, a verified public-channel destination, exact reviewed create/update proposals, a durable worker operation, and receipts. It has been tested with synthetic HTTP transports and disposable PostgreSQL schemas. No live Slack delivery or shared-runtime migration is established by those tests.

## Authority and destination

Private backend configuration supplies the client ID, client secret and existing 32-byte provider encryption key. The OAuth callback is the application origin plus `/api/integrations/slack/callback`. OAuth state is bound to the browser session, workspace and user, expires after ten minutes, and is consumed once. Returned app, team, bot identity and grant scopes are checked against Slack's token and `auth.test` responses before encrypted storage.

The required bot scopes are `chat:write`, `channels:read`, `channels:history`, and `commands`. Reading channel information verifies the selected destination; history is used for bounded receipt reconciliation and checks before updating an existing M2O message. The commands scope supports the separately gated actions described in [SLACK_ACTIONS.md](SLACK_ACTIONS.md). These are backend requirements; installing the earlier `chat:write` manifest alone does not grant them.

A workspace owner must select an active public channel that contains the bot. Private, shared, externally shared, organization-shared and direct-message destinations are rejected. M2O never joins channels automatically. Installation ownership cannot silently move to another M2O user. Reconnection increments the account generation and each existing destination version and invalidates channel verification. Rotating credentials retain Slack's returned expiry; non-rotating credentials have no fabricated expiry.

Slack documents create and update as `chat.postMessage` and `chat.update`, respectively. Both are HTTP POST methods; a user-facing update action does not require inventing a PUT API. See [postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/) and [chat.update](https://docs.slack.dev/reference/methods/chat.update/).

## Reviewed flow

1. Connect the bot from a signed-in owner browser and verify a channel in Connections.
2. Review current outcome versions and confirm ambiguous people in M2O.
3. Request a create preview with the current transcript revision, each selected item version and destination version. At most ten outcomes enter one message. Restricted meetings require explicit external-disclosure confirmation; raw evidence text is opt-in.
4. Inspect the stored destination, text, blocks and hash. Plain-text blocks and escaped fallback text prevent outcome content from becoming automatic mentions or arbitrary client-authored Slack blocks.
5. Approve that exact hash within the thirty-minute proposal lifetime. The operation and worker job are recorded in the approval transaction.
6. Inspect the persisted receipt. Delivery does not complete a personal plan item or change its review approval.

An update preview targets a completed, owned M2O receipt for the same meeting and destination. It records the existing message timestamp and observed text/block hash. The worker rereads the message and refuses an update when its content changed. This check is not an atomic remote compare-and-swap: a Slack user can edit between that read and `chat.update`. The interface and documentation must retain that limitation.

## Failure and retry policy

Before an external write, the worker commits a durable uncertain intent. A transport failure, ambiguous server response, malformed successful response, or recovered lease becomes uncertain and cannot automatically resend. A definite rejection can be retried only through an explicit, still-current approved proposal. The receipt exposes `can_reconcile` and `can_retry_rejected`; a stale source, expired proposal, revoked role, or changed destination can disable those actions.

Reconciliation reads the exact timestamp in the original verified channel and checks the M2O marker and exact text/blocks. It does not repeat the write. If Slack serializes content differently or a human edits it, reconciliation can fail closed and require investigation. An exhausted worker retry budget retains the uncertain receipt; a previously confirmed completion survives a missed final job update.

Slack's stored connection status is capability discovery, not continuous provider-access verification. Provider permissions are checked again when a network action occurs. Rate limits and provider availability can still reject a locally valid proposal; see [Slack rate limits](https://docs.slack.dev/apis/web-api/rate-limits/).

## HTTP contracts

All browser routes below are relative to `/api/workspaces/{workspace_id}` and use existing workspace authorization and CSRF checks:

| Method and route | Contract |
| --- | --- |
| `POST /integrations/slack/connect` | Returns the session-bound authorization URL. |
| `GET /integrations/slack` | Saved connection/destination versions and separate delivery/action capability flags. |
| `POST /integrations/slack/destination` | `channel_id`, strict `expected_version`. |
| `DELETE /integrations/slack` | Removes the current workspace binding and credentials when no bindings remain. No remote revoke call. |
| `POST /meetings/{slug}/slack/preview` | `action`, `expected_revision`, `versions`, `expected_destination_version`, optional evidence/disclosure flags and update `target_operation_id`. |
| `POST /slack/proposals/{id}/approve` | Exact `payload_hash`, optional strict `retry_rejected`; returns HTTP 202 with operation/job IDs. |
| `GET /slack/operations/{id}` | `operation_id`, state, result, source versions, exact proposal and action flags. |
| `GET /meetings/{slug}/slack/deliveries` | Latest fifty receipts owned by the current publisher. |
| `POST /slack/operations/{id}/reconcile` | Exact `message_ts`; read-only external reconciliation. |

## Private local setup

`integrations/slack/manifest.json` contains the bot scopes without an invented production URL. Generate an origin-specific manifest with `python scripts/slack_manifest.py --origin http://localhost:8080`. Use the actual deployment origin when it is known. Add `--interactions` only for an actual publicly reachable HTTPS endpoint that is kept awake. The generator rejects local interaction URLs and credential-bearing or path-bearing origins; it does not create or update a Slack app. Manifest fields follow Slack's [official reference](https://docs.slack.dev/reference/app-manifest/).

`python scripts/configure_slack.py` prompts privately for the client ID, client secret, signing secret and app ID. It saves only the ignored root Compose configuration, preserves an existing provider encryption key and other providers' settings, and leaves both demo mode and interaction gates unchanged. Native backend settings use `backend/.env` instead; the helper does not modify that file. Reinstallation for the revised scopes, configuration changes, migrations and runtime recreation remain explicit setup actions, not side effects of this implementation.
