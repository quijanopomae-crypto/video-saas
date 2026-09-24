from __future__ import annotations

from dataclasses import replace

import pytest

from src.adapters.queue import MemoryJobQueue
from src.adapters.workflow import MemoryWorkflowEngine
from src.modules.generation_pipeline import GenerationPipeline, GenerationRun
from src.modules.intelligence_qa import IntelligenceQA, QAObservation
from src.modules.model_router import (
    MockProviderAdapter,
    MultimodelRouter,
    ProviderCapabilities,
)
from src.modules.planning import ProjectRequest
from src.modules.production_engine import ProductionEngine
from src.modules.video_project import set_quality_lock


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
                provider_id="SORA_2",
                operations=("generate", "continue", "reference", "patch", "premium"),
                cost_per_second_usd="0.0001",
                quality_tier="draft",
                max_duration_sec=600,
            )
        ),
    )


def request():
    return ProjectRequest.from_dict(
        {
            "title": "Intelligence QA",
            "idea": "Validar continuidad y reparar solo la toma defectuosa",
            "duration_sec": 20,
        }
    )


def generated(owner="owner-a"):
    router = MultimodelRouter(providers())
    generation_engine = ProductionEngine(MemoryJobQueue(), MemoryWorkflowEngine())
    run = GenerationPipeline(router, generation_engine).run(
        owner_id=owner, request=request()
    )
    qa_engine = ProductionEngine(MemoryJobQueue(), MemoryWorkflowEngine())
    qa = IntelligenceQA(router, qa_engine)
    return run, qa, qa_engine


def observation(run, *, shot_index=1, action=None):
    shot_id = run.records[shot_index].shot_id
    return QAObservation(
        shot_id=shot_id,
        code="continuity.subject",
        message="explicit mock observation: subject identity drift",
        patch_intent="repair subject identity in this shot only",
        suggested_action=action,
    )


def test_structural_checks_detect_reference_and_selected_asset_lineage_breaks():
    run, qa, _ = generated()
    first = replace(run.records[0], asset_id="asset-not-selected")
    second = replace(run.records[1], reference_asset_ids=("future-or-alien",))
    broken = GenerationRun(
        owner_id=run.owner_id,
        project_id=run.project_id,
        product_flow=run.product_flow,
        video_project=run.video_project,
        records=(first, second, *run.records[2:]),
    )

    session = qa.inspect(owner_id="owner-a", run=broken)
    codes = {item.code for item in session.error_map}
    assert "lineage.selected_asset" in codes
    assert "continuity.reference" in codes
    assert session.visual_inspection_performed is False
    assert session.qa_sources == ("deterministic-structural",)


def test_explicit_mock_observation_creates_error_map_and_defaults_to_patch():
    run, qa, _ = generated()
    obs = observation(run)
    session = qa.inspect(owner_id="owner-a", run=run, observations=(obs,))

    finding = next(item for item in session.error_map if item.code == obs.code)
    assert finding.source == "mock-observation"
    assert finding.recommended_action == "patch"
    assert finding.patch_intent == obs.patch_intent
    assert "explicit-mock-observation" in session.qa_sources
    assert any(
        item.finding_id == finding.finding_id and item.status == "fail"
        for item in session.project.qa_findings
    )


@pytest.mark.parametrize(
    ("action", "expected_operation"),
    [
        ("patch", "patch"),
        ("continue", "continue"),
        ("reference", "reference"),
        ("regenerate", "generate"),
    ],
)
def test_repair_actions_preserve_requested_semantics(action, expected_operation):
    run, qa, _ = generated()
    obs = observation(run, action=action)
    session = qa.inspect(owner_id="owner-a", run=run, observations=(obs,))
    finding = next(item for item in session.error_map if item.code == obs.code)

    record = qa.repair(
        owner_id="owner-a",
        session_id=session.session_id,
        finding_id=finding.finding_id,
        action=action,
    )
    assert record.state == "succeeded"
    assert record.requested_action == action
    assert record.routed_operation == expected_operation
    assert record.provider_id != "SORA_2"


def test_selective_patch_changes_only_failing_shot_and_preserves_accepted_locks():
    run, qa, _ = generated()
    obs = observation(run)
    session = qa.inspect(owner_id="owner-a", run=run, observations=(obs,))
    finding = next(item for item in session.error_map if item.code == obs.code)

    before = {item.shot_id: item.asset_id for item in session.project.timeline}
    failed_shot = finding.shot_id
    assert all(
        item.lock_state == ("unlocked" if item.shot_id == failed_shot else "locked")
        for item in session.project.timeline
    )

    record = qa.repair(
        owner_id="owner-a",
        session_id=session.session_id,
        finding_id=finding.finding_id,
    )
    repaired = qa.get(owner_id="owner-a", session_id=session.session_id)
    after = {item.shot_id: item.asset_id for item in repaired.project.timeline}

    assert record.requested_action == "patch"
    assert after[failed_shot] != before[failed_shot]
    assert {
        shot_id: asset_id for shot_id, asset_id in after.items() if shot_id != failed_shot
    } == {
        shot_id: asset_id
        for shot_id, asset_id in before.items()
        if shot_id != failed_shot
    }


def test_successful_verification_resolves_error_and_quality_locks_repaired_shot():
    run, qa, _ = generated()
    obs = observation(run)
    session = qa.inspect(owner_id="owner-a", run=run, observations=(obs,))
    finding = next(item for item in session.error_map if item.code == obs.code)
    qa.repair(
        owner_id="owner-a",
        session_id=session.session_id,
        finding_id=finding.finding_id,
    )

    verified = qa.verify(
        owner_id="owner-a",
        session_id=session.session_id,
        finding_id=finding.finding_id,
        passed=True,
    )
    resolved = next(
        item for item in verified.error_map if item.finding_id == finding.finding_id
    )
    timeline = next(
        item for item in verified.project.timeline if item.shot_id == finding.shot_id
    )
    assert resolved.status == "resolved"
    assert timeline.lock_state == "locked"
    assert any(
        item.status == "pass" and item.shot_id == finding.shot_id
        for item in verified.project.qa_findings
    )


def test_quality_lock_prevents_selective_repair_before_provider_work():
    run, qa, production = generated()
    obs = observation(run)
    locked_project = set_quality_lock(run.video_project, obs.shot_id, True)
    locked_run = replace(run, video_project=locked_project)
    session = qa.inspect(owner_id="owner-a", run=locked_run, observations=(obs,))
    finding = next(item for item in session.error_map if item.code == obs.code)

    with pytest.raises(ValueError, match="quality-locked"):
        qa.repair(
            owner_id="owner-a",
            session_id=session.session_id,
            finding_id=finding.finding_id,
        )
    assert production.list_owner(owner_id="owner-a") == ()


def test_equivalent_repair_failure_is_blocked_by_canonical_failure_memory():
    run, qa, production = generated()
    obs = observation(run)
    session = qa.inspect(owner_id="owner-a", run=run, observations=(obs,))
    finding = next(item for item in session.error_map if item.code == obs.code)

    first = qa.repair(
        owner_id="owner-a",
        session_id=session.session_id,
        finding_id=finding.finding_id,
        causal_change="baseline patch prompt",
        simulated_failure=("mock_timeout", "provider mock timeout"),
    )
    second = qa.repair(
        owner_id="owner-a",
        session_id=session.session_id,
        finding_id=finding.finding_id,
        causal_change="baseline patch prompt",
        simulated_failure=("mock_timeout", "provider mock timeout"),
    )

    assert first.state == "retryable"
    assert second.state == "blocked"
    job = production.get(owner_id="owner-a", job_id=first.job_id)
    assert job.state == "blocked"
    assert len(job.failure_memory) == 2
    assert job.failure_memory[0].fingerprint == job.failure_memory[1].fingerprint


def test_material_causal_change_can_retry_then_succeed():
    run, qa, production = generated()
    obs = observation(run)
    session = qa.inspect(owner_id="owner-a", run=run, observations=(obs,))
    finding = next(item for item in session.error_map if item.code == obs.code)

    first = qa.repair(
        owner_id="owner-a",
        session_id=session.session_id,
        finding_id=finding.finding_id,
        causal_change="baseline patch prompt",
        simulated_failure=("mock_decode", "mock repair decode failure"),
    )
    second = qa.repair(
        owner_id="owner-a",
        session_id=session.session_id,
        finding_id=finding.finding_id,
        causal_change="validated patch framing v2",
        simulated_failure=("mock_decode", "mock repair decode failure"),
    )
    third = qa.repair(
        owner_id="owner-a",
        session_id=session.session_id,
        finding_id=finding.finding_id,
        causal_change="validated patch framing v2",
    )

    assert first.state == "retryable"
    assert second.state == "retryable"
    assert third.state == "succeeded"
    job = production.get(owner_id="owner-a", job_id=third.job_id)
    assert job.state == "succeeded"
    assert job.attempt_count == 3


def test_cross_owner_session_reads_and_mutations_are_denied():
    run, qa, _ = generated()
    obs = observation(run)
    session = qa.inspect(owner_id="owner-a", run=run, observations=(obs,))
    finding = next(item for item in session.error_map if item.code == obs.code)

    with pytest.raises(PermissionError, match="cross-owner"):
        qa.get(owner_id="owner-b", session_id=session.session_id)
    with pytest.raises(PermissionError, match="cross-owner"):
        qa.repair(
            owner_id="owner-b",
            session_id=session.session_id,
            finding_id=finding.finding_id,
        )
