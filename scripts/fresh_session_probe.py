from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from projectctl.core import git_snapshot, read_journal, render_resume, validate_operating_state


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe(root: Path) -> dict:
    root = root.resolve()
    agents = root / "AGENTS.md"
    project_path = root / "PROJECT_STATE.yaml"
    current_path = root / ".state" / "CURRENT.json"
    resume_path = root / ".state" / "RESUME.md"
    for path in (agents, project_path, current_path, resume_path):
        if not path.exists():
            raise RuntimeError(f"missing durable handoff file: {path.relative_to(root)}")

    project = yaml.safe_load(project_path.read_text(encoding="utf-8"))
    current = json.loads(current_path.read_text(encoding="utf-8"))
    operating = validate_operating_state(root)
    active_task_id = project.get("active_task_id")
    task_path = None
    if active_task_id is None:
        current_task = current.get("task") or {}
        if current_task.get("task_id") is not None:
            raise RuntimeError("CURRENT task_id must be null while repository is IDLE")
        if current_task.get("task_contract_sha256") not in {None, ""}:
            raise RuntimeError("CURRENT Task Contract hash must be null while repository is IDLE")
    else:
        task_path = root / "tasks" / f"{active_task_id}.yaml"
        if not task_path.exists():
            raise RuntimeError(f"active Task Contract missing: {task_path.relative_to(root)}")
        contract = yaml.safe_load(task_path.read_text(encoding="utf-8"))
        if (contract.get("task") or {}).get("id") != active_task_id:
            raise RuntimeError("Task Contract id does not match PROJECT_STATE active_task_id")
        if (current.get("task") or {}).get("task_id") != active_task_id:
            raise RuntimeError("CURRENT task_id does not match PROJECT_STATE active_task_id")
        expected_contract_hash = sha256_file(task_path)
        if (current.get("task") or {}).get("task_contract_sha256") != expected_contract_hash:
            raise RuntimeError("CURRENT Task Contract SHA-256 mismatch")
    expected_resume = render_resume(current)
    if resume_path.read_text(encoding="utf-8") != expected_resume:
        raise RuntimeError("RESUME.md is not the generated view of CURRENT.json")
    events, incomplete = read_journal(root, repair_incomplete_final_line=False)
    if incomplete:
        raise RuntimeError("journal has an incomplete final line")
    if not events:
        raise RuntimeError("journal contains no events")
    if current.get("last_journal_sequence") != len(events):
        raise RuntimeError("CURRENT sequence does not match journal")
    if current.get("last_journal_event_sha256") != events[-1].get("event_sha256"):
        raise RuntimeError("CURRENT tail hash does not match journal")
    ext = current.get("external_operations") or {}
    if ext.get("provider_preflight_started"):
        raise RuntimeError("Provider Preflight unexpectedly started")
    if ext.get("paid_requests_allowed"):
        raise RuntimeError("paid provider requests unexpectedly enabled")

    read_order = ["AGENTS.md", "PROJECT_STATE.yaml"]
    if task_path is not None:
        read_order.append(str(task_path.relative_to(root)))
    read_order += [".state/CURRENT.json", ".state/RESUME.md", ".state/journal.ndjson"]

    return {
        "status": "FRESH_SESSION_HANDOFF_OK",
        "operating_state": operating["status"],
        "read_order": read_order,
        "active_task_id": active_task_id,
        "phase": (current.get("task") or {}).get("phase"),
        "next_gate": project.get("next_gate"),
        "next_gate_authorized": project.get("next_gate_authorized"),
        "next_action": (current.get("progress") or {}).get("next_action"),
        "journal_sequence": len(events),
        "provider_preflight_started": False,
        "paid_requests_allowed": False,
        "repository_snapshot": git_snapshot(root),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        print(json.dumps(probe(args.root), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "FRESH_SESSION_HANDOFF_FAIL", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
