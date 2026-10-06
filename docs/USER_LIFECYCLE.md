# M2O public exploration and invited private use

Updated October 5, 2026. This guide describes the implemented backend lifecycle. Browser integration, shared runtime activation and deployment are separately verified in USER_LIFECYCLE_ACCEPTANCE.md. No email transport or automatic external invitation is configured.

## Authority and storage

Each public explorer gets a unique visitor account, session and three synthetic department workspaces. The server supplies the Engineering, People Operations, Finance Control and no-outcome examples. Loading an example twice opens the same persisted meeting. Visitors can confirm seeded people, review/edit outcomes, build their own daily plan and export reviewed handoffs. They cannot upload arbitrary transcripts, create a custom directory, administer membership, obtain API-token access or connect/publish to a provider. These restrictions remain in force when PUBLIC_DEMO_MODE=false.

Visitor jobs use deterministic hash embeddings and rules extraction, with `synthetic_demo_rules` in the result warnings. They never borrow operator model inference or provider credentials. `/api/me` hides operator repository and model configuration. Ordinary invited private accounts retain the configured local AI behavior.

Default visitor lifetime is two hours. Admission is serialized in PostgreSQL with limits of 100 active and 500 retained visitors. Each visitor can commit 200 mutations and enqueue 12 jobs across their three workspaces; duplicate fixture loads and already-pending extraction do not consume another job. Logout remains available after the mutation limit. Expiry revokes access immediately but does not itself erase storage. The bounded operator cleanup described below performs erasure. Quotas and admission controls mitigate storage/computation abuse; they are not a measured load-capacity claim.

Private accounts are created by operator bootstrap or accepted invitations. There is no open signup. Workspace roles remain owner, reviewer, editor and viewer. A scoped API token cannot administer or erase a different workspace, including another workspace owned by the same user.

## Invitation flow

1. An owner creates an invitation with the recipient email and role. M2O returns a link once; the owner manually shares it through an appropriate private channel.
2. The recipient opens `/invite#token=...`. The frontend reads the fragment into memory and removes it before making API requests. The secret is sent in POST bodies, not URL queries, and is never stored as a plaintext database value.
3. A new recipient chooses their own name and password. An existing recipient must sign in to the matching account and accept without a password field. An invitation cannot overwrite an existing global password.
4. Membership and single-use consumption share a transaction. New recipients sign in afterward; accepting a link does not automatically log them in.

The default link lifetime is 48 hours. Revocation, expiry, repeated acceptance, changed issuer authority, owner password recovery and wrong recipient/session are denied. Acceptance locks the issuer and existing recipient accounts in sorted ID order, then checks the current browser session before membership is granted. Creating another pending invitation for the same recipient invalidates the older link. A workspace can have at most 30 unconsumed, unexpired invitations.

Legacy `POST /members` now returns 409 and directs callers to invitations. Owner-set passwords and membership grants without recipient acceptance are deliberately discontinued. Role changes still use expected current authority and retain an active owner.

HTTP contracts, where ROOT is `/api/workspaces/{workspace_id}`:

| Method and path | Body | Result |
| --- | --- | --- |
| POST ROOT/invitations | `{email, role}` | 201: summary, `workspace_name`, one-time `accept_url`, `delivery: manual` |
| GET ROOT/invitations | none | Latest 50 summaries; no secret link returned |
| DELETE ROOT/invitations/{id} | none | Revoked summary; accepted memberships are handled separately |
| POST /api/invitations/inspect | `{token}` | Workspace name, recipient email, role, expiry, `requires_sign_in` |
| POST /api/invitations/accept | `{token,email,name?,password?}` | Workspace ID/role, `account_created`, `sign_in_required` |

## Operator-assisted recovery

The public request endpoint gives the same manual-recovery instructions for known and unknown email addresses. It does not send email or issue a public reset token. The operator must independently verify the account holder's identity before running the local helper.

From the backend directory, using the installed virtual environment:

```powershell
.venv\Scripts\python.exe -m scripts.issue_recovery
```

Enter the verified private email locally and type `VERIFIED`. The helper stores the expiring link in `backend/.runtime/recovery-<random>.txt`, which `.gitignore` excludes. It prints the file path, never the secret link. Open the file locally and share it privately with the verified holder. The file is protected with mode 0600 on POSIX; Windows relies on the existing workspace/user-directory ACLs. Remove the private file after delivery. This command was tested with synthetic temporary files; it has not been run against a real account during this increment.

The fragment route is `/recover#token=...`. `POST /api/auth/recovery/reset` accepts `{token,email,password}`. A token expires after 30 minutes, is bound to an account/authority generation and is single-use. A successful reset does not sign the user in automatically.

Reset commits a new account authority generation before child cleanup can wait for locks. Old browser sessions, scoped tokens, queued/running jobs and Slack identity mappings then fail generation checks. Old owner invitations also fail. Old session/API/OAuth rows are removed, and queued old-generation jobs are cancelled with safe receipt state. New credentials or jobs issued under the new generation remain valid. A provider request already accepted outside M2O cannot be withdrawn; its confirmed or uncertain receipt is retained rather than resending.

## Export and local erasure

Account export returns the signed-in user's profile, memberships, personal plans and own LinkedIn drafts. Workspace export requires a current owner and includes transcript revisions, evidence, outcomes/review history, directory records, sanitized delivery receipts and audit provenance. It excludes provider ciphertext, credentials, OAuth/session secrets and other people's personal plans. Browser workspace export is bounded to two million stored transcript characters; larger exports require the documented operator database-backup procedure. All export responses use `Cache-Control: no-store`; downloaded files remain the user's responsibility.

| Method and path | Purpose |
| --- | --- |
| GET /api/privacy/account/export | Signed-in browser account export |
| GET ROOT/privacy/export | Owner workspace export, including archived content |
| GET ROOT/privacy | Name/version, active or pending-erasure state and retention information |
| POST ROOT/privacy/erase | `{password,confirmation_name,expected_version}` |
| POST /api/privacy/account/erase | `{password,confirmation: DELETE MY ACCOUNT}` |

Workspace erasure requires password confirmation and the current exact name/version. It first commits a scope freeze so new requests/jobs cannot act. Cleanup acquires job rows afterward, avoiding holding account locks while waiting for a worker. If a running lease or active worker lock remains, the response is 202 `pending_erasure`; content remains frozen. The owner can still read ROOT/privacy and retry with the returned version through the known workspace ID. Once workers settle, erasure removes transcripts/chunks/embeddings, extracted and review records, every user's plans for those outcomes, local drafts/proposals, jobs, directory, invitations, scoped tokens/bindings and raw audit details. It does not delete provider content.

An erased workspace retains an opaque ID, department and erasure timestamps; its name becomes `Erased workspace`. Delivery retention records hold provider/operation IDs, delivery and payload hashes, effect state and whitelisted resource coordinates. They do not contain approved bodies, transcript evidence, arbitrary error text, grant ciphertext or original destination names. Known effects have a minimum 90-day retention. **Uncertain or sending effects are excluded from automatic deletion until an operator explicitly resolves or accepts the uncertainty.** Remote Jira issues, GitHub issues, Slack messages or LinkedIn posts require separately authorized provider actions to remove.

Account erasure deactivates and anonymizes the account, revokes its credentials/session/token/Slack mappings, removes own plans/profile and redacts own LinkedIn drafts/proposals. Other collaborators' meetings and shared review/audit actor references remain. A sole active owner must hand off ownership or erase the workspace first. This is not a promise to remove the person's words from all collaborative transcripts, remote tools, downloaded exports or backups. Shared content follows the owning workspace's lifecycle. Workspace erasure preserves a provider grant when another active workspace explicitly uses it; unused associated grant ciphertext is cleared under a connection-row lock. New LinkedIn publishing consent and explicit use record a workspace association. Historical personal consent with neither a workspace binding nor publication provenance remains account-owned until reconnect, disconnect or account erasure; the missing historical association cannot be inferred safely.

Private editors/viewers can revoke their own LinkedIn publishing credential through workspace DELETE `/integrations/linkedin/publishing`; publishing roles are still required to connect or publish. A removed member uses browser-only `DELETE /api/integrations/linkedin/publishing` to revoke their own account-wide grant. CSRF and current account generation still apply; scoped API tokens, visitors and unauthenticated calls cannot use the account-wide route. No input selects another person's credential. This deletes local ciphertext and pending consent state, with no remote provider request.

## Bounded retention maintenance

First inspect a dry-run report from the backend directory:

```powershell
.venv\Scripts\python.exe -m scripts.privacy_retention --limit 20
```

After reviewing the target environment and obtaining authorization for its data removal:

```powershell
.venv\Scripts\python.exe -m scripts.privacy_retention --limit 20 --apply
```

The maximum batch is 100. Expired visitors are frozen, their synthetic workspaces are purged, and their account/session rows are removed after workers settle. Unexpected shared/private memberships are reported as protected and left untouched. Pending worker effects retain the visitor until a later run can finish. Expired temporary security records and eligible known/resolved delivery records are separately bounded. This is an operator command, not a claimed scheduled task; no automation was installed.

For an unresolved retention record, inspect its effect manually and preview an explicit decision:

```powershell
.venv\Scripts\python.exe -m scripts.privacy_retention --resolve RECORD_UUID --resolution accepted_unknown
```

`RECORD_UUID` is an unmistakable placeholder for the actual retention record ID. Choices are `confirmed`, `not_sent` or `accepted_unknown`. Applying requires `--apply` and typing the exact ID at the prompt. The decision is stored with a timestamp, and a fresh minimum retention period begins. This command does not query, publish or delete anything at a provider.

Backups have their own retention and access policy. Applying local erasure does not rewrite existing backups. Before restoring one, the operator must preserve/reapply the latest erasure and revocation records so deleted data or grants are not silently reactivated. Durable private hosting still requires an approved backup/restore and retention policy; Render Free is not evidence of those guarantees.

## Focused verification

From backend, with PostgreSQL configured, the tests create and remove randomly named disposable schemas rather than upgrading the shared application schema:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_visitors.py tests\test_invitations_recovery.py tests\test_privacy.py tests\test_retention.py tests\test_slack_migration.py tests\test_worker_delivery_authority.py -q --postgres --tb=short
```

The tests cover two-browser isolation, CSRF/origin, visitor/token/worker expiry, admission races, deterministic demo extraction, invitation replay/identity/issuer checks, forced reset/acceptance overlap, session/job generation revocation, erasure freeze/resume, private/token scope, minimum uncertain retention and preservation of another workspace's data/grants. Final results and integrated browser evidence belong in USER_LIFECYCLE_ACCEPTANCE.md; do not infer deployment or live provider behavior from synthetic checks.

Observed broad backend verification on October 5: `python -m pytest -q --postgres --tb=short` completed **349 passed, no skips, in 351.59 seconds**. The native SQLite run completed **327 passed, 22 PostgreSQL-only skipped**. Scoped Ruff check/format and backend Pyright passed. The later account-wide publishing-disconnect correction passed **two shared HTTP PostgreSQL regressions**; Phase 4 reported **nine focused native service/HTTP tests** passing. These overlapping local results do not establish hosted release readiness.
