# M2O experience V2 — approved change and verification contract

October 5, 2026. Hamza requested a simpler sidebar, fewer primary meeting steps, Google Meet transcript import, and a playful celestial outcome calendar. This records the new authorized implementation scope; it is not a completion or live-provider claim.

## Navigation and workflow

The user said three options but named four. Implement four primary destinations: **My day, Meetings, Audit, Settings**. My day owns personal execution, Meetings owns source/review/handoff workflows, Audit shows permitted change history, and Settings contains addressable People, Connections, Privacy & data, Access, and Motion sections. Preserve current role/workspace/visitor boundaries and legacy links.

Meeting stages become **1 Transcript → 2 People → 3 Review & Deliver → 4 Calendar**. Review and handoff are compact subviews of stage 3; review approval and exact external-delivery approval remain separate explicit actions. Combining screens does not combine authority, state, payload versions or delivery intent. Older `/review` and `/share` links continue to work as stage-3 subviews.

Each stage should occupy a deliberate full-page workspace. Supplementary evidence, history and controls collapse smoothly rather than creating a long form. Header and sidebar have accessible, persistent expand/collapse controls, visible reopen handles, focus management and mobile touch support. Motion is optional through calm mode and system preferences.

## Meeting-list finding

Read-only inspection of the screenshot's Engineering delivery workspace found **36 Release readiness records, 36 distinct database IDs and 36 distinct slugs**. These are separate saved records sharing a title, not one React card duplicated. Recent creation timestamps include October 3 and October 5; the creation source of every legacy record is not proven. No records are deleted, merged or relabeled as tests without evidence and authorization.

Use existing created/updated timestamps, actual meeting dates where available, short stable identifiers, bounded list navigation, search and optional title grouping to disambiguate. Never deduplicate by title. Repeatedly loading a private synthetic example into a newly generated meeting is different from reopening a persisted example; the UI should make that distinction clear.

## Constellation calendar

The user explicitly selected **all reviewed meeting outcomes**, not only items chosen for My day. Show all approved kinds in the current transcript revision, with current-meeting focus and an optional permitted workspace overview. Respect restricted meetings even in aggregate counts.

Only an explicitly reviewed `due_date` places an outcome on a day. Unscheduled outcomes stay visible in a separate constellation/card cluster, with literal unresolved hints retained. Do not infer Friday/Monday, substitute a meeting's creation date, or silently use personal `planned_on` as a shared deadline. Confirmed directory owners get their actual names; missing/unconfirmed ownership is Unassigned. Personal plan state remains separate and belongs only to the current user.

The visual treatment uses an original lunar/arcana atmosphere: chronological date points, person/outcome stars, connecting arcs and dimensional detail cards. Motion can celebrate actual confirmed saves, never fabricated publication/completion. Every visual has a keyboard/touch-operable equivalent and an accessible agenda; date-only values must not shift a day through UTC conversion. Crowded days need grouped counts and expandable detail rather than overlapping labels. No required drag-only actions or forced speed-review mechanics.

## Google Meet import

Human availability: **meetings currently do not generate transcripts, and no Google Cloud OAuth app exists for M2O**. The implementation must be a real configurable integration with honest setup/absent/pending/error states, not a fake successful import. Live activation remains dependent on the user's eligible account/settings, generated transcript, app consent and privately configured credentials.

Place **Import latest Google Meet transcript** beside transcript upload. Connect an invited private user's own read grant; visitors cannot import real data. Fetch the latest accessible conference by documented descending start time and explicitly handle active/missing/pending transcripts without silently selecting an older conference. Gather every ready transcript session/page and participant label within documented hard limits. Reject partial, over-limit, invalid, expired and looping results rather than truncate. Google participant labels are source provenance, not confirmed M2O identity.

Use a preview and explicit save, actor/workspace/auth-generation/connection binding, content hashes, short expiry and transactional reimport idempotency. Unchanged sources reuse the existing authorized meeting; changed content does not overwrite reviewed revisions automatically. Keep source conference and transcript resource identities rather than reusable meeting codes. Ensure preview/raw-content cleanup, account/workspace erasure and other-workspace grant preservation. Do not hold authority locks across bulk read fetches. The accepted implementation bounds the whole preview operation to 25 seconds, bulk reads to 20 seconds and individual provider requests to 10 seconds, within the current 30-second proxy timeout. A timeout returns 504 without storing a partial preview or meeting. See [Google Meet import](GOOGLE_MEET_IMPORT.md) for the implemented contracts and setup requirements.

Minimal Meet read scope is `meetings.space.readonly`; Drive read scopes are unnecessary for entry import. API entries can differ from edited Docs and expire 30 days after conference end. OAuth Testing refresh-token lifetime and revoked grants must have explicit reconnect states. No Cloud app creation, provider writes, credential disclosure or external communications are authorized by implementation.

## Visual research and assets

Named references: gentlerain.ai, remove.bg, ZType, The Real Size (exact site clarification pending), Species in Pieces, Kahoot and Hades II. These are interaction/visual references, not all installable frameworks. Research rendered behavior where text extraction cannot show it. Useful directions include confident stage transitions, meaningful immediate feedback, clear foreground cutouts, low-polygon transformations, readable comparison/scale and lunar constellation navigation. Document actual observations separately from hypotheses.

Use original high-quality assets and existing dependencies where possible. Do not upload private images/transcripts to remove.bg or copy game/site art. SVG/CSS is suitable for real interactive calendar geometry; original raster illustrations may support atmosphere. Keep real data/evidence legible, limit asset weight, pause background motion, and test both phone and desktop. Department themes remain equally developed.

## Ownership and gates

- Phase 3: backend calendar/import contracts, typed validation, shared models/migrations/worker/security/privacy, setup guides and backend tests.
- Phase 5: all frontend navigation, stages, settings, meeting list, calendar, import interface, collapsible chrome, graphics and frontend/browser tests.
- Phase 4: independent primary-source provider/lifecycle/preview review; no overlapping edits unless assigned.
- Coordinator: source/data diagnosis, this contract, research/asset coordination, independent acceptance, runtime scheduling and final documentation.

Required evidence: no title-based data loss; legacy URLs and Back/refresh/dirty guards; exact review/delivery source/hash/visibility checks; all approved calendar kinds with undated/stale/restricted/confirmed-person cases; Google no-transcript vs pending vs expired, all pages/sessions, reconnect/revoke/erase, duplicate/concurrent reimport and no partial save; header/sidebar focus and mobile geometry; reduced motion and actual saved-state animation; Docker assets, current migrations and real API/worker/browser acceptance. Existing passing counts are historical until affected current changes are verified.

## Primary references

- [Meet authorization](https://developers.google.com/workspace/meet/api/guides/authenticate-authorize)
- [Conference ordering and filters](https://developers.google.com/workspace/meet/api/reference/rest/v2/conferenceRecords/list)
- [Artifacts and retention](https://developers.google.com/workspace/meet/api/guides/artifacts)
- [Transcript states](https://developers.google.com/workspace/meet/api/reference/rest/v2/conferenceRecords.transcripts)
- [Transcript entry pagination](https://developers.google.com/workspace/meet/api/reference/rest/v2/conferenceRecords.transcripts.entries/list)
- [Google transcription availability](https://support.google.com/meet/answer/12849897?hl=en)
- [Hades II official showcase](https://www.supergiantgames.com/games/hades-ii/)
