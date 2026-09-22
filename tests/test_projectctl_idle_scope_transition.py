from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from projectctl.core import OperatingStateError, check_scope, validate_operating_state


def run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=root,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def write_yaml(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")


def project(*, active_task_id, next_gate: str, authorized: bool) -> dict:
    return {
        "schema_version": 1,
        "project_id": "VIDEO-SAAS",
        "current_authorized_phase": "AUDIT_REMEDIATION",
        "active_task_id": active_task_id,
        "provider_preflight_allowed": False,
        "paid_provider_requests_allowed": False,
        "next_gate": next_gate,
        "next_gate_authorized": authorized,
    }


def task(status: str) -> dict:
    return {
        "schema_version": 1,
        "task": {"id": "TASK-X", "status": status},
        "scope": {
            "allowed_paths": [
                "PROJECT_STATE.yaml",
                "README.md",
                "tasks/TASK-X.yaml",
            ],
            "forbidden_paths": ["manifests/**"],
        },
    }


def make_repo(tmp_path: Path, *, active: bool = True, status: str = "IMPLEMENTING") -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    write_yaml(
        root / "PROJECT_STATE.yaml",
        project(
            active_task_id="TASK-X" if active else None,
            next_gate="AUDIT_REMEDIATION" if active else "NONE_AUTHORIZED",
            authorized=active,
        ),
    )
    if active:
        write_yaml(root / "tasks" / "TASK-X.yaml", task(status))
    run(root, "git", "init", "-b", "main")
    run(root, "git", "config", "user.email", "ci@example.test")
    run(root, "git", "config", "user.name", "CI")
    run(root, "git", "add", ".")
    run(root, "git", "commit", "-m", "base")
    return root


def test_active_to_active_scope_passes(tmp_path):
    root = make_repo(tmp_path)
    base = run(root, "git", "rev-parse", "HEAD").stdout.strip()
    (root / "README.md").write_text("allowed active change\n", encoding="utf-8")
    run(root, "git", "add", "README.md")
    run(root, "git", "commit", "-m", "active change")

    result = check_scope(root, base_ref=base)

    assert result["status"] == "SCOPE_OK"
    assert result["contract_source"] == "current"
    assert result["task_id"] == "TASK-X"


def test_active_to_idle_uses_base_contract_and_passes(tmp_path):
    root = make_repo(tmp_path)
    base = run(root, "git", "rev-parse", "HEAD").stdout.strip()

    write_yaml(
        root / "PROJECT_STATE.yaml",
        project(active_task_id=None, next_gate="NONE_AUTHORIZED", authorized=False),
    )
    write_yaml(root / "tasks" / "TASK-X.yaml", task("DONE"))
    (root / "README.md").write_text("closed cleanly\n", encoding="utf-8")
    run(root, "git", "add", ".")
    run(root, "git", "commit", "-m", "close task")

    assert validate_operating_state(root)["status"] == "OPERATING_STATE_IDLE"
    result = check_scope(root, base_ref=base)

    assert result["status"] == "SCOPE_OK"
    assert result["contract_source"] == f"base_ref:{base}"
    assert result["task_id"] == "TASK-X"


def test_idle_without_prior_active_contract_blocks_arbitrary_changes(tmp_path):
    root = make_repo(tmp_path, active=False)
    base = run(root, "git", "rev-parse", "HEAD").stdout.strip()
    (root / "README.md").write_text("arbitrary idle change\n", encoding="utf-8")
    run(root, "git", "add", "README.md")
    run(root, "git", "commit", "-m", "arbitrary idle change")

    with pytest.raises(OperatingStateError) as exc:
        check_scope(root, base_ref=base)

    assert exc.value.code == "NO_PRIOR_ACTIVE_TASK"


def test_terminal_task_left_active_is_blocked(tmp_path):
    root = make_repo(tmp_path, active=True, status="DONE")

    with pytest.raises(OperatingStateError) as exc:
        validate_operating_state(root)

    assert exc.value.code == "ACTIVE_TASK_TERMINAL"
