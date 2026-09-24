from __future__ import annotations

from decimal import Decimal

import pytest

from src.adapters.queue import MemoryJobQueue
from src.adapters.workflow import MemoryWorkflowEngine
from src.modules.generation_pipeline import GenerationPipeline
from src.modules.model_router import (
    MockProviderAdapter,
    MultimodelRouter,
    NoRoute,
    ProviderCapabilities,
)
from src.modules.planning import ProjectRequest
from src.modules.production_engine import ProductionEngine


def providers():
    return (
        MockProviderAdapter(
            ProviderCapabilities(
                provider_id="mock-economy",
                operations=("generate", "continue", "patch"),
                cost_per_second_usd="0.01",
                quality_tier="draft",
                max_duration_sec=60,
            )
        ),
        MockProviderAdapter(
            ProviderCapabilities(
                provider_id="mock-standard",
                operations=("generate", "continue", "reference", "patch"),
                cost_per_second_usd="0.02",
                quality_tier="standard",
                max_duration_sec=120,
            )
        ),
        MockProviderAdapter(
            ProviderCapabilities(
                provider_id="mock-premium",
                operations=("generate", "reference", "patch", "premium"),
                cost_per_second_usd="0.20",
                quality_tier="premium",
                max_duration_sec=120,
            )
        ),
        MockProviderAdapter(
            ProviderCapabilities(
                provider_id="SORA_2",
                operations=("generate", "continue", "reference", "patch", "premium"),
                cost_per_second_usd="0.0001",
                quality_tier="draft",
                max_duration_sec=600,
            )
        ),
    )


def stack():
    production = ProductionEngine(MemoryJobQueue(), MemoryWorkflowEngine())
    pipeline = GenerationPipeline(MultimodelRouter(providers()), production)
    return pipeline, production


def request():
    return ProjectRequest.from_dict(
        {
            "title": "Stage 4 generation",
            "idea": "Construir un flujo determinista sin gasto real",
            "duration_sec": 20,
        }
    )


def test_generation_pipeline_runs_prompt_to_video_project_e2e_without_real_providers():
    pipeline, production = stack()
    result = pipeline.run(owner_id="owner-a", request=request())

    assert result.owner_id == "owner-a"
    assert len(result.records) == len(result.product_flow.shot_contracts)
    assert len(result.video_project.assets) == len(result.records)
    assert len(result.video_project.timeline) == len(result.records)
    assert result.records[0].operation == "generate"
    assert all(record.operation == "reference" for record in result.records[1:])
    assert all(record.provider_id != "SORA_2" for record in result.records)

    selected = {item.shot_id: item.asset_id for item in result.video_project.timeline}
    for record in result.records:
        job = production.get(owner_id="owner-a", job_id=record.job_id)
        assert job.state == "succeeded"
        assert job.output_asset_id == record.asset_id
        assert selected[record.shot_id] == record.asset_id

    result.video_project.validate()


def test_reference_lineage_uses_only_previously_generated_assets():
    pipeline, _ = stack()
    result = pipeline.run(owner_id="owner-a", request=request())

    seen: set[str] = set()
    for index, record in enumerate(result.records):
        assert set(record.reference_asset_ids) <= seen
        if index == 0:
            assert record.reference_asset_ids == ()
        else:
            assert record.reference_asset_ids == (result.records[index - 1].asset_id,)
        seen.add(record.asset_id)


def test_asset_and_cost_lineage_are_carried_into_video_project():
    pipeline, _ = stack()
    result = pipeline.run(owner_id="owner-a", request=request())
    by_id = {asset.asset_id: asset for asset in result.video_project.assets}

    expected_total = Decimal("0")
    for record in result.records:
        asset = by_id[record.asset_id]
        assert asset.shot_id == record.shot_id
        assert asset.uri.startswith(f"mock://owner-a/{result.project_id}/")
        assert asset.source == f"{record.provider_id}:{record.operation}"
        assert asset.source_ref == record.job_id
        assert asset.cost_usd == record.estimated_cost_usd
        expected_total += Decimal(record.estimated_cost_usd)

    assert result.total_cost_usd == expected_total
    assert result.video_project.total_cost_usd == expected_total


def test_replay_is_idempotent_without_duplicate_jobs_assets_or_cost():
    pipeline, production = stack()
    first = pipeline.run(owner_id="owner-a", request=request())
    job_count = len(production.list_owner(owner_id="owner-a"))
    asset_count = len(first.video_project.assets)
    cost = first.total_cost_usd

    second = pipeline.run(owner_id="owner-a", request=request())

    assert second == first
    assert len(production.list_owner(owner_id="owner-a")) == job_count
    assert len(second.video_project.assets) == asset_count
    assert second.total_cost_usd == cost


def test_generation_runs_are_owner_scoped_and_mock_assets_are_owner_distinct():
    pipeline, production = stack()
    first = pipeline.run(owner_id="owner-a", request=request())

    with pytest.raises(PermissionError, match="cross-owner"):
        pipeline.get(owner_id="owner-b", project_id=first.project_id)

    second = pipeline.run(owner_id="owner-b", request=request())
    assert second.project_id == first.project_id
    assert {record.asset_id for record in first.records}.isdisjoint(
        {record.asset_id for record in second.records}
    )
    assert pipeline.list_owner(owner_id="owner-a") == (first,)
    assert pipeline.list_owner(owner_id="owner-b") == (second,)
    assert len(production.list_owner(owner_id="owner-a")) == len(first.records)
    assert len(production.list_owner(owner_id="owner-b")) == len(second.records)


def test_budget_is_enforced_before_any_job_or_asset_is_created():
    pipeline, production = stack()

    with pytest.raises(NoRoute):
        pipeline.run(
            owner_id="owner-a",
            request=request(),
            budget_usd_per_shot="0.001",
        )

    assert production.list_owner(owner_id="owner-a") == ()
    assert pipeline.list_owner(owner_id="owner-a") == ()


def test_invalid_budget_and_owner_are_rejected_before_generation():
    pipeline, production = stack()
    with pytest.raises(ValueError, match="owner_id"):
        pipeline.run(owner_id="   ", request=request())
    with pytest.raises(ValueError, match="budget"):
        pipeline.run(owner_id="owner-a", request=request(), budget_usd_per_shot="-1")
    assert production.list_owner(owner_id="owner-a") == ()
