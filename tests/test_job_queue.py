"""Test the JobQueue dispatch layer — execute_step, execute_parallel, event logging."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.job_queue import (
    FailurePolicy,
    JobQueue,
    JobResult,
    JobStatus,
    PipelineContext,
)
from src.models.base import StepOutput


# ── mock step ────────────────────────────────────────────────────────────────


class _MockStep:
    """Mock PipelineStep for testing JobQueue dispatch."""

    def __init__(
        self,
        name: str = "mock",
        should_fail: bool = False,
        output_data: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.should_fail = should_fail
        self.output_data = output_data or {"result": "ok"}
        self.run_count = 0

    async def run(self, context: PipelineContext) -> StepOutput:
        self.run_count += 1
        if self.should_fail:
            raise RuntimeError(f"Step {self.name} failed")
        return StepOutput(
            data=self.output_data,
            step_name=self.name,
            artifact_id=f"{self.name}_abc123",
        )


# ── tests ────────────────────────────────────────────────────────────────────


class TestJobQueueExecuteStep:
    """Sequential step dispatch."""

    @pytest.mark.asyncio
    async def test_execute_step_returns_output(self) -> None:
        queue = JobQueue()
        step = _MockStep("world_builder")
        ctx = PipelineContext(run_id="r1", seed=42)

        output = await queue.execute_step(step, ctx, "wb")

        assert output.artifact_id == "world_builder_abc123"
        assert output.data == {"result": "ok"}
        assert output.step_name == "world_builder"

    @pytest.mark.asyncio
    async def test_execute_step_records_result(self) -> None:
        queue = JobQueue()
        step = _MockStep("test")
        ctx = PipelineContext(run_id="r1", seed=1)

        await queue.execute_step(step, ctx, "test_job")

        result = queue.get_result("test_job")
        assert result is not None
        assert result.status == JobStatus.COMPLETED
        assert result.duration_seconds >= 0

    @pytest.mark.asyncio
    async def test_execute_step_propagates_exception(self) -> None:
        queue = JobQueue()
        step = _MockStep("fail_step", should_fail=True)
        ctx = PipelineContext(run_id="r1", seed=1)

        with pytest.raises(RuntimeError, match="fail_step"):
            await queue.execute_step(step, ctx, "fail")

        result = queue.get_result("fail")
        assert result is not None
        assert result.status == JobStatus.FAILED
        assert "fail_step" in result.errors[0]

    @pytest.mark.asyncio
    async def test_completed_and_failed_counts(self) -> None:
        queue = JobQueue()
        ctx = PipelineContext(run_id="r1", seed=1)

        await queue.execute_step(_MockStep("ok1"), ctx, "j1")
        await queue.execute_step(_MockStep("ok2"), ctx, "j2")

        try:
            await queue.execute_step(_MockStep("fail", should_fail=True), ctx, "j3")
        except RuntimeError:
            pass

        assert queue.completed_count == 2
        assert queue.failed_count == 1


class TestJobQueueExecuteParallel:
    """Parallel step dispatch via asyncio.gather."""

    @pytest.mark.asyncio
    async def test_execute_parallel_runs_concurrently(self) -> None:
        queue = JobQueue()
        steps = [
            ("img", _MockStep("image_gen", output_data={"type": "image"})),
            ("mus", _MockStep("music_gen", output_data={"type": "music"})),
        ]
        ctx = PipelineContext(run_id="r1", seed=42)

        results = await queue.execute_parallel(steps, ctx)

        assert len(results) == 2
        data_types = {r.data["type"] for r in results}
        assert data_types == {"image", "music"}

    @pytest.mark.asyncio
    async def test_execute_parallel_handles_exceptions(self) -> None:
        queue = JobQueue()
        steps = [
            ("img", _MockStep("image", should_fail=True)),
            ("mus", _MockStep("music", output_data={"type": "music"})),
        ]
        ctx = PipelineContext(run_id="r1", seed=42)

        results = await queue.execute_parallel(steps, ctx)

        # One exception, one success
        exceptions = [r for r in results if isinstance(r, Exception)]
        outputs = [r for r in results if isinstance(r, StepOutput)]
        assert len(exceptions) == 1
        assert len(outputs) == 1
        assert outputs[0].data["type"] == "music"

    @pytest.mark.asyncio
    async def test_execute_parallel_empty_list(self) -> None:
        queue = JobQueue()
        results = await queue.execute_parallel([], PipelineContext(run_id="r1", seed=1))
        assert results == []


class TestJobQueueEventLogging:
    """JSONL event logging."""

    @pytest.mark.asyncio
    async def test_events_logged_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = str(Path(tmpdir) / "events.jsonl")
            queue = JobQueue(event_log_path=log_path)
            ctx = PipelineContext(run_id="r1", seed=42)

            await queue.execute_step(_MockStep("test"), ctx, "job_01")
            await queue.execute_step(_MockStep("test2"), ctx, "job_02")

            with open(log_path) as f:
                lines = f.readlines()

            assert len(lines) == 4  # start + completed for each
            events = [json.loads(line) for line in lines]
            assert events[0]["type"] == "step_started"
            assert events[0]["step_id"] == "job_01"
            assert events[2]["type"] == "step_started"
            assert events[2]["step_id"] == "job_02"

    @pytest.mark.asyncio
    async def test_failure_events_logged(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = str(Path(tmpdir) / "events.jsonl")
            queue = JobQueue(event_log_path=log_path)
            ctx = PipelineContext(run_id="r1", seed=1)

            try:
                await queue.execute_step(
                    _MockStep("fail", should_fail=True), ctx, "bad_job",
                )
            except RuntimeError:
                pass

            with open(log_path) as f:
                lines = f.readlines()

            events = [json.loads(line) for line in lines]
            assert events[0]["type"] == "step_started"
            assert events[1]["type"] == "step_failed"
            assert "bad_job" in events[1]["step_id"]

    @pytest.mark.asyncio
    async def test_no_log_without_path(self) -> None:
        """No crash when event_log_path is None."""
        queue = JobQueue(event_log_path=None)
        ctx = PipelineContext(run_id="r1", seed=1)
        await queue.execute_step(_MockStep("test"), ctx, "j1")
        # Should not raise


class TestJobResult:
    """JobResult dataclass."""

    def test_job_result_fields(self) -> None:
        result = JobResult(
            job_id="test",
            status=JobStatus.COMPLETED,
            output={"key": "val"},
            duration_seconds=1.5,
        )
        assert result.job_id == "test"
        assert result.status == JobStatus.COMPLETED
        assert result.output == {"key": "val"}
        assert result.duration_seconds == 1.5

    def test_job_result_defaults(self) -> None:
        result = JobResult(job_id="test", status=JobStatus.FAILED)
        assert result.output is None
        assert result.errors == []
        assert result.duration_seconds == 0.0
