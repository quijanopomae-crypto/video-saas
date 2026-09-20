# AGENTS.md

## Authority

Read these before any repository work:
1. This file.
2. `PROJECT_STATE.yaml`.
3. The active Task Contract under `tasks/`.
4. `.state/CURRENT.json`.
5. `.state/RESUME.md` as a generated human view only.

## Repository Control Plane

- `.state/` is only the durable/recoverable cursor of the engineering agent.
- `.state/` MUST NOT store customer video job state.
- Customer production state belongs to PostgreSQL, Queues/Workflows, provider ledgers and asset/cost ledgers.
- Task scope comes from the active Task Contract. Do not expand it silently.
- Frozen manifests are authoritative and must not be modified unless an approved amendment explicitly authorizes it.
- Never claim a test, probe, cost, provider capability or external action was executed unless it was actually observed.
- Never store API keys, tokens, credentials or secrets in `.state/`, tasks, manifests or evidence.
- Equivalent attempts must not be repeated without a causal change or a verified transient failure.
- A paid request with unknown billing state blocks an equivalent paid retry.

## Current Gate

Repository Control A-D and minimum development infrastructure are complete.
The validated `product-flow-001` planning core has been promoted to canonical backend code under `apps/api/src/modules/planning/`.
The promotion task is complete subject to normal merge/post-merge verification.
Provider Preflight remains forbidden and no paid provider requests are authorized.

## Canonical planning boundary

- `apps/api/src/modules/planning/` is canonical product code.
- Canonical `apps/**` MUST NOT import or depend on `lab/**`.
- `lab/**` remains provenance/experimentation, not a runtime dependency.
- The next product gate is CANONICAL_PLANNING_API_INTEGRATION.
- Do not add HTTP endpoints, persistence, UI, provider SDKs or paid provider calls without a new Task Contract that explicitly authorizes that scope.
