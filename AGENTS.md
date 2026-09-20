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
The explicitly authorized current phase is PRODUCT_LAB.
Provider Preflight remains forbidden and no paid provider requests are authorized.

## Product Lab boundary

- Experimental product code belongs under `lab/**` only.
- `apps/**` is canonical product code and is outside the scope of the active lab task.
- Canonical code MUST NOT import from `lab/**`.
- Lab experiments must work without real provider credentials or paid external calls unless a later Task Contract explicitly authorizes them.
- A lab experiment is not production merely because it passes tests.
- Promotion to canonical code requires observed lab validation, Repository Control CI, Product CI, explicit user approval, and a separate promotion Task Contract.
- Failed or superseded experiments stay non-canonical until an authorized cleanup task removes them.
