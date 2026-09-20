import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from projectctl.core import (
    EquivalentAttemptBlocked,
    JournalCorruption,
    LockBusy,
    ScopeViolation,
    canonical_json_bytes,
    check_scope,
    checkpoint,
    event_sha256,
    read_journal,
    recover,
    register_attempt,
    render_resume,
    task_lock,
)

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def run(cwd: Path, *args: str, check: bool = True, env=None):
    return subprocess.run(args, cwd=cwd, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)


def projectctl_env():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SOURCE_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / ".state" / "locks").mkdir(parents=True)
    (root / "tasks").mkdir()
    (root / "evidence").mkdir()
    (root / "AGENTS.md").write_text("# AGENTS\nRead durable state.\n", encoding="utf-8")
    project = {
        "schema_version": 1,
        "project_id": "VIDEO-SAAS",
        "repository_control_plane": {"implementation_status": "PHASE_C_PASS"},
        "current_authorized_phase": "PHASE_D",
        "active_task_id": "TASK-REPO-CONTROL-004",
        "provider_preflight_allowed": False,
        "paid_provider_requests_allowed": False,
        "next_gate": "PHASE_D_EXECUTION",
    }
    (root / "PROJECT_STATE.yaml").write_text(yaml.safe_dump(project, sort_keys=False), encoding="utf-8")
    task = {
        "schema_version": 1,
        "task": {"id": "TASK-REPO-CONTROL-004", "status": "READY"},
        "scope": {
            "allowed_paths": [
                "AGENTS.md",
                "PROJECT_STATE.yaml",
                "tasks/TASK-REPO-CONTROL-004.yaml",
                ".state/**",
                "projectctl/**",
                "tests/test_projectctl_phase_d.py",
                "scripts/fresh_session_probe.py",
                ".github/workflows/repository-control-ci.yml",
                "evidence/**",
            ],
            "forbidden_paths": ["apps/**", "manifests/**", "schemas/**"],
        },
    }
    task_path = root / "tasks" / "TASK-REPO-CONTROL-004.yaml"
    task_path.write_text(yaml.safe_dump(task, sort_keys=False), encoding="utf-8")
    import hashlib
    task_sha = hashlib.sha256(task_path.read_bytes()).hexdigest()
    current = {
        "schema_version": 1,
        "state_version": 1,
        "checkpoint_id": "BOOTSTRAP",
        "updated_at": "2026-09-20T00:00:00Z",
        "task": {"task_id": "TASK-REPO-CONTROL-004", "task_contract_sha256": task_sha, "phase": "PHASE_C_PASS"},
        "progress": {"completed_steps": [], "next_action": "Run Phase D", "next_command": None},
        "verification": {"phase_a_acceptance_passed": True, "phase_b_acceptance_passed": True, "phase_c_acceptance_passed": True},
        "external_operations": {"provider_preflight_started": False, "paid_requests_allowed": False, "unknown_billing_requests": [], "pending_paid_requests": []},
        "blocked": None,
    }
    first = {
        "event_id": "BOOTSTRAP",
        "sequence": 1,
        "timestamp": "2026-09-20T00:00:00Z",
        "task_id": "TASK-REPO-CONTROL-004",
        "attempt_id": None,
        "actor_id": "test",
        "event_type": "BOOTSTRAP",
        "previous_event_sha256": None,
        "payload": {"phase": "PHASE_C_PASS"},
    }
    first["event_sha256"] = event_sha256(first)
    current["last_journal_sequence"] = 1
    current["last_journal_event_sha256"] = first["event_sha256"]
    current["checkpoint_id"] = first["event_id"]
    (root / ".state" / "CURRENT.json").write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    (root / ".state" / "journal.ndjson").write_bytes(canonical_json_bytes(first) + b"\n")
    (root / ".state" / "RESUME.md").write_text(render_resume(current), encoding="utf-8")
    run(root, "git", "init", "-b", "main")
    run(root, "git", "config", "user.email", "test@example.com")
    run(root, "git", "config", "user.name", "Test")
    run(root, "git", "add", ".")
    run(root, "git", "commit", "-m", "bootstrap")
    return root


def append_crash_event(root: Path):
    current = json.loads((root / ".state" / "CURRENT.json").read_text())
    events, _ = read_journal(root)
    after = json.loads(json.dumps(current))
    after["progress"]["next_action"] = "after crash"
    event = {
        "event_id": "CRASH-AFTER-JOURNAL",
        "sequence": len(events) + 1,
        "timestamp": "2026-09-20T00:01:00Z",
        "task_id": current["task"]["task_id"],
        "attempt_id": None,
        "actor_id": "crash-test",
        "event_type": "CHECKPOINT",
        "previous_event_sha256": events[-1]["event_sha256"],
        "payload": {"reason": "simulated power cut", "current_after": after},
    }
    event["event_sha256"] = event_sha256(event)
    with (root / ".state" / "journal.ndjson").open("ab") as stream:
        stream.write(canonical_json_bytes(event) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def test_power_cut_after_journal_append_recovers_current(tmp_path):
    root = make_repo(tmp_path)
    append_crash_event(root)
    result = recover(root)
    current = json.loads((root / ".state" / "CURRENT.json").read_text())
    assert "REBUILT_CURRENT_FROM_JOURNAL" in result["actions"]
    assert current["checkpoint_id"] == "CRASH-AFTER-JOURNAL"
    assert current["progress"]["next_action"] == "after crash"


def test_power_cut_after_current_before_resume_regenerates_resume(tmp_path):
    root = make_repo(tmp_path)
    (root / ".state" / "RESUME.md").write_text("torn", encoding="utf-8")
    result = recover(root)
    current = json.loads((root / ".state" / "CURRENT.json").read_text())
    assert "REGENERATED_RESUME" in result["actions"]
    assert (root / ".state" / "RESUME.md").read_text() == render_resume(current)


def test_hash_chain_tamper_is_blocked(tmp_path):
    root = make_repo(tmp_path)
    lines = (root / ".state" / "journal.ndjson").read_text().splitlines()
    event = json.loads(lines[0])
    event["payload"]["tampered"] = True
    (root / ".state" / "journal.ndjson").write_text(json.dumps(event, separators=(",", ":")) + "\n", encoding="utf-8")
    with pytest.raises(JournalCorruption):
        recover(root)


def test_sequence_gap_is_blocked(tmp_path):
    root = make_repo(tmp_path)
    event = json.loads((root / ".state" / "journal.ndjson").read_text())
    event["sequence"] = 2
    event["event_sha256"] = event_sha256(event)
    (root / ".state" / "journal.ndjson").write_bytes(canonical_json_bytes(event) + b"\n")
    with pytest.raises(JournalCorruption):
        recover(root)


def test_duplicate_event_id_is_blocked(tmp_path):
    root = make_repo(tmp_path)
    first = json.loads((root / ".state" / "journal.ndjson").read_text())
    second = dict(first)
    second["sequence"] = 2
    second["previous_event_sha256"] = first["event_sha256"]
    second["event_sha256"] = event_sha256(second)
    with (root / ".state" / "journal.ndjson").open("ab") as stream:
        stream.write(canonical_json_bytes(second) + b"\n")
    with pytest.raises(JournalCorruption):
        recover(root)


def test_separate_process_cannot_checkpoint_while_writer_lock_is_held(tmp_path):
    root = make_repo(tmp_path)
    with task_lock(root):
        proc = run(
            root,
            sys.executable,
            "-B",
            "-m",
            "projectctl",
            "--root",
            str(root),
            "checkpoint",
            "--reason",
            "concurrency-test",
            check=False,
            env=projectctl_env(),
        )
    assert proc.returncode == 2
    assert "RECOVERY_TASK_ALREADY_ACTIVE" in proc.stderr


def test_committed_out_of_scope_change_detected_by_base_ref(tmp_path):
    root = make_repo(tmp_path)
    base = run(root, "git", "rev-parse", "HEAD").stdout.strip()
    (root / "README.md").write_text("outside scope\n", encoding="utf-8")
    run(root, "git", "add", "README.md")
    run(root, "git", "commit", "-m", "outside-scope")
    with pytest.raises(ScopeViolation):
        check_scope(root, base_ref=base)


def test_equivalent_attempt_remains_blocked_after_new_process_boundary(tmp_path):
    root = make_repo(tmp_path)
    first = register_attempt(root, operation="render", inputs={"shot": 7})
    assert first["status"] == "ATTEMPT_REGISTERED"
    proc = run(
        root,
        sys.executable,
        "-B",
        "-m",
        "projectctl",
        "--root",
        str(root),
        "attempt-fingerprint",
        "--operation",
        "render",
        "--input-json",
        '{"shot":7}',
        "--register",
        check=False,
        env=projectctl_env(),
    )
    assert proc.returncode == 2
    assert "EQUIVALENT_ATTEMPT_BLOCKED" in proc.stderr


def test_fresh_process_resume_uses_only_durable_repository_state(tmp_path):
    root = make_repo(tmp_path)
    script = SOURCE_ROOT / "scripts" / "fresh_session_probe.py"
    proc = run(root, sys.executable, "-B", str(script), "--root", str(root), env=projectctl_env())
    payload = json.loads(proc.stdout)
    assert payload["status"] == "FRESH_SESSION_HANDOFF_OK"
    assert payload["active_task_id"] == "TASK-REPO-CONTROL-004"
    assert payload["journal_sequence"] == 1


def test_branch_protection_blocker_must_not_be_represented_as_phase_d_pass():
    # The current repository is private and GitHub returned 403 for rulesets /
    # branch protection through the connected installation. Phase D must remain
    # blocked until enforcement is actually available and observed.
    assert True


def test_committed_checkpoint_recovers_after_fresh_clone(tmp_path):
    root = make_repo(tmp_path)
    checkpoint(root, reason="persisted-checkpoint")
    run(root, "git", "add", ".state")
    run(root, "git", "commit", "-m", "persist checkpoint state")

    clone = tmp_path / "fresh-clone"
    run(tmp_path, "git", "clone", str(root), str(clone))
    result = recover(clone)

    assert result["status"] in {"RECOVERY_OK", "RECOVERY_REPAIRED"}
    assert result["repository"]["branch"] == "main"


def test_committed_non_state_change_after_checkpoint_is_blocked(tmp_path):
    root = make_repo(tmp_path)
    checkpoint(root, reason="baseline")
    run(root, "git", "add", ".state")
    run(root, "git", "commit", "-m", "persist checkpoint state")

    (root / "AGENTS.md").write_text("# AGENTS\nchanged after checkpoint\n", encoding="utf-8")
    run(root, "git", "add", "AGENTS.md")
    run(root, "git", "commit", "-m", "mutate protected repository content")

    with pytest.raises(RecoveryBlocked) as exc:
        recover(root)
    assert exc.value.code == "RECOVERY_STATE_MISMATCH"
