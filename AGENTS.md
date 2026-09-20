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

Repository Control Phase A only.
Provider Preflight is forbidden until a later authorized phase explicitly enables it.
No paid provider requests are authorized.

## Phase A Scope

Allowed paths for `TASK-REPO-CONTROL-001`:
- `AGENTS.md`
- `PROJECT_STATE.yaml`
- `tasks/TASK-REPO-CONTROL-001.yaml`
- `.state/**`

Everything else is read-only for this task.
