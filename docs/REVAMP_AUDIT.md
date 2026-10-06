# Revamp audit report and implementation blueprint

Audit baseline: detached HEAD `8beac1b`, inspected before implementation. This report preserves the Phase 1 findings and records the locally implemented response. It does not imply that an external deployment, identity provider, or GitHub publication has been verified.

## Existing application

The repository contained 54 tracked files, including 31 Python files and 17 tests across six test files. Its product was a FastAPI/React transcript-to-GitHub tool. SQLite held meetings, transcript chunks, task drafts and issue publication records. Retrieval used Sentence Transformers with FAISS or an ephemeral memory fallback. Ollama generated task candidates, with explicit-action rules as a fallback. REST and MCP shared some application services, and a project Codex configuration started local tools.

That foundation was useful for a single-user demonstration, but authentication, workspace ownership, production migrations, and end-to-end verification were absent. The UI assumed an active backend and mixed network state, unsaved form state, and persisted meeting state.

## Prioritized findings

| Priority | Baseline defect and concrete consequence | Implemented response |
| --- | --- | --- |
| Blocking | REST mutations had no authenticated ownership boundary; another caller could read or replace meeting data. | Session/scoped-token authentication, per-workspace roles, restricted-meeting policy, service-level access checks and IDOR tests. |
| Blocking | GitHub publishing used a process-wide token and accepted fresh client task data; approved preview and sent body could differ. | Stored exact proposals with hashes, expiry, current revision/version checks, allowlisted repositories, durable operations and demo write blocking. |
| Blocking | Invalid citations such as index 999 fell back to chunk zero; ambiguous arrays could silently cite the wrong text. | Actual source UUID validation, same-revision evidence foreign keys, strict legacy citation validation without positional repair. |
| Blocking | Re-extraction and transcript replacement could erase human review, and title-only edits could delete drafts. | Immutable transcript/review versions, fingerprints that preserve existing edits, version-checked metadata edits and retained read-only history. |
| Important | SQLite schema had no migration history, workspace partitioning, connection pooling or durable worker queue. | PostgreSQL/SQLAlchemy, reviewed Alembic migration, bounded pools, separate lease-based worker and transactional queue creation. |
| Important | Memory vectors disappeared on restart, while fallback behavior could obscure the chosen provider. | Persisted bounded vectors and revision provider metadata; explicit local provider/fallback reporting. |
| Important | Extraction focused on retrieved context and narrow action rules; decisions, blockers and completed/negated items were mishandled. | Full-revision batched extraction, five outcome kinds, structured model validation and deterministic literal/negation guards. |
| Important | Names and relative dates could be treated as resolved facts. | Explicit participant confirmation with ambiguity handling, human-entered responsibilities, unresolved date hints and reviewer-selected calendar dates. |
| Important | Duplicate prevention considered only open issues; network retries could duplicate an ambiguous POST. | Marker scans include closed issues; persisted write intent and uncertain state prevent blind retries; read-only reconciliation. |
| Important | MCP extraction was labeled read-only despite state changes; network MCP could be exposed without authentication. | Accurate tool annotations, mandatory workspace token, shared service rules, local stdio only and sanitized failures. |
| Important | UI requests could overwrite newer state; mobile hid useful controls, and inputs lacked reliable labels. | Request cancellation, scope-owned state, unsaved-change protection, explicit load/error states, labeled controls, mobile layout and browser regression checks. |
| Important | No CI/container workflow established startup, migrations, health, or critical journeys. | Non-root images, Compose dependency ordering, readiness checks, local backup/restore helper, backend/component/browser suites and verification workflow. |
| Improvement | Documentation and dependency claims could overstate tested behavior. | Current setup/API/security/runbooks and an evidence register separating local verification from unexecuted CI and external services. |

## Security analysis

The most consequential OWASP concerns were broken access control, insecure design around publication approval, and authentication/configuration gaps. Input-to-citation coercion was an integrity vulnerability: an impressive issue body could cite unrelated transcript text. Provider-generated JSON and frontend data were both trust boundaries.

The revamp addresses injection through parameterized typed database access and strict input contracts; session mutations require CSRF and exact Origin checks. Safe validation errors omit supplied values. Uploads are byte-bounded and UTF-8/text-only. React renders text rather than raw HTML, and Nginx supplies CSP and security headers. Provider endpoints are configured server-side; a transcript cannot select an outbound URL. Secrets are privately configured, hashed where appropriate, and excluded from build contexts and logs.

Dependency audits were run on the pinned Python runtime and full frontend dependency tree, with discovered frontend advisories patched. This does not establish that OS images, optional semantic-model dependencies, or every possible vulnerability have been audited. Production proxy, TLS, identity policy, retention and monitoring remain environment-specific controls.

## Concrete blueprint

Keep an explainable monolith with two adapters and a worker, rather than introducing distributed services without a demonstrated load problem. PostgreSQL owns normalized workspace/meeting/review state and durable jobs. Local inference stays in Ollama. The browser owns transient edits; services and database constraints own authorization and data integrity.

The database migration creates the new schema without modifying the legacy SQLite file. A read-only legacy importer defaults to dry run, rejects malformed citations/confidence, imports atomically, preserves human wording and original evidence, and retains publication provenance without replaying external writes. Existing shared migration history is not rewritten.

The API exposes workspace-scoped routes with owners, reviewers, editors and viewers. Mutating endpoints validate strict runtime contracts; long computation returns a durable job. Review conflicts use HTTP 409. The worker rechecks lease, membership and revision before commit. Publication approval is a separate deliberate boundary after exact payload preparation.

The UI provides three department examples, sourced review cards, confirmed participant assignment, relative-date resolution, read-only history, local export, exact issue previews, workspace administration and audit access. HR/finance demonstrate workflow coordination; the application does not make hiring, compensation, credit or accounting judgments.

LinkedIn uses its approved OIDC product only for consenting users. Arbitrary name lookup is not available through ordinary self-service OIDC. No approved app existed; the functional configurable adapter is gated until actual credentials and approval are supplied. Signed synthetic-provider tests verify its security behavior without implying live product access.

## Phase completion and professional limits

Phases 2–5 have been implemented locally: PostgreSQL schema/migration/access layer, authenticated backend/services, modular frontend, tests, container configuration and CI configuration. Detailed observed results are in `VALIDATION.md`.

The code is not certified as enterprise-ready merely because these layers exist. Before public deployment, verify the target environment, TLS/cookies/proxy policy, identity lifecycle, backup recovery, retention, external-provider permissions, alerts and representative load. Optional semantic retrieval and live LinkedIn/GitHub integrations remain unverified. All source changes remain uncommitted; no remote action was performed.
