# Render deployment scope and zero-cost constraints

Selected by Hamza on 2026-10-03: Render Free for now; isolated synthetic demo plus invited private users; local/self-hosted AI remains the inference direction. No Render resources were created or changed. This document records hosting constraints. A synthetic-only container and Blueprint are now implemented locally; no Render deployment has been verified. See [hosted runtime](HOSTED_DEMO_RUNTIME.md).

## Verified platform constraints

Render's [free-service documentation](https://render.com/docs/free) states that free web services sleep after 15 minutes without inbound traffic and take about a minute to wake. Their filesystem is ephemeral and persistent disks are unavailable. Free PostgreSQL expires after 30 days, has no managed backups, and can be deleted after the subsequent grace period. Free background worker services are not offered; the existing dedicated worker cannot simply be assigned a Free plan.

The current Compose deployment uses web/API, a dedicated worker, PostgreSQL and optional Ollama. A Render Blueprint must describe actual Render services; uploading Compose does not reproduce this topology. No domain, region, secret or resource identifier has been invented here.

## Recommended scope under the current budget

Treat an all-Render-Free release as a time-bounded portfolio demonstration using synthetic data. Keep private real-transcript use out of that environment until durable database/backup ownership and operational recovery are established. Do not promise persistent accounts/plan history beyond the free database's lifetime.

Before implementation, select the database persistence path: a temporary Render Free database, a separately verified free external PostgreSQL offering with its own limits, or a future paid database. This choice remains open; no third-party account has been configured.

The existing queue remains PostgreSQL-backed. To fit a single free web service, an explicitly configured supervised worker process could share the container and recover leased jobs after wakeup. That supervisor/startup lifecycle is implemented in `scripts.serve_demo` and has local verification recorded in [VALIDATION.md](VALIDATION.md). Target-platform behavior still requires verification. It would stop when the service sleeps; do not imply always-on processing. A proper paid worker remains the cleaner operational architecture.

Local Ollama is retained. Free-tier self-hosted model memory/CPU and model-file persistence have not been established. A hosted demonstration may need the existing deterministic rules mode, clearly identified as such, while the local run demonstrates real AI. Do not replace local AI with an unapproved cloud provider or present rules as model inference.

## Implemented isolation and remaining hosting work

The isolated visitor flow creates expiring synthetic workspaces with server-enforced authority, quotas and blocked provider actions. Private invitation, activation, operator-assisted recovery and privacy controls are implemented separately. The public deployment must use visitor sessions rather than a shared demo login, contain no operator provider credentials, and use a dedicated synthetic database. See [user lifecycle](USER_LIFECYCLE.md) and dated [verification](VALIDATION.md).

The October 5 prepublication audit identified a hosting availability gate: rate limits use the direct peer IP while proxy headers are disabled. Behind a hosting proxy, unrelated visitors can share budgets. Define and test an explicit trusted-proxy policy or deliberate global admission policy before deployment; never trust arbitrary forwarded headers.

## Release gates

- Finish and test the selected isolation/account flows and supported provider adapters.
- Define the verified single-service or paid-service runtime, migration/bootstrap lifecycle, worker health and failure recovery.
- Confirm HTTPS origin, secure cookies, trusted host/proxy policy and provider callback URLs using the real deployment address.
- Establish database export/restore, retention, expiry ownership, capacity limits and spend controls before private usage.
- Test cold start, interrupted jobs, provider revocation/uncertain writes and model/rules labels in the target environment.
- Measure assets on mobile; decorative video must not block interaction or consume the free bandwidth budget uncontrolled.

No deploy action is authorized merely by selecting Render. Any resource creation/deployment needs the exact account, destination and publication scope established first.
