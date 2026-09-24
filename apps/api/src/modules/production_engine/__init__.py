from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from ...adapters.queue import JobQueue
from ...adapters.workflow import WorkflowEngine


JobState = Literal["queued", "running", "retryable", "succeeded", "failed", "blocked"]


@dataclass(frozen=True)
class FailureRecord:
    fingerprint: str
    error_code: str
    message: str
    causal_change: str | None
    attempt_number: int


@dataclass(frozen=True)
class ProductionJob:
    job_id: str
    owner_id: str
    project_id: str
    shot_id: str
    operation: str
    idempotency_key: str
    state: JobState
    attempt_count: int = 0
    max_attempts: int = 3
    recovery_count: int = 0
    queue_delivery_ids: tuple[str, ...] = ()
    workflow_run_id: str | None = None
    output_asset_id: str | None = None
    failure_memory: tuple[FailureRecord, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProductionEngine:
    """Deterministic provider-independent production job lifecycle.

    The engine owns logical job state. Queue and workflow adapters only provide
    delivery/orchestration boundaries so the same invariants survive a later
    Cloudflare-backed implementation.
    """

    def __init__(self, queue: JobQueue, workflows: WorkflowEngine) -> None:
        self._queue = queue
        self._workflows = workflows
        self._jobs: dict[str, ProductionJob] = {}
        self._idempotency: dict[tuple[str, str], str] = {}

    @staticmethod
    def _required(value: str, name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{name} is required")
        return normalized

    @staticmethod
    def _job_id(owner_id: str, idempotency_key: str) -> str:
        material = f"{owner_id}|{idempotency_key}".encode("utf-8")
        return "job-" + hashlib.sha256(material).hexdigest()[:16]

    @staticmethod
    def _failure_fingerprint(job: ProductionJob, error_code: str, message: str) -> str:
        normalized_message = " ".join(message.strip().lower().split())
        material = "|".join(
            [job.operation, job.shot_id, error_code.strip().lower(), normalized_message]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def _owned(self, owner_id: str, job_id: str) -> ProductionJob:
        owner = self._required(owner_id, "owner_id")
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(job_id)
        if job.owner_id != owner:
            raise PermissionError("cross-owner production job access denied")
        return job

    def _store(self, job: ProductionJob) -> ProductionJob:
        self._jobs[job.job_id] = job
        return job

    def _enqueue(self, job: ProductionJob) -> ProductionJob:
        delivery_id = self._queue.enqueue(
            {
                "production_job_id": job.job_id,
                "owner_id": job.owner_id,
                "project_id": job.project_id,
                "shot_id": job.shot_id,
                "operation": job.operation,
            }
        )
        return self._store(
            replace(job, queue_delivery_ids=job.queue_delivery_ids + (delivery_id,))
        )

    def submit(
        self,
        *,
        owner_id: str,
        project_id: str,
        shot_id: str,
        operation: str,
        idempotency_key: str,
        max_attempts: int = 3,
    ) -> ProductionJob:
        owner = self._required(owner_id, "owner_id")
        project = self._required(project_id, "project_id")
        shot = self._required(shot_id, "shot_id")
        op = self._required(operation, "operation")
        key = self._required(idempotency_key, "idempotency_key")
        if type(max_attempts) is not int or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")

        existing_id = self._idempotency.get((owner, key))
        if existing_id is not None:
            existing = self._jobs[existing_id]
            requested = (project, shot, op, max_attempts)
            original = (
                existing.project_id,
                existing.shot_id,
                existing.operation,
                existing.max_attempts,
            )
            if requested != original:
                raise ValueError("idempotency key already belongs to a different request")
            return existing

        job_id = self._job_id(owner, key)
        workflow_run_id = self._workflows.start(
            "production-job",
            {
                "production_job_id": job_id,
                "owner_id": owner,
                "project_id": project,
                "shot_id": shot,
                "operation": op,
            },
        )
        job = ProductionJob(
            job_id=job_id,
            owner_id=owner,
            project_id=project,
            shot_id=shot,
            operation=op,
            idempotency_key=key,
            state="queued",
            max_attempts=max_attempts,
            workflow_run_id=workflow_run_id,
        )
        self._idempotency[(owner, key)] = job_id
        return self._enqueue(job)

    def get(self, *, owner_id: str, job_id: str) -> ProductionJob:
        return self._owned(owner_id, job_id)

    def list_owner(self, *, owner_id: str) -> tuple[ProductionJob, ...]:
        owner = self._required(owner_id, "owner_id")
        return tuple(
            sorted(
                (job for job in self._jobs.values() if job.owner_id == owner),
                key=lambda item: item.job_id,
            )
        )

    def claim_next(self) -> ProductionJob | None:
        while True:
            delivery = self._queue.dequeue()
            if delivery is None:
                return None
            job_id = str(delivery.get("production_job_id", ""))
            job = self._jobs.get(job_id)
            if job is None or job.state not in {"queued", "retryable"}:
                continue
            if job.attempt_count >= job.max_attempts:
                return self._store(replace(job, state="failed"))
            return self._store(
                replace(job, state="running", attempt_count=job.attempt_count + 1)
            )

    def complete(
        self, *, owner_id: str, job_id: str, output_asset_id: str
    ) -> ProductionJob:
        job = self._owned(owner_id, job_id)
        asset_id = self._required(output_asset_id, "output_asset_id")
        if job.state != "running":
            raise ValueError("only a running job can complete")
        return self._store(
            replace(job, state="succeeded", output_asset_id=asset_id)
        )

    def fail(
        self,
        *,
        owner_id: str,
        job_id: str,
        error_code: str,
        message: str,
        causal_change: str | None = None,
        retryable: bool = True,
    ) -> ProductionJob:
        job = self._owned(owner_id, job_id)
        if job.state != "running":
            raise ValueError("only a running job can fail")
        code = self._required(error_code, "error_code")
        detail = self._required(message, "message")
        change = causal_change.strip() if isinstance(causal_change, str) else None
        change = change or None
        fingerprint = self._failure_fingerprint(job, code, detail)
        previous = next(
            (
                item
                for item in reversed(job.failure_memory)
                if item.fingerprint == fingerprint
            ),
            None,
        )
        record = FailureRecord(
            fingerprint=fingerprint,
            error_code=code,
            message=detail,
            causal_change=change,
            attempt_number=job.attempt_count,
        )
        memory = job.failure_memory + (record,)

        equivalent_repeat = previous is not None and (
            change is None or change == previous.causal_change
        )
        if equivalent_repeat:
            return self._store(
                replace(job, state="blocked", failure_memory=memory)
            )
        if not retryable or job.attempt_count >= job.max_attempts:
            return self._store(
                replace(job, state="failed", failure_memory=memory)
            )

        retry_job = self._store(
            replace(job, state="retryable", failure_memory=memory)
        )
        return self._enqueue(retry_job)

    def recover_inflight(self) -> tuple[ProductionJob, ...]:
        recovered: list[ProductionJob] = []
        for job in tuple(self._jobs.values()):
            if job.state != "running":
                continue
            # A process interruption does not consume a logical attempt because
            # no outcome was recorded. Reclaiming restores the same attempt budget.
            restored_attempts = max(0, job.attempt_count - 1)
            recovered_job = self._store(
                replace(
                    job,
                    state="retryable",
                    attempt_count=restored_attempts,
                    recovery_count=job.recovery_count + 1,
                )
            )
            recovered.append(self._enqueue(recovered_job))
        return tuple(recovered)

    def workflow_status(self, *, owner_id: str, job_id: str) -> dict[str, Any]:
        job = self._owned(owner_id, job_id)
        if job.workflow_run_id is None:
            raise ValueError("job has no workflow run")
        return self._workflows.status(job.workflow_run_id)
