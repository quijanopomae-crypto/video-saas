from __future__ import annotations

import hashlib
import math
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


def _stable_project_id(request: ProjectRequest) -> str:
    material = "|".join(
        [
            request.title,
            request.idea,
            str(request.duration_sec),
            request.aspect_ratio,
            request.audience,
            request.tone,
            request.language,
        ]
    )
    return "prj-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


def _distribute(total: int, parts: int) -> list[int]:
    if parts <= 0:
        raise ValueError("parts must be positive")
    base, remainder = divmod(total, parts)
    return [base + (1 if index < remainder else 0) for index in range(parts)]


def build_project_bible(request: ProjectRequest) -> ProjectBible:
    project_id = _stable_project_id(request)
    return ProjectBible(
        project_id=project_id,
        title=request.title,
        core_idea=request.idea,
        audience=request.audience,
        tone=request.tone,
        language=request.language,
        aspect_ratio=request.aspect_ratio,
        continuity_rules=(
            "Preserve declared subject identity across adjacent shots.",
            "Preserve aspect ratio across the project.",
            "Do not introduce provider-specific assumptions into planning contracts.",
        ),
    )


def build_scene_graph(request: ProjectRequest, bible: ProjectBible) -> tuple[SceneNode, ...]:
    scene_count = max(1, math.ceil(request.duration_sec / 12))
    durations = _distribute(request.duration_sec, scene_count)
    nodes: list[SceneNode] = []
    for index, duration in enumerate(durations, start=1):
        if scene_count == 1:
            objective = "deliver"
        elif index == 1:
            objective = "hook"
        elif index == scene_count:
            objective = "resolve"
        else:
            objective = "develop"
        nodes.append(
            SceneNode(
                scene_id=f"{bible.project_id}-s{index:02d}",
                order=index,
                duration_sec=duration,
                objective=objective,
                narrative_beat=f"{objective}: {request.idea}",
            )
        )
    return tuple(nodes)


def build_shot_contracts(
    request: ProjectRequest,
    bible: ProjectBible,
    scenes: tuple[SceneNode, ...],
) -> tuple[ShotContract, ...]:
    shots: list[ShotContract] = []
    global_order = 1
    for scene in scenes:
        shot_count = max(1, math.ceil(scene.duration_sec / 5))
        shot_durations = _distribute(scene.duration_sec, shot_count)
        for local_index, duration in enumerate(shot_durations, start=1):
            shots.append(
                ShotContract(
                    shot_id=f"{scene.scene_id}-sh{local_index:02d}",
                    scene_id=scene.scene_id,
                    order=global_order,
                    duration_sec=duration,
                    intent=f"{scene.objective} / beat {local_index}: {request.idea}",
                    continuity_refs=(bible.project_id, scene.scene_id),
                    production_mode="PLACEHOLDER",
                )
            )
            global_order += 1
    return tuple(shots)


def build_preview_plan(shots: tuple[ShotContract, ...]) -> PreviewPlan:
    cursor = 0
    segments: list[PreviewSegment] = []
    for shot in shots:
        end = cursor + shot.duration_sec
        segments.append(PreviewSegment(shot_id=shot.shot_id, start_sec=cursor, end_sec=end))
        cursor = end
    return PreviewPlan(total_duration_sec=cursor, segments=tuple(segments))


def run_product_flow(request: ProjectRequest) -> ProductFlow:
    bible = build_project_bible(request)
    scenes = build_scene_graph(request, bible)
    shots = build_shot_contracts(request, bible, scenes)
    preview = build_preview_plan(shots)
    return ProductFlow(
        request=request,
        project_bible=bible,
        scene_graph=scenes,
        shot_contracts=shots,
        preview_plan=preview,
    )
