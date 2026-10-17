# Redesign plan: phases 3–7

Written October 16, 2026, after phase 1 (PR #80) merged and while phase 2 (visual regression, branch `feat/phase2-visual-regression`) was in progress. The direction is in `AGENTS.md`: calm, Linear-inspired, tokens in `frontend/src/theme.css`, motion from `frontend/src/motion.css`, light and dark both first-class, calm mode and reduced motion turn all motion off.

This is a plan, not evidence. Each phase records what actually passed in `docs/VALIDATION.md` when it finishes.

## How to run each phase

- One fresh Claude Code session per phase, started from the repo folder. Open it with: "Phase N of docs/REDESIGN_PHASES_3_7.md".
- Start in plan mode; refine this section against the code as it is then, and approve before editing.
- One branch and one PR per phase, branched from an up-to-date `main`.
- Ask all open questions in one round at the start.
- Phase 2's screenshot tests guard every later phase: an intended visual change updates the baselines (`npm run test:visual:update`) in the same PR, and the reviewer checks the images.

## Decisions after discovery (October 17, 2026)

Parallel read-only discovery ran for phases 3–6 and the reports were cross-checked. Approved by Hamza ("all recommended"):

1. React pinned exactly to **19.3.0** (with matching `@types`); the October 14 patch line waits for a later bump under the two-week rule. 19.3.0 exports a stable `<ViewTransition>` (checked in the published package), so phase 4 uses it.
2. Phase 4 adds a transcript line view on People that becomes a "draft outcomes found" list; it is what the signature moment morphs from.
3. Page and step entrances use the Linear-style **reveal** (fade + 8 px blur to sharp + 8 px rise, about 320 ms, staggered 120–160 ms). Interactions stay 120–280 ms.
4. Style guide is a **separate HTML entry** (not Storybook, not a route in `App.tsx`), and is browsable in the public demo build.
5. Remove the lunar calendar scene (`constellation.css`, `OutcomeCalendar.tsx` SVG) and the unmounted `Toast`.
6. Raise `--border-strong` so input borders reach 3:1 (WCAG 1.4.11); new baselines expected.
7. Install `cmdk@1.1.1` with `npm install --before=2026-10-03` so its Radix dependencies also meet the two-week rule.
8. Raise the demo start limit **for the CI/test stack only** so new browser specs fit; production keeps 10 per hour.

Cross-check corrections to this plan:
- Phases 4 and 6 both rewrite `motion.css`/`theme.css`, and 4 and 5 both change `ThemeSwitch.tsx`. So a shared **foundation** step (tokens, reveal/stagger primitives, calm-mode-before-first-paint fix in `public/theme-init.js`, retuning off-token keyframes, the duplicate reduced-motion rule, decisions 5–6) runs after phase 3 and before 4, 5 and 6 split into parallel worktrees.
- Phase 3 needs one code change (`ContextBubble.tsx:27` argument-less `useRef`); axe has no React peer.
- Bugs to fix in the foundation or the phase that touches them: the calendar outcome card may render white with light text in dark mode; the "Motion & layout" tab is clipped on phone Settings; `--success` on `--success-soft` is 4.40:1 in light.

## Order and dependencies

```
2 visual regression ──► 3 React 19.3 ──► F foundation (tokens + motion primitives + fixes)
                                               │
                     ┌─────────────────────────┼──────────────────────────┐
                     ▼                         ▼                          ▼
        4 fluidity + signature moment   5 keyboard + ⌘K menu     6 style guide (own entry)
                     │       (parallel worktrees; rebase on main as each merges)
                     ▼                         │                          │
              (LinkedIn post)                  └────────────┬─────────────┘
                                                            ▼
                                                   7 release audit
```

Status: the foundation step (F) is done; it merged in PR #84 on October 17, 2026.

- 2 before everything: later phases change how things look, so the screenshot tests need to exist first.
- 3 before the rest: new code is written against React 19 once.
- F before 4–6: it owns the shared files (`theme.css`, `motion.css`, `ThemeSwitch.tsx` helper) so the parallel phases don't collide.
- 4, 5 and 6 then touch mostly separate files; `visual.spec.ts` baselines are the shared point, so each PR regenerates only its own screens and rebases before merge.
- 7 last: it audits the finished result.

---

## Phase 3 — React 19

**Goal:** move from React 18.2 to React 19 with no change in behavior or appearance.

**Starting point (checked October 16):** `main.tsx` already uses `createRoot` and `StrictMode`. No `forwardRef`, `defaultProps`, `ReactDOM.render`, `findDOMNode` or argument-less `useRef()` in `src`. 69 `.tsx` files, 29 test files, 13 files using `act(`. Testing Library is already v16, which supports React 19.

**Approach:** follow the official React 19 upgrade guide and its codemods (`npx codemod@latest react/19/migration-recipe`, `types-react-codemod` for the type changes).
1. Bump `react`, `react-dom`, `@types/react`, `@types/react-dom` to 19.x (exact versions at least two weeks old).
2. Run the codemods; review every change by hand.
3. Fix type errors from the stricter types (`useRef` needs an argument, `JSX` namespace moves under `React.JSX`, ref callbacks can't implicitly return a value).
4. Replace `act` imports from `react-dom/test-utils` with `act` from `react`.
5. Don't adopt new React 19 features in this PR (Actions, `use`, form actions). Keep the upgrade reviewable on its own.

**Risks:** hidden StrictMode double-effect assumptions in polling hooks (`components/workbench/useJobPolling.ts`); `@axe-core/playwright` and other dev dependencies' declared React range.

**Done when:** frontend checks pass (`format:check`, `typecheck`, `test`, `build`), `python scripts/run_e2e.py` passes, and the visual tests pass **without** updating baselines (proof that nothing changed visually).

---

## Phase 4 — Transcript-to-outcome moment

**Goal:** the one signature animation the direction calls for: when extraction finishes, the evidence lines in the transcript visibly become outcome cards. It replaces the decorative scenes phase 1 retired.

**Where it happens:** extraction job status is polled in `components/workbench/useJobPolling.ts` and shown by `JobStatus.tsx`; outcomes render in `OutcomeCard.tsx`; the steps live in `MeetingSteps.tsx` and `Workbench.tsx`.

**Approach:** the View Transitions API, which `ThemeSwitch.tsx` already uses for theme changes (including the calm-mode check).
- Give each evidence span and its outcome card a shared `view-transition-name`, so the browser animates one into the other.
- Durations and easing from `motion.css` tokens; this moment may run longer than the 280 ms used for interactions. Decide the exact length in the phase session and keep it under about 1 second.
- Browsers without the API, calm mode and reduced motion get the end state immediately, with no animation.
- No new animation library unless the View Transitions version can't do it. If one is needed, say so and compare it first.

**Feedback after phase 2 screenshots (October 17):** the static screens look right but the app is "missing some fluidity" — things should emerge rather than appear. In scope for this phase alongside the signature moment: staggered entrance of lists and cards, panels and step changes that slide or fade in, and content that settles into place after loading — all from `motion.css` tokens and all off under calm mode and reduced motion.

**Reference the user supplied (October 17): Linear's homepage on a phone, 7.2 s recording.** Measured from the frames:
- Hero text enters with a combined fade, blur-to-sharp and slight upward settle, staggered by element: headline crisp at about 2.4 s, subtitle about 170 ms later, link about 240 ms after that. Each element sharpens over 240–350 ms.
- The product screenshot sits below the fold with a soft edge glow and scrolls in as one block. Customer logos drift sideways as a slow marquee.
- Nothing pops; every block arrives in reading order, and nothing moves once it has arrived.

Translate it into M2O as: a `reveal` entrance (opacity 0→1, `filter: blur(8px)`→0, `translateY(8px)`→0, about 320 ms, `--ease-out`) with a 120–160 ms stagger between a screen's heading, lead text and primary content; used for page and step entrances, the landing page and the signature moment. Clicks, hovers and toggles stay at the fast 120–280 ms. Calm mode and reduced motion remove all of it, including blur.

**Found during phase 3 (PR #82):** under React 19 the workspace content mounts 100–300 ms after the demo banner (lazy content commits later), so the banner shows alone for a moment and the content then fades in. Cover it with the loading-slot and entrance work so the screen arrives as one sequence.

**Questions for the phase session:** exactly which moment triggers it (job completed on the People step, or entering Review); whether people who come back to a meeting see it again (recommend: only the first time after extraction).

**Done when:** visual baselines update for the end state only (screenshots run with animations disabled); a Playwright test proves calm mode and reduced motion skip the animation; the existing accessibility checks still pass. Record a short screen capture for the PR and the LinkedIn post.

---

## Phase 5 — Keyboard and command menu (⌘K / Ctrl+K)

**Goal:** everything reachable from the keyboard, plus a command menu like Linear's.

**Starting point:** only a few key handlers today (`ContextBubble.tsx` and a handful of others). Navigation targets are already defined in `App.tsx` and `navigation.ts` (`routePath`, `settingsPath`); meeting search exists in `components/workbench/useMeetingSearch.ts`.

**Approach:** the `cmdk` library, a widely used headless command menu that implements the ARIA combobox pattern and works with React 18 and 19. Style it with Tailwind on the existing tokens. Writing an accessible combobox by hand is avoidable risk.
- Commands: go to My day / Meetings / Audit / Settings sections; switch workspace or department; new meeting; search meetings by title; theme (System/Light/Dark); calm mode on/off.
- Shortcuts: ⌘K / Ctrl+K opens the menu; `?` opens a shortcut list. Single-key shortcuts never fire while typing in an input, textarea, select or contenteditable.
- Every command respects the same permissions as the UI (for example, no Audit for roles without access, no New meeting in the public demo).

**Done when:** unit tests cover command filtering and the "not while typing" rule; a Playwright test runs a full keyboard-only journey (open menu, go to a meeting, extract, review) and passes axe in both themes; visual baselines added for the open menu.

---

## Phase 6 — Style guide

**Goal:** a living reference for tokens and components so future UI stays consistent, and a page interviewers and contributors can browse.

**Decision for the phase session — two standard options:**

| | Storybook (Vite builder) | In-app `/styleguide` route |
|---|---|---|
| What it is | The most widely used component workshop | A dev-only page in the app itself |
| Strengths | Each component state isolated; built-in accessibility add-on; well known on a CV | No new tooling; uses the real app shell and themes; phase 2 screenshots it for free |
| Costs | Many dev dependencies, its own build, extra CI time | Must be kept out of the production bundle; less isolation |

Recommendation: decide by how many components need isolated states. If the answer is "most", Storybook; if it's mainly tokens plus a dozen components, the in-app route.

**Content either way:** color tokens (both themes, with contrast ratios), type scale, spacing and radius, motion tokens with live examples, and the main components in every state (buttons, inputs, badges, outcome card, empty/loading/error states). Document the rule "write new components with Tailwind on theme tokens."

**Done when:** every token in `theme.css` is shown; components render in light and dark; axe passes on the page; visual baselines cover it.

---

## Phase 7 — Release audit

**Goal:** evidence that the redesigned app is ready to show publicly. The audit records results; it doesn't assume them.

**Already in place:** CI runs backend lint/types/tests on PostgreSQL, `pip-audit`, `npm audit`, container builds, the browser suite with axe (light, plus dark from phase 1), and the hosted-runtime check. Not yet present: Dependabot, CodeQL, secret scanning in CI, Lighthouse, Firefox/WebKit runs.

**Checklist:**
1. **Security review:** run `/security-review` on the redesign changes; triage every finding.
2. **Secrets:** gitleaks over the full git history (one-off), then on every PR in CI.
3. **Static analysis:** GitHub CodeQL default setup for Python and JavaScript/TypeScript (free for public repos).
4. **Dependencies:** `.github/dependabot.yml` for npm, pip, GitHub Actions and Docker, weekly, grouped minor/patch.
5. **Performance:** Lighthouse CI (`@lhci/cli`) against the Compose stack for the landing page and demo: record scores and set budgets slightly below them.
6. **Accessibility:** axe in light and dark on every main screen (extend if phases 4–6 added screens); one manual pass with keyboard only and with a screen reader (NVDA on Windows); check 200% zoom.
7. **Cross-browser:** add Firefox and WebKit Playwright projects for the functional visitor journey (screenshots stay Chromium-only to avoid triple baselines).
8. **Calm mode and reduced motion:** verify no motion anywhere, including the phase 4 moment and the command menu.
9. **Docs media:** refresh `docs/media/` with `MTT_UPDATE_DOC_MEDIA=1` and update the README screenshots.
10. **Evidence:** add a dated "Redesign release audit" section to `docs/VALIDATION.md` with every result and anything not verified.

**Done when:** every item has a recorded result or an explicitly accepted gap. Deploying is a separate step the user authorizes.
