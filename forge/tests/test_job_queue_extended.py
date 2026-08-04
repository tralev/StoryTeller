"""Extended JobQueue tests — FailurePolicy, PipelineContext, parallel timing."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.job_queue import (
    FailurePolicy,
    JobQueue,
    JobStatus,
    PipelineContext,
)
from src.models.base import StepOutput


class _SlowStep:
    """Step that sleeps to simulate real work."""

    def __init__(self, name: str = "slow", delay: float = 0.05) -> None:
        self.name = name
        self.delay = delay

    async def run(self, context: PipelineContext) -> StepOutput:
        await asyncio.sleep(self.delay)
        return StepOutput(
            data={"name": self.name},
            step_name=self.name,
            artifact_id=f"{self.name}_id",
        )


class TestPipelineContext:
    """PipelineContext accumulates state across steps."""

    def test_outputs_accumulate(self) -> None:
        ctx = PipelineContext(run_id="r1", seed=42)
        ctx.outputs["bible"] = {"world": "test"}
        ctx.outputs["story"] = {"chapters": []}
        assert ctx.outputs.get("bible") is not None
        assert ctx.outputs.get("story") is not None

    def test_feedback_accumulation(self) -> None:
        ctx = PipelineContext(run_id="r1", seed=1)
        ctx.add_feedback(["error1", "error2"])
        assert len(ctx.feedback) == 2
        ctx.clear_feedback()
        assert len(ctx.feedback) == 0

    def test_state_dict(self) -> None:
        ctx = PipelineContext(run_id="r1", seed=42)
        ctx.state["tone"] = "dark_fantasy"
        ctx.state["temperature"] = 0.7
        assert ctx.state["tone"] == "dark_fantasy"


class TestFailurePolicy:
    """FailurePolicy enum values."""

    def test_abort_value(self) -> None:
        assert FailurePolicy.ABORT.value == "abort"

    def test_quarantine_value(self) -> None:
        assert FailurePolicy.QUARANTINE.value == "quarantine"


class TestParallelTiming:
    """Parallel execution is actually concurrent."""

    @pytest.mark.asyncio
    async def test_parallel_is_faster_than_sequential(self) -> None:
        ctx = PipelineContext(run_id="r1", seed=1)
        delay = 0.1

        # Sequential
        t0 = asyncio.get_event_loop().time()
        queue_seq = JobQueue()
        await queue_seq.execute_step(_SlowStep("a", delay), ctx, "a")
        await queue_seq.execute_step(_SlowStep("b", delay), ctx, "b")
        seq_time = asyncio.get_event_loop().time() - t0

        # Parallel
        t0 = asyncio.get_event_loop().time()
        queue_par = JobQueue()
        steps = [
            ("a", _SlowStep("a", delay)),
            ("b", _SlowStep("b", delay)),
        ]
        await queue_par.execute_parallel(steps, ctx)
        par_time = asyncio.get_event_loop().time() - t0

        # Parallel should be ~2x faster (both sleep concurrently)
        assert par_time < seq_time * 0.8, (
            f"Parallel ({par_time:.3f}s) not faster than sequential ({seq_time:.3f}s)"
        )


class TestMultipleStepsInSequence:
    """Simulate a multi-phase pipeline through the queue."""

    @pytest.mark.asyncio
    async def test_multi_phase_pipeline(self) -> None:
        """Simulate: WorldBuilder → StoryWriter → (Image ∥ Music) → Packager."""
        queue = JobQueue()
        ctx = PipelineContext(run_id="full", seed=42)

        # Phase 1: World Bible
        out = await queue.execute_step(
            _SlowStep("world_builder"), ctx, "wb",
        )
        ctx.outputs["bible"] = out.data

        # Phase 2: Story
        out = await queue.execute_step(
            _SlowStep("story_writer"), ctx, "sw",
        )
        ctx.outputs["story"] = out.data

        # Phase 3: Parallel assets
        results = await queue.execute_parallel(
            [("img", _SlowStep("image")), ("mus", _SlowStep("music"))],
            ctx,
        )
        ctx.outputs["images"] = results[0].data
        ctx.outputs["midi"] = results[1].data

        # Phase 4: Package
        out = await queue.execute_step(
            _SlowStep("packager"), ctx, "pkg",
        )

        assert queue.completed_count == 5  # 4 steps + 1 parallel
        assert queue.failed_count == 0
        assert ctx.outputs.get("bible") is not None
        assert ctx.outputs.get("images") is not None

    @pytest.mark.asyncio
    async def test_pipeline_with_event_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = str(Path(tmpdir) / "pipeline.jsonl")
            queue = JobQueue(event_log_path=log_path)
            ctx = PipelineContext(run_id="logged", seed=99)

            await queue.execute_step(_SlowStep("step1", 0.01), ctx, "s1")
            await queue.execute_step(_SlowStep("step2", 0.01), ctx, "s2")

            with open(log_path) as f:
                lines = f.readlines()

            # 4 events: started+completed × 2
            assert len(lines) == 4

            events = [json.loads(line) for line in lines]
            event_types = [e["type"] for e in events]
            assert event_types.count("step_started") == 2
            assert event_types.count("step_completed") == 2
