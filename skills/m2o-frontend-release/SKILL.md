---
name: m2o-frontend-release
description: Plan and verify M2O frontend journeys, async state integrity, accessibility, performance and developer setup for Phase 7 or later releases. Use for workflow reliability and release acceptance; use Pandora frontend for substantial visual design.
---

# M2O frontend release workflow

Locate the repository and verify source revision and running build separately. Read AGENTS.md, docs/M2O_IMPLEMENTATION_CONTRACT.md and relevant experience/provider contracts. Paths are repository-relative. Read Phase 7 planning if present; proposed choices are not implementation approval. Preserve other chats' ownership.

Map frontend/src/navigation.ts, api.ts, types.ts and affected components. Inspect rendering rather than assuming SSR; the published checkpoint uses React/Vite client rendering. Framework migration needs a concrete benefit and approved scope. For substantial visual work use pandora-frontend when available, or its portable skills/pandora-frontend/SKILL.md copy.

Keep Transcript → People → Review/Deliver → Calendar clear. Preserve My day, Meetings, Audit and grouped Settings unless requested otherwise. Calm/system reduced motion must remove decoration without hiding information. Graphical calendars need readable agenda/evidence paths; never invent owners/dates for appearance.

Trace request ownership through workspace/route changes, stale responses, double clicks, expiry and unmounts. Pending controls improve UX; server version/approval checks establish correctness. Approval is tied to the current exact preview. Personal completion must not change review or provider status.

Exercise affected loading/empty/error/expired/forbidden/stale/uncertain/setup-required states. Make the next user action clear without leaking operator configuration or implying a connection is active. Preserve deep links and unsaved-work behavior according to current contracts.

Inspect package.json and browser fixtures. Run focused component tests, TypeScript and affected real API/browser acceptance. Mocked provider responses prove UI behavior, not live activation. Inspect desktop/mobile output, keyboard focus/reopen, reflow, evidence readability and reduced motion. Automated a11y checks are scoped evidence, not certification.

Measure bundles/media before adding heavier libraries. Verify served assets/caching/MIME/missing-file behavior and current container build when relevant. Old screenshots are not new verification. Fresh-clone demo setup must need no real provider secrets; telemetry/replay must not capture private fields by default.

Present proposed tools with official links, free/paid limits, disclosure and simpler alternatives for due diligence before adoption. Report observed local/hosted results and gaps. Invoking this skill does not authorize publication, provider writes or deployment.

For telemetry, adoption is not blanket permission to create accounts, report runtime data, upload source maps/source, or change build secrets and CI. Inspect actual SDK defaults for URLs, query/hash/referrer, IPs, console, DOM/replay and request bodies. Use synthetic sensitive canaries to inspect outbound payloads and prove sanitization/disabled collection before any private use. In a planning-only assignment, inspect test/build configuration but do not start mutation-producing setup, builds or runtimes unless separately authorized.
