---
name: governance
description: Shared guardrails for every agent working on VIDEO-SAAS. Use before any coordination, research, audit, implementation, review, or recovery task.
---

# VIDEO-SAAS multi-agent governance

## Mission
Drive the repository to **5-USERS-READY**: five test users can create projects and complete the product flow with mock/free validation; paid provider calls remain disabled until the owner explicitly authorizes the provider-spend gate.

## Authority order
Read and obey, in order:
1. `AGENTS.md`
2. `PROJECT_STATE.yaml`
3. active Task Contract under `tasks/`
4. `.state/CURRENT.json`
5. this skill and the assigned role skill
6. the GitHub Issue/task used for coordination

If instructions conflict, stop and report the conflict. Never silently reinterpret canonical state.

## Non-negotiable rules
- GitHub is the shared source of truth between chats.
- One task has one `TASK-ID`.
- Exactly one Writer may modify product code for an active implementation task.
- Coordinator, Researcher and Auditor are READ-ONLY with respect to product code.
- Do not use branches as chat. Use the task Issue/PR for handoffs; branches isolate code changes.
- Do not create a second state machine, journal, checkpoint system, or lock system. Reuse `projectctl`, `.state/`, Task Contracts and existing CI.
- Infrastructure is frozen unless a demonstrated blocker on the 5-user critical path requires a change.
- No scope expansion. Non-blocking improvements go to POST-MVP.
- Never repeat an equivalent failed attempt without a causal change or verified transient failure.
- Never claim tests, CI, provider capability, cost, or external action unless observed.
- Never store secrets or credentials in repository coordination artifacts.
- Provider preflight and paid requests remain OFF until explicit owner authorization.
- Never merge to `main` unless the task contract and owner authorization permit it.

## Anti-loop
For the same failure:
1. record evidence and root-cause hypothesis;
2. allow one materially changed retry;
3. if it fails for the same cause, mark `BLOCKED` and return control to Coordinator.

Polling is not work. Check asynchronous CI only when needed for a gate; do not narrate repeated equivalent checks.

## Shared task states
`BACKLOG -> NEEDS_RESEARCH -> RESEARCHED -> READY -> IMPLEMENTING -> PR_OPEN -> AUDIT -> CI -> DONE`

Failure states: `BLOCKED`, `AUDIT_FAIL`, `CI_FAIL`.
Only Coordinator chooses the next task/state; Writer may report implementation/PR/CI facts but does not invent the next task.

## Definition of done for the program
Do not call the SaaS 5-USERS-READY until the critical user path, persistence/isolation, job lifecycle, provider abstraction, generation pipeline, QA/patch/verify, assembly, error handling and mock E2E are verified. Real paid-provider activation is a later explicit gate.
