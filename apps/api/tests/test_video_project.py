from __future__ import annotations

from decimal import Decimal

import pytest

from src.modules.planning import ProjectRequest, run_product_flow
from src.modules.video_project import (
    AssetRecord,
    QAFinding,
    add_qa_finding,
    attach_asset,
    from_product_flow,
    select_asset,
    set_quality_lock,
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
        select_asset(project, shot_id, second.asset_id)

    project = set_quality_lock(project, shot_id, False)
    project = select_asset(project, shot_id, second.asset_id)
    assert project.timeline[0].asset_id == second.asset_id


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
