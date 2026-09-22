# AGENTS.md

## Authority

Read these before any repository work:
1. This file.
2. `REPO_MAP.yaml` for navigation only.
3. `PROJECT_STATE.yaml`.
4. `.state/CURRENT.json`.
5. The active Task Contract under `tasks/`, only when `active_task_id` is not null.

Read `.state/RESUME.md` only on demand as a generated human view; it is not an independent source of truth.

## Low-token navigation and audits

- `REPO_MAP.yaml` is the short canonical navigation index. It is not operational authority and MUST NOT override this file, `PROJECT_STATE.yaml`, the active Task Contract or `.state/CURRENT.json`.
- Read only the state fields identified in `REPO_MAP.yaml` first; expand when the current task or evidence requires more context.
- NEVER read `.state/journal.ndjson` in full. Query only the event, sequence or bounded range needed for the claim under review.
- Do not load all closed Task Contracts. Read only the active Task Contract, when one exists; consult a closed contract only as targeted historical evidence.
- Start audits with changed paths, the exact diff, modified files and directly related tests. Expand to dependencies or history only when a concrete finding requires it.
- Treat manifests, evidence and dependency lockfiles as on-demand material rather than startup context.
- `apps/api/src/` is the canonical product backend. Root `src/` is baseline-validation support used by the root integrity tests; it is NOT the SaaS backend or product runtime and MUST NOT receive new business code.

## Repository Control Plane

- `.state/` is only the durable/recoverable cursor of the engineering agent.
- `.state/` MUST NOT store customer video job state.
- Customer production state belongs to PostgreSQL, Queues/Workflows, provider ledgers and asset/cost ledgers.
- Task scope comes from the active Task Contract. Do not expand it silently.
- Frozen manifests are authoritative baseline artifacts and must not be modified unless an approved amendment explicitly authorizes it.
- A state string inside a frozen manifest (including `READY_FOR_PROVIDER_PREFLIGHT`) is baseline metadata, NOT the operational cursor and MUST NOT authorize provider activity or NEXT_ACTION.
- Operational NEXT_ACTION authority comes from `PROJECT_STATE.yaml`, the active Task Contract when one exists, and the durable `.state/` cursor.
- Never claim a test, probe, cost, provider capability or external action was executed unless it was actually observed.
- Never store API keys, tokens, credentials or secrets in `.state/`, tasks, manifests or evidence.
- Equivalent attempts must not be repeated without a causal change or a verified transient failure.
- A paid request with unknown billing state blocks an equivalent paid retry.

## Current Gate

Repository Control A-D and minimum development infrastructure are complete.
The validated `product-flow-001` planning core has been promoted to canonical backend code under `apps/api/src/modules/planning/`.
Canonical planning API integration, owner-scoped planning persistence, and authenticated owner authorization have been merged. Owner-scoped endpoints now verify the authenticated principal server-side and do not trust a caller-supplied `owner_id` as identity.
Provider Preflight remains forbidden and no paid provider requests are authorized.
`TASK-AUDIT-REMEDIATION-001` is complete. The repository is IDLE; no later product gate or Task Contract is authorized.

## Canonical planning boundary

- `apps/api/src/modules/planning/` is canonical product code.
- Canonical `apps/**` MUST NOT import or depend on `lab/**`.
- `lab/**` remains provenance/experimentation, not a runtime dependency.
- Owner-scoped persistence plus authenticated server-side authorization is canonical and cross-owner denial is required by tests.
- Authentication/authorization must remain enabled and verified for the five-user pilot.
- Do not add later product scope, UI, provider SDKs or paid provider calls without a Task Contract that explicitly authorizes that scope.

## Single Autonomous Operator

The repository is operated by one active autonomous engineering chat. GitHub remains the source of truth, durable mailbox, evidence record and recovery point. The human owner MUST NOT be used as a courier between artificial roles.

The operator MUST continue through the authorized critical path without waiting for routine owner confirmations. For each gate it performs these phases sequentially inside the same active session:

`RECOVER -> RESEARCH -> CONTRACT -> IMPLEMENT -> TEST -> AUDIT -> CI -> INTEGRATE -> NEXT_GATE`

These are execution phases, not separate agents. The operator may write product code only during IMPLEMENT/FIX work authorized by the active Task Contract. During RESEARCH and AUDIT it must reason from repository evidence and must not silently expand implementation scope.

### Autonomous continuation

At start/resume and before each new gate, recover the real state from:
- `AGENTS.md`
- `PROJECT_STATE.yaml`
- active `tasks/**` Task Contract
- `.state/CURRENT.json`
- relevant Issues and PRs
- CI/check results

Then continue automatically from the first incomplete authorized phase.

Do NOT stop merely because a handoff names `RESEARCHER`, `COORDINATOR`, `WRITER` or `AUDITOR`. Those legacy role labels are interpreted as phase ownership inside this single operator. Existing Issues/handoffs remain valid evidence and do not need to be recreated solely to rename the role.

The operator may create/update branches, scoped code, tests, evidence, Issues/PRs and repository state when the active Task Contract authorizes those paths/actions. It may audit its own implementation only as a distinct post-implementation phase after reviewing the exact diff, tests and CI evidence. Preserve the repository's Task Contract and CI gates; do not bypass them for speed.

When acceptance gates pass, integrate according to repository policy, perform post-merge verification, update canonical state, select/materialize only the next critical-path Task Contract, and continue. Do not open later gates in parallel.

### Owner-only stop conditions

Stop and request the owner only when at least one of these is true:
- credentials, secrets or account access not already available are required;
- Provider Preflight or any paid provider request would be required;
- authorization to spend money is required;
- a material product/business decision is not already frozen by repository evidence;
- an irreversible/destructive external action requires owner approval;
- a technical blocker remains after the anti-loop allowance and cannot be resolved inside authorized scope;
- the next required change would materially exceed the current approved product scope.

Routine research conclusions, code edits within scope, test fixes, PR creation, audit, CI verification, merges allowed by repository policy, state updates and transition to the next already-defined critical-path gate do NOT require owner confirmation.

### Task lifecycle and evidence

Use the existing repository mechanisms rather than creating a second orchestration system.

Canonical task states:
`BACKLOG -> NEEDS_RESEARCH -> RESEARCHED -> READY -> IMPLEMENTING -> PR_OPEN -> AUDIT -> CI -> DONE`.

When there is no authorized work, the repository is explicitly IDLE: `active_task_id: null`, `next_gate: NONE_AUTHORIZED`, and `next_gate_authorized: false`. A Task Contract in `DONE` or legacy terminal `PASS` state MUST NOT remain active.

Failure states:
`BLOCKED`, `AUDIT_FAIL`, `CI_FAIL`.

For durable handoffs/evidence, use the relevant GitHub Issue or PR and include as applicable:
- `TASK-ID`
- `STATUS`
- `OBJECTIVE`
- `INPUTS/EVIDENCE`
- `ALLOWED SCOPE`
- `FORBIDDEN SCOPE`
- `ACCEPTANCE`
- `BLOCKERS`
- `NEXT_PHASE`

Legacy `OWNER_ROLE` / `NEXT_ROLE` fields may remain for compatibility but MUST NOT cause the single operator to wait for another chat.

### Single-writer discipline and anti-loop

- There is exactly one active operator and therefore one product-code writer.
- Never run two implementation scopes in parallel.
- Do not create a second journal, checkpoint system, lock system or orchestration state machine. Reuse Task Contracts, `.state/`, `projectctl`, PRs, Issues and CI.
- One causal approach per failed attempt. One materially changed retry is allowed. A repeated equivalent failure becomes `BLOCKED`.
- Do not repeatedly poll CI. Inspect asynchronous status only when a gate requires it.
- Do not fix findings by broad refactor. Fix the smallest demonstrated cause within the active Task Contract.
- Preserve an evidence trail for tests and CI actually observed.

## Program objective and infrastructure freeze

The operating objective is **5-USERS-READY**, not infrastructure perfection.
Infrastructure is frozen unless a demonstrated blocker on the five-user critical path requires a change.
Non-blocking improvements are POST-MVP.

Do not declare 5-USERS-READY until the critical user path, persistence/isolation, job lifecycle, provider abstraction, generation pipeline, QA/patch/verify, assembly, error handling and mock E2E are verified.

Provider Preflight and paid provider requests remain OFF until explicit owner authorization.
