from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Literal

from ..generation_pipeline import GenerationRun
from ..model_router import MultimodelRouter, RoutingContext
from ..production_engine import ProductionEngine
from ..video_project import (
    AssetRecord,
    QAFinding,
    VideoProject,
    add_qa_finding,
    attach_asset,
    select_asset,
    set_quality_lock,
)


RepairAction = Literal["patch", "continue", "reference", "regenerate"]
FindingStatus = Literal["open", "resolved"]
FindingSource = Literal["structural", "mock-observation"]
RepairState = Literal["retryable", "blocked", "failed", "succeeded"]


@dataclass(frozen=True)
class QAObservation:
    """Explicit deterministic mock observation.

    This is test/input evidence, not a claim that a vision model inspected media.
    """

    shot_id: str
    code: str
    message: str
    patch_intent: str | None = None
    suggested_action: RepairAction | None = None
    local_repair_sufficient: bool = True


@dataclass(frozen=True)
class ErrorMapEntry:
    finding_id: str
    project_id: str
    scene_id: str
    shot_id: str
    code: str
    message: str
    source: FindingSource
    recommended_action: RepairAction
    patch_intent: str | None
    status: FindingStatus = "open"


@dataclass(frozen=True)
class RepairRecord:
    finding_id: str
    requested_action: RepairAction
    routed_operation: str
    job_id: str
    provider_id: str
    state: RepairState
    prior_asset_id: str | None
    output_asset_id: str | None
    estimated_cost_usd: str
    causal_change: str | None


@dataclass(frozen=True)
class QASession:
    session_id: str
    owner_id: str
    project_id: str
    project: VideoProject
    error_map: tuple[ErrorMapEntry, ...]
    repairs: tuple[RepairRecord, ...] = ()
    qa_sources: tuple[str, ...] = ("deterministic-structural",)
    visual_inspection_performed: bool = False

    @property
    def open_findings(self) -> tuple[ErrorMapEntry, ...]:
        return tuple(item for item in self.error_map if item.status == "open")


class IntelligenceQA:
    """Owner-scoped deterministic QA and selective repair orchestration.

    Structural checks operate only on canonical metadata. Additional findings
    must be supplied explicitly as QAObservation mocks. Provider execution stays
    behind the canonical mock-only router and ProductionEngine.
    """

    _ACTIONS = {"patch", "continue", "reference", "regenerate"}

    def __init__(self, router: MultimodelRouter, production: ProductionEngine) -> None:
        self._router = router
        self._production = production
        self._sessions: dict[str, QASession] = {}

    @staticmethod
    def _required(value: str, name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{name} must be a string")
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{name} is required")
        return normalized

    @staticmethod
    def _stable_id(prefix: str, *parts: str) -> str:
        material = "|".join(parts).encode("utf-8")
        return prefix + hashlib.sha256(material).hexdigest()[:16]

    @staticmethod
    def _scene_by_shot(run: GenerationRun) -> dict[str, str]:
        return {shot.shot_id: shot.scene_id for shot in run.product_flow.shot_contracts}

    @staticmethod
    def _timeline_item(project: VideoProject, shot_id: str):
        item = next((item for item in project.timeline if item.shot_id == shot_id), None)
        if item is None:
            raise ValueError("finding references unknown shot")
        return item

    @classmethod
    def _recommended_action(
        cls,
        *,
        patch_intent: str | None,
        suggested_action: RepairAction | None,
        local_repair_sufficient: bool,
    ) -> RepairAction:
        if suggested_action is not None:
            if suggested_action not in cls._ACTIONS:
                raise ValueError("unsupported repair action")
            return suggested_action
        if local_repair_sufficient or (patch_intent and patch_intent.strip()):
            return "patch"
        return "regenerate"

    def _entry(
        self,
        *,
        run: GenerationRun,
        shot_id: str,
        code: str,
        message: str,
        source: FindingSource,
        patch_intent: str | None,
        suggested_action: RepairAction | None,
        local_repair_sufficient: bool,
    ) -> ErrorMapEntry:
        scene_id = self._scene_by_shot(run).get(shot_id)
        if scene_id is None:
            raise ValueError("QA evidence references unknown shot")
        normalized_code = self._required(code, "code")
        normalized_message = self._required(message, "message")
        normalized_patch = patch_intent.strip() if isinstance(patch_intent, str) else None
        normalized_patch = normalized_patch or None
        action = self._recommended_action(
            patch_intent=normalized_patch,
            suggested_action=suggested_action,
            local_repair_sufficient=local_repair_sufficient,
        )
        finding_id = self._stable_id(
            "finding-",
            run.project_id,
            shot_id,
            normalized_code,
            normalized_message,
            source,
        )
        return ErrorMapEntry(
            finding_id=finding_id,
            project_id=run.project_id,
            scene_id=scene_id,
            shot_id=shot_id,
            code=normalized_code,
            message=normalized_message,
            source=source,
            recommended_action=action,
            patch_intent=normalized_patch,
        )

    def _structural_findings(self, run: GenerationRun) -> tuple[ErrorMapEntry, ...]:
        findings: list[ErrorMapEntry] = []
        timeline_selected = {item.shot_id: item.asset_id for item in run.video_project.timeline}
        prior_asset_ids: set[str] = set()
        previous_asset_id: str | None = None

        for record in run.records:
            selected = timeline_selected.get(record.shot_id)
            if selected != record.asset_id:
                findings.append(
                    self._entry(
                        run=run,
                        shot_id=record.shot_id,
                        code="lineage.selected_asset",
                        message="selected timeline asset does not match generation record",
                        source="structural",
                        patch_intent="restore the selected asset lineage for this shot only",
                        suggested_action="patch",
                        local_repair_sufficient=True,
                    )
                )

            invalid_refs = tuple(
                ref for ref in record.reference_asset_ids if ref not in prior_asset_ids
            )
            if invalid_refs:
                findings.append(
                    self._entry(
                        run=run,
                        shot_id=record.shot_id,
                        code="continuity.reference",
                        message="reference lineage includes an asset not produced by an earlier shot",
                        source="structural",
                        patch_intent="repair reference continuity for this shot only",
                        suggested_action="patch",
                        local_repair_sufficient=True,
                    )
                )
            if record.operation == "reference" and previous_asset_id is not None:
                if previous_asset_id not in record.reference_asset_ids:
                    findings.append(
                        self._entry(
                            run=run,
                            shot_id=record.shot_id,
                            code="continuity.previous_asset",
                            message="reference generation omitted the immediately previous accepted asset",
                            source="structural",
                            patch_intent="restore adjacency continuity without regenerating accepted shots",
                            suggested_action="patch",
                            local_repair_sufficient=True,
                        )
                    )

            prior_asset_ids.add(record.asset_id)
            previous_asset_id = record.asset_id

        return tuple(findings)

    def inspect(
        self,
        *,
        owner_id: str,
        run: GenerationRun,
        observations: tuple[QAObservation, ...] = (),
    ) -> QASession:
        owner = self._required(owner_id, "owner_id")
        if not isinstance(run, GenerationRun):
            raise TypeError("run must be GenerationRun")
        if run.owner_id != owner:
            raise PermissionError("cross-owner generation run QA denied")

        entries = list(self._structural_findings(run))
        for observation in observations:
            if not isinstance(observation, QAObservation):
                raise TypeError("observations must be QAObservation values")
            self._timeline_item(run.video_project, observation.shot_id)
            entries.append(
                self._entry(
                    run=run,
                    shot_id=observation.shot_id,
                    code=observation.code,
                    message=observation.message,
                    source="mock-observation",
                    patch_intent=observation.patch_intent,
                    suggested_action=observation.suggested_action,
                    local_repair_sufficient=observation.local_repair_sufficient,
                )
            )

        deduped: dict[str, ErrorMapEntry] = {}
        for entry in entries:
            deduped[entry.finding_id] = entry
        error_map = tuple(deduped[key] for key in sorted(deduped))
        project = run.video_project
        failing_shots = {item.shot_id for item in error_map}

        for entry in error_map:
            if not any(item.finding_id == entry.finding_id for item in project.qa_findings):
                project = add_qa_finding(
                    project,
                    QAFinding(
                        finding_id=entry.finding_id,
                        shot_id=entry.shot_id,
                        status="fail",
                        code=entry.code,
                        message=entry.message,
                        patch_intent=entry.patch_intent,
                    ),
                )

        # Structural QA can quality-lock shots for which no finding exists. A
        # supplied mock observation is explicit evidence of failure, so that shot
        # intentionally remains unlocked for selective repair.
        for item in project.timeline:
            if item.shot_id not in failing_shots and item.lock_state != "locked":
                project = set_quality_lock(project, item.shot_id, True)

        observation_signature = ";".join(
            f"{item.shot_id}:{item.code}:{item.message}" for item in observations
        )
        session_id = self._stable_id(
            "qa-",
            owner,
            run.project_id,
            observation_signature,
            ",".join(item.finding_id for item in error_map),
        )
        sources = ("deterministic-structural",)
        if observations:
            sources += ("explicit-mock-observation",)
        session = QASession(
            session_id=session_id,
            owner_id=owner,
            project_id=run.project_id,
            project=project,
            error_map=error_map,
            qa_sources=sources,
            visual_inspection_performed=False,
        )
        self._sessions[session_id] = session
        return session

    def get(self, *, owner_id: str, session_id: str) -> QASession:
        owner = self._required(owner_id, "owner_id")
        session = self._sessions.get(self._required(session_id, "session_id"))
        if session is None:
            raise KeyError(session_id)
        if session.owner_id != owner:
            raise PermissionError("cross-owner QA session access denied")
        return session

    @staticmethod
    def _finding(session: QASession, finding_id: str) -> ErrorMapEntry:
        finding = next(
            (item for item in session.error_map if item.finding_id == finding_id),
            None,
        )
        if finding is None:
            raise KeyError(finding_id)
        if finding.status != "open":
            raise ValueError("QA finding is already resolved")
        return finding

    @staticmethod
    def _previous_selected_asset(project: VideoProject, shot_id: str) -> str | None:
        previous: str | None = None
        for item in project.timeline:
            if item.shot_id == shot_id:
                return previous
            previous = item.asset_id
        raise ValueError("unknown shot")

    @staticmethod
    def _next_asset_version(project: VideoProject, shot_id: str) -> int:
        versions = [asset.version for asset in project.assets if asset.shot_id == shot_id]
        return max(versions, default=0) + 1

    @staticmethod
    def _route_context(
        *,
        session: QASession,
        finding: ErrorMapEntry,
        action: RepairAction,
        budget_usd: str,
    ) -> RoutingContext:
        item = IntelligenceQA._timeline_item(session.project, finding.shot_id)
        duration = item.end_sec - item.start_sec
        if action == "patch":
            patch_intent = finding.patch_intent or finding.message
            return RoutingContext(
                owner_id=session.owner_id,
                project_id=session.project_id,
                shot_id=finding.shot_id,
                duration_sec=duration,
                budget_usd=budget_usd,
                patch_intent=patch_intent,
            )
        if action == "continue":
            if item.asset_id is None:
                raise ValueError("CONTINUE requires a selected asset")
            return RoutingContext(
                owner_id=session.owner_id,
                project_id=session.project_id,
                shot_id=finding.shot_id,
                duration_sec=duration,
                budget_usd=budget_usd,
                continue_asset_id=item.asset_id,
            )
        if action == "reference":
            reference_id = IntelligenceQA._previous_selected_asset(
                session.project, finding.shot_id
            )
            if reference_id is None:
                raise ValueError("REFERENCE requires an earlier selected asset")
            return RoutingContext(
                owner_id=session.owner_id,
                project_id=session.project_id,
                shot_id=finding.shot_id,
                duration_sec=duration,
                budget_usd=budget_usd,
                reference_asset_ids=(reference_id,),
            )
        if action == "regenerate":
            return RoutingContext(
                owner_id=session.owner_id,
                project_id=session.project_id,
                shot_id=finding.shot_id,
                duration_sec=duration,
                budget_usd=budget_usd,
            )
        raise ValueError("unsupported repair action")

    def repair(
        self,
        *,
        owner_id: str,
        session_id: str,
        finding_id: str,
        action: RepairAction | None = None,
        budget_usd: str = "5.00",
        causal_change: str | None = None,
        simulated_failure: tuple[str, str] | None = None,
    ) -> RepairRecord:
        session = self.get(owner_id=owner_id, session_id=session_id)
        finding = self._finding(session, finding_id)
        requested = action or finding.recommended_action
        if requested not in self._ACTIONS:
            raise ValueError("unsupported repair action")

        item = self._timeline_item(session.project, finding.shot_id)
        if item.lock_state == "locked":
            raise ValueError("quality-locked shot cannot be selectively repaired")

        context = self._route_context(
            session=session,
            finding=finding,
            action=requested,
            budget_usd=budget_usd,
        )
        decision = self._router.route(context)
        expected_operation = {
            "patch": "patch",
            "continue": "continue",
            "reference": "reference",
            "regenerate": "generate",
        }[requested]
        if decision.operation != expected_operation:
            raise RuntimeError("router changed requested repair semantics")

        idempotency_key = (
            f"qa-repair:{session.project_id}:{finding.finding_id}:{requested}"
        )
        job = self._production.submit(
            owner_id=session.owner_id,
            project_id=session.project_id,
            shot_id=finding.shot_id,
            operation=decision.operation,
            idempotency_key=idempotency_key,
        )

        if job.state == "blocked":
            record = RepairRecord(
                finding_id=finding.finding_id,
                requested_action=requested,
                routed_operation=decision.operation,
                job_id=job.job_id,
                provider_id=decision.provider_id,
                state="blocked",
                prior_asset_id=item.asset_id,
                output_asset_id=None,
                estimated_cost_usd=decision.estimated_cost_usd,
                causal_change=causal_change,
            )
            return record
        if job.state == "succeeded":
            existing = next(
                (
                    record
                    for record in reversed(session.repairs)
                    if record.job_id == job.job_id and record.state == "succeeded"
                ),
                None,
            )
            if existing is None:
                raise RuntimeError("succeeded repair job has no session repair record")
            return existing

        running = self._production.claim_next()
        if running is None or running.job_id != job.job_id:
            raise RuntimeError(
                "Intelligence/QA mock repair requires exclusive sequential queue access"
            )

        normalized_change = (
            causal_change.strip() if isinstance(causal_change, str) else None
        )
        normalized_change = normalized_change or None
        if simulated_failure is not None:
            error_code, message = simulated_failure
            failed = self._production.fail(
                owner_id=session.owner_id,
                job_id=job.job_id,
                error_code=error_code,
                message=message,
                causal_change=normalized_change,
                retryable=True,
            )
            record = RepairRecord(
                finding_id=finding.finding_id,
                requested_action=requested,
                routed_operation=decision.operation,
                job_id=job.job_id,
                provider_id=decision.provider_id,
                state=failed.state,
                prior_asset_id=item.asset_id,
                output_asset_id=None,
                estimated_cost_usd=decision.estimated_cost_usd,
                causal_change=normalized_change,
            )
            self._sessions[session.session_id] = replace(
                session, repairs=session.repairs + (record,)
            )
            return record

        output = self._router.invoke_mock(decision, context)
        if output.get("mock") is not True:
            raise RuntimeError("selective repair received a non-mock provider result")
        provider_asset_id = str(output["asset_id"])
        asset_id = self._stable_id(
            "repair-asset-",
            provider_asset_id,
            finding.finding_id,
            str(running.attempt_count),
        )
        done = self._production.complete(
            owner_id=session.owner_id,
            job_id=job.job_id,
            output_asset_id=asset_id,
        )
        if done.state != "succeeded":
            raise RuntimeError("repair job did not complete")

        asset = AssetRecord(
            asset_id=asset_id,
            shot_id=finding.shot_id,
            kind="video",
            uri=f"mock://{session.owner_id}/{session.project_id}/{asset_id}",
            source=f"{decision.provider_id}:{decision.operation}",
            source_ref=job.job_id,
            version=self._next_asset_version(session.project, finding.shot_id),
            cost_usd=decision.estimated_cost_usd,
        )
        project = attach_asset(session.project, asset)
        project = select_asset(project, finding.shot_id, asset_id)
        record = RepairRecord(
            finding_id=finding.finding_id,
            requested_action=requested,
            routed_operation=decision.operation,
            job_id=job.job_id,
            provider_id=decision.provider_id,
            state="succeeded",
            prior_asset_id=item.asset_id,
            output_asset_id=asset_id,
            estimated_cost_usd=decision.estimated_cost_usd,
            causal_change=normalized_change,
        )
        self._sessions[session.session_id] = replace(
            session,
            project=project,
            repairs=session.repairs + (record,),
        )
        return record

    def verify(
        self,
        *,
        owner_id: str,
        session_id: str,
        finding_id: str,
        passed: bool,
        note: str = "deterministic mock verification",
    ) -> QASession:
        session = self.get(owner_id=owner_id, session_id=session_id)
        finding = self._finding(session, finding_id)
        successful = next(
            (
                item
                for item in reversed(session.repairs)
                if item.finding_id == finding_id and item.state == "succeeded"
            ),
            None,
        )
        if successful is None:
            raise ValueError("finding has no successful selective repair to verify")

        normalized_note = self._required(note, "note")
        project = session.project
        if not passed:
            verify_id = self._stable_id(
                "verify-",
                finding_id,
                successful.output_asset_id or "",
                "fail",
                normalized_note,
            )
            project = add_qa_finding(
                project,
                QAFinding(
                    finding_id=verify_id,
                    shot_id=finding.shot_id,
                    status="fail",
                    code=f"verify.{finding.code}",
                    message=normalized_note,
                    patch_intent=finding.patch_intent,
                ),
            )
            updated = replace(session, project=project)
            self._sessions[session.session_id] = updated
            return updated

        verify_id = self._stable_id(
            "verify-",
            finding_id,
            successful.output_asset_id or "",
            "pass",
            normalized_note,
        )
        project = add_qa_finding(
            project,
            QAFinding(
                finding_id=verify_id,
                shot_id=finding.shot_id,
                status="pass",
                code=f"verify.{finding.code}",
                message=normalized_note,
            ),
        )
        project = set_quality_lock(project, finding.shot_id, True)
        error_map = tuple(
            replace(item, status="resolved")
            if item.finding_id == finding_id
            else item
            for item in session.error_map
        )
        updated = replace(session, project=project, error_map=error_map)
        self._sessions[session.session_id] = updated
        return updated
