---
name: m2o-deploy-security
description: Plan, review and verify M2O CI/CD, container hosting, proxy trust and security release gates for Phase 8 or later deployment work. Use for release engineering, not as authorization to provision or deploy.
---

# M2O deployment and security gates

Resolve repository, branch, commit and dirty state. Read AGENTS.md and docs/M2O_IMPLEMENTATION_CONTRACT.md. Read docs/SECURITY.md, HOSTED_DEMO_RUNTIME.md, RENDER_PLAN.md and current validation as relevant. These paths are repository-relative. Verify executable .github/workflows/verify.yml, Dockerfile.render, render.yaml, compose.yaml, backend/scripts/serve_demo.py, app/hosted.py, settings and ingress configuration; report stale documentation.

Separate credential-free synthetic hosting from invited private use. Verify startup guards, dedicated database, blocked provider effects, origin, cookies and static containment. Keep local Ollama distinct from rules-mode hosting; do not silently add cloud inference. Research current official hosting limits/prices instead of freezing them here.

The Oct5 audit identified shared proxy-IP quotas. Reinspect current source before treating this as open or fixed. Establish direct peers, ingress header overwrite/append rules and actual public reachability. Never solve attribution with arbitrary forwarding-header trust or trust-all. Test legitimate chains, spoofed headers, direct requests, distinct clients, shared NAT/IPv6 and multi-process budgets as relevant. A deliberate shared cap needs explicit UX/abuse analysis.

Inspect affected session hashing, CSRF/origin, workspace/restricted-meeting checks, OAuth replay/state, revocation, credential encryption, uploads, CSP and safe errors/logs. Dependency/image checks must not weaken controls for passing results. Tests do not establish blanket security or compliance.

Plan exact-commit CI, compatible migrations, supervisor/API/worker health, lease recovery, shutdown, backup/restore and rollback. Builds are not hosted startup tests; process liveness does not establish worker health. Measure actual cold/warm resource behavior before promising availability/capacity.

Before external mutations establish existing explicit authorization and exact repo/branch, account/service, environment/database, scope and cost ceiling. A previous checkpoint push does not authorize later publication. Prepare concrete reviewable changes first. Do not guess deployment identities, enable paid upgrades or alter access/secrets during investigation.

Report commands, revisions, results and environment. Retrieve hosted CI for the actual commit; local passes do not substitute. Define stop/rollback conditions and owner actions. Give user research links before adopting services; retain honest hosted/live gaps.
