"""Phase 5.6G: Configured policies — ExecutionPolicy, config-driven behavior.

Verifies:
  1. ExecutionPolicy.from_config() reads PipelineConfig fields
  2. ExecutionPolicy.default() returns sensible defaults
  3. total_attempts() = max_retries + 1
  4. PipelineStep uses policy.max_retries, not MAX_RETRIES
  5. failure_policy from config overrides class default
  6. policy parameter forwarded through step constructors
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.job_queue import FailurePolicy


class TestExecutionPolicy:
    """ExecutionPolicy dataclass and factory methods."""

    def test_default_values(self) -> None:
        from src.pipeline.policy import ExecutionPolicy
        p = ExecutionPolicy.default()
        assert p.max_retries == 3
        assert p.checkpoint_interval == 1
        assert p.failure_policy == FailurePolicy.QUARANTINE
        assert p.model_unload_threshold == 0.9

    def test_total_attempts(self) -> None:
        from src.pipeline.policy import ExecutionPolicy
        p = ExecutionPolicy(max_retries=3)
        assert p.total_attempts() == 4  # 1 initial + 3 retries

        p0 = ExecutionPolicy(max_retries=0)
        assert p0.total_attempts() == 1  # 1 initial, no retries

    def test_from_config_reads_max_retries(self) -> None:
        from src.pipeline.policy import ExecutionPolicy

        class MockConfig:
            max_retries = 5
            checkpoint_interval = 2
            failure_policy = "abort"
            model_unload_threshold = 0.8

        p = ExecutionPolicy.from_config(MockConfig())
        assert p.max_retries == 5
        assert p.checkpoint_interval == 2
        assert p.failure_policy == FailurePolicy.ABORT
        assert p.model_unload_threshold == 0.8

    def test_from_config_defaults_on_missing_fields(self) -> None:
        from src.pipeline.policy import ExecutionPolicy

        class EmptyConfig:
            pass

        p = ExecutionPolicy.from_config(EmptyConfig())
        assert p.max_retries == 3  # default
        assert p.checkpoint_interval == 1  # default

    def test_from_config_clamps_negative_retries(self) -> None:
        from src.pipeline.policy import ExecutionPolicy

        class NegConfig:
            max_retries = -5
            checkpoint_interval = 0

        p = ExecutionPolicy.from_config(NegConfig())
        assert p.max_retries == 0  # clamped to 0
        assert p.checkpoint_interval == 1  # clamped to 1


class TestPipelineStepUsesPolicy:
    """PipelineStep uses ExecutionPolicy for retry limits."""

    def test_step_uses_policy_max_retries(self) -> None:
        from src.models.world_builder import WorldBuilder
        from src.pipeline.policy import ExecutionPolicy

        from .test_production_wiring import TrackedTextGenerator

        gen = TrackedTextGenerator()
        policy = ExecutionPolicy(max_retries=5)
        step = WorldBuilder(gen, policy=policy)
        assert step.policy.max_retries == 5
        assert step.failure_policy == FailurePolicy.QUARANTINE  # From policy

    def test_abort_policy_overrides_default(self) -> None:
        from src.models.world_builder import WorldBuilder
        from src.pipeline.policy import ExecutionPolicy

        from .test_production_wiring import TrackedTextGenerator

        gen = TrackedTextGenerator()
        policy = ExecutionPolicy(failure_policy=FailurePolicy.ABORT)
        step = WorldBuilder(gen, policy=policy)
        assert step.failure_policy == FailurePolicy.ABORT

    def test_step_runs_with_custom_retries(self, tmp_path: Path) -> None:
        from src.models.world_builder import WorldBuilder
        from src.pipeline.policy import ExecutionPolicy
        from src.job_queue import PipelineContext

        from .test_production_wiring import (
            TrackedTextGenerator, _clear_fakes,
        )

        _clear_fakes()
        gen = TrackedTextGenerator()
        # Only 1 total attempt (0 retries) — should fail immediately if invalid
        policy = ExecutionPolicy(max_retries=0, failure_policy=FailurePolicy.ABORT)
        step = WorldBuilder(gen, policy=policy)

        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))
        ctx.state["tone"] = "dark_fantasy"
        ctx.state["title"] = "Policy Test"
        ctx.state["temperature"] = 0.7
        ctx.state["start_time"] = __import__("time").time()

        import asyncio
        output = asyncio.run(step.run(ctx))
        assert output is not None
        # With 0 retries, the step completes on first attempt (tracked data passes validation enough for world_builder)
        assert gen.call_count == 1
