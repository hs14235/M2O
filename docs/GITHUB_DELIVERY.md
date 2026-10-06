# GitHub delivery contract

Implementation checkpoint: October 4, 2026. This describes local source behavior and synthetic verification; live GitHub access or issue publication has not been exercised in this increment.

## Authority and preparation

The backend operator configures `GITHUB_TOKEN` and `GITHUB_ALLOWED_REPOS`. A workspace owner must also bind one allowed repository through `POST /api/workspaces/{workspace_id}/integrations/github/destination` with `{repo, expected_version}`. First binding uses version zero; subsequent changes require the displayed version. This is an operator-token integration, not a GitHub App installation or individual OAuth flow.

`GET /api/workspaces/{workspace_id}/integrations/github` reports configuration, current binding, and separate management/publication capabilities. A configured token alone does not authorize workspace delivery. Viewers cannot prepare or approve; editors prepare; owners/reviewers approve. Demo mode blocks provider writes. The shared private-scope guard also denies visitors/demo workspaces independently of global demo mode; visitor readiness hides operator configuration and destination names. Expired/revoked authority blocks queued delivery. Local visitor previews omit private destination bindings.

`POST /api/workspaces/{workspace_id}/meetings/{slug}/preview` selects approved current outcome IDs. Include `expected_versions` and `expected_destination_version` to reject stale selections. Evidence is omitted by default. Restricted meetings require `external_disclosure_confirmed: true`; that acknowledgment is stored and rechecked. Offline previews can be prepared without a binding, but private approval requires a current binding.

The stored preview binds the repository, destination ID/version, exact issue payloads, reviewed source versions and transcript revision. Approval supplies that preview's hash to `/proposals/{id}/approve`. Reapproval returns the existing operation/job. Sending does not change outcome approval or personal-plan progress.

## Results and conflicts

`GET /operations/{id}` and `GET /meetings/{slug}/deliveries/github` recover workspace-visible receipts. Each batch result includes its source item/version/revision. Later items are `not_attempted` when an earlier result stops the batch.

| Result | Meaning | Automatic behavior |
| --- | --- | --- |
| `created` | A canonical issue receipt and returned title/body/labels/assignees match the approved request. | Continue the batch. |
| `existing` | One marked issue has matching current content. Open/closed status is independent. | Continue without another POST. |
| `conflict` | A verified issue exists, but its content differs or necessary comparison fields are missing. `provider_effect` records `created` or `existing`; number/URL are retained. | Mark delivery failed, stop the batch; never overwrite or resend. |
| `uncertain` | Write intent exists and the provider did not establish a reliable effect. | Stop; never resend automatically. |
| `rejected` | The provider explicitly rejected the reviewed request. | Stop; no automatic retry. |

GitHub may silently drop labels/assignees when repository access is insufficient. A 201 response therefore does not establish exact content equality. Comparison requires exact title/body and case-insensitive sets of label names and assignee logins. It intentionally excludes external workflow status, timestamps and comments. A receipt records delivery-time observation; it is not continuously refreshed external status.

The marker identifies workspace/repository/outcome/version, rather than including a mutable payload option. Changing evidence options cannot justify creating a second issue for the same marked outcome. If another proposal finds changed remote content, it exposes a conflict instead of treating resource existence as exact delivery.

## Reconciliation and failure bounds

`POST /operations/{id}/reconcile` is a read-only provider check for authorized uncertain operations and failed operations containing conflicts. It requires the original current destination. It resolves only exact matching marked content; neither absence nor mismatch allows another write. For an interrupted batch, checking a delivered issue does not send its remaining unattempted items.

The scan includes closed issues, excludes pull requests, detects multiple matches across pages and validates issue URLs against the requested repository on `https://github.com`. It stops at 100 pages or 30 seconds; an incomplete scan fails closed. Offset pagination is not a provider snapshot, so concurrent remote mutation remains a limitation. M2O does not claim globally exactly-once GitHub effects.

The fixed API origin, 15-second request timeout, explicit 201 handling, disabled automatic retry and durable write intent bound failure behavior. Revoked roles, changed source/destination versions and recovery leases are rechecked by the worker. External issue updates and completion synchronization are separate, unimplemented capabilities.

## Verification

Run from `backend` with the existing environment:

```powershell
.venv/Scripts/python.exe -m pytest -q tests/test_github_adapter.py tests/test_github_destinations.py tests/test_publication.py --postgres
```

PostgreSQL tests use isolated disposable schemas; provider responses are synthetic. Runtime database migration and live provider calls require separately authorized execution. See [cross-phase review](CROSS_PHASE_REVIEW.md) and [parallel ownership](PARALLEL_IMPLEMENTATION.md).

Protocol references: [GitHub issue endpoints and access requirements](https://docs.github.com/en/rest/issues/issues), [API version policy](https://docs.github.com/en/rest/about-the-rest-api/api-versions).
