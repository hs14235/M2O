# Integration groundwork

The core product prepares reviewed meeting outcomes independently of their eventual destination. A destination adapter translates approved versions into the target provider's contract. Participant context is a separate responsibility; a LinkedIn connection does not publish outcomes or resolve arbitrary transcript names.

## Implemented capabilities

| Provider | Current behavior | Verification boundary |
| --- | --- | --- |
| Local handoff | Server-checked Markdown/JSON exports of selected approved outcomes, with revision/version checks and evidence opt-in. | Synthetic backend and browser tests; no external account needed. |
| GitHub | Exact stored issue previews, reviewer approval, destination allow-list, persisted worker jobs, duplicate markers and uncertain-response reconciliation. | Synthetic adapter tests and local preview journeys. Live publication remains unverified. |
| LinkedIn | Consenting account OIDC connection, minimum profile retention, signed-token/state validation and disconnect. | Signed synthetic token/HTTP tests. Live approval/credentials remain unconfigured. |
| Jira | Owner-owned OAuth, verified destination, bounded field discovery, exact approved create/update, queue, receipts and reconciliation. | Synthetic provider verification only; live consent/writes unverified. Demo blocks access. Unsupported required fields block delivery. See JIRA_DELIVERY.md. |
| Slack | The capability catalog reports unavailable. No Slack request is made. | No Slack adapter is implemented. |

The frontend asks for a destination only in Share. The Connections page exposes the server's capabilities. Local handoffs are the default, so reviewing a meeting does not depend on a GitHub repository. The catalog supplies one typed frontend boundary; it does not imply that each listed provider has a working adapter.

## Provider-independent handoff

The local JSON envelope contains `schema_version`, meeting identifier/title/revision, department and outcomes. Outcomes retain their ID and reviewed version, type, title, details, labels, confirmed owner, explicit calendar date or unresolved date hint, and evidence references. Raw evidence is opt-in. The export endpoint locks the meeting and verifies the exact selected approved versions before producing an artifact. It is a snapshot of the review at preparation time, not a live document.

## Adding Jira or Slack

The next adapter must consume this reviewed domain data without embedding provider-specific rules into extraction or review. Its implementation needs:

1. Operator-managed credentials or approved OAuth access; secrets stay on the backend. The UI selects permitted destinations, never accepts a secret.
2. Validated destination identity: Jira site/project/issue type or Slack workspace/channel. Workspace membership does not automatically grant access to an external destination.
3. A stored exact payload preview bound to provider, destination, transcript revision, selected outcome versions and evidence policy. A provider switch must invalidate any existing preview.
4. Reviewer approval of that snapshot, a durable worker operation, audit history, and provider-specific retry/idempotency handling. An ambiguous write must not be blindly replayed.
5. Controlled HTTP tests for invalid credentials, missing scopes, destination denial, rate limits, provider errors, duplicate delivery, stale approvals and cancellation; then an explicitly authorized live test.

Jira Cloud issue creation requires project/issue-type fields and its documented rich-text representation. See [Jira's issue API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/) and [Atlassian Document Format](https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/). Slack message delivery requires an allowed channel and a token with the appropriate message-writing scope; formatting and rate limits need Slack-specific handling. See [Slack chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/). Jira's implemented subset and limits are documented in JIRA_DELIVERY.md; these remain requirements for the future Slack adapter and additional field mappings.

LinkedIn's ordinary [OpenID Connect product](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2) supplies the consenting member's basic profile. It does not provide arbitrary name search, career-history enrichment or identity verification. Workspace directory context remains explicitly supplied and confirmed.

## Transcript sources

Zoom/Meet import would be a separate upstream adapter: authorized source artifact → normalized text and provenance → existing transcript revision/indexing service. It must not bypass meeting visibility or send outcomes directly to a destination. The current import scope remains pasted text and UTF-8 text/Markdown files.
