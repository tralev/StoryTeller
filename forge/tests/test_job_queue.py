"""Test the Job Queue and worker pool."""

from __future__ import annotations

import asyncio

import pytest

from src.job_queue import (
    FailurePolicy,
    Job,
    JobQueue,
    JobResult,
    JobStatus,
    JobType,
    PipelineContext,
)


class MockGenerator:
    """Mock TextGenerator that returns predefined output."""

    def __init__(self, output: dict | None = None, should_fail: bool = False) -> None:
        self.output = output or {"result": "ok"}
        self.should_fail = should_fail
        self.call_count = 0

    async def generate(
        self,
        prompt: str = "",
        schema: dict | None = None,
        seed: int | None = None,
    ) -> dict:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("Mock generator failure")
        return dict(self.output)


class MockValidator:
    """Mock Validator that passes or fails based on config."""

    def __init__(self, should_pass: bool = True) -> None:
        self.should_pass = should_pass
        self.call_count = 0

    async def validate(self, content: dict, context: dict | None = None):
        from src.interfaces import ValidationResult

        self.call_count += 1
        if self.should_pass:
            return ValidationResult(is_valid=True)
        return ValidationResult(
            is_valid=False,
            errors=["Mock validation error"],
        )


class TestJob:
    """Job dataclass tests."""

    def test_job_defaults(self) -> None:
        """Job has correct default values."""
        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_BIBLE,
            prompt="Test prompt",
            seed=42,
        )
        assert job.status == JobStatus.PENDING
        assert job.attempts == 0
        assert job.errors == []
        assert job.dependencies == []

    def test_job_duration(self) -> None:
        """Job duration is computed correctly."""
        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_BIBLE,
            prompt="Test",
            seed=42,
            started_at=1000.0,
            completed_at=1005.5,
        )
        assert job.duration_seconds == 5.5

    def test_job_duration_not_started(self) -> None:
        """Duration is 0 if not started."""
        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_BIBLE,
            prompt="Test",
            seed=42,
        )
        assert job.duration_seconds == 0.0


class TestPipelineContext:
    """PipelineContext tests."""

    def test_add_feedback(self) -> None:
        """Feedback accumulates."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.add_feedback(["error 1"])
        ctx.add_feedback(["error 2"])
        assert len(ctx.feedback) == 2

    def test_clear_feedback(self) -> None:
        """Clear removes all feedback."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.add_feedback(["error"])
        ctx.clear_feedback()
        assert len(ctx.feedback) == 0


class TestJobQueue:
    """Job queue integration tests."""

    @pytest.mark.asyncio
    async def test_single_job_completes(self) -> None:
        """A single job with a mock generator completes."""
        queue = JobQueue(worker_count=1)
        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_BIBLE,
            prompt="Test",
            seed=42,
            generator=MockGenerator({"bible": "ok"}),
        )
        await queue.enqueue(job)
        results = await queue.drain()
        assert "test_01" in results
        assert results["test_01"].status == JobStatus.COMPLETED
        assert results["test_01"].output == {"bible": "ok"}

    @pytest.mark.asyncio
    async def test_multiple_jobs_complete(self) -> None:
        """Multiple jobs all complete."""
        queue = JobQueue(worker_count=2)

        for i in range(5):
            job = Job(
                job_id=f"job_{i:02d}",
                job_type=JobType.GENERATE_NODE,
                prompt=f"Node {i}",
                seed=42,
                generator=MockGenerator({"node": i}),
            )
            await queue.enqueue(job)

        results = await queue.drain()
        assert len(results) == 5
        for r in results.values():
            assert r.status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_job_with_validator_passes(self) -> None:
        """Job with a passing validator succeeds."""
        queue = JobQueue(worker_count=1)
        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_BIBLE,
            prompt="Test",
            seed=42,
            generator=MockGenerator({"ok": True}),
            validator=MockValidator(should_pass=True),
        )
        await queue.enqueue(job)
        results = await queue.drain()
        assert results["test_01"].status == JobStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_job_retries_on_validation_failure(self) -> None:
        """Job retries when validator fails, up to max_retries."""
        queue = JobQueue(worker_count=1)
        gen = MockGenerator({"ok": True})
        val = MockValidator(should_pass=False)

        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_BIBLE,
            prompt="Test",
            seed=42,
            generator=gen,
            validator=val,
            max_retries=2,
        )
        await queue.enqueue(job)
        results = await queue.drain()
        # Should fail after max_retries + 1 attempts
        assert results["test_01"].status == JobStatus.FAILED
        assert gen.call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_quarantine_mode(self) -> None:
        """QUARANTINE mode marks job as quarantined instead of failing."""
        queue = JobQueue(worker_count=1)
        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_NODE,
            prompt="Test",
            seed=42,
            generator=MockGenerator(should_fail=True),
            failure_policy=FailurePolicy.QUARANTINE,
            max_retries=0,
        )
        await queue.enqueue(job)
        results = await queue.drain()
        assert results["test_01"].status == JobStatus.QUARANTINED

    @pytest.mark.asyncio
    async def test_abort_mode_stops_pipeline(self) -> None:
        """ABORT mode raises an exception, stopping the pipeline."""
        queue = JobQueue(worker_count=1)
        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_BIBLE,
            prompt="Test",
            seed=42,
            generator=MockGenerator(should_fail=True),
            failure_policy=FailurePolicy.ABORT,
            max_retries=0,
        )
        await queue.enqueue(job)
        results = await queue.drain()
        assert results["test_01"].status == JobStatus.FAILED

    @pytest.mark.asyncio
    async def test_mixed_sequential_and_parallel(self) -> None:
        """Sequential text jobs and parallel image jobs coexist."""
        queue = JobQueue(worker_count=3)

        # Sequential text jobs
        for i in range(3):
            await queue.enqueue(Job(
                job_id=f"text_{i}",
                job_type=JobType.GENERATE_NODE,
                prompt=f"Node {i}",
                seed=42,
                generator=MockGenerator({"text": i}),
            ))

        # Parallel image jobs
        for i in range(2):
            await queue.enqueue(Job(
                job_id=f"image_{i}",
                job_type=JobType.GENERATE_IMAGE,
                prompt=f"Image {i}",
                seed=42,
                generator=MockGenerator({"image": i}),
            ))

        results = await queue.drain()
        assert len(results) == 5
        completed = sum(1 for r in results.values() if r.status == JobStatus.COMPLETED)
        assert completed == 5
