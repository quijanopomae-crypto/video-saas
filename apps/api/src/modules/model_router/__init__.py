from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol


Operation = Literal["generate", "continue", "reference", "patch", "premium"]
QualityTier = Literal["draft", "standard", "premium"]
_DO_NOT_ROUTE = {"sora_2", "sora-2", "sora2"}


class NoRoute(ValueError):
    pass


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_id: str
    operations: tuple[Operation, ...]
    cost_per_second_usd: str
    quality_tier: QualityTier = "standard"
    max_duration_sec: int = 60
    enabled: bool = True
    mock: bool = True

    def validate(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id is required")
        if not self.operations:
            raise ValueError("provider must expose at least one operation")
        if self.max_duration_sec < 1:
            raise ValueError("max_duration_sec must be positive")
        try:
            cost = Decimal(self.cost_per_second_usd)
        except InvalidOperation as exc:
            raise ValueError("provider cost must be decimal") from exc
        if cost < 0:
            raise ValueError("provider cost cannot be negative")
        if not self.mock:
            raise ValueError("real providers are disabled in this stage")


@dataclass(frozen=True)
class RoutingContext:
    owner_id: str
    project_id: str
    shot_id: str
    duration_sec: int
    budget_usd: str
    patch_intent: str | None = None
    continue_asset_id: str | None = None
    reference_asset_ids: tuple[str, ...] = ()
    premium_justified: bool = False

    def validate(self) -> None:
        for value, name in (
            (self.owner_id, "owner_id"),
            (self.project_id, "project_id"),
            (self.shot_id, "shot_id"),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")
        if type(self.duration_sec) is not int or self.duration_sec < 1:
            raise ValueError("duration_sec must be a positive integer")
        try:
            budget = Decimal(self.budget_usd)
        except InvalidOperation as exc:
            raise ValueError("budget_usd must be decimal") from exc
        if budget < 0:
            raise ValueError("budget_usd cannot be negative")


@dataclass(frozen=True)
class RouteDecision:
    provider_id: str
    operation: Operation
    estimated_cost_usd: str
    fallback_provider_ids: tuple[str, ...]
    reasons: tuple[str, ...]


class ProviderAdapter(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...

    def invoke_mock(
        self, decision: RouteDecision, context: RoutingContext
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class MockProviderAdapter:
    capabilities: ProviderCapabilities

    def __post_init__(self) -> None:
        self.capabilities.validate()

    def invoke_mock(
        self, decision: RouteDecision, context: RoutingContext
    ) -> dict[str, Any]:
        if decision.provider_id != self.capabilities.provider_id:
            raise ValueError("decision belongs to a different provider")
        if decision.operation not in self.capabilities.operations:
            raise ValueError("provider does not support requested operation")
        material = "|".join(
            [
                context.owner_id,
                context.project_id,
                context.shot_id,
                decision.provider_id,
                decision.operation,
                decision.estimated_cost_usd,
            ]
        )
        mock_asset_id = "mock-asset-" + hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest()[:16]
        return {
            "mock": True,
            "provider_id": decision.provider_id,
            "operation": decision.operation,
            "estimated_cost_usd": decision.estimated_cost_usd,
            "asset_id": mock_asset_id,
            "shot_id": context.shot_id,
        }


class MultimodelRouter:
    def __init__(self, providers: tuple[ProviderAdapter, ...]) -> None:
        if not providers:
            raise ValueError("at least one provider adapter is required")
        by_id: dict[str, ProviderAdapter] = {}
        for adapter in providers:
            adapter.capabilities.validate()
            provider_id = adapter.capabilities.provider_id
            if provider_id in by_id:
                raise ValueError("duplicate provider_id")
            by_id[provider_id] = adapter
        self._providers = by_id

    @staticmethod
    def choose_operation(context: RoutingContext) -> Operation:
        context.validate()
        if context.patch_intent and context.patch_intent.strip():
            return "patch"
        if context.continue_asset_id and context.continue_asset_id.strip():
            return "continue"
        if context.reference_asset_ids:
            return "reference"
        if context.premium_justified:
            return "premium"
        return "generate"

    @staticmethod
    def _blocked(provider_id: str) -> bool:
        return provider_id.strip().lower() in _DO_NOT_ROUTE

    @staticmethod
    def _cost(capabilities: ProviderCapabilities, duration_sec: int) -> Decimal:
        return Decimal(capabilities.cost_per_second_usd) * Decimal(duration_sec)

    def route(
        self,
        context: RoutingContext,
        *,
        excluded_provider_ids: tuple[str, ...] = (),
    ) -> RouteDecision:
        context.validate()
        operation = self.choose_operation(context)
        excluded = set(excluded_provider_ids)
        budget = Decimal(context.budget_usd)
        candidates: list[tuple[Decimal, str, ProviderAdapter]] = []
        rejection_reasons: list[str] = []

        for provider_id, adapter in self._providers.items():
            cap = adapter.capabilities
            if self._blocked(provider_id):
                rejection_reasons.append(f"{provider_id}:do-not-route")
                continue
            if provider_id in excluded:
                rejection_reasons.append(f"{provider_id}:excluded-after-failure")
                continue
            if not cap.enabled:
                rejection_reasons.append(f"{provider_id}:disabled")
                continue
            if operation not in cap.operations:
                rejection_reasons.append(f"{provider_id}:operation")
                continue
            if context.duration_sec > cap.max_duration_sec:
                rejection_reasons.append(f"{provider_id}:duration")
                continue
            # Premium capacity is never consumed implicitly. The logical premium
            # operation is the only path that can select a premium-tier provider.
            if operation != "premium" and cap.quality_tier == "premium":
                rejection_reasons.append(f"{provider_id}:premium-not-justified")
                continue
            if operation == "premium" and cap.quality_tier != "premium":
                rejection_reasons.append(f"{provider_id}:not-premium")
                continue
            cost = self._cost(cap, context.duration_sec)
            if cost > budget:
                rejection_reasons.append(f"{provider_id}:budget")
                continue
            candidates.append((cost, provider_id, adapter))

        if not candidates:
            detail = ",".join(sorted(rejection_reasons))
            raise NoRoute(
                f"no compatible provider for operation={operation}; {detail}"
            )

        candidates.sort(key=lambda item: (item[0], item[1]))
        cost, provider_id, _ = candidates[0]
        fallbacks = tuple(item[1] for item in candidates[1:])
        return RouteDecision(
            provider_id=provider_id,
            operation=operation,
            estimated_cost_usd=format(cost, "f"),
            fallback_provider_ids=fallbacks,
            reasons=(
                f"operation={operation}",
                "capability-compatible",
                "within-budget",
                "lowest-cost-compatible",
            ),
        )

    def invoke_mock(
        self, decision: RouteDecision, context: RoutingContext
    ) -> dict[str, Any]:
        adapter = self._providers.get(decision.provider_id)
        if adapter is None or self._blocked(decision.provider_id):
            raise NoRoute("provider is not routable")
        return adapter.invoke_mock(decision, context)
