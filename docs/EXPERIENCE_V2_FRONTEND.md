# Experience V2 frontend verification

October 5, 2026. This ledger describes the current local frontend pass. Shared-runtime activation, container acceptance and deployment remain coordinator-owned gates; a native browser check does not establish those results.

## Implemented surface

- Four primary destinations: My day, Meetings, Audit and Settings. Settings contains People, Connections, Privacy & data, Access, and Motion & layout; legacy directory/integration/privacy/access URLs remain supported.
- Four visible meeting stages: Transcript, People, Review & Deliver, Calendar. Review and delivery remain separate compact subviews with distinct approval and exact-preview contracts. Existing review/share URLs remain addressable.
- Header/sidebar collapse preferences persist locally. Reopen controls remain outside hidden regions; hidden content is inert, and focus returns to the outside toggle when needed. Calm and system reduced motion retain the same information and controls.
- Original SVG/CSS constellation calendar shows current approved outcomes of every kind. Explicit reviewed dates determine placement; unresolved hints remain undated. Confirmed directory names and Unassigned are distinct. Personal planned dates/progress remain separate metadata.
- Latest Google Meet import is beside transcript upload. Read preview, expiry, source/participant provenance, exact hash and explicit save are separate steps. Target/visibility changes and canceled reads invalidate previews. Saving follows the actual returned meeting identifier, including reused imports. No Google OAuth app or generated transcripts are currently available for live acceptance.
- Bounded server search, pagination, timestamps, revision/access metadata and optional title grouping preserve separate records sharing a title.

## Current evidence

| Gate | Observed result | Boundary |
| --- | --- | --- |
| Components/navigation | 104/104 tests in 27 files; 17.47 seconds | Local Vitest; includes calendar dates/ownership/pagination/stale scope, Google readiness/failure/reuse/cancel/visibility, acknowledged save, role gates, shell focus and legacy navigation |
| TypeScript | `npm.cmd run typecheck`, exit 0 | Current local frontend contracts |
| Production bundle | Vite build, exit 0, 67 modules | Entry 174.34 kB / 55.89 kB gzip; separate Settings/Audit and existing lazy feature chunks |
| V2 browser journeys | 3/3; 25.9 seconds | Disposable schema 11 API/worker at coordinator-owned 19082; actual indexing, rule extraction, review, calendar and search; third case uses explicitly synthetic Google responses |
| Affected legacy workflow regression | 4/4; 51.3 seconds | Same disposable API/worker; synthetic Jira create/update approval and receipt recovery, local handoff/GitHub preview invalidation and deep links, department themes/personal-plan persistence, ambiguous people and retained review across revisions |
| Rendered surfaces | Desktop 1440 and mobile 390 captures inspected | Calendar and settings; no horizontal overflow; axe WCAG A/AA tags reported zero violations on tested views, not a full compliance certification |

The browser calendar journey explicitly creates and confirms a synthetic Alex, then checks the actual confirmed owner name on an action card. It approves five outcome kinds, preserves an undated/unassigned risk, opens the correct source outcome from Calendar, checks Step 3 subviews, keyboard-collapse/focus/persistence/reopen, Settings/Connections, calm mode and system reduced motion. The search journey creates two same-title synthetic records and checks distinct identifiers, timestamps, server query and grouping.

A separate synthetic Google browser-response case passed in `frontend/e2e/experience-v2.spec.ts`. Its readiness/preview/save responses are intercepted; it is UI contract evidence rather than live Google or backend-import acceptance. It checks absent and processing transcripts without a save/fallback, exact restricted hash/save input, unconfirmed participant labels, no nested forms, mobile preview and actual returned reused-meeting navigation. The original local source save/index and reused-meeting read use the real disposable API. Backend import/migration evidence belongs to the backend owner and `GOOGLE_MEET_IMPORT.md`.

## Corrections found by verification

- An initial Google fixture used an unrealistically distant expiry, overflowing JavaScript timers. It now follows the 15-minute contract.
- A real effect-order race could replace the Calendar-selected outcome when tasks arrived asynchronously. Selection fallback now respects an already valid state update; a regression exercises delayed task arrival.
- Desktop browser tests use the visible outcome navigation rather than the mobile-only picker. Stepper accessible names omit decorative numbers.
- Settings helper copy collapses instead of adding a duplicate page heading above child views.

## Reusable frontend skill

`skills/pandora-frontend` is the source package; the personal installed skill is `$pandora-frontend`. It includes a scoped entry skill, seven focused guides, an independent synthetic rehearsal and a read-only HTTP asset verifier. Source and installed structure validation passed; the verifier passed five local tests. No external upload, commit or publication occurred.

## Remaining release boundaries

- Current frontend is React client rendering, not SSR.
- Google live activation requires the user's approved/configured app, eligible transcript-generating meetings and private credentials; no older-meeting fallback or fake successful connection is introduced.
- Current calendar artwork is original code-native graphics, not authored cinematic video. Existing department media remains separate.
- Provider writes, synchronization expansion, shared-runtime activation, container browser acceptance and Render deployment are not authorized by this ledger.
- Existing private lifecycle and visitor suites have navigation expectations updated for Settings; those whole suites were not rerun after V2 in this pass. The affected four-case workflow suite passed separately as recorded above.
