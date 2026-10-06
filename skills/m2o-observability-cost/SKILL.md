---
name: m2o-observability-cost
description: Plan and implement authorized M2O privacy-safe diagnostics, monitoring, operational recovery and free/paid cost scenarios for Phase 9 and later maintenance. Use for operational measurements or integration due diligence, not unrelated vendor shopping.
---

# M2O operations, observability and cost

Locate the current repository and inspect its contracts and dated verification. Read backend/app/observability.py, jobs/worker, pooling, privacy/retention and runbooks before proposing tools. Paths are repository-relative. Read docs/OPERATIONS.md, SECURITY.md, USER_LIFECYCLE.md and current Phase 9 planning as relevant; proposals are not accepted decisions.

Begin with the operator question/action: unavailable API, old queued work, exhausted pool, storage/admission capacity, revoked grant, uncertain write, migration failure or database expiry. Existing logs/health checks may suffice. Audit history records accountable product actions; diagnostics explain operation. Neither replaces the other.

Specify low-cardinality metrics and safe correlation: request latency/errors, queue age/lease recovery, pool usage, storage and budgets. Define proposed thresholds, sampling, retention, alert recipient/owner and failure handling. Exclude transcript bodies, tokens, cookies, OAuth codes, private names/email and full provider responses. IDs may also be personal data; justify access/retention. Review data flow before session replay, third-party export or tracing propagation.

Respect platform sleep; do not add keep-alive traffic to evade tier limits. Separate cold start, warm response, queue wait, extraction and provider duration. Measure before promising objectives or changing architecture. Bound buffering/cardinality so diagnostics cannot exhaust M2O.

Trace idle worker database polling before assuming a serverless database will scale to zero or fit compute-hour allowances. Verify current cadence, active duration and connection behavior; low visitor traffic is not the same as low database activity. Inspect every logger/exporter channel before export: use route templates or scrub raw URL paths and query/referrer fields. SDK setup does not authorize source-map/source uploads, replay or outbound reporting; review those disclosures separately and verify sanitization with synthetic canaries in actual outbound payloads.

Research a bounded shortlist using current primary documentation. Compare existing tools/no addition, free demo, minimal durable private hosting and growth scenarios. Each option needs purpose, compatibility, region/retention, scopes/secrets, limits/prices/date, assumptions, egress/storage/build/seat charges, upgrade triggers, spend controls, maintenance and exit path. Free software is not free hosting/operation; unknown usage cannot yield a precise bill.

Provider synchronization requires version ownership, conflicts, stale/duplicate events, revocation, reconciliation and uncertain-write rules first. Webhooks/streams do not establish consistency by themselves.

Give Hamza sources and a research checklist before adopting services in the requested due-diligence workflow. No accounts, subscriptions, source/transcript/trace uploads, external alerts or provisioning without applicable explicit authorization. Verify approved instrumentation with redaction, bounded cardinality, unavailable-exporter, overhead and recovery tests. Define expiry/backup/restore ownership; a local dump is not off-host recovery. Report measured vs proposed targets and hosted/live gaps.
