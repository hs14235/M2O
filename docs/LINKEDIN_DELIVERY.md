# LinkedIn drafts and separately authorized publication

Implementation checkpoint: October 4, 2026. Local draft, consent, preview, worker and receipt paths are implemented with synthetic verification. Approved LinkedIn products, live author compatibility and actual publication remain unverified external activation requirements.

October 5 privacy update: consent and explicit authorized grant use now record a workspace association in the existing destination table. Current-workspace readiness requires that association. Scope, membership, workspace and connection are locked/rechecked before associating or storing a returned token. A frozen workspace cannot be restored by a delayed callback, and a cleared token cannot be restored from the SQLAlchemy identity cache.

## Three distinct capabilities

Existing profile context uses OIDC for the consenting private user's own minimal profile. It discards provider tokens and is not identity verification. The account lock serializes callbacks with profile disconnect/erasure; verified cancellation consumes only the relevant challenge. Visitors cannot connect a real profile. Publishing does not broaden or reuse that flow.

Local post/outreach drafts require current approved outcome versions and a manually reviewed text body. They preserve exact text, keep source snapshots, detect stale sources and support version-checked edits. They do not copy transcript evidence automatically. Drafts are meeting/workspace-visible to authorized members, including viewers; they are not private personal notes. Authors and workspace owners/reviewers can edit, while contributors can create their own drafts. Local drafts work without LinkedIn credentials, including the synthetic demo.

Publication is a separate, explicit consent path for a private owner/reviewer's own LinkedIn account. Visitor readiness hides saved author/expiry/configuration, and expired/revoked authority blocks queued posts. It supports a public text-only member post. Outreach is a copyable local draft; automated lead messaging and arbitrary participant-name lookup are unsupported. People Operations, Finance and Engineering can use drafts for an intentionally public process update, while reviewing private names/figures before disclosure.

## Configuration and consent

Enable `LINKEDIN_PUBLISHING_ENABLED` only after the application has appropriate products and permissions. Backend configuration needs `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, `PROVIDER_ENCRYPTION_KEY` and the configured `APP_ORIGIN`. `LINKEDIN_API_VERSION` selects the supported YYYYMM API version (current source default `202609`). Keep secrets in ignored private backend configuration or the approved hosting secret store.

Register these distinct exact callbacks on the actual application origin:

- Existing profile context: `/api/integrations/linkedin/callback`.
- Publishing: `/api/integrations/linkedin/publishing/callback`.

Publishing requests `openid profile w_member_social`. The application needs Sign In with LinkedIn using OpenID Connect and Share on LinkedIn product access; requesting a scope string does not grant it. A public policy, appropriate LinkedIn Page association and actual configured callback are activation dependencies. No deployment origin is assumed here.

Consent validates signed RS256 ID claims, issuer, audience, expiry, nonce and matching userinfo subject. Token introspection must establish an active token for the configured app, the required granted scopes and a future expiry. Optional introspection fields missing from a provider reply cause a fail-closed setup error. The effective expiry is bounded by both the token response and introspection.

Only the access token and consenting member author are encrypted in the provider connection. Secrets and token material never appear in readiness responses. The person URN is derived from the verified app-bound subject; it must be validated against the real approved application during activation. No programmatic token refresh is assumed; expiration or revoked permission requires reconnecting.

Callback, account replacement and disconnect serialize through the user lock. A pending exchange cannot reconnect after disconnect has completed. A valid cancelled/rejected exchange consumes its state. Disconnect deletes ciphertext while retaining historical references. Reconnecting changes the credential generation and invalidates previous publication proposals. Existing OIDC profile context remains independent.

Disconnecting one's own publishing grant does not require permission to publish. Active private editors/viewers can use the existing scoped DELETE; removed members can use browser-authenticated `DELETE /api/integrations/linkedin/publishing` without workspace membership. The account-wide route requires the normal cookie/CSRF checks and denies scoped bearer tokens. It can target only the authenticated user's connection, and clears that personal grant across workspaces. Visitors, inactive accounts and revoked authentication generations are denied. Connect/preview/approval retain owner/reviewer authorization. Scoped revocation records the workspace audit event; account-only revocation persists connection state/time and emits a structured event without fabricating a workspace audit scope.

Workspace erasure removes its association and clears the publishing credential only when no other active workspace binding or proposal still needs it. Explicit private-workspace use associates only a currently valid, freshly locked personal grant; it cannot revive a revoked credential. Account erasure clears the user's grant across workspaces and redacts owned post text/sources while retaining minimal delivery facts. OIDC profile context is account-owned and is removed by profile disconnect/account erasure, rather than by erasing one workspace.

Historical credentials created without a workspace association or proposal provide no reliable workspace provenance. They remain account-owned until explicit reconnect, disconnect or account erasure; M2O does not invent an expiry or assume which workspace owns them. New publishing consent always records an association. Erased drafts with empty source snapshots are stale and cannot produce a publication preview.

## HTTP contract

All scoped routes begin `/api/workspaces/{workspace_id}`.

| Route | Input/result |
| --- | --- |
| `GET/POST /meetings/{slug}/linkedin/drafts` | Create `{kind: post or outreach, text, versions: {item_id: version}}`; list latest 50. Text is nonblank, exact, bounded to 3000 characters. |
| `PATCH /meetings/{slug}/linkedin/drafts/{id}` | Same draft fields plus `expected_version`; stale edit returns conflict. |
| `GET /integrations/linkedin/publishing` | Configuration, consent state, author/expiry and `can_connect/can_publish/can_draft`; messaging/reconciliation are false. |
| `POST /integrations/linkedin/publishing/connect` | Browser session required; returns consent URL. |
| `DELETE /integrations/linkedin/publishing` | Clear the publishing grant and pending publishing state. |
| `POST /meetings/{slug}/linkedin/preview` | `{draft_id, expected_draft_version, disclosure_confirmed: true}`; public post only. |
| `POST /linkedin/proposals/{id}/approve` | `{payload_hash}`; returns 202 with operation/job/state. |
| `GET /linkedin/operations/{id}` | Recover the actor-owned, workspace/meeting-authorized receipt. |
| `GET /meetings/{slug}/deliveries/linkedin` | Latest 50 receipts for the current publishing actor. |

Draft responses include ID/kind/text/version, actor, timestamps and sources `{item_id, version, revision_id, title}` with `source_stale`. Preview responses include the exact post payload, consenting author, PUBLIC audience, pinned API version, source snapshots, hash and expiry. Approval binds that author, credential generation, draft version, source revision and exact payload/version. A changed draft, source, grant or role blocks sending.

Distinct previews of the same workspace/author/draft version share one durable post intent. A completed delivery does not approve outcomes or complete a personal plan. Reapproval never queues a replacement post for the same intent.

## Receipt and uncertain-write policy

The worker records write intent before making one bounded POST to the fixed `/rest/posts` endpoint. A valid 201 plus `x-restli-id` yields `{status: created, post_id}`. No guessed post URL is returned. Explicit rejection yields `failed/rejected`; 401/403 require reauthorization. Timeouts, unexpected status codes and invalid success IDs retain uncertainty; a recovered lease does not repeat the POST.

Posting permission does not establish unrestricted member-post reading. M2O therefore exposes neither automatic reconciliation nor rejected-write retry for LinkedIn. An uncertain result requires human inspection of the LinkedIn account, with no claim that absence of a receipt proves absence of a post. Changing source versions to circumvent that boundary is not a resolution workflow.

## Verification and operational limits

```powershell
# From backend, using the existing environment
.venv/Scripts/python.exe -m pytest -q tests/test_linkedin.py tests/test_linkedin_publishing.py --postgres
```

Checks cover actual-grant validation, signed claims, public disclosure, stale/tampered drafts, browser binding, actor/workspace isolation, HTTP contracts, no resend after uncertainty, credential revocation, OAuth/disconnect ordering, visitor suppression and concurrent approval. Synthetic transports do not prove live product access or posting. The complete retention/deletion lifecycle, operational key rotation and public deployment remain cross-phase release gates.

Primary protocol references: [OIDC](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2), [Share product](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin), [token introspection](https://learn.microsoft.com/en-us/linkedin/shared/authentication/token-introspection), [Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api), [restricted programmatic refresh](https://learn.microsoft.com/en-us/linkedin/shared/authentication/programmatic-refresh-tokens).
