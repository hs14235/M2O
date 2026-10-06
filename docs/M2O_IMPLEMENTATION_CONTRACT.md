# M2O implementation contract and architecture research

Date: October 3, 2026, America/New_York. This document records planning decisions and researched recommendations, not completed features or deployment approval.

## Accepted product promise and priorities

Turn a meeting into reviewed, accountable outcomes, organize the next steps for your day, and deliver them to the tools your team already uses.

Hamza explicitly prioritized overview sections 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, and 12. Other sections remain important; these are implementation review gates, not permission to omit department cases, testing, or delivery planning.

| Original section | Required consideration before implementation |
| --- | --- |
| 1 Baseline | Separate implemented behavior, user-reported account setup, and verified live capabilities. |
| 2 Structure | Routes adapt HTTP; services own product rules; adapters own provider protocols; database owns persistent truth. |
| 3 Architecture | Use explicit module/process boundaries and justify any distributed boundary against measured needs. |
| 4 Domain | Preserve source revisions, immutable reviews, scope/provenance constraints, expected versions, exact previews, and uncertain-write handling. |
| 5 Users | Prove visitor, contributor, facilitator, reviewer, department coordinator, owner, and operator journeys. |
| 7 Functions | Complete capture, extraction, people confirmation, review, planning, delivery, connections, isolation/invitations, completion, accessibility, and privacy lifecycle. |
| 8 Integrations | Jira, Slack, GitHub, and supported LinkedIn capabilities are all core requirements; order is dependency-driven, not a removal of scope. |
| 9 Synchronization | Hamza approved separate personal-plan progress and external tool status on October 3. Define ownership/conflicts before implementing deliberate synchronization; delivery alone does not change completion state. |
| 10 Experience | Vivid bubbly graphics, dimensional scenes, department-wide cinematic transitions, authored video where useful, calm mode, and accessible mobile flows. |
| 11 Operations | Credentials, authorization, job recovery, quotas, retention, invitations/recovery, backups, monitoring, and truthful errors. |
| 12 Hosting | Render Free is the selected budget; distinguish a bounded public synthetic demo from durable private use and local AI. |

The October 3 feature-completion target and October 4–6 bug-fix/optimization window are the user's desired schedule. Completion requires observed acceptance results. Provider product approvals, credentials, callback addresses, hosting persistence, and inference capacity remain external dependencies, not promises of same-day activation.

## Evidence inspected this turn

- Current code uses FastAPI, SQLAlchemy, Alembic, PostgreSQL, React/TypeScript/Vite, an API process and a job worker.
- `backend/app/tasks.py` sends a Pydantic JSON schema to Ollama `/api/chat`, validates source identifiers, requests an 8192-token context, and limits generation to 2000 tokens at temperature zero.
- The private root configuration's model name and the running worker's model environment both say `qwen2.5:1.5b`. Only non-secret model/endpoint values were inspected.
- Worker inference URL is `http://ollama:11434`. Compose reports Ollama exited; API/database are healthy and web/worker running. Host Ollama endpoints did not respond. No model inference benchmark ran this turn.
- Host reports 31.8 GiB physical RAM and NVIDIA GeForce RTX 3080 Laptop GPU. VRAM and usable container GPU acceleration remain unverified; NVIDIA tooling refused access. No model downloaded or configuration changed.
- Existing documented test evidence is in VALIDATION.md; no application suites reran for this documentation/research change.

## Layering versus distributed services

A modular monolith is compatible with a multi-layer architecture. M2O already separates transport, authentication, application services, persistence, provider adapters, and inference. Separate API/worker processes allow different concurrency settings and worker counts while sharing schema and business rules.

Recommendation: retain this deployment/code ownership structure for the next implementation phase. It is a recommendation based on current coupling, workload evidence, budget, and release needs, not a rule that monoliths are universally better.

Concrete transaction example: approve a current outcome, record the exact delivery proposal/operation, and enqueue work without a gap between committed business state and job creation. These records can share a PostgreSQL transaction. Breaking review and delivery into separate database-owning services requires durable event publication, consumers, explicit ordering, stale-version checks, and compensating/reconciliation behavior.

Tradeoffs: shared deployments/schema couple modules; long-running work must stay off request paths; database connection and queue contention must be measured. The current PostgreSQL queue is not an unlimited streaming platform. Worker concurrency can scale independently but shares application and database capacity.

Reconsider a separate service when inference needs a GPU deployment lifecycle, inbound integrations need independent availability/isolation, modules have separate owners/release cadence, or measured queue/database contention persists after appropriate tuning. Inference is already an external process through Ollama.

Kafka provides durable replayable event streams, partitions and consumer groups. It is useful when multiple independent consumers need the same event history, stream processing, or demonstrated event volumes warrant its operational cost. Adding Jira/Slack/GitHub/LinkedIn adapters alone does not establish those needs. Kafka does not make provider HTTP writes atomic with database state, remove duplicate handling, or establish exactly-once Jira/Slack effects.

If adopted later, publish through a transactional outbox (or a deliberately tested CDC design), keep event/version contracts, partition by an appropriate aggregate, and retain consumer idempotency and external reconciliation. Do not assume an event broker replaces domain authorization or approval.

Reference: [Apache Kafka introduction](https://kafka.apache.org/intro/).

## LinkedIn creation and activation

The supplied screenshot is the initial Create an app form, not the final integration configuration.

- App name: M2O (Meeting 2 Outcomes).
- LinkedIn Page: use the actual project/organization Page whose super admin can approve association. A personal member-profile URL is not a Page. Association is permanent; individual-developer default Pages are product-specific and must not be treated as a generic shortcut for OIDC/posting.
- Privacy policy: use an actual publicly reachable policy describing the implemented data flows and contact/retention practices. No deployment domain or policy URL has been established here; do not fabricate one.
- Logo: upload the user's chosen project asset. Screenshot requests a square image with at least one dimension of 100 px. No logo was created this turn.
- Terms: the human account holder reviews and accepts them.

After creation, inspect Page association verification and request Sign In with LinkedIn using OpenID Connect. Existing M2O scopes are `openid profile`; `email` is optional and unnecessary for current minimal storage. Register the exact existing callback `/api/integrations/linkedin/callback` on the actual application origin, then configure credentials privately.

Posting requires a separate Share on LinkedIn product/scope (`w_member_social`) and a retained member-authorized publishing credential. The existing OIDC adapter discards access tokens and rejects unrelated scopes; broadening its configuration alone cannot implement posting. Confirm supported posting API/version during implementation. Actual lead-message delivery is not promised by OIDC or posting permission.

Sources: [Page association](https://www.linkedin.com/help/linkedin/answer/a548360), [OIDC](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2), [Share on LinkedIn](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin).

## Model selection research

Hardware correction from Hamza: the discrete GPU is unusable. Treat this machine as CPU-only with integrated graphics. Keep Qwen2.5 1.5B as the baseline and evaluate small, appropriately quantized candidates first; 4B models are optional quality comparisons after CPU latency measurement. A detected GPU name is not usable acceleration evidence.

Recommended evaluation candidate: `qwen3.5:4b`, a current Ollama-distributed Apache-2.0 model. Its current default artifact is Q4_K_M, approximately 3.4 GB. Alternative: `qwen3:4b`, Apache-2.0, Q4_K_M approximately 2.5 GB, if runtime support or measured latency favors it. `qwen3.5:2b` is also Apache-2.0 but its current default artifact is Q8_0 and approximately 2.7 GB; fewer parameters do not guarantee less artifact memory under different quantizations.

Phi-3 Mini is MIT-licensed, 3.8B, and its default `phi3:mini` tag is documented as a 4K-context variant (separate larger-context variants exist). Requesting `num_ctx=8192` does not establish useful native 8K context. The running worktree is currently configured for Qwen2.5 1.5B, so evaluate against that actual baseline as well as Phi if available.

Do not default to Qwen2.5 3B under an assumed Apache-2.0 license: its Ollama page identifies a separate Qwen Research license. No license restriction is inferred here; the distinction needs review for intended distribution.

These are compatibility/benchmark candidates, not a claim of superior M2O extraction. Verify Ollama runtime version, model digest, quantization, native context, actual GPU offload, thinking controls, JSON-schema compatibility, memory, latency and fallback rate. For reasoning-capable models, explicitly test supported thinking settings: the current request does not set `think`. Revisit decoding options against each model's official guidance rather than silently carrying all defaults over.

Evaluation plan: at least 24 synthetic cases, distributed across People Operations, Finance Control and Engineering. Include explicit/implicit commitments, no outcomes, completed/negated/hypothetical actions, conflicting dates, tentative decisions, same-name people, numeric facts, tail-of-transcript items, mixed language, and transcript prompt injection. Record valid-schema rate, valid citation rate, supported precision/recall, owner/date errors, hallucinations, correction/fallback frequency, warm/cold latency and peak memory. Inspect raw model results separately from application-preserved literal outcomes so safeguards do not conceal model weakness. Pin an accepted artifact and retain the prior model for rollback only after measured acceptance.

Sources: [Qwen3.5 4B Ollama](https://ollama.com/library/qwen3.5:4b), [official model card](https://huggingface.co/Qwen/Qwen3.5-4B), [Qwen3 4B](https://ollama.com/library/qwen3:4b), [Qwen3.5 2B](https://ollama.com/library/qwen3.5:2b), [Phi-3 Mini](https://ollama.com/library/phi3:mini), [Qwen2.5 3B](https://ollama.com/library/qwen2.5:3b), [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs), [thinking controls](https://docs.ollama.com/capabilities/thinking).

## Provider setup reported by Hamza

- Slack installed in M2O Sandbox and invited to `#m2o-demo`; screenshots confirm invitation. Destination channel ID supplied: `C0C6JQ7TA65`. No live backend send verified.
- Jira site supplied: `https://m2o.atlassian.net`; space key changed and accepted as `M2O`. OAuth app created and `read:jira-work` / `write:jira-work` added according to user reports. OAuth/token lifecycle, destination verification and exact issue create/update with queued receipts are now locally verified with synthetic provider responses; live consent/writes remain unverified. See JIRA_CONNECTION.md and JIRA_DELIVERY.md.
- LinkedIn app creation is in progress. Product grants and callback activation are not verified.

## Release work order and gates

### Rendering recommendation and approved state ownership — October 3

Rendering recommendation, pending Hamza's decision: retain React client rendering for the authenticated, separate-page workflow. Serve public landing, privacy and informational pages as static or prerendered HTML. Consider selective SSR if measured initial-load performance or public dynamic content warrants it. No renderer migration is authorized or implemented by this recommendation.

An API-intensive application can use SSR: the renderer can fetch authorized FastAPI data to produce initial HTML, then hydrate client interactions. SSR does not replace API authorization, job processing, polling, revision checks, or browser motion. Moving this React/Vite frontend from static Nginx serving to request-time React SSR would introduce a JavaScript renderer runtime, session forwarding, hydration consistency and private-response caching responsibilities. Separate workflow pages do not require SSR. Render Free cold starts remain a backend dependency under either approach.

References: [React server rendering and hydration](https://react.dev/reference/react-dom/server/renderToPipeableStream), [Render Free constraints](https://render.com/docs/free).

Approved ownership policy:

| State | Authority | Consequence |
| --- | --- | --- |
| Transcript revisions, evidence, outcome review and approval | M2O | Provider status cannot approve or alter a reviewed source revision. |
| Personal daily-plan progress | M2O | Completing a personal item does not automatically transition a Jira or GitHub issue. |
| External issue workflow status | Jira or GitHub | Closing an issue does not automatically complete or reopen a personal plan item. |
| External delivery receipt | M2O record of the provider result | Links the reviewed delivery to the external resource; sending is distinct from execution completion. |
| Future Slack progress interaction | Authorized command to M2O | Requires explicit user mapping and scope checks; a message or reaction alone is not authorization. |

Future synchronization must be explicit and separately implemented. Define supported directions and transition mappings, authorization, expected versions, conflict handling, event deduplication, retries, uncertain-write reconciliation, revoked-access behavior and audit history. Show source and freshness of observed external status. Do not introduce implicit bidirectional completion propagation.

1. Preserve the approved separate-state policy and all priority areas while implementing connection/storage primitives. Rendering remains a recommendation pending decision; provider implementation does not depend on an SSR migration.
2. Complete Jira OAuth, destination/field discovery, exact proposal, approved create/update, receipts and failure handling.
3. Complete Slack delivery/update and explicit user mapping, then command/modal/shortcut/progress actions with signatures, replay prevention, authorization and immediate acknowledgment.
4. Align GitHub delivery UI and implement supported LinkedIn context/post draft/publishing boundaries according to granted access.
5. Complete isolated synthetic visitor provisioning, private invitation/recovery flows and privacy lifecycle.
6. Finish department cinematic assets, focused task flows, completion view and daily planning usability, with reduced motion/accessibility/mobile/performance verification.
7. Prepare and test the actual Render runtime, persistence/recovery, secure origin/callbacks and operational monitoring before separately authorized deployment.

Render Free's sleep/ephemeral storage, database lifetime and worker/inference constraints are unresolved deployment dependencies. See RENDER_PLAN.md. In particular, sleeping web services cannot be assumed to meet Slack's three-second acknowledgment deadline. A target date does not change this limitation.

Freeze features only after completed user journeys pass; carry external blockers explicitly instead of calling disconnected functionality complete. October 4: integration/isolation regressions; October 5: accessibility/mobile/media/inference optimization; October 6: release-candidate rerun and operational/deployment review. This is a proposed work allocation, not an automation or guarantee.
