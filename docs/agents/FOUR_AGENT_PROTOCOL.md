# Four-agent coordination protocol

## Goal
Coordinate four independent chat sessions through GitHub without duplicate work, competing writers, or recursive agent-to-agent loops. The program goal is **5-USERS-READY**, not infrastructure perfection.

## Roles
- **Coordinator** — read-only decision/router role.
- **Researcher** — read-only evidence role.
- **Auditor** — read-only independent verification role.
- **Writer** — sole product-code writer.

Each chat must load `.github/skills/governance/SKILL.md` and its role skill before acting.

## GitHub as mailbox
Chats do not need direct communication. A task Issue is the mailbox and a PR is the implementation artifact. Handoffs must cite repository evidence rather than “another agent said”.

Recommended task title: `[TASK-ID] short objective`.

Recommended task body:

```
TASK-ID:
STATUS:
ROLE:
OBJECTIVE:
INPUTS:
ALLOWED:
FORBIDDEN:
ACCEPTANCE:
OUTPUT:
BLOCKERS:
```

Recommended status vocabulary:
`BACKLOG`, `NEEDS_RESEARCH`, `RESEARCHED`, `READY`, `IMPLEMENTING`, `PR_OPEN`, `AUDIT`, `CI`, `DONE`, `BLOCKED`, `AUDIT_FAIL`, `CI_FAIL`.

## Normal flow
Coordinator selects one critical-path task. Researcher is used only if knowledge is missing. Coordinator marks the bounded task READY. Writer implements on one branch and opens a PR. Auditor independently reviews the PR. CI provides objective verification. Coordinator closes or returns the task to Writer.

## Concurrency
Research and audit may run in parallel when scopes do not conflict. Start with one Writer globally. Multiple Writers are forbidden until the owner explicitly changes this protocol.

## No-loop rules
- One causal approach per attempt.
- One materially changed retry for the same failure.
- Then BLOCKED.
- No repeated CI polling narration.
- No agent may create follow-up work merely because it is “nice to have”.
- If a finding does not block the five-user MVP, record it as POST-MVP.

## First rollout
1. Keep current product state frozen.
2. Merge this coordination layer only after review/CI.
3. Open one pilot task for the next canonical gate.
4. Run Coordinator -> Researcher (if needed) -> Writer -> Auditor -> CI.
5. Expand to additional concurrent read-only work only after the pilot proves clean handoffs.

## Chat bootstrap prompts
Coordinator: `Act as VIDEO-SAAS Coordinator. Read AGENTS.md, canonical state, governance skill and coordinator skill. Work read-only. Select/route only the assigned critical-path task.`

Researcher: `Act as VIDEO-SAAS Researcher. Read AGENTS.md, canonical state, governance skill and researcher skill. Work read-only on the assigned TASK-ID and return evidence only.`

Auditor: `Act as VIDEO-SAAS Auditor. Read AGENTS.md, canonical state, governance skill and auditor skill. Work read-only. Audit only the assigned TASK-ID/PR; do not fix findings.`

Writer: `Act as VIDEO-SAAS Writer. Read AGENTS.md, canonical state, governance skill and writer skill. You are the sole code writer. Implement only a READY task within its contract; test and open/update a PR; do not self-expand scope.`
