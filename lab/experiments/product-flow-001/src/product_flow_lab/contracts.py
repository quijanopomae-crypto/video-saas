from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


_ALLOWED_ASPECT_RATIOS = {"16:9", "9:16", "1:1"}


@dataclass(frozen=True)
class ProjectRequest:
    title: str
    idea: str
    duration_sec: int
    aspect_ratio: str = "16:9"
    audience: str = "general"
    tone: str = "clear"
    language: str = "es"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ProjectRequest":
        request = cls(
            title=str(payload["title"]).strip(),
            idea=str(payload["idea"]).strip(),
            duration_sec=int(payload["duration_sec"]),
            aspect_ratio=str(payload.get("aspect_ratio", "16:9")).strip(),
            audience=str(payload.get("audience", "general")).strip(),
            tone=str(payload.get("tone", "clear")).strip(),
            language=str(payload.get("language", "es")).strip(),
        )
        request.validate()
        return request

    def validate(self) -> None:
        if not self.title:
            raise ValueError("title is required")
        if not self.idea:
            raise ValueError("idea is required")
        if not 5 <= self.duration_sec <= 600:
            raise ValueError("duration_sec must be between 5 and 600")
        if self.aspect_ratio not in _ALLOWED_ASPECT_RATIOS:
            raise ValueError(f"unsupported aspect_ratio: {self.aspect_ratio}")


@dataclass(frozen=True)
class ProjectBible:
    project_id: str
    title: str
    core_idea: str
    audience: str
    tone: str
    language: str
    aspect_ratio: str
    continuity_rules: tuple[str, ...]


@dataclass(frozen=True)
class SceneNode:
    scene_id: str
    order: int
    duration_sec: int
    objective: str
    narrative_beat: str


@dataclass(frozen=True)
class ShotContract:
    shot_id: str
    scene_id: str
    order: int
    duration_sec: int
    intent: str
    continuity_refs: tuple[str, ...]
    production_mode: str


@dataclass(frozen=True)
class PreviewSegment:
    shot_id: str
    start_sec: int
    end_sec: int


@dataclass(frozen=True)
class PreviewPlan:
    total_duration_sec: int
    segments: tuple[PreviewSegment, ...]


@dataclass(frozen=True)
class ProductFlow:
    request: ProjectRequest
    project_bible: ProjectBible
    scene_graph: tuple[SceneNode, ...]
    shot_contracts: tuple[ShotContract, ...]
    preview_plan: PreviewPlan

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
