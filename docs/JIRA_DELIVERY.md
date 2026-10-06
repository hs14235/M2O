# Exact Jira outcome delivery

Implemented October 3, 2026: issue-type/field discovery, stored exact create/update proposals, approval, durable queue processing, persistent receipts and uncertain-write reconciliation. Local verification uses synthetic provider responses. Live consent and issue writes remain unverified. Demo mode blocks provider access.

## User pathway

In a private configured environment, connect Jira and verify the workspace destination in Connections. Open a meeting's Share step, select approved outcomes, and choose Jira. Each delivery handles one selected outcome. Choose Create an issue or Update an existing issue, discover issue types or load the existing issue, complete required supported fields, and generate the exact preview. Inspect destination, action and every field before approving.

Title and description come from the current approved outcome. Additional fields cannot override either or the destination. Evidence is opt-in and can contain private meeting details. Rich text uses Atlassian Document Format text nodes. Updates explicitly replace title/description and supplied optional fields; omitted optional fields remain unchanged. A completed delivery does not change review status or daily-plan progress.

Supported controls: plain/rich text, dates, numbers/integers, single options identified by provider IDs, and arrays of plain string values. Required unsupported fields block preview/delivery; optional unsupported fields remain omitted. Parent/subtask, assignee/reporter/user, cascading option, attachment, and plugin-specific mappings are not implemented. Confirmed M2O participants are not silently mapped to Jira accounts. Choose a compatible screen/type rather than fabricating required values.

## Integrity and recovery

Migration `20261003_04` adds Jira proposals/operations and extends the job-kind constraint without replacing existing records. Preview binds the consenting owner, transcript/outcome revision, destination identity/version, action, exact payload and (for updates) remote issue timestamp. Preview expires after 30 minutes. Approval atomically stores operation/job; active account, membership, destination and source are rechecked before sending. Concurrent approval cannot enqueue duplicate operations for the same workspace/outcome version/action/target, even through different owners.

Only the consenting owner can preview/approve/send using that personal grant. Team-delegated publishing is not implemented. Scopes do not replace project permissions or screen/field rules. Discovery uses fixed Atlassian API hosts and bounded complete pagination. Provider response URLs are not used as request targets or receipt links.

The worker durably records write intent before the provider boundary. Timeout, server error, malformed success, or recovered in-flight lease leaves an uncertain receipt and does not automatically resend. A confirmed rejection or failure before sending permits explicit retry after reviewing an identical current preview and selecting the retry option. Prior jobs and audit events remain retained. Ordinary repeated approval returns the existing operation. A completed worker job means processing finished; inspect the operation receipt for delivered, rejected or uncertain state.

For uncertain delivery, inspect Jira yourself and enter the issue key in Verify delivery receipt. M2O verifies the original project and `m2o.delivery` property. A matching marker confirms recorded delivery without resending; it does not establish that nobody subsequently edited the issue. Missing/mismatched marker remains uncertain. No force-resend or destructive reset path exists. Reconnect invalidates destination versions; reconciliation currently requires the original binding/version and can require operator investigation after reconnect/disconnect.

Before updating, M2O compares Jira's `updated` timestamp with the preview. A changed issue is rejected before PUT. Another remote edit can still race between this read and the standard Jira edit request. The UI discloses this limitation; this is not an atomic cross-system transaction. Issue workflow transitions and automatic bidirectional status propagation are outside this increment.

## Workspace API

All paths below are relative to `/api/workspaces/{workspace_id}`. Browser mutations require CSRF/Origin validation. IDs and request bodies are runtime validated.

| Method/path | Behavior |
| --- | --- |
| GET `/integrations/jira/metadata` | Discover types; optional `issue_type_id` loads create fields or `issue_key` loads existing issue/edit fields. |
| POST `/meetings/{meeting_id}/jira/preview` | `JiraPreviewInput`: expected outcome/destination versions, type/action/key, optional additional fields and evidence choice. Stores exact payload/hash. |
| POST `/jira/proposals/{proposal_id}/approve` | Exact `payload_hash`, optional strict boolean `retry_rejected` (default false). Owner-only, non-demo, current preview; returns operation/job IDs. |
| GET `/meetings/{meeting_id}/jira/deliveries` | Latest 50 deliveries belonging to the acting account, with persistent receipts. |
| GET `/jira/operations/{operation_id}` | Stored proposal/receipt; original consenting user plus workspace/meeting access required. |
| POST `/jira/operations/{operation_id}/reconcile?issue_key=...` | Verify an uncertain marker through provider reads. No resend. |

Connection/callback/private credential instructions remain in [JIRA_CONNECTION.md](JIRA_CONNECTION.md). Live application configuration and an explicitly authorized provider-write test remain separate activation steps.

Sources: [Jira issue metadata/create/edit API](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/), [Atlassian Document Format](https://developer.atlassian.com/cloud/jira/platform/apis/document/structure/).
