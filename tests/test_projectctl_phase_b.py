import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from projectctl.core import (
    JournalCorruption,
    LockBusy,
    RecoveryBlocked,
    canonical_json_bytes,
    checkpoint,
    event_sha256,
    recover,
    render_resume,
    task_lock,
    write_atomic,
)


def run(cwd: Path, *args: str):
    subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".state" / "locks").mkdir(parents=True)
    (root / "tasks").mkdir()
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "PROJECT_STATE.yaml").write_text("current_authorized_phase: PHASE_B\n", encoding="utf-8")
    (root / "tasks" / "TASK.yaml").write_text("task: {id: TASK-B}\n", encoding="utf-8")
    current = {
        "schema_version": 1,
        "state_version": 1,
        "checkpoint_id": "BOOTSTRAP",
        "updated_at": "2026-09-20T00:00:00Z",
        "task": {"task_id": "TASK-B", "task_contract_sha256": "a" * 64, "phase": "PHASE_B"},
        "progress": {"completed_steps": [], "next_action": "test", "next_command": None},
        "verification": {"phase_a_acceptance_passed": True, "baseline_regression_suite_passed": True},
        "external_operations": {
            "provider_preflight_started": False,
            "paid_requests_allowed": False,
            "unknown_billing_requests": [],
            "pending_paid_requests": [],
        },
        "blocked": None,
    }
    (root / ".state" / "CURRENT.json").write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    first = {
        "event_id": "BOOTSTRAP",
        "sequence": 1,
        "timestamp": "2026-09-20T00:00:00Z",
        "task_id": "TASK-B",
        "attempt_id": None,
        "actor_id": "test",
        "event_type": "BOOTSTRAP",
        "previous_event_sha256": None,
        "payload": {"phase": "PHASE_B"},
    }
    first["event_sha256"] = event_sha256(first)
    (root / ".state" / "journal.ndjson").write_bytes(canonical_json_bytes(first) + b"\n")
    (root / ".state" / "RESUME.md").write_text(render_resume(current), encoding="utf-8")
    run(root, "git", "init", "-b", "main")
    run(root, "git", "config", "user.email", "test@example.com")
    run(root, "git", "config", "user.name", "Test")
    run(root, "git", "add", ".")
    run(root, "git", "commit", "-m", "bootstrap")
    return root


def test_checkpoint_materializes_current_resume_and_journal(tmp_path):
    root = make_repo(tmp_path)
    result = checkpoint(root, reason="unit-test", next_action="next")
    current = json.loads((root / ".state" / "CURRENT.json").read_text())
    lines = (root / ".state" / "journal.ndjson").read_text().splitlines()
    assert result["status"] == "CHECKPOINT_OK"
    assert len(lines) == 2
    assert current["last_journal_sequence"] == 2
    assert current["checkpoint_id"] == result["checkpoint_id"]
    assert current["repository"]["branch"] == "main"
    assert (root / ".state" / "RESUME.md").read_text() == render_resume(current)


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not portable to Windows")
def test_write_atomic_preserves_existing_file_permissions(tmp_path):
    path = tmp_path / "state.json"
    path.write_bytes(b"before")
    path.chmod(0o644)

    write_atomic(path, b"after")

    assert path.read_bytes() == b"after"
    assert path.stat().st_mode & 0o777 == 0o644


def test_recover_truncates_incomplete_final_line(tmp_path):
    root = make_repo(tmp_path)
    checkpoint(root)
    with (root / ".state" / "journal.ndjson").open("ab") as f:
        f.write(b'{"partial"')
    result = recover(root)
    assert "TRUNCATED_INCOMPLETE_FINAL_JOURNAL_LINE" in result["actions"]
    assert (root / ".state" / "journal.ndjson").read_bytes().endswith(b"\n")


def test_recover_blocks_intermediate_corruption(tmp_path):
    root = make_repo(tmp_path)
    raw = (root / ".state" / "journal.ndjson").read_bytes()
    (root / ".state" / "journal.ndjson").write_bytes(raw + b"not-json\n" + raw)
    with pytest.raises(JournalCorruption):
        recover(root)


def test_recover_rebuilds_current_when_journal_ahead(tmp_path):
    root = make_repo(tmp_path)
    checkpoint(root)
    current = json.loads((root / ".state" / "CURRENT.json").read_text())
    # Roll CURRENT/RESUME back while leaving journal at the newer checkpoint.
    current["last_journal_sequence"] = 1
    current["checkpoint_id"] = "BOOTSTRAP"
    current.pop("repository", None)
    (root / ".state" / "CURRENT.json").write_text(json.dumps(current, indent=2) + "\n")
    result = recover(root)
    rebuilt = json.loads((root / ".state" / "CURRENT.json").read_text())
    assert "REBUILT_CURRENT_FROM_JOURNAL" in result["actions"]
    assert rebuilt["last_journal_sequence"] == 2


def test_recover_regenerates_stale_resume(tmp_path):
    root = make_repo(tmp_path)
    checkpoint(root)
    (root / ".state" / "RESUME.md").write_text("stale", encoding="utf-8")
    result = recover(root)
    current = json.loads((root / ".state" / "CURRENT.json").read_text())
    assert "REGENERATED_RESUME" in result["actions"]
    assert (root / ".state" / "RESUME.md").read_text() == render_resume(current)


def test_recover_blocks_working_tree_mismatch(tmp_path):
    root = make_repo(tmp_path)
    checkpoint(root)
    (root / "untracked.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(RecoveryBlocked) as exc:
        recover(root)
    assert exc.value.code == "RECOVERY_STATE_MISMATCH"


def test_task_lock_rejects_second_writer(tmp_path):
    root = make_repo(tmp_path)
    with task_lock(root):
        with pytest.raises(LockBusy):
            with task_lock(root):
                pass


def test_unknown_billing_blocks_recovery(tmp_path):
    root = make_repo(tmp_path)
    checkpoint(root)
    current_path = root / ".state" / "CURRENT.json"
    current = json.loads(current_path.read_text())
    current["external_operations"]["unknown_billing_requests"] = ["req-1"]
    current_path.write_text(json.dumps(current, indent=2) + "\n")
    with pytest.raises(RecoveryBlocked) as exc:
        recover(root)
    assert exc.value.code == "RECOVERY_UNRESOLVED_BILLING"
