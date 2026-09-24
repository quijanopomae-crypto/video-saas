from __future__ import annotations

import pytest

from src.modules.model_router import (
    MockProviderAdapter,
    MultimodelRouter,
    NoRoute,
    ProviderCapabilities,
    RoutingContext,
)


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


def context(**overrides):
    data = {
        "owner_id": "owner-a",
        "project_id": "project-1",
        "shot_id": "shot-1",
        "duration_sec": 10,
        "budget_usd": "10.00",
    }
    data.update(overrides)
    return RoutingContext(**data)


def test_default_route_is_lowest_cost_compatible_non_premium():
    router = MultimodelRouter(providers())
    decision = router.route(context())
    assert decision.provider_id == "mock-economy"
    assert decision.operation == "generate"
    assert decision.estimated_cost_usd == "0.10"
    assert decision.fallback_provider_ids == ("mock-standard",)


def test_patch_intent_wins_over_regeneration():
    router = MultimodelRouter(providers())
    decision = router.route(context(patch_intent="repair only the subject identity"))
    assert decision.operation == "patch"
    assert decision.provider_id == "mock-economy"


def test_continue_and_reference_preserve_requested_semantics():
    router = MultimodelRouter(providers())
    continued = router.route(context(continue_asset_id="asset-prev"))
    assert continued.operation == "continue"
    assert continued.provider_id == "mock-economy"

    referenced = router.route(context(reference_asset_ids=("ref-a",)))
    assert referenced.operation == "reference"
    assert referenced.provider_id == "mock-standard"


def test_premium_requires_explicit_justification():
    router = MultimodelRouter(providers())
    normal = router.route(context())
    assert normal.provider_id != "mock-premium"

    premium = router.route(context(premium_justified=True, budget_usd="5.00"))
    assert premium.operation == "premium"
    assert premium.provider_id == "mock-premium"
    assert premium.estimated_cost_usd == "2.00"


def test_fallback_excludes_failed_provider_without_changing_operation():
    router = MultimodelRouter(providers())
    first = router.route(context(patch_intent="local repair"))
    second = router.route(
        context(patch_intent="local repair"),
        excluded_provider_ids=(first.provider_id,),
    )
    assert first.provider_id == "mock-economy"
    assert second.provider_id == "mock-standard"
    assert first.operation == second.operation == "patch"


def test_budget_and_duration_are_hard_filters():
    router = MultimodelRouter(providers())
    with pytest.raises(NoRoute, match="no compatible provider"):
        router.route(context(budget_usd="0.05"))

    long_reference = router.route(
        context(duration_sec=90, reference_asset_ids=("ref-a",), budget_usd="5.00")
    )
    assert long_reference.provider_id == "mock-standard"

    with pytest.raises(NoRoute):
        router.route(
            context(duration_sec=121, reference_asset_ids=("ref-a",), budget_usd="50")
        )


def test_sora_2_is_never_routable_even_when_cheapest():
    router = MultimodelRouter(providers())
    decisions = [
        router.route(context()),
        router.route(context(patch_intent="patch")),
        router.route(context(reference_asset_ids=("ref",))),
        router.route(context(premium_justified=True)),
    ]
    assert all(item.provider_id != "SORA_2" for item in decisions)


def test_mock_invocation_is_deterministic_and_contains_cost_lineage():
    router = MultimodelRouter(providers())
    ctx = context(patch_intent="repair")
    decision = router.route(ctx)
    first = router.invoke_mock(decision, ctx)
    second = router.invoke_mock(decision, ctx)
    assert first == second
    assert first == {
        "mock": True,
        "provider_id": "mock-economy",
        "operation": "patch",
        "estimated_cost_usd": "0.10",
        "asset_id": first["asset_id"],
        "shot_id": "shot-1",
    }


def test_real_provider_adapter_is_rejected_in_this_stage():
    with pytest.raises(ValueError, match="real providers are disabled"):
        MockProviderAdapter(
            ProviderCapabilities(
                provider_id="real-provider",
                operations=("generate",),
                cost_per_second_usd="1.00",
                mock=False,
            )
        )
