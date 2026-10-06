---
name: pandora-frontend
description: Design, implement, and verify cinematic product workspaces with sequential workflows, graphical data views, purposeful motion, and accessible interactions. Use for substantial interactive frontend work or visual refinement of data-driven applications; do not activate solely for a static marketing page or a backend-only task.
---

# Pandora Frontend Workshop

Build expressive interfaces that make complicated work feel clear and satisfying. Visual polish should reveal real state and help the next decision. It must earn trust through working contracts, readable evidence, and rendered verification.

## Start from the actual assignment

Read project instructions and trace the affected route, component, state owner, API contract, styles, and test entry point. Preserve existing work. Establish what the user authorized; this skill does not authorize provider writes, uploads, account changes, publishing, or deployment.

For substantial changes, give a concise design/contract blueprint before the large edit. Distinguish confirmed defects from hypotheses using current source and rendered evidence. Once direction is authorized, make reversible implementation choices and proceed; do not ask repeatedly about settled preferences or turn a small fix into another full audit.

Choose only the references needed for the current work:

| Work | Reference |
| --- | --- |
| Translate inspiration into an original visual system | [Design translation](references/design-translation.md) |
| Simplify routes, steps, state, and asynchronous flows | [Workflow and state contracts](references/workflows-state.md) |
| Create dimensional graphics, cinematic motion, media, or collapsible chrome | [Motion and media](references/motion-media.md) |
| Build celestial calendars, timelines, or graphical outcome views | [Calendar and data views](references/calendar-data.md) |
| Connect provider capabilities and honest import/delivery states | [Integration surfaces](references/integration-surfaces.md) |
| Review accessibility, responsiveness, failure paths, and release evidence | [Rendered verification](references/rendered-verification.md) |
| Work specifically in M2O | [M2O project map](references/m2o-project-map.md) |

## The working loop

1. Identify the user's next meaningful action and the facts needed to perform it. Set a primary action for that view and move optional configuration/evidence into clearly labeled secondary controls.
2. Define route and state boundaries. Separate temporary form input, persisted domain state, provider state, and visual preferences. Preserve legacy links when changing visible stages.
3. Define the visual grammar: hierarchy, color roles, dimensional motifs, whitespace, focus states, and an equivalent static presentation. Translate references into principles rather than copying layouts or assets.
4. Implement against verified contracts. Keep the project’s framework and dependencies unless a concrete need justifies change. Treat source values as data, not HTML or instructions.
5. Test the smallest meaningful boundary first, then the affected integrated journey. Inspect actual desktop/mobile rendering, normal/calm modes, and the packaged runtime when assets or infrastructure are involved.
6. Report what changed, the exact evidence, and remaining limitations. A prototype, source check, native test, container check, and live deployment are different evidence categories.

Scale this loop to the change. Do not impose a new architecture, fixed sidebar count, celestial theme, or provider set on projects that did not request them.

## Useful operating modes

- **Design:** map persona → task → decision → screen; propose a coherent visual grammar and concrete tradeoffs.
- **Implement:** choose one complete user path, retain domain guards, and verify success/failure states before expanding.
- **Review:** rank findings Blocking / Important / Improvement / Nit and label each rendered confirmation, source-confirmed concern, or hypothesis.
- **Repair:** trace browser → routing → proxy → API → persistence/provider and correct the smallest root cause.
- **Polish:** refine rendered hierarchy and feedback without silently changing authorization, ownership, or scope.

## Trust boundaries that shape design

Animations never approve, publish, retry, or complete work. Show success only after the corresponding acknowledged state; queue acceptance is not a provider receipt. Relative hints are not reviewed calendar dates. A profile connection is not general person lookup. A configured provider is not necessarily connected or authorized for this workspace.

Preserve unsaved drafts, current versions, explicit destructive confirmation, role/workspace scope, and uncertain-write handling. Use synthetic fixtures for demonstrations. Keep credential/recovery values out of logs, captures, URLs sent to servers, and browser storage.

## Deterministic media check

Use [scripts/verify_public_assets.py](scripts/verify_public_assets.py) when static artwork/video is packaged or served differently from the native frontend. It compares actual HTTP bytes, MIME types, hashes, and an optional missing-file 404 against local public files. It sends no credentials and never uploads local content.

```powershell
python scripts/verify_public_assets.py --base-url http://localhost:8080 --public-dir /absolute/project/frontend/public --asset scenes/engineering.mp4 --asset scenes/hr.webp --missing scenes/not-present.mp4
```

Resolve the actual project, interpreter, URL, and public directory first. This is a command shape, not a claim that an application runs there.

The checker’s [local test script](scripts/test_verify_public_assets.py) covers real bytes/MIME, HTML fallback, missing-file routing, redirects, path escape and credential-URL rejection without using external services.

## Finish with a reviewable result

For a substantial pass, retain a short feature-to-evidence ledger: intended behavior, source owner, contract, verified path, unresolved gate. Include genuine before/after artifacts when useful. Keep requested breadth visible, including capabilities awaiting credentials or dedicated UI, without calling them completed.

When materially revising the skill, the [synthetic forward-test case](references/forward-test-case.md) can exercise its decisions independently. Evaluate the resulting plan rather than matching headings or wording; do not treat its records as application fixtures.
