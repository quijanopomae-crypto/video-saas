import json
from pathlib import Path

import pytest
import yaml

from projectctl.core import OperatingStateError, active_task_contract_path, validate_operating_state


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "tasks").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    return root


def write_project(
    root: Path,
    *,
    active_task_id,
    next_gate: str,
    next_gate_authorized: bool,
) -> None:
    project = {
        "schema_version": 1,
        "project_id": "VIDEO-SAAS",
        "current_authorized_phase": "TEST",
        "active_task_id": active_task_id,
        "provider_preflight_allowed": False,
        "paid_provider_requests_allowed": False,
        "next_gate": next_gate,
        "next_gate_authorized": next_gate_authorized,
    }
    (root / "PROJECT_STATE.yaml").write_text(
        yaml.safe_dump(project, sort_keys=False),
        encoding="utf-8",
    )


def write_task(root: Path, task_id: str, status: str) -> None:
    contract = {
        "schema_version": 1,
        "task": {"id": task_id, "status": status},
        "scope": {"allowed_paths": ["PROJECT_STATE.yaml"]},
    }
    (root / "tasks" / f"{task_id}.yaml").write_text(
        yaml.safe_dump(contract, sort_keys=False),
        encoding="utf-8",
    )


def test_active_non_terminal_task_is_valid(tmp_path):
    root = make_root(tmp_path)
    write_task(root, "TASK-X", "IMPLEMENTING")
    write_project(
        root,
        active_task_id="TASK-X",
        next_gate="AUDIT_REMEDIATION",
        next_gate_authorized=True,
    )
    result = validate_operating_state(root)
    assert result["status"] == "OPERATING_STATE_ACTIVE"
    assert result["active_task_id"] == "TASK-X"


def test_terminal_task_cannot_remain_active(tmp_path):
    root = make_root(tmp_path)
    write_task(root, "TASK-X", "DONE")
    write_project(
        root,
        active_task_id="TASK-X",
        next_gate="NONE_AUTHORIZED",
        next_gate_authorized=False,
    )
    with pytest.raises(OperatingStateError) as exc:
        validate_operating_state(root)
    assert exc.value.code == "ACTIVE_TASK_TERMINAL"


def test_idle_none_authorized_is_valid(tmp_path):
    root = make_root(tmp_path)
    write_project(
        root,
        active_task_id=None,
        next_gate="NONE_AUTHORIZED",
        next_gate_authorized=False,
    )
    result = validate_operating_state(root)
    assert result == {
        "status": "OPERATING_STATE_IDLE",
        "active_task_id": None,
        "next_gate": "NONE_AUTHORIZED",
        "next_gate_authorized": False,
    }
    with pytest.raises(OperatingStateError) as exc:
        active_task_contract_path(root)
    assert exc.value.code == "NO_ACTIVE_TASK"


def test_idle_is_invalid_when_a_gate_is_authorized(tmp_path):
    root = make_root(tmp_path)
    write_project(
        root,
        active_task_id=None,
        next_gate="AUDIT_REMEDIATION",
        next_gate_authorized=True,
    )
    with pytest.raises(OperatingStateError) as exc:
        validate_operating_state(root)
    assert exc.value.code == "IDLE_WITH_AUTHORIZED_GATE"


def test_project_state_schema_allows_null_active_task():
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas" / "project-state.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert "null" in schema["properties"]["active_task_id"]["type"]
