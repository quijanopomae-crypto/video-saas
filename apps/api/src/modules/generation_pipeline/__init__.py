from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ..model_router import MultimodelRouter, RouteDecision, RoutingContext
from ..planning import ProductFlow, ProjectRequest, run_product_flow
from ..production_engine import ProductionEngine
from ..video_project import (
    AssetRecord,
    VideoProject,
    attach_asset,
    from_product_flow,
    select_asset,
)


@dataclass(frozen=True)
class GenerationRecord:
    shot_id: str
    job_id: str
    asset_id: str
    provider_id: str
    operation: str
    reference_asset_ids: tuple[str, ...]
    estimated_cost_usd: str


@dataclass(frozen=True)
class GenerationRun:
    owner_id: str
    project_id: str
    product_flow: ProductFlow
    video_project: VideoProject
    records: tuple[GenerationRecord, ...]

    @property
    def total_cost_usd(self) -> Decimal:
        return self.video_project.total_cost_usd


class GenerationPipeline:
    """Synchronous no-spend integration of the canonical video-generation core.

    Stage 4 deliberately drives only deterministic mock providers. The pipeline
    reuses canonical planning, production jobs, routing and VideoProject asset
    lineage instead of introducing a second orchestration or ledger system.
    """

    def __init__(self, router: MultimodelRouter, production: ProductionEngine) -> None:
        self._router = router
        self._production = production
        self._runs: dict[tuple[str, str], GenerationRun] = {}

    @staticmethod
    def _required(value: str, name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{name} is required")
        return normalized

    @staticmethod
    def _budget(value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("budget_usd_per_shot must be a decimal string")
        try:
            amount = Decimal(value)
        except InvalidOperation as exc:
            raise ValueError("budget_usd_per_shot must be decimal") from exc
        if amount < 0:
            raise ValueError("budget_usd_per_shot cannot be negative")
        return format(amount, "f")

    @staticmethod
    def _idempotency_key(project_id: str, shot_id: str, operation: str) -> str:
        return f"generation:{project_id}:{shot_id}:{operation}"

    @staticmethod
    def _asset_from_mock(
        *,
        owner_id: str,
        project_id: str,
        decision: RouteDecision,
        job_id: str,
        shot_id: str,
        asset_id: str,
    ) -> AssetRecord:
        return AssetRecord(
            asset_id=asset_id,
            shot_id=shot_id,
            kind="video",
            uri=f"mock://{owner_id}/{project_id}/{asset_id}",
            source=f"{decision.provider_id}:{decision.operation}",
            source_ref=job_id,
            cost_usd=decision.estimated_cost_usd,
        )

    def run(
        self,
        *,
        owner_id: str,
        request: ProjectRequest,
        budget_usd_per_shot: str = "5.00",
    ) -> GenerationRun:
        owner = self._required(owner_id, "owner_id")
        if not isinstance(request, ProjectRequest):
            raise TypeError("request must be ProjectRequest")
        budget = self._budget(budget_usd_per_shot)

        flow = run_product_flow(request)
        project_id = flow.project_bible.project_id
        key = (owner, project_id)
        existing = self._runs.get(key)
        if existing is not None:
            if existing.product_flow.to_dict() != flow.to_dict():
                raise ValueError("project id collision with different planning input")
            return existing

        project = from_product_flow(flow)
        records: list[GenerationRecord] = []
        prior_asset_ids: list[str] = []

        for shot in flow.shot_contracts:
            references = tuple(prior_asset_ids[-1:])
            context = RoutingContext(
                owner_id=owner,
                project_id=project_id,
                shot_id=shot.shot_id,
                duration_sec=shot.duration_sec,
                budget_usd=budget,
                reference_asset_ids=references,
            )
            decision = self._router.route(context)
            job = self._production.submit(
                owner_id=owner,
                project_id=project_id,
                shot_id=shot.shot_id,
                operation=decision.operation,
                idempotency_key=self._idempotency_key(
                    project_id, shot.shot_id, decision.operation
                ),
            )
            running = self._production.claim_next()
            if running is None or running.job_id != job.job_id:
                raise RuntimeError(
                    "generation pipeline requires exclusive sequential access to its mock queue"
                )

            output = self._router.invoke_mock(decision, context)
            if output.get("mock") is not True:
                raise RuntimeError("generation pipeline received a non-mock provider result")
            asset_id = str(output["asset_id"])
            completed = self._production.complete(
                owner_id=owner,
                job_id=job.job_id,
                output_asset_id=asset_id,
            )
            if completed.state != "succeeded" or completed.output_asset_id != asset_id:
                raise RuntimeError("production job did not record the generated asset")

            asset = self._asset_from_mock(
                owner_id=owner,
                project_id=project_id,
                decision=decision,
                job_id=job.job_id,
                shot_id=shot.shot_id,
                asset_id=asset_id,
            )
            project = attach_asset(project, asset)
            project = select_asset(project, shot.shot_id, asset_id)
            records.append(
                GenerationRecord(
                    shot_id=shot.shot_id,
                    job_id=job.job_id,
                    asset_id=asset_id,
                    provider_id=decision.provider_id,
                    operation=decision.operation,
                    reference_asset_ids=references,
                    estimated_cost_usd=decision.estimated_cost_usd,
                )
            )
            prior_asset_ids.append(asset_id)

        project.validate()
        result = GenerationRun(
            owner_id=owner,
            project_id=project_id,
            product_flow=flow,
            video_project=project,
            records=tuple(records),
        )
        self._runs[key] = result
        return result

    def get(self, *, owner_id: str, project_id: str) -> GenerationRun:
        owner = self._required(owner_id, "owner_id")
        project = self._required(project_id, "project_id")
        result = self._runs.get((owner, project))
        if result is not None:
            return result
        if any(run_project_id == project for _, run_project_id in self._runs):
            raise PermissionError("cross-owner generation run access denied")
        raise KeyError(project)

    def list_owner(self, *, owner_id: str) -> tuple[GenerationRun, ...]:
        owner = self._required(owner_id, "owner_id")
        return tuple(
            sorted(
                (run for (run_owner, _), run in self._runs.items() if run_owner == owner),
                key=lambda item: item.project_id,
            )
        )
