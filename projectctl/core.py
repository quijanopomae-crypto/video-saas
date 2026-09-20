from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
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


def git_snapshot(root: Path) -> dict[str, Any]:
    top = Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if top != root.resolve():
        raise RecoveryBlocked("RECOVERY_WRONG_REPOSITORY", f"git root {top} != expected {root.resolve()}")
    branch = _git(root, "branch", "--show-current").decode().strip()
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    # `.state/` is the agent cursor itself; checkpoint/recovery writes there must
    # not make the checkpoint immediately look stale. Reconcile all other
    # repository changes, including untracked files.
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
    progress = current.get("progress", {})
    verification = current.get("verification", {})
    external = current.get("external_operations", {})
    repository = current.get("repository", {})
    completed = progress.get("completed_steps") or []
    lines = [
        f"# RESUME — {task.get('task_id', 'UNKNOWN')}",
        "",
        "Generated view of `.state/CURRENT.json`. It is not an independent source of truth.",
        "",
        f"- **Phase:** {task.get('phase')}",
        f"- **Checkpoint:** {current.get('checkpoint_id')}",
        f"- **State version:** {current.get('state_version')}",
        f"- **Branch:** {repository.get('branch', 'UNRECORDED')}",
        f"- **HEAD:** {repository.get('head_commit', 'UNRECORDED')}",
        f"- **Working tree dirty:** {repository.get('working_tree_dirty', 'UNRECORDED')}",
        f"- **Provider Preflight started:** {str(external.get('provider_preflight_started', False)).lower()}",
        f"- **Paid requests allowed:** {str(external.get('paid_requests_allowed', False)).lower()}",
        f"- **Phase A acceptance:** {str(verification.get('phase_a_acceptance_passed', False)).lower()}",
        f"- **Baseline regression suite:** {str(verification.get('baseline_regression_suite_passed', False)).lower()}",
        f"- **Phase B acceptance:** {str(verification.get('phase_b_acceptance_passed', False)).lower()}",
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
        f"`{task.get('task_contract_sha256')}`",
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


def _verify_snapshot_vs_git(current: dict[str, Any], observed: dict[str, Any]) -> None:
    expected = current.get("repository")
    if not expected:
        return
    if expected.get("branch") != observed.get("branch"):
        raise RecoveryBlocked(
            "RECOVERY_WRONG_BRANCH",
            f"expected {expected.get('branch')!r}; observed {observed.get('branch')!r}",
        )
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
            _verify_snapshot_vs_git(current, observed)
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
