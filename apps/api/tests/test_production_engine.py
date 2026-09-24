from __future__ import annotations

import pytest

from src.adapters.queue import MemoryJobQueue
from src.adapters.workflow import MemoryWorkflowEngine
from src.modules.production_engine import ProductionEngine


def engine():
    queue = MemoryJobQueue()
    workflows = MemoryWorkflowEngine()
    return ProductionEngine(queue, workflows), queue, workflows


def submit(production, *, owner="owner-a", key="idem-1", max_attempts=3):
    return production.submit(
        owner_id=owner,
        project_id="project-1",
        shot_id="shot-1",
        operation="generate",
        idempotency_key=key,
        max_attempts=max_attempts,
    )


def test_submission_is_owner_scoped_and_idempotent():
    production, queue, _ = engine()
    first = submit(production)
    second = submit(production)
    assert second == first
    assert production.get(owner_id="owner-a", job_id=first.job_id) == first
    with pytest.raises(PermissionError, match="cross-owner"):
        production.get(owner_id="owner-b", job_id=first.job_id)

    delivery = queue.dequeue()
    assert delivery is not None
    assert delivery["production_job_id"] == first.job_id
    assert queue.dequeue() is None


def test_idempotency_key_rejects_payload_collision():
    production, _, _ = engine()
    submit(production)
    with pytest.raises(ValueError, match="different request"):
        production.submit(
            owner_id="owner-a",
            project_id="project-1",
            shot_id="shot-other",
            operation="generate",
            idempotency_key="idem-1",
        )


def test_queue_and_workflow_mocks_drive_successful_lifecycle():
    production, _, _ = engine()
    job = submit(production)
    workflow = production.workflow_status(owner_id="owner-a", job_id=job.job_id)
    assert workflow["workflow"] == "production-job"
    assert workflow["payload"]["production_job_id"] == job.job_id

    running = production.claim_next()
    assert running is not None
    assert running.state == "running"
    assert running.attempt_count == 1

    done = production.complete(
        owner_id="owner-a",
        job_id=running.job_id,
        output_asset_id="asset-accepted",
    )
    assert done.state == "succeeded"
    assert done.output_asset_id == "asset-accepted"
    assert production.claim_next() is None


def test_cross_owner_mutation_is_denied():
    production, _, _ = engine()
    job = submit(production)
    running = production.claim_next()
    assert running is not None
    with pytest.raises(PermissionError, match="cross-owner"):
        production.complete(
            owner_id="owner-b",
            job_id=job.job_id,
            output_asset_id="asset-stolen",
        )
    with pytest.raises(PermissionError, match="cross-owner"):
        production.fail(
            owner_id="owner-b",
            job_id=job.job_id,
            error_code="denied",
            message="cross owner",
        )


def test_failure_memory_blocks_equivalent_repeated_failure():
    production, _, _ = engine()
    job = submit(production)
    running = production.claim_next()
    assert running is not None

    retry = production.fail(
        owner_id="owner-a",
        job_id=job.job_id,
        error_code="TEMPORARY_TIMEOUT",
        message=" Mock timeout   while generating ",
        causal_change="baseline mock response",
    )
    assert retry.state == "retryable"
    assert len(retry.failure_memory) == 1

    running_again = production.claim_next()
    assert running_again is not None
    blocked = production.fail(
        owner_id="owner-a",
        job_id=job.job_id,
        error_code="temporary_timeout",
        message="mock timeout while generating",
        causal_change="baseline mock response",
    )
    assert blocked.state == "blocked"
    assert len(blocked.failure_memory) == 2
    assert blocked.failure_memory[0].fingerprint == blocked.failure_memory[1].fingerprint
    assert production.claim_next() is None


def test_material_causal_change_allows_retry_until_success():
    production, _, _ = engine()
    job = submit(production)
    assert production.claim_next() is not None

    first_retry = production.fail(
        owner_id="owner-a",
        job_id=job.job_id,
        error_code="decode",
        message="asset decode failed",
        causal_change="baseline parser",
    )
    assert first_retry.state == "retryable"

    assert production.claim_next() is not None
    second_retry = production.fail(
        owner_id="owner-a",
        job_id=job.job_id,
        error_code="decode",
        message="asset decode failed",
        causal_change="validated parser v2",
    )
    assert second_retry.state == "retryable"

    third = production.claim_next()
    assert third is not None
    done = production.complete(
        owner_id="owner-a",
        job_id=job.job_id,
        output_asset_id="asset-v2",
    )
    assert done.state == "succeeded"
    assert done.attempt_count == 3


def test_retry_budget_ends_in_failed_terminal_state():
    production, _, _ = engine()
    job = submit(production, max_attempts=2)
    assert production.claim_next() is not None
    retry = production.fail(
        owner_id="owner-a",
        job_id=job.job_id,
        error_code="network",
        message="first failure",
    )
    assert retry.state == "retryable"
    assert production.claim_next() is not None
    failed = production.fail(
        owner_id="owner-a",
        job_id=job.job_id,
        error_code="network-2",
        message="second distinct failure",
    )
    assert failed.state == "failed"
    assert production.claim_next() is None


def test_recovery_requeues_only_interrupted_inflight_work():
    production, _, _ = engine()
    job = submit(production)
    running = production.claim_next()
    assert running is not None
    assert running.attempt_count == 1

    recovered = production.recover_inflight()
    assert len(recovered) == 1
    assert recovered[0].job_id == job.job_id
    assert recovered[0].state == "retryable"
    assert recovered[0].attempt_count == 0
    assert recovered[0].recovery_count == 1

    reclaimed = production.claim_next()
    assert reclaimed is not None
    assert reclaimed.attempt_count == 1
    done = production.complete(
        owner_id="owner-a",
        job_id=job.job_id,
        output_asset_id="asset-after-recovery",
    )
    assert done.state == "succeeded"
    assert production.recover_inflight() == ()
    assert production.claim_next() is None


def test_owner_listing_is_partitioned():
    production, _, _ = engine()
    a = submit(production, owner="owner-a", key="a")
    b = submit(production, owner="owner-b", key="b")
    assert production.list_owner(owner_id="owner-a") == (a,)
    assert production.list_owner(owner_id="owner-b") == (b,)
