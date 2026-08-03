"""Extended tests for JobQueue — event logging, dependencies, context fields."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from src.job_queue import (
    FailurePolicy,
    Job,
    JobQueue,
    JobStatus,
    JobType,
    PipelineContext,
)


class MockGenerator:
    def __init__(self, output: dict | None = None) -> None:
        self.output = output or {"result": "ok"}
        self.call_count = 0

    async def generate(self, prompt: str = "", schema: dict | None = None, seed: int | None = None) -> dict:
        self.call_count += 1
        return dict(self.output)


class FailingOnceGenerator:
    """Generator that succeeds on Nth call, fails before that."""

    def __init__(self, fail_count: int = 1) -> None:
        self.fail_count = fail_count
        self.call_count = 0

    async def generate(self, prompt: str = "", schema: dict | None = None, seed: int | None = None) -> dict:
        self.call_count += 1
        if self.call_count <= self.fail_count:
            raise RuntimeError(f"Boom #{self.call_count}")
        return {"ok": True}


class TestAbortMode:
    """ABORT failure policy stops the pipeline immediately."""

    @pytest.mark.asyncio
    async def test_abort_stops_other_workers(self) -> None:
        """When a job fails in ABORT mode, remaining jobs are not processed."""
        queue = JobQueue(worker_count=2)

        # Job 1: will succeed
        job_ok = Job(
            job_id="ok_job",
            job_type=JobType.GENERATE_BIBLE,
            prompt="ok",
            seed=1,
            generator=MockGenerator({"ok": True}),
            failure_policy=FailurePolicy.ABORT,
        )
        # Job 2: will fail immediately (no retries)
        job_fail = Job(
            job_id="fail_job",
            job_type=JobType.GENERATE_CHAPTER,
            prompt="fail",
            seed=2,
            generator=FailingOnceGenerator(fail_count=1),
            max_retries=0,
            failure_policy=FailurePolicy.ABORT,
        )
        # Job 3: should NEVER be processed because ABORT stops the pipeline
        job_never = Job(
            job_id="never_job",
            job_type=JobType.GENERATE_NODE,
            prompt="never",
            seed=3,
            generator=MockGenerator({"should_not_run": True}),
            failure_policy=FailurePolicy.ABORT,
        )

        await queue.enqueue(job_ok)
        await queue.enqueue(job_fail)
        await queue.enqueue(job_never)

        results = await queue.drain()

        # Job 1 should succeed
        assert "ok_job" in results
        # Job 2 should fail
        assert "fail_job" in results
        assert results["fail_job"].status == JobStatus.FAILED
        # Job 3 should NOT be completed (aborted before processing)
        never_result = results.get("never_job")
        assert never_result is None or never_result.status in (
            JobStatus.PENDING, JobStatus.FAILED
        )

    @pytest.mark.asyncio
    async def test_abort_event_is_set_on_failure(self) -> None:
        """After ABORT failure, the abort_event is set."""
        queue = JobQueue(worker_count=1)
        job = Job(
            job_id="fail_job",
            job_type=JobType.GENERATE_BIBLE,
            prompt="fail",
            seed=1,
            generator=FailingOnceGenerator(fail_count=1),
            max_retries=0,
            failure_policy=FailurePolicy.ABORT,
        )
        await queue.enqueue(job)
        results = await queue.drain()
        assert results["fail_job"].status == JobStatus.FAILED
        # The abort event should be set
        assert queue._abort_event.is_set()

    @pytest.mark.asyncio
    async def test_quarantine_does_not_abort(self) -> None:
        """QUARANTINE failure does not stop other workers."""
        queue = JobQueue(worker_count=2)

        job_fail = Job(
            job_id="quarantined_job",
            job_type=JobType.GENERATE_CHAPTER,
            prompt="fail",
            seed=1,
            generator=FailingOnceGenerator(fail_count=1),
            max_retries=0,
            failure_policy=FailurePolicy.QUARANTINE,
        )
        job_ok = Job(
            job_id="still_runs",
            job_type=JobType.GENERATE_NODE,
            prompt="ok",
            seed=2,
            generator=MockGenerator({"ok": True}),
            failure_policy=FailurePolicy.ABORT,
        )

        await queue.enqueue(job_fail)
        await queue.enqueue(job_ok)
        results = await queue.drain()

        assert results["quarantined_job"].status == JobStatus.QUARANTINED
        assert results["still_runs"].status == JobStatus.COMPLETED


class TestEventLogging:
    """Event log writes to a file during pipeline execution."""

    @pytest.mark.asyncio
    async def test_event_log_is_written(self) -> None:
        """_log_event writes JSONL entries to the event log file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = f.name

        try:
            queue = JobQueue(worker_count=1, event_log_path=log_path)
            job = Job(
                job_id="test_01",
                job_type=JobType.GENERATE_BIBLE,
                prompt="Test",
                seed=42,
                generator=MockGenerator({"ok": True}),
            )
            await queue.enqueue(job)
            await queue.drain()

            with open(log_path) as f:
                lines = f.readlines()

            assert len(lines) >= 2  # At minimum: job_started, job_completed
            first = json.loads(lines[0])
            assert first["event"] == "job_started"
            assert first["job_id"] == "test_01"
            assert "timestamp" in first
        finally:
            os.unlink(log_path)

    @pytest.mark.asyncio
    async def test_event_log_records_failure(self) -> None:
        """Failed jobs are recorded in the event log."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = f.name

        try:
            queue = JobQueue(worker_count=1, event_log_path=log_path)
            job = Job(
                job_id="test_fail",
                job_type=JobType.GENERATE_BIBLE,
                prompt="Test",
                seed=42,
                generator=MockGenerator({"ok": True}),
                validator=_FailingValidator(),
                max_retries=1,
                failure_policy=FailurePolicy.QUARANTINE,
            )
            await queue.enqueue(job)
            await queue.drain()

            with open(log_path) as f:
                lines = f.readlines()

            events = [json.loads(l)["event"] for l in lines]
            assert "validation_failed" in events
            assert "job_quarantined" in events
        finally:
            os.unlink(log_path)

    @pytest.mark.asyncio
    async def test_no_event_log_when_path_is_none(self) -> None:
        """When event_log_path is None, no file is created."""
        queue = JobQueue(worker_count=1, event_log_path=None)
        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_BIBLE,
            prompt="Test",
            seed=42,
            generator=MockGenerator({"ok": True}),
        )
        await queue.enqueue(job)
        results = await queue.drain()
        assert results["test_01"].status == JobStatus.COMPLETED


class _FailingValidator:
    async def validate(self, content: dict, context: dict | None = None):
        from src.interfaces import ValidationResult
        return ValidationResult(is_valid=False, errors=["fail"])


class TestJobDependencies:
    """Job dependencies field is passed through correctly."""

    def test_job_with_dependencies(self) -> None:
        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_NODE,
            prompt="Test",
            seed=42,
            dependencies=["node_01", "node_02"],
        )
        assert job.dependencies == ["node_01", "node_02"]

    def test_job_no_dependencies_by_default(self) -> None:
        job = Job(
            job_id="test_01",
            job_type=JobType.GENERATE_BIBLE,
            prompt="Test",
            seed=42,
        )
        assert job.dependencies == []


class TestPipelineContextFields:
    """PipelineContext.outputs and .state are usable dicts."""

    def test_outputs_is_mutable(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.outputs["bible"] = {"world_name": "Test"}
        ctx.outputs["story"] = {"chapters": []}
        assert len(ctx.outputs) == 2

    def test_state_is_mutable(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.state["current_phase"] = 3
        ctx.state["nodes_generated"] = 12
        assert ctx.state["current_phase"] == 3

    def test_context_has_run_id_and_seed(self) -> None:
        ctx = PipelineContext(run_id="run_abc", seed=123)
        assert ctx.run_id == "run_abc"
        assert ctx.seed == 123
