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
