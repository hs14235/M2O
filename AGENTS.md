# M2O implementation priorities

Read `docs/M2O_IMPLEMENTATION_CONTRACT.md` before backend, schema, integration, infrastructure, or architectural changes. It records Hamza's approved product promise, numbered priorities, research findings, and release conditions as of October 3, 2026.

Treat Jira, Slack, GitHub, and supported LinkedIn capabilities as core product requirements. Explain recommendations through concrete tradeoffs; do not dismiss integration breadth or extensive requirements. Sequence implementation by dependencies without silently dropping a provider.

Preserve these priority areas from the planning overview: 1 current capability inventory; 2 repository structure; 3 architecture; 4 domain integrity; 5 user journeys; 7 functional requirements; 8 integrations; 9 synchronization ownership; 10 cinematic UI/UX; 11 security/operations; 12 Render constraints. Department use cases, delivery phases, and verification evidence remain required too.

Keep review approval, external delivery, and personal execution separate. Preserve workspace isolation, explicit participant confirmation, revision checks, exact delivery previews, audit history, and uncertain-write handling across every adapter.

Hamza approved separate personal-plan progress and external tool status on October 3, 2026. M2O owns personal execution state; each provider owns its external workflow state. Delivery receipts link them without automatically completing or reopening either side. Define and test explicit ownership, conflict, authorization, duplicate-event, and stale-version rules before introducing synchronization.

UI direction: vivid, bubbly, dimensional department experiences with cinematic transitions, calm mode, system reduced motion, mobile usability, and readable evidence. Current CSS scenes are not authored videos. Current React page navigation is not SSR; do not claim or assume the rendering decision is settled.

Use current source/runtime evidence for model configuration. Evaluate replacements against M2O synthetic extraction cases before changing the default. Do not substitute cloud inference or claim model superiority based only on general benchmarks.

Preserve existing uncommitted work. No commits, pushes, PRs, deployment, provider writes, account changes, or messages without the user's explicit authorization for the action. Secrets stay in private backend configuration. A feature-completion target is not evidence that release gates passed.
