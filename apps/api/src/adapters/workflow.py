from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class WorkflowEngine(Protocol):
    def start(self, workflow: str, payload: dict[str, Any]) -> str: ...
    def status(self, run_id: str) -> dict[str, Any]: ...


@dataclass
class MemoryWorkflowEngine:
    _runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    _counter: int = 0

    def start(self, workflow: str, payload: dict[str, Any]) -> str:
        self._counter += 1
        run_id = f"local-run-{self._counter}"
        self._runs[run_id] = {
            "run_id": run_id,
            "workflow": workflow,
            "payload": payload,
            "status": "queued",
        }
        return run_id

    def status(self, run_id: str) -> dict[str, Any]:
        return dict(self._runs[run_id])
