"""Async job queue with worker pool for the Generator → Validator → Normalizer → Commit pipeline."""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict

from .config import AppConfig
from .interfaces import TextGenerator, Validator, ValidationResult


class JobType(Enum):
    """Types of pipeline jobs."""

    GENERATE_BIBLE = "generate_bible"
    GENERATE_STYLE_BIBLE = "generate_style_bible"
    GENERATE_OUTLINE = "generate_outline"
    GENERATE_CHAPTER = "generate_chapter"
    CONSISTENCY_CHECK = "consistency_check"
    EXTRACT_DECISION_POINTS = "extract_decision_points"
    BUILD_GRAPH_SKELETON = "build_graph_skeleton"
    GENERATE_NODE = "generate_node"
    GENERATE_IMAGE = "generate_image"
    GENERATE_MUSIC = "generate_music"
    BUILD_GM_INDEX = "build_gm_index"
    PACKAGE = "package"


class FailurePolicy(Enum):
    """What to do when a job fails after max retries."""

    ABORT = "abort"  # Stop entire pipeline (default for sequential phases)
    QUARANTINE = "quarantine"  # Skip failed job, continue with placeholder


class JobStatus(Enum):
    """Current state of a job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    QUARANTINED = "quarantined"


@dataclass
class PipelineContext:
    """Context passed through every pipeline step. Accumulates outputs and state."""

    run_id: str
    seed: int
    config: AppConfig | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    feedback: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)

    def add_feedback(self, errors: list[str]) -> None:
        """Accumulate validation errors for retry feedback."""
        self.feedback.extend(errors)

    def clear_feedback(self) -> None:
        """Clear feedback after a successful generation."""
        self.feedback.clear()


@dataclass
class Job:
    """A unit of work in the pipeline."""

    job_id: str
    job_type: JobType
    prompt: str
    seed: int
    generator: Any = None  # TextGenerator | ImageGenerator | MusicGenerator
    validator: Any = None  # Validator
    schema: dict[str, Any] | None = None
    context: PipelineContext | None = None
    max_retries: int = 3
    failure_policy: FailurePolicy = FailurePolicy.ABORT
    dependencies: list[str] = field(default_factory=list)

    # Set by the queue
    status: JobStatus = JobStatus.PENDING
    attempts: int = 0
    result: Any = None
    errors: list[str] = field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def duration_seconds(self) -> float:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return 0.0


@dataclass
class JobResult:
    """Result of a completed (or failed) job."""

    job_id: str
    status: JobStatus
    output: Any = None
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class JobQueue:
    """Async job queue with configurable worker pool.

    Workers process jobs through: Generator → Validator → Normalizer → Commit.
    Sequential phases enqueue jobs one at a time. Parallel phases enqueue
    multiple independent jobs (images, MIDI) that run concurrently.
    """

    def __init__(
        self,
        worker_count: int = 4,
        normalizer: Callable[[Dict[str, Any], str], Dict[str, Any]] | None = None,
        commit_callback: Callable[[str, Any], None] | None = None,
        event_log_path: str | None = None,
    ) -> None:
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.worker_count = worker_count
        self.normalizer = normalizer or self._default_normalizer
        self.commit_callback = commit_callback or self._default_commit
        self.results: dict[str, JobResult] = {}
        self.event_log_path = event_log_path

    async def enqueue(self, job: Job) -> None:
        """Add a job to the queue."""
        await self.queue.put(job)

    async def enqueue_sequential(self, jobs: list[Job]) -> None:
        """Enqueue jobs that must run sequentially (text generation)."""
        for job in jobs:
            await self.queue.put(job)

    async def enqueue_parallel(self, jobs: list[Job]) -> None:
        """Enqueue jobs that can run concurrently (images, MIDI)."""
        for job in jobs:
            await self.queue.put(job)

    async def drain(self) -> dict[str, JobResult]:
        """Process all jobs in the queue using the worker pool.

        Returns:
            Dict of job_id → JobResult for all completed/failed jobs.
        """
        workers = [
            asyncio.create_task(self._worker(i))
            for i in range(self.worker_count)
        ]
        await self.queue.join()

        # Stop workers
        for _ in workers:
            await self.queue.put(None)  # type: ignore[arg-type]

        await asyncio.gather(*workers, return_exceptions=True)
        return self.results

    async def _worker(self, worker_id: int) -> None:
        """Worker loop: dequeue job → Generator → Validator → Normalizer → Commit."""
        while True:
            job = await self.queue.get()
            if job is None:  # Poison pill
                self.queue.task_done()
                break

            job.status = JobStatus.RUNNING
            job.started_at = time.time()
            self._log_event("job_started", job.job_id, job.job_type.value)

            try:
                for attempt in range(1, job.max_retries + 2):
                    job.attempts = attempt
                    try:
                        # 1. Generate
                        output = await job.generator.generate(
                            prompt=job.prompt,
                            schema=job.schema,
                            seed=job.seed,
                        )

                        # 2. Validate (if validator is provided)
                        if job.validator is not None:
                            validation: ValidationResult = await job.validator.validate(
                                output,
                                {"schema": job.schema, "context": job.context},
                            )
                            if not validation.is_valid:
                                if attempt <= job.max_retries:
                                    self._log_event(
                                        "validation_failed",
                                        job.job_id,
                                        str(validation.errors),
                                    )
                                    # Inject error feedback into context for retry
                                    if job.context:
                                        job.context.add_feedback(validation.errors)
                                    continue
                                else:
                                    raise RuntimeError(
                                        f"Validation failed after {job.max_retries} retries: "
                                        f"{validation.errors}"
                                    )

                        # 3. Normalize
                        normalized = self.normalizer(output, job.job_type.value)

                        # 4. Commit
                        self.commit_callback(job.job_id, normalized)

                        job.status = JobStatus.COMPLETED
                        job.result = normalized
                        job.completed_at = time.time()
                        self.results[job.job_id] = JobResult(
                            job_id=job.job_id,
                            status=JobStatus.COMPLETED,
                            output=normalized,
                            duration_seconds=job.duration_seconds,
                        )
                        self._log_event(
                            "job_completed",
                            job.job_id,
                            f"duration={job.duration_seconds:.1f}s",
                        )
                        break

                    except Exception as e:
                        if attempt > job.max_retries:
                            raise
                        self._log_event("retry", job.job_id, f"attempt={attempt}")

            except Exception as e:
                job.completed_at = time.time()
                if job.failure_policy == FailurePolicy.QUARANTINE:
                    job.status = JobStatus.QUARANTINED
                    self.results[job.job_id] = JobResult(
                        job_id=job.job_id,
                        status=JobStatus.QUARANTINED,
                        errors=[str(e)],
                        duration_seconds=job.duration_seconds,
                    )
                    self._log_event("job_quarantined", job.job_id, str(e))
                else:
                    job.status = JobStatus.FAILED
                    self.results[job.job_id] = JobResult(
                        job_id=job.job_id,
                        status=JobStatus.FAILED,
                        errors=[str(e)],
                        duration_seconds=job.duration_seconds,
                    )
                    self._log_event("job_failed", job.job_id, str(e))
                    # In ABORT mode, re-raise to stop the pipeline
                    self.queue.task_done()
                    raise

            self.queue.task_done()

    def _log_event(self, event: str, job_id: str, detail: str = "") -> None:
        """Append an event to the pipeline event log."""
        if not self.event_log_path:
            return
        entry = json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "event": event,
            "job_id": job_id,
            "detail": detail,
        })
        with open(self.event_log_path, "a") as f:
            f.write(entry + "\n")

    @staticmethod
    def _default_normalizer(data: dict[str, Any], _schema_name: str) -> dict[str, Any]:
        """Pass-through normalizer (actual normalization in normalizer.py)."""
        return data

    @staticmethod
    def _default_commit(job_id: str, data: Any) -> None:
        """No-op commit (real commits write to disk via callback)."""
        pass
