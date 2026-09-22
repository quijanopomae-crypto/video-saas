from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import os
import socket
import stat
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

import yaml


class ProjectCtlError(RuntimeError):
    """Base projectctl error."""


class JournalCorruption(ProjectCtlError):
    pass


class RecoveryBlocked(ProjectCtlError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class LockBusy(ProjectCtlError):
    pass


class OperatingStateError(ProjectCtlError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


TERMINAL_TASK_STATUSES = {"DONE", "PASS"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def event_sha256(event: dict[str, Any]) -> str:
    material = dict(event)
    material.pop("event_sha256", None)
    return hashlib.sha256(canonical_json_bytes(material)).hexdigest()


def fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        # Windows does not expose O_DIRECTORY consistently. os.replace remains
        # atomic on the same volume; file fsync still occurs before replace.
        return
    flags = getattr(os, "O_DIRECTORY", 0)
    fd = os.open(directory, os.O_RDONLY | flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        target_mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        target_mode = 0o644
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        if os.name != "nt":
            os.fchmod(fd, target_mode)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        fsync_directory(path.parent)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def append_durable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, content)
        os.fsync(fd)
    finally:
        os.close(fd)
    fsync_directory(path.parent)


def find_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "AGENTS.md").exists() and (candidate / "PROJECT_STATE.yaml").exists():
            return candidate
    raise ProjectCtlError("repository root not found (AGENTS.md + PROJECT_STATE.yaml required)")


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectCtlError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectCtlError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ProjectCtlError(f"expected JSON object in {path}")
    return value


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


@contextmanager
def task_lock(root: Path):
    lock_dir = root / ".state" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "repository-control.lock"
    metadata = {
        "owner_id": f"projectctl-{os.getpid()}",
        "process_id": os.getpid(),
        "host_id": socket.gethostname(),
        "acquired_at": utc_now(),
        "lease_seconds": 120,
    }
    payload = canonical_json_bytes(metadata) + b"\n"
    try:
        fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        try:
            existing = json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise LockBusy("LOCK_INVALID: existing lock cannot be parsed") from exc
        same_host = existing.get("host_id") == socket.gethostname()
        pid = int(existing.get("process_id") or 0)
        if same_host and not _pid_alive(pid):
            current = load_json(root / ".state" / "CURRENT.json")
            ext = current.get("external_operations", {})
            if ext.get("unknown_billing_requests") or ext.get("pending_paid_requests"):
                raise LockBusy("BLOCKED_STALE_LOCK_REVIEW: unresolved external operation")
            lock_path.unlink(missing_ok=True)
            fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        else:
            raise LockBusy("RECOVERY_TASK_ALREADY_ACTIVE")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        fsync_directory(lock_dir)
        yield lock_path
    finally:
        try:
            lock_path.unlink(missing_ok=True)
            fsync_directory(lock_dir)
        except OSError:
            pass


def _git(root: Path, *args: str, check: bool = True) -> bytes:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        raise ProjectCtlError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout


def _repository_content_fingerprint(root: Path) -> str:
    """Hash repository-visible bytes outside .state/ independent of commit identity.

    A durable checkpoint is normally committed after it is created. Therefore an
    exact HEAD equality check is self-referential: committing CURRENT/journal
    necessarily creates a new HEAD. This fingerprint tracks the actual repository
    content that the checkpoint is protecting while excluding the control cursor
    itself.
    """
    raw = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    paths = sorted(
        {
            item.decode("utf-8", "surrogateescape")
            for item in raw.split(b"\0")
            if item
            and item != b".state"
            and not item.startswith(b".state/")
        }
    )
    digest = hashlib.sha256()
    for rel in paths:
        path = root / rel
        try:
            st = path.lstat()
        except FileNotFoundError:
            # A path disappearing while the snapshot is being taken is itself a
            # concurrent mutation. Encode it so verification cannot silently pass.
            kind = b"M"
            payload = b""
            mode = 0
        else:
            mode = st.st_mode & 0o777
            if path.is_symlink():
                kind = b"L"
                payload = os.readlink(path).encode("utf-8", "surrogateescape")
            elif path.is_file():
                kind = b"F"
                payload = path.read_bytes()
            else:
                kind = b"O"
                payload = b""
        rel_bytes = rel.encode("utf-8", "surrogateescape")
        digest.update(len(rel_bytes).to_bytes(8, "big"))
        digest.update(rel_bytes)
        digest.update(kind)
        digest.update(mode.to_bytes(4, "big"))
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    proc = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    return proc.returncode == 0


def git_snapshot(root: Path) -> dict[str, Any]:
    top = Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if top != root.resolve():
        raise RecoveryBlocked("RECOVERY_WRONG_REPOSITORY", f"git root {top} != expected {root.resolve()}")
    branch = _git(root, "branch", "--show-current").decode().strip()
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    # `.state/` is the agent cursor itself; checkpoint/recovery writes there must
    # not make the checkpoint immediately look stale. The content fingerprint is
    # deliberately commit-independent so persisting the checkpoint does not make
    # its own HEAD assertion impossible to satisfy.
    status = _git(
        root,
        "status",
        "--porcelain=v2",
        "-z",
        "--",
        ".",
        ":(exclude).state/**",
    )
    return {
        "branch": branch,
        "head_commit": head,
        "working_tree_dirty": bool(status),
        "working_tree_fingerprint": hashlib.sha256(status).hexdigest(),
        "content_fingerprint": _repository_content_fingerprint(root),
    }


def read_journal(root: Path, *, repair_incomplete_final_line: bool = False) -> tuple[list[dict[str, Any]], bool]:
    path = root / ".state" / "journal.ndjson"
    raw = path.read_bytes() if path.exists() else b""
    incomplete = False
    if raw and not raw.endswith(b"\n"):
        incomplete = True
        last_nl = raw.rfind(b"\n")
        valid_prefix = raw[: last_nl + 1] if last_nl >= 0 else b""
        if repair_incomplete_final_line:
            write_atomic(path, valid_prefix)
            raw = valid_prefix
        else:
            raw = valid_prefix

    events: list[dict[str, Any]] = []
    previous_hash: str | None = None
    seen_ids: set[str] = set()
    for index, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            raise JournalCorruption(f"RECOVERY_CORRUPT_JOURNAL: empty line at {index}")
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise JournalCorruption(f"RECOVERY_CORRUPT_JOURNAL: invalid line {index}: {exc}") from exc
        if not isinstance(event, dict):
            raise JournalCorruption(f"RECOVERY_CORRUPT_JOURNAL: line {index} is not an object")
        if event.get("sequence") != index:
            raise JournalCorruption(
                f"RECOVERY_CORRUPT_JOURNAL: expected sequence {index}, found {event.get('sequence')}"
            )
        eid = event.get("event_id")
        if not isinstance(eid, str) or not eid or eid in seen_ids:
            raise JournalCorruption(f"RECOVERY_CORRUPT_JOURNAL: invalid/duplicate event_id at {index}")
        if event.get("previous_event_sha256") != previous_hash:
            raise JournalCorruption(f"RECOVERY_CORRUPT_JOURNAL: hash-chain break at sequence {index}")
        actual = event_sha256(event)
        if event.get("event_sha256") != actual:
            raise JournalCorruption(f"RECOVERY_CORRUPT_JOURNAL: event hash mismatch at sequence {index}")
        seen_ids.add(eid)
        previous_hash = actual
        events.append(event)
    return events, incomplete


def render_resume(current: dict[str, Any]) -> str:
    task = current.get("task", {})
    task_id = task.get("task_id") or "IDLE"
    task_contract_sha256 = task.get("task_contract_sha256") or "none"
    progress = current.get("progress", {})
    verification = current.get("verification", {})
    external = current.get("external_operations", {})
    repository = current.get("repository", {})
    completed = progress.get("completed_steps") or []
    lines = [
        f"# RESUME — {task_id}",
        "",
        "Generated view of `.state/CURRENT.json`. It is not an independent source of truth.",
        "",
        f"- **Phase:** {task.get('phase')}",
        f"- **Checkpoint:** {current.get('checkpoint_id')}",
        f"- **State version:** {current.get('state_version')}",
        f"- **Branch:** {repository.get('branch', 'UNRECORDED')}",
        f"- **Checkpoint base HEAD:** {repository.get('head_commit', 'UNRECORDED')}",
        f"- **Checkpoint working tree dirty:** {repository.get('working_tree_dirty', 'UNRECORDED')}",
        f"- **Provider Preflight started:** {str(external.get('provider_preflight_started', False)).lower()}",
        f"- **Paid requests allowed:** {str(external.get('paid_requests_allowed', False)).lower()}",
        f"- **Phase A acceptance:** {str(verification.get('phase_a_acceptance_passed', False)).lower()}",
        f"- **Baseline regression suite:** {str(verification.get('baseline_regression_suite_passed', False)).lower()}",
        f"- **Phase B acceptance:** {str(verification.get('phase_b_acceptance_passed', False)).lower()}",
        f"- **Phase C acceptance:** {str(verification.get('phase_c_acceptance_passed', False)).lower()}",
        f"- **Latest evidence:** {verification.get('latest_evidence_id') or 'none'}",
        f"- **Blocked:** {current.get('blocked') or 'none'}",
        f"- **Next action:** {progress.get('next_action')}",
        "",
        "## Completed steps",
        "",
    ]
    lines.extend(f"- {item}" for item in completed)
    lines += [
        "",
        "The active Task Contract SHA-256 is:",
        "",
        f"`{task_contract_sha256}`",
        "",
    ]
    return "\n".join(lines)


def _materialize_after_event(
    current: dict[str, Any],
    event: dict[str, Any],
    *,
    repository: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot = deepcopy(event.get("payload", {}).get("current_after") or current)
    snapshot["checkpoint_id"] = event["event_id"]
    snapshot["updated_at"] = event["timestamp"]
    snapshot["last_journal_sequence"] = event["sequence"]
    snapshot["last_journal_event_sha256"] = event["event_sha256"]
    if repository is not None:
        snapshot["repository"] = repository
    return snapshot


def _verify_snapshot_vs_git(root: Path, current: dict[str, Any], observed: dict[str, Any]) -> None:
    expected = current.get("repository")
    if not expected:
        return
    expected_branch = expected.get("branch")
    if expected_branch and expected_branch != observed.get("branch"):
        raise RecoveryBlocked(
            "RECOVERY_WRONG_BRANCH",
            f"expected {expected_branch!r}; observed {observed.get('branch')!r}",
        )

    expected_content = expected.get("content_fingerprint")
    if expected_content is not None:
        if expected_content != observed.get("content_fingerprint"):
            raise RecoveryBlocked(
                "RECOVERY_STATE_MISMATCH",
                "repository content outside .state differs from checkpoint",
            )
        expected_head = expected.get("head_commit")
        observed_head = observed.get("head_commit")
        if expected_head and observed_head and expected_head != observed_head:
            if not _git_is_ancestor(root, expected_head, observed_head):
                raise RecoveryBlocked(
                    "RECOVERY_STATE_MISMATCH",
                    f"checkpoint HEAD {expected_head} is not an ancestor of observed HEAD {observed_head}",
                )
        return

    # Backward compatibility for checkpoints written before content_fingerprint
    # existed. These retain the stricter legacy semantics.
    if expected.get("head_commit") != observed.get("head_commit"):
        raise RecoveryBlocked(
            "RECOVERY_STATE_MISMATCH",
            f"HEAD expected {expected.get('head_commit')}; observed {observed.get('head_commit')}",
        )
    if expected.get("working_tree_fingerprint") != observed.get("working_tree_fingerprint"):
        raise RecoveryBlocked(
            "RECOVERY_STATE_MISMATCH",
            "working tree fingerprint differs from checkpoint",
        )


def _new_event_id() -> str:
    return f"CP-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"


def checkpoint(root: Path, *, reason: str = "manual", next_action: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    with task_lock(root):
        current_path = root / ".state" / "CURRENT.json"
        journal_path = root / ".state" / "journal.ndjson"
        resume_path = root / ".state" / "RESUME.md"
        current = load_json(current_path)
        events, incomplete = read_journal(root, repair_incomplete_final_line=False)
        if incomplete:
            raise RecoveryBlocked("RECOVERY_INCOMPLETE_FINAL_LINE", "run projectctl recover before checkpoint")
        repository = git_snapshot(root)
        if (current.get("task") or {}).get("task_id") is None:
            repository["branch"] = None
        state_after = deepcopy(current)
        state_after["state_version"] = int(current.get("state_version", 0)) + 1
        state_after.setdefault("progress", {})
        if next_action is not None:
            state_after["progress"]["next_action"] = next_action
        state_after["repository"] = repository
        sequence = len(events) + 1
        previous_hash = events[-1]["event_sha256"] if events else None
        event = {
            "event_id": _new_event_id(),
            "sequence": sequence,
            "timestamp": utc_now(),
            "task_id": state_after.get("task", {}).get("task_id"),
            "attempt_id": None,
            "actor_id": f"projectctl@{socket.gethostname()}",
            "event_type": "CHECKPOINT",
            "previous_event_sha256": previous_hash,
            "payload": {
                "reason": reason,
                "current_after": state_after,
            },
        }
        event["event_sha256"] = event_sha256(event)
        append_durable(journal_path, canonical_json_bytes(event) + b"\n")
        materialized = _materialize_after_event(state_after, event, repository=repository)
        write_atomic(current_path, json.dumps(materialized, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
        resume_text = render_resume(materialized)
        write_atomic(resume_path, resume_text.encode("utf-8"))

        verified_events, incomplete2 = read_journal(root, repair_incomplete_final_line=False)
        verified_current = load_json(current_path)
        if incomplete2 or verified_events[-1]["event_id"] != materialized["checkpoint_id"]:
            raise ProjectCtlError("checkpoint verification failed: journal")
        if verified_current.get("checkpoint_id") != materialized["checkpoint_id"]:
            raise ProjectCtlError("checkpoint verification failed: CURRENT")
        if resume_path.read_text(encoding="utf-8") != render_resume(verified_current):
            raise ProjectCtlError("checkpoint verification failed: RESUME")
        return {
            "status": "CHECKPOINT_OK",
            "checkpoint_id": materialized["checkpoint_id"],
            "sequence": materialized["last_journal_sequence"],
            "repository": repository,
        }


def recover(root: Path) -> dict[str, Any]:
    root = root.resolve()
    with task_lock(root):
        current_path = root / ".state" / "CURRENT.json"
        resume_path = root / ".state" / "RESUME.md"
        current = load_json(current_path)
        events, incomplete = read_journal(root, repair_incomplete_final_line=True)
        actions: list[str] = []
        if incomplete:
            actions.append("TRUNCATED_INCOMPLETE_FINAL_JOURNAL_LINE")
        if not events:
            raise RecoveryBlocked("RECOVERY_CORRUPT_JOURNAL", "journal contains no complete events")
        latest = events[-1]
        current_seq = int(current.get("last_journal_sequence", 0))
        latest_seq = int(latest["sequence"])

        if current_seq > latest_seq:
            raise RecoveryBlocked(
                "RECOVERY_STATE_MISMATCH",
                f"CURRENT sequence {current_seq} is ahead of journal {latest_seq}",
            )
        if current_seq < latest_seq:
            current = _materialize_after_event(current, latest)
            write_atomic(current_path, json.dumps(current, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
            actions.append("REBUILT_CURRENT_FROM_JOURNAL")
        elif current.get("checkpoint_id") != latest.get("event_id"):
            # Phase A snapshots predate projectctl and may not have last_journal_sequence.
            # If sequence was explicitly present, disagreement is corruption.
            if "last_journal_sequence" in current:
                raise RecoveryBlocked("RECOVERY_STATE_MISMATCH", "CURRENT checkpoint does not match journal tail")

        observed = git_snapshot(root)
        if current.get("repository"):
            _verify_snapshot_vs_git(root, current, observed)
        else:
            current["repository"] = observed
            current["state_version"] = int(current.get("state_version", 0)) + 1
            write_atomic(current_path, json.dumps(current, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
            actions.append("RECORDED_INITIAL_GIT_SNAPSHOT")

        expected_resume = render_resume(current)
        actual_resume = resume_path.read_text(encoding="utf-8") if resume_path.exists() else ""
        if actual_resume != expected_resume:
            write_atomic(resume_path, expected_resume.encode("utf-8"))
            actions.append("REGENERATED_RESUME")

        ext = current.get("external_operations", {})
        if ext.get("unknown_billing_requests"):
            raise RecoveryBlocked("RECOVERY_UNRESOLVED_BILLING", "unknown billing request exists")

        return {
            "status": "RECOVERY_OK" if not actions else "RECOVERY_REPAIRED",
            "actions": actions,
            "checkpoint_id": current.get("checkpoint_id"),
            "journal_sequence": latest_seq,
            "repository": observed,
        }


def resume(root: Path) -> tuple[dict[str, Any], str]:
    result = recover(root)
    text = (root / ".state" / "RESUME.md").read_text(encoding="utf-8")
    return result, text


class ScopeViolation(ProjectCtlError):
    def __init__(self, violations: list[dict[str, str]]):
        self.violations = violations
        super().__init__(f"SCOPE_VIOLATION: {json.dumps(violations, ensure_ascii=False)}")


class EquivalentAttemptBlocked(ProjectCtlError):
    def __init__(self, fingerprint: str):
        self.fingerprint = fingerprint
        super().__init__(f"EQUIVALENT_ATTEMPT_BLOCKED: {fingerprint}")


class TransitionBlocked(ProjectCtlError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


REPOSITORY_PHASE_TRANSITIONS = {
    "PHASE_A_PASS": {"PHASE_B_PASS"},
    "PHASE_B_PASS": {"PHASE_C_PASS"},
    "PHASE_C_PASS": {"PHASE_D_PASS"},
}


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ProjectCtlError(f"missing required file: {path}") from exc
    if not isinstance(value, dict):
        raise ProjectCtlError(f"expected YAML object in {path}")
    return value


def validate_operating_state(root: Path) -> dict[str, Any]:
    """Validate ACTIVE vs IDLE semantics for the repository operating cursor."""
    root = root.resolve()
    project = load_yaml(root / "PROJECT_STATE.yaml")
    active_task_id = project.get("active_task_id")
    next_gate = project.get("next_gate")
    next_gate_authorized = project.get("next_gate_authorized")

    if not isinstance(next_gate_authorized, bool):
        raise OperatingStateError("NEXT_GATE_AUTHORIZATION_INVALID", "next_gate_authorized must be boolean")
    if not isinstance(next_gate, str) or not next_gate:
        raise OperatingStateError("NEXT_GATE_INVALID", "next_gate must be a non-empty string")

    if active_task_id is None:
        if next_gate != "NONE_AUTHORIZED" or next_gate_authorized:
            raise OperatingStateError(
                "IDLE_WITH_AUTHORIZED_GATE",
                "active_task_id=null is valid only with next_gate=NONE_AUTHORIZED and next_gate_authorized=false",
            )
        return {
            "status": "OPERATING_STATE_IDLE",
            "active_task_id": None,
            "next_gate": next_gate,
            "next_gate_authorized": False,
        }

    if not isinstance(active_task_id, str) or not active_task_id:
        raise OperatingStateError("ACTIVE_TASK_ID_INVALID", "active_task_id must be a non-empty string or null")

    path = root / "tasks" / f"{active_task_id}.yaml"
    if not path.exists():
        raise OperatingStateError("ACTIVE_TASK_CONTRACT_MISSING", str(path.relative_to(root)))
    contract = load_yaml(path)
    task = contract.get("task") or {}
    if task.get("id") != active_task_id:
        raise OperatingStateError("ACTIVE_TASK_ID_MISMATCH", f"{active_task_id} != {task.get('id')}")
    status = str(task.get("status") or "").upper()
    if status in TERMINAL_TASK_STATUSES:
        raise OperatingStateError(
            "ACTIVE_TASK_TERMINAL",
            f"{active_task_id} has terminal status {status}; set active_task_id=null when no later gate is authorized",
        )
    if not next_gate_authorized or next_gate == "NONE_AUTHORIZED":
        raise OperatingStateError(
            "ACTIVE_TASK_WITHOUT_AUTHORIZED_GATE",
            "a non-terminal active task requires a named authorized gate",
        )
    return {
        "status": "OPERATING_STATE_ACTIVE",
        "active_task_id": active_task_id,
        "task_status": status,
        "task_contract": str(path.relative_to(root)),
        "next_gate": next_gate,
        "next_gate_authorized": True,
    }


def active_task_contract_path(root: Path) -> Path:
    project = load_yaml(root / "PROJECT_STATE.yaml")
    task_id = project.get("active_task_id")
    if task_id is None:
        raise OperatingStateError("NO_ACTIVE_TASK", "repository is IDLE; no Task Contract is active")
    if not isinstance(task_id, str) or not task_id:
        raise OperatingStateError("ACTIVE_TASK_ID_INVALID", "active_task_id must be a non-empty string or null")
    path = root / "tasks" / f"{task_id}.yaml"
    if not path.exists():
        raise ProjectCtlError(f"active Task Contract not found: {path}")
    return path


def _norm_repo_path(value: str | Path) -> str:
    text = str(value).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return str(PurePosixPath(text))


def _scope_match(path: str, pattern: str) -> bool:
    path = _norm_repo_path(path)
    pattern = _norm_repo_path(pattern)
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    return fnmatch.fnmatchcase(path, pattern)


def git_changed_paths(root: Path, base_ref: str | None = None) -> list[str]:
    changed: set[str] = set()
    if base_ref:
        committed = _git(root, "diff", "--name-only", "-z", f"{base_ref}...HEAD")
        changed.update(x.decode("utf-8", "surrogateescape") for x in committed.split(b"\0") if x)
    tracked = _git(root, "diff", "--name-only", "-z", "HEAD")
    changed.update(x.decode("utf-8", "surrogateescape") for x in tracked.split(b"\0") if x)
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    changed.update(x.decode("utf-8", "surrogateescape") for x in untracked.split(b"\0") if x)
    return sorted(_norm_repo_path(x) for x in changed)


def assert_frozen_manifests_immutable(root: Path, changed_paths: Iterable[str]) -> None:
    manifest_path = root / "manifests" / "model-manifest-bench100-v1.1.yaml"
    if not manifest_path.exists():
        return
    manifest = load_yaml(manifest_path)
    if manifest.get("current_state") != "MODEL_MANIFEST_FROZEN":
        return
    touched = sorted(p for p in {_norm_repo_path(x) for x in changed_paths} if _scope_match(p, "manifests/**"))
    if touched:
        raise TransitionBlocked("FROZEN_MANIFEST_MODIFICATION_BLOCKED", ", ".join(touched))


def _load_yaml_from_git_ref(root: Path, ref: str, rel_path: str) -> dict[str, Any]:
    proc = subprocess.run(
        ["git", "show", f"{ref}:{rel_path}"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise OperatingStateError(
            "BASE_STATE_UNAVAILABLE",
            f"cannot read {rel_path} from {ref}: {proc.stderr.decode('utf-8', 'replace').strip()}",
        )
    try:
        value = yaml.safe_load(proc.stdout.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise OperatingStateError("BASE_STATE_INVALID", f"{ref}:{rel_path}") from exc
    if not isinstance(value, dict):
        raise OperatingStateError("BASE_STATE_INVALID", f"{ref}:{rel_path} is not a YAML object")
    return value


def _scope_contract(
    root: Path,
    *,
    task_contract_path: Path | None,
    base_ref: str | None,
) -> tuple[Path, dict[str, Any], str]:
    if task_contract_path is not None:
        path = task_contract_path if task_contract_path.is_absolute() else root / task_contract_path
        return path, load_yaml(path), "explicit"

    project = load_yaml(root / "PROJECT_STATE.yaml")
    active_task_id = project.get("active_task_id")
    if isinstance(active_task_id, str) and active_task_id:
        path = root / "tasks" / f"{active_task_id}.yaml"
        return path, load_yaml(path), "current"

    # Closing a task legitimately produces an IDLE destination tree. In that
    # tree there is intentionally no active Task Contract, so scope authority
    # must come from the active contract in the comparison base. This keeps the
    # closing PR/merge verifiable without weakening the scope gate.
    operating = validate_operating_state(root)
    if operating.get("status") != "OPERATING_STATE_IDLE":
        raise OperatingStateError("NO_ACTIVE_TASK", "no current active Task Contract")

    if not base_ref:
        raise OperatingStateError(
            "NO_ACTIVE_TASK",
            "repository is IDLE and no base_ref was supplied to recover prior scope authority",
        )

    base_project = _load_yaml_from_git_ref(root, base_ref, "PROJECT_STATE.yaml")
    base_task_id = base_project.get("active_task_id")
    if not isinstance(base_task_id, str) or not base_task_id:
        raise OperatingStateError(
            "NO_PRIOR_ACTIVE_TASK",
            f"{base_ref} does not contain an active Task Contract authorizing this transition",
        )
    if base_project.get("next_gate_authorized") is not True or base_project.get("next_gate") == "NONE_AUTHORIZED":
        raise OperatingStateError(
            "PRIOR_TASK_NOT_AUTHORIZED",
            f"{base_ref} does not show an authorized active gate",
        )

    rel = f"tasks/{base_task_id}.yaml"
    contract = _load_yaml_from_git_ref(root, base_ref, rel)
    task = contract.get("task") or {}
    if task.get("id") != base_task_id:
        raise OperatingStateError(
            "PRIOR_TASK_ID_MISMATCH",
            f"{base_task_id} != {task.get('id')}",
        )
    status = str(task.get("status") or "").upper()
    if status in TERMINAL_TASK_STATUSES:
        raise OperatingStateError(
            "PRIOR_ACTIVE_TASK_TERMINAL",
            f"{base_task_id} was already terminal ({status}) in {base_ref}",
        )
    return root / rel, contract, f"base_ref:{base_ref}"


def check_scope(
    root: Path,
    *,
    task_contract_path: Path | None = None,
    paths: Iterable[str] | None = None,
    base_ref: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    contract_path, contract, contract_source = _scope_contract(
        root,
        task_contract_path=task_contract_path,
        base_ref=base_ref,
    )
    scope = contract.get("scope") or {}
    allowed = list(scope.get("allowed_paths") or [])
    forbidden = list(scope.get("forbidden_paths") or [])
    if not allowed:
        raise ProjectCtlError(f"Task Contract has no allowed_paths: {contract_path}")
    changed = sorted({_norm_repo_path(x) for x in (paths if paths is not None else git_changed_paths(root, base_ref))})
    violations: list[dict[str, str]] = []
    for path in changed:
        if any(_scope_match(path, pattern) for pattern in forbidden):
            violations.append({"path": path, "reason": "FORBIDDEN_PATH"})
        elif not any(_scope_match(path, pattern) for pattern in allowed):
            violations.append({"path": path, "reason": "OUTSIDE_ALLOWED_PATHS"})
    assert_frozen_manifests_immutable(root, changed)
    if violations:
        raise ScopeViolation(violations)
    return {
        "status": "SCOPE_OK",
        "task_id": (contract.get("task") or {}).get("id"),
        "task_contract": str(contract_path.relative_to(root)),
        "contract_source": contract_source,
        "paths_checked": changed,
    }


def attempt_fingerprint(
    *,
    task_id: str,
    operation: str,
    inputs: Any,
    causal_change: str | None = None,
) -> str:
    if not task_id or not operation:
        raise ProjectCtlError("task_id and operation are required for attempt fingerprint")
    material = {
        "schema_version": 1,
        "task_id": task_id,
        "operation": operation,
        "inputs": inputs,
        "causal_change": causal_change or "NONE",
    }
    return hashlib.sha256(canonical_json_bytes(material)).hexdigest()


def _journal_attempt_fingerprints(events: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for event in events:
        if event.get("event_type") != "ATTEMPT_REGISTERED":
            continue
        fp = (event.get("payload") or {}).get("attempt_fingerprint")
        if isinstance(fp, str):
            out.add(fp)
    return out


def _ensure_state_journal_aligned(current: dict[str, Any], events: list[dict[str, Any]]) -> None:
    if not events:
        raise RecoveryBlocked("RECOVERY_CORRUPT_JOURNAL", "journal contains no complete events")
    current_seq = int(current.get("last_journal_sequence", len(events)))
    if current_seq != len(events):
        raise RecoveryBlocked(
            "RECOVERY_STATE_MISMATCH",
            f"CURRENT sequence {current_seq} does not match journal {len(events)}; run recover",
        )
    if "last_journal_sequence" in current and current.get("checkpoint_id") != events[-1].get("event_id"):
        raise RecoveryBlocked("RECOVERY_STATE_MISMATCH", "CURRENT checkpoint does not match journal tail")


def _append_control_event_locked(
    root: Path,
    current: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    event_type: str,
    payload: dict[str, Any],
    state_after: dict[str, Any] | None = None,
    attempt_id: str | None = None,
) -> dict[str, Any]:
    journal_path = root / ".state" / "journal.ndjson"
    current_path = root / ".state" / "CURRENT.json"
    resume_path = root / ".state" / "RESUME.md"
    new_state = deepcopy(state_after or current)
    new_state["state_version"] = int(current.get("state_version", 0)) + 1
    sequence = len(events) + 1
    event = {
        "event_id": _new_event_id(),
        "sequence": sequence,
        "timestamp": utc_now(),
        "task_id": new_state.get("task", {}).get("task_id"),
        "attempt_id": attempt_id,
        "actor_id": f"projectctl@{socket.gethostname()}",
        "event_type": event_type,
        "previous_event_sha256": events[-1]["event_sha256"] if events else None,
        "payload": {**payload, "current_after": new_state},
    }
    event["event_sha256"] = event_sha256(event)
    append_durable(journal_path, canonical_json_bytes(event) + b"\n")
    materialized = _materialize_after_event(new_state, event, repository=new_state.get("repository"))
    write_atomic(current_path, json.dumps(materialized, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    write_atomic(resume_path, render_resume(materialized).encode("utf-8"))
    return materialized


def register_attempt(
    root: Path,
    *,
    operation: str,
    inputs: Any,
    causal_change: str | None = None,
    paid_request: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    with task_lock(root):
        current = load_json(root / ".state" / "CURRENT.json")
        events, incomplete = read_journal(root)
        if incomplete:
            raise RecoveryBlocked("RECOVERY_INCOMPLETE_FINAL_LINE", "run projectctl recover before registering attempt")
        _ensure_state_journal_aligned(current, events)
        ext = current.get("external_operations", {})
        if paid_request and ext.get("unknown_billing_requests"):
            raise RecoveryBlocked("PAID_REQUEST_BLOCKED_UNKNOWN_BILLING", "unknown billing request exists")
        task_id = current.get("task", {}).get("task_id")
        fp = attempt_fingerprint(task_id=task_id, operation=operation, inputs=inputs, causal_change=causal_change)
        if fp in _journal_attempt_fingerprints(events):
            raise EquivalentAttemptBlocked(fp)
        attempt_id = f"ATTEMPT-{fp[:16]}"
        new_state = deepcopy(current)
        new_state["last_attempt"] = {
            "attempt_id": attempt_id,
            "attempt_fingerprint": fp,
            "operation": operation,
            "causal_change": causal_change or "NONE",
            "paid_request": bool(paid_request),
        }
        materialized = _append_control_event_locked(
            root,
            current,
            events,
            event_type="ATTEMPT_REGISTERED",
            attempt_id=attempt_id,
            payload={
                "attempt_fingerprint": fp,
                "operation": operation,
                "causal_change": causal_change or "NONE",
                "paid_request": bool(paid_request),
            },
            state_after=new_state,
        )
        return {"status": "ATTEMPT_REGISTERED", "attempt_id": attempt_id, "attempt_fingerprint": fp, "checkpoint_id": materialized["checkpoint_id"]}


_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
]


def redact_secrets(text: str) -> str:
    value = text
    for pattern in _SECRET_PATTERNS:
        if pattern.groups:
            value = pattern.sub(lambda m: m.group(1) + "[REDACTED]", value)
        else:
            value = pattern.sub("[REDACTED]", value)
    return value


def _bounded_text(data: bytes, limit: int = 65536) -> tuple[str, bool]:
    decoded = data.decode("utf-8", "replace")
    redacted = redact_secrets(decoded)
    if len(redacted) <= limit:
        return redacted, False
    return redacted[:limit] + "\n...[TRUNCATED]...", True


def run_evidence(
    root: Path,
    *,
    evidence_id: str,
    command: list[str],
    expected_exit: int = 0,
    paid_request: bool = False,
) -> dict[str, Any]:
    root = root.resolve()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", evidence_id):
        raise ProjectCtlError("invalid evidence_id; use only letters, digits, dot, underscore or hyphen")
    if not command:
        raise ProjectCtlError("evidence command is required")
    current = load_json(root / ".state" / "CURRENT.json")
    ext = current.get("external_operations", {})
    if paid_request and ext.get("unknown_billing_requests"):
        raise RecoveryBlocked("PAID_REQUEST_BLOCKED_UNKNOWN_BILLING", "unknown billing request exists")
    evidence_path = root / "evidence" / f"{evidence_id}.json"
    if evidence_path.exists():
        raise ProjectCtlError(f"evidence is immutable and already exists: {evidence_path}")
    started = utc_now()
    started_ns = time.monotonic_ns()
    before = git_snapshot(root)
    proc = subprocess.run(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    duration_ms = (time.monotonic_ns() - started_ns) // 1_000_000
    finished = utc_now()
    stdout_text, stdout_truncated = _bounded_text(proc.stdout)
    stderr_text, stderr_truncated = _bounded_text(proc.stderr)
    evidence = {
        "schema_version": 1,
        "evidence_id": evidence_id,
        "task_id": current.get("task", {}).get("task_id"),
        "status": "PASS" if proc.returncode == expected_exit else "FAIL",
        "command": [redact_secrets(str(x)) for x in command],
        "expected_exit": expected_exit,
        "exit_code": proc.returncode,
        "started_at": started,
        "finished_at": finished,
        "duration_ms": duration_ms,
        "paid_request": bool(paid_request),
        "repository_before": before,
        "stdout_sha256": hashlib.sha256(proc.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(proc.stderr).hexdigest(),
        "stdout": stdout_text,
        "stderr": stderr_text,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }
    write_atomic(evidence_path, json.dumps(evidence, ensure_ascii=False, indent=2).encode("utf-8") + b"\n")
    evidence_sha = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    with task_lock(root):
        current2 = load_json(root / ".state" / "CURRENT.json")
        events, incomplete = read_journal(root)
        if incomplete:
            raise RecoveryBlocked("RECOVERY_INCOMPLETE_FINAL_LINE", "run projectctl recover before recording evidence")
        _ensure_state_journal_aligned(current2, events)
        new_state = deepcopy(current2)
        new_state.setdefault("verification", {})["latest_evidence_id"] = evidence_id
        _append_control_event_locked(
            root,
            current2,
            events,
            event_type="EVIDENCE_RECORDED",
            payload={"evidence_id": evidence_id, "status": evidence["status"], "file_sha256": evidence_sha},
            state_after=new_state,
        )
    return {"status": evidence["status"], "evidence_id": evidence_id, "path": str(evidence_path.relative_to(root)), "exit_code": proc.returncode, "sha256": evidence_sha}


def _load_evidence(root: Path, evidence_id: str) -> dict[str, Any]:
    path = root / "evidence" / f"{evidence_id}.json"
    if not path.exists():
        raise TransitionBlocked("TRANSITION_EVIDENCE_MISSING", evidence_id)
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TransitionBlocked("TRANSITION_EVIDENCE_INVALID", f"{evidence_id}: {exc}") from exc
    if evidence.get("status") != "PASS":
        raise TransitionBlocked("TRANSITION_EVIDENCE_NOT_PASS", evidence_id)
    return evidence


def close_active_task(root: Path, *, final_phase: str, evidence_ids: list[str]) -> dict[str, Any]:
    """Close the current authorized task and materialize a durable IDLE cursor."""
    root = root.resolve()
    with task_lock(root):
        operating = validate_operating_state(root)
        if operating.get("status") != "OPERATING_STATE_ACTIVE":
            raise OperatingStateError("NO_ACTIVE_TASK", "only an ACTIVE task can be closed")

        current = load_json(root / ".state" / "CURRENT.json")
        events, incomplete = read_journal(root)
        if incomplete:
            raise RecoveryBlocked("RECOVERY_INCOMPLETE_FINAL_LINE", "run projectctl recover before task close")
        _ensure_state_journal_aligned(current, events)

        project_path = root / "PROJECT_STATE.yaml"
        project = load_yaml(project_path)
        task_id = project.get("active_task_id")
        if not isinstance(task_id, str) or not task_id:
            raise OperatingStateError("NO_ACTIVE_TASK", "PROJECT_STATE has no active task")
        contract_path = root / "tasks" / f"{task_id}.yaml"
        contract = load_yaml(contract_path)
        task = contract.get("task") or {}
        if task.get("id") != task_id:
            raise OperatingStateError("ACTIVE_TASK_ID_MISMATCH", f"{task_id} != {task.get('id')}")
        if str(task.get("status") or "").upper() in TERMINAL_TASK_STATUSES:
            raise OperatingStateError("ACTIVE_TASK_TERMINAL", f"{task_id} is already terminal")

        ext = current.get("external_operations", {})
        if ext.get("unknown_billing_requests") or ext.get("pending_paid_requests"):
            raise TransitionBlocked("TASK_CLOSE_BLOCKED_EXTERNAL_OPERATION", task_id)
        if ext.get("provider_preflight_started"):
            raise TransitionBlocked("TASK_CLOSE_BLOCKED_PROVIDER_PREFLIGHT", task_id)
        if not evidence_ids:
            raise TransitionBlocked("TASK_CLOSE_EVIDENCE_REQUIRED", task_id)
        for evidence_id in evidence_ids:
            _load_evidence(root, evidence_id)

        # Scope is checked while the task is still ACTIVE. The resulting closing
        # commit is subsequently verifiable from IDLE by check_scope(base_ref=...).
        check_scope(root)

        expected_outcome = ((contract.get("objective") or {}).get("expected_outcome"))
        if expected_outcome and final_phase != expected_outcome:
            raise TransitionBlocked(
                "TASK_CLOSE_OUTCOME_MISMATCH",
                f"expected {expected_outcome}; requested {final_phase}",
            )

        contract.setdefault("task", {})["status"] = "DONE"
        contract["closure"] = {
            "final_phase": final_phase,
            "evidence_ids": evidence_ids,
            "provider_preflight_started": False,
            "paid_provider_requests_executed": False,
        }
        write_atomic(
            contract_path,
            yaml.safe_dump(contract, sort_keys=False, allow_unicode=True).encode("utf-8"),
        )

        project["current_authorized_phase"] = final_phase
        project["active_task_id"] = None
        project["next_gate"] = "NONE_AUTHORIZED"
        project["next_gate_authorized"] = False
        project["provider_preflight_allowed"] = False
        project["paid_provider_requests_allowed"] = False
        for value in project.values():
            if isinstance(value, dict) and value.get("task_id") == task_id:
                if "status" in value:
                    value["status"] = "PASS"
                value["completion_phase"] = final_phase
        write_atomic(
            project_path,
            yaml.safe_dump(project, sort_keys=False, allow_unicode=True).encode("utf-8"),
        )

        new_state = deepcopy(current)
        new_state["task"] = {
            "task_id": None,
            "task_contract_sha256": None,
            "phase": final_phase,
        }
        new_state["blocked"] = None
        new_state.setdefault("progress", {})["next_action"] = None
        new_state["progress"]["next_command"] = None
        completed = new_state["progress"].setdefault("completed_steps", [])
        completed.append(f"{task_id} closed DONE with {final_phase}")
        new_state.setdefault("verification", {})["latest_evidence_id"] = evidence_ids[-1]
        new_state["verification"]["audit_remediation_passed"] = final_phase == "AUDIT_REMEDIATION_PASS"
        new_state.setdefault("external_operations", {})["provider_preflight_started"] = False
        new_state["external_operations"]["paid_requests_allowed"] = False
        new_state["external_operations"]["pending_paid_requests"] = []
        new_state["external_operations"]["unknown_billing_requests"] = []
        terminal_snapshot = git_snapshot(root)
        # A terminal IDLE cursor is content-bound but branch-agnostic so the same
        # tree remains recoverable after the closing PR becomes a merge commit on main.
        terminal_snapshot["branch"] = None
        new_state["repository"] = terminal_snapshot

        materialized = _append_control_event_locked(
            root,
            current,
            events,
            event_type="TASK_CLOSED",
            payload={
                "closed_task_id": task_id,
                "final_phase": final_phase,
                "evidence_ids": evidence_ids,
            },
            state_after=new_state,
        )
        return {
            "status": "TASK_CLOSE_OK",
            "task_id": task_id,
            "final_phase": final_phase,
            "checkpoint_id": materialized["checkpoint_id"],
            "evidence_ids": evidence_ids,
        }


def transition_repository_state(root: Path, *, to_phase: str, evidence_ids: list[str]) -> dict[str, Any]:
    root = root.resolve()
    with task_lock(root):
        current = load_json(root / ".state" / "CURRENT.json")
        events, incomplete = read_journal(root)
        if incomplete:
            raise RecoveryBlocked("RECOVERY_INCOMPLETE_FINAL_LINE", "run projectctl recover before transition")
        _ensure_state_journal_aligned(current, events)
        from_phase = current.get("task", {}).get("phase")
        if to_phase not in REPOSITORY_PHASE_TRANSITIONS.get(from_phase, set()):
            raise TransitionBlocked("INVALID_REPOSITORY_STATE_TRANSITION", f"{from_phase} -> {to_phase}")
        ext = current.get("external_operations", {})
        if ext.get("unknown_billing_requests"):
            raise TransitionBlocked("TRANSITION_BLOCKED_UNKNOWN_BILLING", "unknown billing request exists")
        if not evidence_ids:
            raise TransitionBlocked("TRANSITION_EVIDENCE_REQUIRED", to_phase)
        for evidence_id in evidence_ids:
            _load_evidence(root, evidence_id)
        scope_result = check_scope(root)
        assert_frozen_manifests_immutable(root, scope_result["paths_checked"])

        new_state = deepcopy(current)
        new_state.setdefault("task", {})["phase"] = to_phase
        letter = to_phase.removeprefix("PHASE_").removesuffix("_PASS").lower()
        new_state.setdefault("verification", {})[f"phase_{letter}_acceptance_passed"] = True
        new_state["verification"]["latest_evidence_id"] = evidence_ids[-1]
        new_state.setdefault("progress", {})["next_action"] = (
            "Await Phase D: crash/corruption/concurrency/scope/anti-loop/fresh-session/CI demonstration"
            if to_phase == "PHASE_C_PASS" else new_state.get("progress", {}).get("next_action")
        )
        materialized = _append_control_event_locked(
            root,
            current,
            events,
            event_type="STATE_TRANSITION",
            payload={"from_phase": from_phase, "to_phase": to_phase, "evidence_ids": evidence_ids},
            state_after=new_state,
        )

        project_path = root / "PROJECT_STATE.yaml"
        project = load_yaml(project_path)
        project.setdefault("repository_control_plane", {})["implementation_status"] = to_phase
        project["current_authorized_phase"] = to_phase.replace("_PASS", "")
        project["next_gate"] = "PHASE_D_AUTHORIZATION" if to_phase == "PHASE_C_PASS" else project.get("next_gate")
        # Preserve the safety gates explicitly.
        project["provider_preflight_allowed"] = False
        project["paid_provider_requests_allowed"] = False
        rendered = yaml.safe_dump(project, sort_keys=False, allow_unicode=True)
        write_atomic(project_path, rendered.encode("utf-8"))
        return {"status": "STATE_TRANSITION_OK", "from_phase": from_phase, "to_phase": to_phase, "evidence_ids": evidence_ids, "checkpoint_id": materialized["checkpoint_id"]}
