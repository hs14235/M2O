# Jira account connection and workspace destination

The implemented connection flow is **Connect Jira → consent → find authorized sites → verify a space key → save destination → disconnect**. Exact reviewed issue creation/update and receipts are now implemented separately; see [JIRA_DELIVERY.md](JIRA_DELIVERY.md). Live consent and site access have not been tested with Hamza's credentials. Provider tests use controlled synthetic HTTP responses; PostgreSQL tests execute the real migration, transactions, and locks.

## Local setup

Use the one M2O developer application maintained by the operator. Invited users should authorize that application, not create individual developer apps or supply personal API tokens.

1. In the Atlassian console, open M2O → Authorization → OAuth 2.0 → configure the callback for the actual M2O origin. For the current Compose origin, the implemented URL is `http://localhost:8080/api/integrations/jira/callback`. The authorization request derives the exact URL from `APP_ORIGIN`; native Vite development uses its separately configured origin. The remote environment must use its actual HTTPS origin. Provider acceptance of a local callback remains unverified.
2. The app requires `read:jira-work` and `write:jira-work`. Authorization also requests `offline_access` for renewable credentials.
3. From the repository root, run `backend\.venv\Scripts\python.exe scripts/configure_jira.py` in your own terminal. Enter the client ID and the secret at the hidden prompt. The helper updates ignored root `.env`, preserves other settings, generates a random 32-byte encryption key only when absent, and retains an existing valid key. It does not display credentials or change demo mode.
4. Provider connections are intentionally blocked when `PUBLIC_DEMO_MODE=true`. Enable a private local environment explicitly before connecting; do not use this change as public-demo isolation. The default demo remains protected. No live issue write follows from account connection.
5. Recreate local processes with `docker compose up -d --force-recreate api worker` after configuring their environment. Keep the existing database volume. No database reset is needed.
6. Sign in as a workspace owner, open Connections, and choose Connect Jira. After consent, M2O returns to that workspace's Connections page.
7. Choose Find authorized Jira sites, select the intended site and enter its actual space key. Hamza reported `https://m2o.atlassian.net` and `M2O`; the backend independently verifies the granted cloud ID and project details. This verifies project visibility, not every eventual create/update permission or required issue field.

Never paste tokens or client secrets into chat, frontend variables, screenshots, tracked files, or command arguments. Back up the provider encryption key separately under operator-controlled secret storage; losing or replacing it makes stored credentials unreadable. Automatic key rotation is not implemented.

## Data and authorization boundaries

- A provider connection belongs to one application user. Atlassian account-level credentials are shared across that user's explicitly connected workspaces, so each workspace does not keep a competing copy of the same rotating refresh token.
- A destination belongs to a membership and a connection owned by the same user, enforced by composite foreign keys. Owners see/manage their own connection; another owner does not inherit their credentials. Team-delegated publication authority is not implemented by this account flow.
- AES-GCM encrypts access/refresh credentials with a fresh nonce and authenticated connection/provider/user context. APIs expose connection state and destination metadata only.
- OAuth state is random, hashed, session-bound, workspace-bound, expires after ten minutes and is consumed once. Callback cancellation also requires valid state. Current user/membership authority is rechecked before token exchange.
- A per-user lock and connection row lock serialize account changes and refresh across workspaces. Rotating credentials commit before subsequent resource requests; a failed later request cannot roll back the refresh token replacement.
- Reconnecting invalidates all previous destination selections attached to that user's Jira connection and advances their versions. Each workspace must reverify its site/project because the consenting account or grants may have changed.
- Workspace disconnect deletes its binding and pending consent. Last-binding disconnect deletes locally stored credentials. Local disconnect does not revoke the remote Atlassian grant; users can revoke it in Atlassian connected-app settings.
- Transient failures retain safe errors. Definitive refresh rejection clears stored credentials and marks reauthorization required. No provider POST is blindly retried. Read discovery uses fixed Atlassian API endpoints, not submitted site URLs.

## API contract

All workspace routes use `/api/workspaces/{workspace_id}/integrations/jira` and require current membership. Mutations require CSRF/Origin verification for browser sessions. Owner authority and non-demo mode are required to connect/discover/select; disconnect remains available in demo mode or when configuration is missing, for the current owner of the connection.

| Method/path | Behavior |
| --- | --- |
| GET base | Returns `configured`, `can_manage`, `state`, destination version and verified destination metadata. No provider request. |
| POST `/connect` | Returns the official consent URL; requires a live browser session. |
| GET `/sites` | Refreshes credentials if needed; returns sites granting both required scopes. |
| POST `/destination` | Strict body: `resource_id` UUID, uppercase `project_key`, integer `expected_version`. Checks the site grant and project, then saves the selection. Stale version returns 409. |
| DELETE base | Disconnects only the acting user's binding for this workspace. |
| GET `/api/integrations/jira/callback` | Validates bounded state/code/error query fields and session, consumes consent once and redirects to the originating workspace. |

Scopes do not replace Jira permissions. Issue types, supported required fields, exact proposals and queued delivery are documented in JIRA_DELIVERY.md. Assignee/user mapping remains unimplemented; unsupported required fields block delivery.

Sources: [Atlassian OAuth](https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/), [Jira project API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-projects/).
