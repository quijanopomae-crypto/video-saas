from __future__ import annotations

import hashlib
import math

from product_flow_lab.contracts import (
    PreviewPlan,
    PreviewSegment,
    ProductBible,
    ProductFlow,
    ProjectRequest,
    SceneNode,
    ShotContract,
)


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
