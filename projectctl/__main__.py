from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import ProjectCtlError, checkpoint, find_root, recover, resume


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m projectctl")
    parser.add_argument("--root", type=Path, default=None, help="repository root (auto-detected by default)")
    sub = parser.add_subparsers(dest="command", required=True)

    cp = sub.add_parser("checkpoint", help="create a durable repository-control checkpoint")
    cp.add_argument("--reason", default="manual")
    cp.add_argument("--next-action", default=None)

    sub.add_parser("recover", help="validate and repair recoverable repository-control state")
    sub.add_parser("resume", help="recover if needed and print generated resume state")
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
        return 0
    except ProjectCtlError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
