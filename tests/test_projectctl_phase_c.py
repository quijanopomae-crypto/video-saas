import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from projectctl.core import (
    EquivalentAttemptBlocked,
    RecoveryBlocked,
    ScopeViolation,
    TransitionBlocked,
    attempt_fingerprint,
    canonical_json_bytes,
    check_scope,
    event_sha256,
    register_attempt,
    render_resume,
    run_evidence,
    transition_repository_state,
)


def run(cwd: Path, *args: str):
    subprocess.run(args, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def make_repo(tmp_path: Path, *, frozen: bool = False) -> Path:
    root = tmp_path / "repo"
    (root / ".state" / "locks").mkdir(parents=True)
    (root / "tasks").mkdir()
    (root / "manifests").mkdir()
    (root / "evidence").mkdir()
    (root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    project = {
        "schema_version": 1,
        "project_id": "VIDEO-SAAS",
        "repository_control_plane": {"implementation_status": "PHASE_B_PASS"},
        "current_authorized_phase": "PHASE_C",
        "active_task_id": "TASK-REPO-CONTROL-003",
        "provider_preflight_allowed": False,
        "paid_provider_requests_allowed": False,
        "next_gate": "PHASE_C_EXECUTION",
    }
    (root / "PROJECT_STATE.yaml").write_text(yaml.safe_dump(project, sort_keys=False), encoding="utf-8")
    task = {
        "schema_version": 1,
        "task": {"id": "TASK-REPO-CONTROL-003", "status": "READY"},
        "scope": {
            "allowed_paths": [
                "AGENTS.md",
                "PROJECT_STATE.yaml",
                "tasks/TASK-REPO-CONTROL-003.yaml",
                ".state/**",
                "projectctl/**",
                "tests/test_projectctl_phase_c.py",
                "evidence/**",
            ],
            "forbidden_paths": ["apps/**", "manifests/**", "schemas/**"],
        },
    }
    task_path = root / "tasks" / "TASK-REPO-CONTROL-003.yaml"
    task_path.write_text(yaml.safe_dump(task, sort_keys=False), encoding="utf-8")
    (root / "manifests" / "model-manifest-bench100-v1.1.yaml").write_text(
        yaml.safe_dump({"current_state": "MODEL_MANIFEST_FROZEN" if frozen else "READY_FOR_PROVIDER_PREFLIGHT"}),
        encoding="utf-8",
    )
    current = {
        "schema_version": 1,
        "state_version": 3,
        "checkpoint_id": "BOOTSTRAP",
        "updated_at": "2026-09-20T00:00:00Z",
        "task": {"task_id": "TASK-REPO-CONTROL-003", "task_contract_sha256": "a" * 64, "phase": "PHASE_B_PASS"},
        "progress": {"completed_steps": [], "next_action": "Implement Phase C", "next_command": None},
        "verification": {"phase_a_acceptance_passed": True, "phase_b_acceptance_passed": True},
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
        "task_id": "TASK-REPO-CONTROL-003",
        "attempt_id": None,
        "actor_id": "test",
        "event_type": "BOOTSTRAP",
        "previous_event_sha256": None,
        "payload": {"phase": "PHASE_B_PASS"},
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


def test_check_scope_allows_authorized_and_blocks_forbidden(tmp_path):
    root = make_repo(tmp_path)
    result = check_scope(root, paths=["projectctl/core.py", ".state/CURRENT.json", "evidence/E1.json"])
    assert result["status"] == "SCOPE_OK"
    with pytest.raises(ScopeViolation) as exc:
        check_scope(root, paths=["apps/api/src/main.py"])
    assert exc.value.violations[0]["reason"] == "FORBIDDEN_PATH"
    with pytest.raises(ScopeViolation):
        check_scope(root, paths=["README.md"])


def test_frozen_manifest_change_is_blocked(tmp_path):
    root = make_repo(tmp_path, frozen=True)
    with pytest.raises(TransitionBlocked) as exc:
        check_scope(root, paths=["manifests/asset-manifest-v1.0.json"])
    assert exc.value.code == "FROZEN_MANIFEST_MODIFICATION_BLOCKED"


def test_attempt_fingerprint_is_deterministic_and_causal_change_changes_it():
    a = attempt_fingerprint(task_id="TASK-X", operation="render", inputs={"shot": 1}, causal_change=None)
    b = attempt_fingerprint(task_id="TASK-X", operation="render", inputs={"shot": 1}, causal_change=None)
    c = attempt_fingerprint(task_id="TASK-X", operation="render", inputs={"shot": 1}, causal_change="seed changed")
    assert a == b
    assert a != c


def test_equivalent_attempt_is_blocked_but_causal_change_allows_retry(tmp_path):
    root = make_repo(tmp_path)
    first = register_attempt(root, operation="render", inputs={"shot": 1})
    assert first["status"] == "ATTEMPT_REGISTERED"
    with pytest.raises(EquivalentAttemptBlocked):
        register_attempt(root, operation="render", inputs={"shot": 1})
    second = register_attempt(root, operation="render", inputs={"shot": 1}, causal_change="seed changed")
    assert second["attempt_fingerprint"] != first["attempt_fingerprint"]


def test_unknown_billing_blocks_paid_attempt(tmp_path):
    root = make_repo(tmp_path)
    p = root / ".state" / "CURRENT.json"
    current = json.loads(p.read_text())
    current["external_operations"]["unknown_billing_requests"] = ["req-unknown"]
    p.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    with pytest.raises(RecoveryBlocked) as exc:
        register_attempt(root, operation="provider-call", inputs={"shot": 1}, paid_request=True)
    assert exc.value.code == "PAID_REQUEST_BLOCKED_UNKNOWN_BILLING"


def test_evidence_runner_records_real_execution_and_redacts_secret(tmp_path):
    root = make_repo(tmp_path)
    result = run_evidence(
        root,
        evidence_id="PHASE-C-E1",
        command=[sys.executable, "-c", "print('Authorization: Bearer secret123')"],
    )
    assert result["status"] == "PASS"
    evidence = json.loads((root / "evidence" / "PHASE-C-E1.json").read_text())
    assert evidence["exit_code"] == 0
    assert evidence["status"] == "PASS"
    assert "secret123" not in evidence["stdout"]
    assert "[REDACTED]" in evidence["stdout"]
    assert len(evidence["stdout_sha256"]) == 64


def test_transition_requires_valid_edge_and_passing_evidence(tmp_path):
    root = make_repo(tmp_path)
    with pytest.raises(TransitionBlocked) as exc:
        transition_repository_state(root, to_phase="PHASE_D_PASS", evidence_ids=[])
    assert exc.value.code == "INVALID_REPOSITORY_STATE_TRANSITION"
    with pytest.raises(TransitionBlocked) as exc2:
        transition_repository_state(root, to_phase="PHASE_C_PASS", evidence_ids=[])
    assert exc2.value.code == "TRANSITION_EVIDENCE_REQUIRED"


def test_transition_to_phase_c_pass_with_evidence(tmp_path):
    root = make_repo(tmp_path)
    run_evidence(root, evidence_id="PHASE-C-TESTS", command=[sys.executable, "-c", "print('pass')"])
    result = transition_repository_state(root, to_phase="PHASE_C_PASS", evidence_ids=["PHASE-C-TESTS"])
    assert result["status"] == "STATE_TRANSITION_OK"
    current = json.loads((root / ".state" / "CURRENT.json").read_text())
    project = yaml.safe_load((root / "PROJECT_STATE.yaml").read_text())
    assert current["task"]["phase"] == "PHASE_C_PASS"
    assert current["verification"]["phase_c_acceptance_passed"] is True
    assert project["repository_control_plane"]["implementation_status"] == "PHASE_C_PASS"
    assert project["provider_preflight_allowed"] is False
    assert project["paid_provider_requests_allowed"] is False
