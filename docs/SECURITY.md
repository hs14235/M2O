# Security, privacy and provider boundaries

The October 5 lifecycle increment adds independent visitor/workspace expiry, bounded admission/storage/job budgets, private-scope provider guards, email-bound single-use invitation acceptance, operator-assisted password recovery and explicit local erasure. Account authority generations revoke old sessions, API tokens, jobs, Slack mappings and owner invitations. Scope freeze is committed before erasure waits for worker/child locks. See [USER_LIFECYCLE.md](USER_LIFECYCLE.md) for exact implemented boundaries, retained uncertainty, shared content, manual recovery and backup limitations. These controls have local synthetic verification; they do not establish hosted security or a compliance certification.

## Verified application controls

The application is a local workspace product with authorization in both services and adapters. Passwords use Argon2. Session and API token values are hashed in storage and expire. Session cookies are HttpOnly and SameSite; production settings reject an insecure cookie or non-HTTPS application origin. Browser mutations require CSRF and the exact Origin. CORS uses the configured origin, and hosts are constrained.

Workspace roles control every meeting, review, participant, job and audit access path. Restricted meetings are limited to their creator and reviewers/owners. Composite foreign keys prevent cross-workspace ownership and cross-revision citations. Workers recheck active user/membership before committing or sending. Tests exercise unauthorized access, revoked roles, scoped tokens, last-owner protection and stale review conflicts.

Input contracts reject unknown properties and bound strings, lists and enums. Uploads are text-only, UTF-8 and byte-bounded. SQLAlchemy uses bound parameters and hides SQL parameters in database exceptions. Safe error handlers omit submitted values and internal exception messages. Structured application logs contain request IDs, safe event names, status and class/code information, not transcript content or credentials.

Nginx uses a self-only content security policy, security headers, no-store API responses, immutable hashed assets and noncached entry HTML. Its access log uses URI without query arguments, so an OAuth authorization code/state is not recorded there. React renders user content as text. API and web containers run as non-root users, and environment/runtime files are excluded from build contexts.

Login quotas use database buckets keyed by hashes of account/IP. Workspace quotas cover expensive indexing/extraction operations across processes. Behind the current reverse proxy, the API sees the proxy IP; do not blindly trust arbitrary forwarded headers to change that. A production gateway needs its own narrowly trusted IP policy and rate limits. The local defaults are not a validated capacity or abuse-resistance claim.

## LinkedIn connection

The implementation uses LinkedIn's approved **Sign In with LinkedIn using OpenID Connect** product. Default scopes are `openid profile`; `email` is optional in validation but its value is discarded and is not required. Scope configuration rejects unsupported names. No approved application or credentials existed during implementation, so the UI correctly shows the integration as unavailable until configured.

This product exposes the consenting member's own basic profile. It does not grant arbitrary transcript-name search, access to other people's professional history, or identity verification. Other-person profile access is restricted. These limits come from [LinkedIn OIDC documentation](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2) and [its Profile API documentation](https://learn.microsoft.com/en-us/linkedin/shared/integrations/people/profile-api).

The adapter provides:

- A random, hashed, session-bound state with a ten-minute expiry and one-time consumption before exchange.
- A nonce and RS256 ID-token verification against LinkedIn JWKS, including issuer, audience, expiry, issued-at and nonce.
- A subject match between verified ID token and userinfo.
- Fixed official authorization/token/userinfo/JWKS endpoints, rather than transcript-controlled URLs.
- Minimum stored subject/name and granted scope metadata. Access tokens, ID tokens, email and arbitrary userinfo fields are discarded.
- Self-account connection and deletion through authenticated routes. Directory account links can only reference the acting user.

To configure an approved app privately, set `LINKEDIN_CLIENT_ID`, `LINKEDIN_CLIENT_SECRET`, and `LINKEDIN_REDIRECT_URI`. Register the exact callback `/api/integrations/linkedin/callback` on the actual application origin. Remote callbacks require HTTPS. Never place the secret in React, a committed environment file, Codex config, screenshots or logs. Restart API processes after configuration changes. Compose forwards these three fields from its ignored root environment; native development reads `backend/.env`.

Tests use real signed synthetic JWTs and a controlled HTTP transport to exercise token/state rejection. They do not prove live app approval or successful LinkedIn consent. Do not infer missing credentials, request unsupported scopes, scrape public profiles, or describe a manual profile link as API research.

## GitHub publication

Default `PUBLIC_DEMO_MODE=true` blocks publication. Compose deliberately reads `MTT_GITHUB_TOKEN`, so an unrelated global `GITHUB_TOKEN` cannot activate the provider. An explicit repository allowlist is also required. Use a destination-scoped token with the minimum issue permissions when live access is authorized; validate its permissions against the selected repository before use.

Outcomes must be approved before preview. A stored proposal includes exact titles, bodies, labels, assignees and duplicate markers, with selected review versions and transcript revision. Approval requires an unexpired hash and reviewer/owner permission. The worker rechecks current authority and destination settings before sending. It never substitutes an easier payload after a provider rejection.

Raw transcript evidence is excluded from issue bodies by default. A reviewer can explicitly include it and must inspect the resulting exact body and destination. HR/finance content may be private even without obvious identifiers. Local export is also a deliberate disclosure; exported files are not automatically encrypted or uploaded.

Marker searches include closed issues. Ambiguous writes retain an uncertain state and cannot be blindly retried. Reconciliation performs only provider reads. All GitHub verification used controlled synthetic HTTP responses; no live repository issue was created.

## Local inference and retention

Ollama runs locally, and the Compose AI service disables its cloud feature. The model is a computation dependency, not an authorization authority. Transcript instructions cannot grant tool access, choose outbound URLs or publish issues. Generated source IDs must belong to the actual batch. Explicit labeled facts use deterministic preservation, but implicit model extraction still needs human review and evaluation.

PostgreSQL stores raw transcripts, chunk text, outcomes, review history and minimum directory context. Archiving is reversible product behavior and does not erase that information. Backup dumps contain the same data and must remain private. This revamp includes no automatic retention deletion or encrypted-at-rest storage claim. Before processing real organizational data, establish consent, permitted uses, retention, deletion/export ownership, storage protection and backup access for that environment.

Dependency scans found no known vulnerabilities in the final audited Python runtime constraints and frontend tree. Optional semantic-model dependencies and operating-system images were not exhaustively scanned. Package advisory results change over time; rerun audits before a release.

## Before a public environment

Verify HTTPS termination, secure cookie behavior, trusted proxy routing, external provider grants, secret distribution, identity offboarding, MFA/SSO requirements, data retention, backup recovery, alerts, dependency/image scans and representative load. The current password-based local account system and loopback Compose configuration are locally tested foundations, not a complete enterprise identity or operating program.
