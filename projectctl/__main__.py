from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import (
    ProjectCtlError,
    attempt_fingerprint,
    check_scope,
    checkpoint,
    find_root,
    recover,
    register_attempt,
    resume,
    run_evidence,
    transition_repository_state,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m projectctl")
    parser.add_argument("--root", type=Path, default=None, help="repository root (auto-detected by default)")
    sub = parser.add_subparsers(dest="command", required=True)

    cp = sub.add_parser("checkpoint", help="create a durable repository-control checkpoint")
    cp.add_argument("--reason", default="manual")
    cp.add_argument("--next-action", default=None)

    sub.add_parser("recover", help="validate and repair recoverable repository-control state")
    sub.add_parser("resume", help="recover if needed and print generated resume state")

    scope = sub.add_parser("check-scope", help="validate repository changes against the active Task Contract")
    scope.add_argument("--task", type=Path, default=None, help="explicit Task Contract path")
    scope.add_argument("--base-ref", default=None, help="also include committed changes since this Git ref")

    attempt = sub.add_parser("attempt-fingerprint", help="compute and optionally register an anti-loop attempt fingerprint")
    attempt.add_argument("--operation", required=True)
    attempt.add_argument("--input-json", default="{}", help="JSON value used as fingerprint input")
    attempt.add_argument("--causal-change", default=None)
    attempt.add_argument("--register", action="store_true")
    attempt.add_argument("--paid", action="store_true")

    evidence = sub.add_parser("evidence", help="execute a command and persist machine-readable evidence")
    evidence.add_argument("--id", required=True, dest="evidence_id")
    evidence.add_argument("--expect-exit", type=int, default=0)
    evidence.add_argument("--paid", action="store_true")
    evidence.add_argument("command_args", nargs=argparse.REMAINDER)

    transition = sub.add_parser("transition", help="apply a gated repository-control phase transition")
    transition.add_argument("--to", required=True, dest="to_phase")
    transition.add_argument("--evidence", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        root = args.root.resolve() if args.root else find_root()
        if args.command == "checkpoint":
            result = checkpoint(root, reason=args.reason, next_action=args.next_action)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "recover":
            result = recover(root)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "resume":
            result, text = resume(root)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            print(text)
        elif args.command == "check-scope":
            task = args.task
            if task is not None and not task.is_absolute():
                task = root / task
            result = check_scope(root, task_contract_path=task, base_ref=args.base_ref)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "attempt-fingerprint":
            inputs = json.loads(args.input_json)
            if args.register:
                result = register_attempt(
                    root,
                    operation=args.operation,
                    inputs=inputs,
                    causal_change=args.causal_change,
                    paid_request=args.paid,
                )
            else:
                current = json.loads((root / ".state" / "CURRENT.json").read_text(encoding="utf-8"))
                result = {
                    "attempt_fingerprint": attempt_fingerprint(
                        task_id=current.get("task", {}).get("task_id"),
                        operation=args.operation,
                        inputs=inputs,
                        causal_change=args.causal_change,
                    )
                }
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif args.command == "evidence":
            command = list(args.command_args)
            if command and command[0] == "--":
                command = command[1:]
            result = run_evidence(
                root,
                evidence_id=args.evidence_id,
                command=command,
                expected_exit=args.expect_exit,
                paid_request=args.paid,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "PASS" else 1
        elif args.command == "transition":
            result = transition_repository_state(root, to_phase=args.to_phase, evidence_ids=args.evidence)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ProjectCtlError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
