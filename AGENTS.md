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

Repository Control A-D and the minimum development infrastructure are complete.
`product-flow-001` passed the isolated Product Lab and the user authorized promotion.
The explicitly authorized current phase is PRODUCT_PROMOTION.
Provider Preflight remains forbidden and no paid provider requests are authorized.

## Product promotion boundary

- Promote only behavior already validated by `product-flow-001`.
- Canonical code belongs under `apps/api/src/modules/planning/**`.
- Canonical `apps/**` MUST NOT import or depend on `lab/**`.
- Do not add HTTP endpoints, persistence, provider SDKs or UI during this promotion task.
- The validated lab artifact remains as provenance and must not be treated as a runtime dependency.
- Do not declare promotion complete until Repository Control CI and Product CI pass on the exact promotion head.
