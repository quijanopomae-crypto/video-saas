from __future__ import annotations

from decimal import Decimal

import pytest

from src.modules.planning import ProjectRequest, run_product_flow
from src.modules.video_project import (
    AssetRecord,
    QAFinding,
    add_qa_finding,
    attach_asset,
    change_caption,
    from_product_flow,
    lock_scene,
    move_overlay,
    patch_scene,
    replace_asset,
    select_asset,
    set_quality_lock,
    trim_clip,
    unlock_scene,
)


def _project():
    flow = run_product_flow(
        ProjectRequest.from_dict(
            {
                "title": "Video core",
                "idea": "Probar un proyecto de video determinista",
                "duration_sec": 20,
            }
        )
    )
    return flow, from_product_flow(flow)


def test_video_project_preserves_canonical_ids_and_timeline() -> None:
    flow, project = _project()
    assert project.project_id == flow.project_bible.project_id
    assert [item.shot_id for item in project.timeline] == [
        item.shot_id for item in flow.preview_plan.segments
    ]
    assert project.timeline[-1].end_sec == flow.preview_plan.total_duration_sec
    assert project.to_dict() == from_product_flow(flow).to_dict()


def test_asset_lineage_and_cost_are_explicit() -> None:
    _, project = _project()
    shot_id = project.timeline[0].shot_id
    asset = AssetRecord(
        asset_id="asset-001",
        shot_id=shot_id,
        kind="video",
        uri="asset://mock/001",
        source="mock-generator",
        source_ref="job-001",
        cost_usd="0.125",
    )
    project = attach_asset(project, asset)
    project = select_asset(project, shot_id, asset.asset_id)
    assert project.timeline[0].asset_id == "asset-001"
    assert project.total_cost_usd == Decimal("0.125")
    assert project.assets[0].source_ref == "job-001"


def test_quality_lock_blocks_silent_asset_replacement() -> None:
    _, project = _project()
    shot_id = project.timeline[0].shot_id
    first = AssetRecord("asset-1", shot_id, "video", "asset://1", "mock", cost_usd="0")
    second = AssetRecord("asset-2", shot_id, "video", "asset://2", "mock", cost_usd="0")
    project = attach_asset(attach_asset(project, first), second)
    project = select_asset(project, shot_id, first.asset_id)
    project = set_quality_lock(project, shot_id, True)

    with pytest.raises(ValueError, match="quality-locked"):
        replace_asset(project, shot_id, second.asset_id)

    project = set_quality_lock(project, shot_id, False)
    project = replace_asset(project, shot_id, second.asset_id)
    assert project.timeline[0].asset_id == second.asset_id


def test_validated_edit_primitives_share_quality_lock() -> None:
    _, project = _project()
    shot_id = project.timeline[0].shot_id
    project = trim_clip(project, shot_id, 0, project.timeline[0].duration_sec - 1)
    project = change_caption(project, shot_id, "  Texto validado  ")
    project = move_overlay(project, shot_id, 0.25, 0.75)

    edited = project.timeline[0]
    assert edited.clip_out_sec == edited.duration_sec - 1
    assert edited.caption_text == "Texto validado"
    assert (edited.overlay_x, edited.overlay_y) == (0.25, 0.75)

    project = set_quality_lock(project, shot_id, True)
    for operation in (
        lambda: trim_clip(project, shot_id, 0, 1),
        lambda: change_caption(project, shot_id, "otro"),
        lambda: move_overlay(project, shot_id, 0.5, 0.5),
    ):
        with pytest.raises(ValueError, match="quality-locked"):
            operation()


def test_scene_patch_and_scene_lock_are_validated() -> None:
    flow, project = _project()
    scene_id = flow.scene_graph[0].scene_id
    shot_ids = {item.shot_id for item in flow.shot_contracts if item.scene_id == scene_id}

    project = patch_scene(project, scene_id, "repair local continuity only")
    assert {
        item.patch_intent for item in project.timeline if item.shot_id in shot_ids
    } == {"repair local continuity only"}

    project = lock_scene(project, scene_id)
    assert all(item.lock_state == "locked" for item in project.timeline if item.shot_id in shot_ids)
    with pytest.raises(ValueError, match="quality-locked scene"):
        patch_scene(project, scene_id, "second patch")

    project = unlock_scene(project, scene_id)
    project = patch_scene(project, scene_id, "second patch")
    assert all(
        item.patch_intent == "second patch"
        for item in project.timeline
        if item.shot_id in shot_ids
    )


def test_edit_primitives_reject_invalid_ranges_and_unknown_scene() -> None:
    _, project = _project()
    shot_id = project.timeline[0].shot_id
    with pytest.raises(ValueError, match="clip trim"):
        trim_clip(project, shot_id, 2, 2)
    with pytest.raises(ValueError, match="overlay position"):
        move_overlay(project, shot_id, 1.1, 0.5)
    with pytest.raises(ValueError, match="unknown scene"):
        patch_scene(project, "scene-missing", "repair")


def test_qa_finding_can_describe_patch_intent() -> None:
    _, project = _project()
    shot_id = project.timeline[0].shot_id
    project = add_qa_finding(
        project,
        QAFinding(
            finding_id="qa-001",
            shot_id=shot_id,
            status="fail",
            code="continuity.subject",
            message="subject identity drift",
            patch_intent="repair subject identity without regenerating accepted shots",
        ),
    )
    assert project.qa_findings[0].patch_intent is not None


def test_invalid_cross_shot_asset_reference_is_rejected() -> None:
    _, project = _project()
    first_shot = project.timeline[0].shot_id
    other_shot = project.timeline[-1].shot_id
    if first_shot == other_shot:
        pytest.skip("flow produced one shot")
    asset = AssetRecord("asset-x", first_shot, "video", "asset://x", "mock")
    project = attach_asset(project, asset)
    with pytest.raises(ValueError, match="not available"):
        select_asset(project, other_shot, asset.asset_id)
