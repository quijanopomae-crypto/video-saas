from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ObjectStorage(Protocol):
    def put_bytes(self, key: str, data: bytes) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...


@dataclass
class MemoryObjectStorage:
    _objects: dict[str, bytes] = field(default_factory=dict)

    def put_bytes(self, key: str, data: bytes) -> None:
        self._objects[key] = bytes(data)

    def get_bytes(self, key: str) -> bytes:
        return self._objects[key]
