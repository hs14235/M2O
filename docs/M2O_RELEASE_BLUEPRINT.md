# M2O product, visual design and release research

Implementation update: user-owned encrypted provider grants and Jira OAuth/site/project verification are now locally tested. Jira field discovery, exact approved create/update, queue/receipts and reconciliation are locally verified; live consent/writes remain pending. Follow JIRA_CONNECTION.md and JIRA_DELIVERY.md. The CPU-only hardware correction and prioritized completion requirements are pinned in AGENTS.md and M2O_IMPLEMENTATION_CONTRACT.md. Older baseline tables below predate this connection increment.

Research date: 2026-10-03. This is a proposed completion contract, not an implementation or deployment claim. Existing capabilities were checked against the local README, integration/operations documentation and frontend manifest. The running browser was not inspected in this research pass. Product choices below remain subject to Hamza's answers.

## Selected direction — 2026-10-03

Hamza selected a bold creative workspace with vivid colors, dimensional shapes and motion throughout, plus calm mode. People Operations, Finance Control and Engineering must each have an end-to-end theme and useful department outcomes. All four destinations matter: GitHub, Jira, Slack and supported LinkedIn functionality. A personal daily plan plus optional provider delivery is required. Render Free is the initial budget, and public access should use an isolated synthetic demo with invited private use. These choices supersede the earlier soft-studio and single-destination recommendations below.

Department themes/calming controls and PostgreSQL daily planning are now implemented locally. The current scenes are code-driven graphics, not the final authored video system. Provider installation, Jira/Slack delivery, LinkedIn posting, isolated visitor provisioning/invitations and the Render runtime still require implementation/access. See PROVIDER_SETUP.md and RENDER_PLAN.md for concrete constraints. Do not call the full release complete based on this visual/planning increment.

## Product promise and release boundary

M2O should help a person finish a meeting with a clear, trustworthy next step and return to those commitments the next day. Keep Transcript → People → Review → Share. Add a completion view and, if selected for the first release, a Today view. Rich scrolling storytelling belongs on welcome/completion surfaces; task input and approval stay on short, focused pages.

Recommended first release: invitation-based small teams, engineering/HR/finance examples, source-linked human review, local exports, GitHub and one additional destination. Choose Slack for a reviewed summary or Jira for structured work tracking. Keep Zoom/Meet import behind a separate, later source adapter unless it is a first-release requirement. Do not build every provider before shipping a coherent product.

## Current baseline and gaps

| Area | Local baseline | Completion decision or remaining work |
| --- | --- | --- |
| Meeting flow | Four URL-addressable React pages, uploads/paste/examples, review and exports | Playful visual system, clearer completion state and usability validation |
| Rendering | React 18.2 / Vite, client-rendered shell | Actual SSR remains undecided; page navigation and scroll animation do not require it |
| Persistence/access | PostgreSQL workspaces, roles, transcript versions and restricted meetings | Evaluate invitations, password recovery, retention/deletion and hosting-specific identity requirements |
| Extraction | Local Ollama or deterministic rules, validated evidence and human review | Representative synthetic quality evaluation; no-outcome, multilingual and interrupted-job journeys |
| Destinations | Local export and GitHub adapter; Jira/Slack unavailable | One real adapter with permissions, exact preview, durable delivery and failure reconciliation |
| Participant context | Confirmed directory matches, configurable self-profile LinkedIn OIDC | Live LinkedIn requires approved configuration; no arbitrary name search |
| Operation | Local Compose, migration/backups and dated test evidence | Public TLS, monitored workers, off-host recovery, resource/cost limits and release verification |

## End-to-end journeys

| User | Journey to prove | Critical boundary |
| --- | --- | --- |
| Individual contributor | Import text → review actions → choose priorities → local daily plan/export → mark work complete | Approval is not task completion; dates are explicitly confirmed |
| Meeting facilitator | Import → resolve ambiguous names → assign ownership → request review → hand off approved outcomes | No automatic identity matching or silent assignment |
| Reviewer/team lead | Open drafts → inspect source → amend/reject → approve exact versions → preview delivery | Concurrent edits and transcript changes invalidate old approvals/previews |
| HR coordinator | Restricted onboarding meeting → confirm responsibilities → approved checklist → permitted destination | Restricted context does not become public through exports or broad channels |
| Finance reviewer | Extract follow-ups/decisions → verify figures and dates → approve reviewed summary | No payment authority, invoice approval or invented arithmetic from an LLM |
| Engineering lead | Extract blocker/action/decision → approve → GitHub/Jira preview → delivery receipt | Provider-required fields and confirmed external assignee mappings |
| Viewer | Read permitted evidence and reviewed outcomes → navigate all saved steps | No editing, approval or external delivery authority inferred from UI access |
| Workspace owner | Invite/manage members → configure allowed destinations → inspect audit → revoke access | Last-owner protection, credential rotation and least privilege |
| Operator | Monitor failed inference/delivery → diagnose safe error → recover/restore | Ambiguous provider writes are not blindly retried |

Required failure journeys: empty or oversized input; invalid UTF-8; transcript with no commitments; contradictory or speculative commitments; same-name participants; unknown relative dates/timezones/DST; repeated upload; changed transcript mid-extraction; worker restart; expired session; revoked membership; stale review; provider disconnect; 429; partial delivery; unknown POST outcome; refresh/deep link; mobile keyboard; reduced motion; missing/blocked video; failed download. Each should have a truthful state and a recovery action.

For Today, introduce an execution lifecycle independently of review status. A possible model is approved outcome → planned/in-progress/blocked/done execution record, with explicit owner, planned date and change history. External delivery success is also separate. Choose one source of truth for completion before implementing two-way sync. A decision or risk should not be forced into a task checkbox.

## Visual direction proposal

Recommended direction: a soft, bubbly studio. Rounded cards, oversized but readable headings, generous spacing, soft depth, original blob illustrations and a consistent visual motif in which scattered conversation fragments settle into ordered outcome cards. A small optional character can guide empty/loading/completion states if selected.

Proposed starting colors (not contrast-certified): warm canvas `#FFF9F3`, dark ink `#242039`, violet accent `#7055E8`, lilac surface `#EDE5FF`, peach surface `#FFE0D1`, mint surface `#DDF3E8`, sky surface `#DDEEFF`. Use dark text on pastel surfaces; test every actual text/control/focus combination against WCAG contrast. Keep department colors supplemental to text/icons, never the only meaning.

Textures: locally bundled low-opacity grain only in decorative artwork, soft radial gradients, occasional tactile paper-like cards and restrained translucent layers. Dense transcript/evidence reading areas remain solid. Prefer original CSS/SVG assets; document the license/provenance of any font, stock video or purchased illustration. Fonts should have a verified redistribution/web license and be self-hosted where appropriate.

Motion storyboard:

1. Welcome: abstract conversation bubbles drift into a clear set of cards as the visitor scrolls.
2. Transcript: an upload produces a brief responsive visual acknowledgment; no video behind the editor.
3. Extraction: abstract sorting motion accompanies real queued/running/coverage states. Do not invent percentage progress.
4. People: explicit confirmation visually connects a name to a directory card.
5. Review: short card transitions reflect real saved state. Reading/evidence remains stationary.
6. Completion: reviewed outcomes settle into a daily-plan composition, with a short optional celebration and a clear delivery receipt.

Animation cannot delay clicks, require dragging, change focus order or conceal errors. Display reduced-motion and user-selected calm modes without removing information. Never use a celebratory delivery state before the server confirms success.

## Ranked runtime and authoring options

| Tool | Recommendation and fit | Cost/maintenance boundary |
| --- | --- | --- |
| React/Vite + existing CSS tokens | Keep the existing foundation; build a coherent design system | Avoid an unrelated frontend framework migration |
| [Motion](https://motion.dev/docs/react-installation) | First choice for React transitions, layout motion and scroll-linked graphics | Supports React 18.2+; pin/review dependency and test bundle/performance before adoption |
| [GSAP ScrollTrigger](https://gsap.com/docs/v3/Plugins/ScrollTrigger/) | Alternative for complex pinned timelines or scrubbed choreography | Use for a demonstrated sequence, not a second overlapping animation system; review the [current license](https://gsap.com/blog/3-13/) |
| [Rive React](https://github.com/rive-app/rive-react) | Optional interactive character driven by app state | Needs authored assets and runtime compatibility review; editor/export terms separate from runtime code |
| [dotLottie React](https://docs.lottiefiles.com/en/runtimes/distributions/react) | Optional small finite decorative/celebration animation | Asset licensing is separate from player licensing; do not add alongside Rive without a concrete need |
| [Remotion](https://www.remotion.dev/docs/license/pricing) | Author deterministic branded video loops outside the app request path | License depends on use/company; no runtime video rendering service needed for decorative media |
| [Spline](https://docs.spline.design/exporting-your-scene/how-to-optimize-your-scene) | Optional 3D prototype, preferably rendered into video for the first release | Interactive scenes need GPU/mobile testing; [self-hosted export](https://docs.spline.design/exporting-your-scene/web/exporting-as-self-hosted-project) terms and asset rights must be checked |
| [Three.js](https://threejs.org/docs/pages/WebGLRenderer.html) | Later, only for interaction that static/vector/video assets cannot deliver | GPU/resource lifecycle, fallback and device budgets become application responsibilities |
| [Radix Primitives](https://www.radix-ui.com/primitives/docs/overview/accessibility) | Selectively use for new dialogs, menus or popovers | Helps keyboard/focus behavior; does not certify the finished interface |
| [Radix Colors](https://www.radix-ui.com/colors/docs/palette-composition/composing-a-palette) | Reference for functional color scales and theming | Actual combinations still require WCAG checks |
| [Magic UI](https://magicui.design/docs/installation) / [Aceternity UI](https://ui.aceternity.com/categories) | Inspiration or individually reviewed components | Existing stack has no Tailwind; verify dependencies/accessibility and [asset/component licenses](https://ui.aceternity.com/licence) before copying |

Do not combine multiple animation players, smooth-scroll overrides and interactive 3D by default. Keep native scrolling unless a specific tested interaction needs an override. The desired aesthetic can start with CSS/SVG and one motion library.

## Video and accessibility contract

Use short original, silent, seamless clips with poster images and reserved dimensions. Provide WebM/MP4 as appropriate to tested browsers; match clip endpoints to avoid visible loop seams. Load offscreen media near use, pause when hidden, handle autoplay rejection, and retain meaningful static fallbacks. Scroll-scrubbed video requires encoding/seek tests; do not assume setting currentTime on every scroll produces smooth playback.

[web.dev video guidance](https://web.dev/articles/lazy-loading-video) explains preload/poster/lazy-loading tradeoffs. An above-the-fold poster should not be indiscriminately lazy-loaded. [Motion reduced-motion guidance](https://motion.dev/docs/react-use-reduced-motion) supports disabling parallax/background autoplay. [WCAG Pause, Stop, Hide](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html) requires control for qualifying automatic motion lasting over five seconds alongside other content. Meaningful narrated media also needs captions/transcripts; decorative media must not carry essential workflow information.

Proposed acceptance targets, to measure rather than claim: p75 LCP ≤2.5s, INP ≤200ms and CLS ≤0.1 on the chosen device/network cohort. Establish a measured initial JS/media budget after the first prototype. Test keyboard-only operation, screen-reader flow, 200% zoom, high contrast, reduced motion, mobile touch and slow/failed media. A graphics failure must never block saving or review.

## Plugins discovered for the build workflow

The plugin directory search returned Figma, Runway, Higgsfield, Adobe/Adobe Express, Atlassian and Slack. None was installed/connected by this research pass. Figma and Runway were recommended as the smallest optional design/video set. Figma supports editable design collaboration; Runway can author video through a connected account. External asset creation needs account/credit and data authorization. Original local synthetic artwork remains a viable path without them.

Codex plugins do not install provider functionality into M2O. Jira/Slack users need M2O's own backend integration and authorization. Do not upload transcripts, repository source or credentials to a design/video service as part of visual authoring.

## Integration contracts

Every delivery adapter consumes reviewed domain data, validates allowed destination and provider-specific fields, creates an exact persisted preview, gets explicit reviewer approval, records durable intent, delivers, and returns a receipt/failure/uncertain state. Provider switches and changed outcome versions invalidate the preview. Partial delivery is represented per item.

[Slack chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/) requires message-writing authorization and destination access; Block Kit needs accessible text fallback and controlled link/mention handling. [Jira issue creation](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/) requires project permissions and valid issue-type/required-field mappings; rich text uses its provider contract. Do not assume a confirmed directory person maps to a Jira/Slack identity.

[Google Meet artifacts](https://developers.google.com/workspace/meet/api/guides/artifacts) support transcript resources/entries when available and authorized; entries have limited availability and can differ from an edited Docs transcript. Store source ID, timestamps and import revision; make repeated import idempotent. [Zoom recording API](https://developers.zoom.us/docs/api/rest/reference/zoom-api/methods/#operation/recordingGet) is another source to evaluate against the actual account and scopes. Neither source is an implemented import adapter today.

LinkedIn remains consenting-user basic profile context, documented in INTEGRATIONS.md. Approval/scopes cannot be inferred from desired functionality. Do not market arbitrary participant enrichment.

## Release and maintenance gates

1. Decide first users, account model, daily-plan scope, first external destination and visual direction. Validate the shortest end-to-end journey with those users.
2. Build one visual vertical slice (welcome → one department example → review → completion), with static/calm equivalents and measured performance, before spreading the theme across all pages.
3. Complete selected product paths and one destination, including setup/recovery and all critical failure journeys. Evaluate local extraction against a versioned synthetic corpus.
4. Run current tests, migration/concurrency checks, browser journeys, dependency scans, visual/accessibility/performance checks and image/container review. Existing dated results do not verify later changes.
5. Prepare environment-specific deployment: domain/TLS, secure cookies/origin, PostgreSQL backups and restore drill, worker/model resources, model privacy boundary, secrets, rate limits, retention, monitoring and release rollback.
6. Establish operational owners and runbooks: failed jobs, provider revocation/429/uncertain writes, restore, incident triage, credential rotation, dependency/model updates and regression evaluation.

Local inference on a deployed server stays self-hosted inference, but uploaded transcripts leave the user's device. Make that boundary explicit before choosing hosting or making privacy claims. Measure model memory, concurrency and cold-start behavior before selecting compute.

Deployment must track API/database readiness and worker health/queue age separately. Record a recovery point/time objective, test off-host restore, and define compatible code/schema rollback. Provider credentials and media assets require lifecycle ownership as well as application code.

Open questions: references/palette/mascot; where rich motion belongs; permitted authoring budget; private demo versus invited team versus public service; Today versus external tracking; first destination; transcript-source priority; host/budget; literal SSR requirement. No application dependencies, remote settings, account connections, deployment, commits or pushes were changed by this research document.
