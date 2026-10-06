# Sequential workflows and trustworthy state

## Decision map

Write persona → task → decision → required information. Make primary stages deliberate routes or addressable states. Keep advanced metadata, evidence, provenance and history available without making them prerequisites to every click.

A smaller visible step count may hide subviews but must not combine business approvals. Review/Deliver can contain a review editor and an exact handoff subview while retaining separate commands and receipts.

Inventory deep links, history, query state, callbacks and dirty guards before changing routes. Decide which old URLs remain aliases. Test direct entry, reload, Back/Forward and rejected navigation.

## State ownership

| State | Owner | Consequence |
| --- | --- | --- |
| Unsaved values | Current editor | Retain on validation/conflict; ask before discarding meaningful work |
| Review/version/permission | Backend/domain | Optimism cannot bypass current authority or versions |
| Exact preview | Server proposal or scoped local artifact | Bind to selected versions, source, destination and disclosure |
| Delivery result | Durable operation/receipt | Queue acceptance and refresh are not proof of delivery |
| Personal execution | Per-user plan | Do not auto-complete from review/provider status |
| Motion/layout preference | Non-sensitive client preference | Do not store credentials/recovery links alongside it |

Adapt these categories rather than creating unnecessary stores/services.

## Async fences

Cancellation is insufficient: a result may finish after the client changes screens. Compare request/current workspace, meeting, source versions, selected IDs, visibility, destination and relevant choices.

Track a stage generation when departure invalidates a response. Comparing only a stage name fails if the user leaves preparation and returns before an older request finishes. Do not force navigation after departure.

If a mutation succeeds but its refresh fails, retain accepted-state feedback and read-only recovery rather than presenting it as never performed.

## Refresh and expiry

Preview deep links must restore a persisted proposal or explain regeneration. A URL is not approval. Download receipt means the browser was asked to save unless completion is observed.

Invalidate previews on source, revision, visibility, selection, credential generation, destination or authority change. Backend rechecks remain mandatory. Preserve uncertainty after lost provider responses; a failed history read does not establish rejection.

## Record identity

Matching titles are not duplicates. Inspect IDs, timestamps, provenance and revisions. Prefer server-scoped title/ID search and stable pagination; client search must identify its subset.

Grouping can summarize loaded records without deleting/merging/relabeling them. Merge repeated pagination results by actual identity only, never title.

## Roles and shell

Navigation explains authority; it cannot grant it. Private and visitor capabilities remain distinct. Preserve privacy-status/recovery routes when normal lists exclude a frozen scope.

Collapsible chrome needs reopen controls outside the region, hidden/inert closed content, expanded state and focus restoration. Hiding header and sidebar must not strand the user. Reduced motion removes decoration without removing controls.
