# M2O-specific application

Use only in Meeting 2 Outcomes. Locate the actual checkout; paths/ports from another task are not current facts.

## Sources of truth

- `AGENTS.md`: permissions, preserved work and invariants.
- `docs/M2O_IMPLEMENTATION_CONTRACT.md`: product breadth and architecture priorities.
- `docs/EXPERIENCE_V2.md`: navigation, merged stage 3, calendar, references/gates.
- `docs/API.md`, `docs/GOOGLE_MEET_IMPORT.md`, provider delivery docs: tested semantics.
- `docs/USER_LIFECYCLE.md`: invitations, recovery, privacy, retention.
- `docs/PARALLEL_IMPLEMENTATION.md`: current ownership/handoffs.
- `docs/VALIDATION.md`, `docs/PHASE_5_REVIEW_FINDINGS.md`: dated evidence, not permanent proof.

## Frontend path

`src/navigation.ts` owns URLs/history/aliases; `App.tsx` owns account/workspace shell. `ShellChrome`/`SettingsPage` handle layout/preferences/settings. `Workbench` connects source/review/delivery/calendar. `MeetingSteps`, `OutcomeCard`, `ShareStep` and composers retain separate commands. `OutcomeCalendar` reads the reviewed feed; `DailyPlanner` owns personal execution. Google Meet is a source import, not a delivery destination.

Inspect styles, original assets, media loading and Docker/Nginx/static wrapper separately. Native `public/` existence does not establish container packaging.

## Invariants

- Jira, Slack, GitHub and supported LinkedIn stay in the ledger; sequencing does not remove one.
- Review approval, external delivery and personal progress are separate.
- Confirm people explicitly; preserve current versions, exact hashes, expiry, destination/credential invalidation and uncertainty.
- Visitors use isolated synthetic workspaces; real upload/grants/administration stay private and scoped.
- Titles are not deduplication authority. Use real IDs/timestamps and server title/slug search.
- Calendar covers current approved kinds, explicit dates, undated hints, confirmed owners/Unassigned, and separate own-plan metadata.
- Latest Meet is latest accessible conference with no older fallback. Save honors visibility/provenance/hash and unchanged-source reuse.

## V2 direction

Primary destinations: My day, Meetings, Audit, Settings. Settings nests People, Connections, Privacy & data, Access and Motion with role boundaries. Stages: Transcript, People, Review & Deliver, Calendar. Legacy review/share links remain stage-3 subviews; approvals stay separate.

Use original celestial geometry and three department identities. Keep compact full-page stages, reversible collapsed chrome, readable evidence, agenda/keyboard/touch equivalents, calm/reduced motion, and finite real-save feedback.

## Reverify changing facts

Credentials/products, transcript availability, Render profile, model default, test counts and composer completion can change. This map is not release proof. Do not change inference defaults without project evaluation or substitute cloud inference for visual convenience.

Check current test launchers and explicit disposable target. Shared runtime refresh, migrations, commits, deployment and provider writes keep their separate authorization boundaries.
