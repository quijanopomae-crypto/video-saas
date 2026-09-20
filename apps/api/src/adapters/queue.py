from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Protocol


class JobQueue(Protocol):
    def enqueue(self, payload: dict[str, Any]) -> str: ...
    def dequeue(self) -> dict[str, Any] | None: ...


@dataclass
class MemoryJobQueue:
    _items: deque[dict[str, Any]] = field(default_factory=deque)
    _counter: int = 0

    def enqueue(self, payload: dict[str, Any]) -> str:
        self._counter += 1
        item = {"job_id": f"local-{self._counter}", **payload}
        self._items.append(item)
        return item["job_id"]

    def dequeue(self) -> dict[str, Any] | None:
        return self._items.popleft() if self._items else None
