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

## Four-agent operating model

The repository may be operated by four independent chat agents. GitHub is their shared mailbox and source of truth; the human owner MUST NOT be used as a message courier.

Roles:
- **COORDINATOR** — READ-ONLY for product code. Recovers state, selects the next critical-path TASK-ID, publishes assignments in GitHub, routes handoffs and controls gates. NO CODE, NO FIX, NO IMPLEMENTATION.
- **RESEARCHER** — STRICTLY READ-ONLY. Investigates only an assigned TASK-ID and publishes evidence, risks and implementation constraints. No branches, commits, fixes, merges, provider activation or paid calls.
- **AUDITOR** — STRICTLY READ-ONLY. Audits the assigned TASK-ID/PR, verifies scope/tests/CI/security/regressions and publishes PASS/FAIL with evidence. Never fixes its own findings.
- **WRITER** — the single product-code writer. Implements only a READY Task Contract, makes the minimum scoped change, tests it and opens/updates the PR. Does not self-audit, invent the next task or expand architecture.

### GitHub mailbox protocol

Agents communicate through the repository, not through copied chat messages.

A coordination handoff MUST use a GitHub Issue or the relevant PR conversation and include:
- `TASK-ID`
- `STATUS`
- `OWNER_ROLE`
- `OBJECTIVE`
- `INPUTS/EVIDENCE`
- `ALLOWED SCOPE`
- `FORBIDDEN SCOPE`
- `ACCEPTANCE`
- `BLOCKERS`
- `NEXT_ROLE` when known

Canonical coordination states:
`BACKLOG -> NEEDS_RESEARCH -> RESEARCHED -> READY -> IMPLEMENTING -> PR_OPEN -> AUDIT -> CI -> DONE`.

Failure states:
`BLOCKED`, `AUDIT_FAIL`, `CI_FAIL`.

An agent starting or resuming a session MUST first recover repository state and inspect GitHub for an assignment addressed to its role. It must not ask the owner to copy a handoff to another agent. It publishes the handoff in GitHub and stops or continues only as authorized by its role and Task Contract.

### Single-writer and anti-loop

- Exactly one Writer may own an implementation scope at a time.
- Coordinator, Researcher and Auditor never modify product code.
- Do not create a second journal, checkpoint system, lock system or orchestration state machine. Reuse Task Contracts, `.state/`, `projectctl`, PRs, Issues and CI.
- One causal approach per failed attempt. One materially changed retry is allowed. A repeated equivalent failure becomes `BLOCKED` and returns to Coordinator.
- Repeated CI polling is not productive work; inspect asynchronous status only when a gate requires it.

### Program objective and infrastructure freeze

The operating objective is **5-USERS-READY**, not infrastructure perfection.
Infrastructure is frozen unless a demonstrated blocker on the five-user critical path requires a change.
Non-blocking improvements are POST-MVP.

Do not declare 5-USERS-READY until the critical user path, persistence/isolation, job lifecycle, provider abstraction, generation pipeline, QA/patch/verify, assembly, error handling and mock E2E are verified.

Provider Preflight and paid provider requests remain OFF until explicit owner authorization.
