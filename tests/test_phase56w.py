"""Tests for Phase 5.6 W — Policy Semantics.

Locks the retry/failure contract so it can never silently drift:

  W1: ``max_retries`` EXCLUDES the first attempt — total attempts are
      always ``max_retries + 1``, in both PipelineStep and BatchScheduler.
  W2: Terminal configuration/resource/persistence/dependency errors are
      NEVER retried — first attempt fails, error propagates immediately.
  W3: Retryable generation/validation errors (and unknown exceptions)
      retry exactly per policy — ``max_retries`` attempts after the first.
  W4: QUARANTINE applies only to independent item jobs (image/music
      nodes); sequential phase steps use ABORT. Terminal errors abort the
      batch even under QUARANTINE.
  W5: Phase dependencies and storage failures always abort — never
      quarantined, never retried.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from src.interfaces import ValidationResult
from src.interfaces.validator import ValidatorStatus
from src.job_queue import FailurePolicy, PipelineContext
from src.models.base import PipelineError, PipelineStep, StepOutput
from src.pipeline.batch import BatchScheduler, NodeJob
from src.pipeline.errors import (
    ConfigurationError,
    DependencyError,
    GenerationError,
    PersistenceError,
    ResourceError,
    StoryTellerError,
    ValidationError,
    is_retryable,
)
from src.pipeline.plan import PipelinePlan
from src.pipeline.policy import ExecutionPolicy

# ── fakes ────────────────────────────────────────────────────────────────────


class RaisingGenerator:
    """Raises a fixed exception on every generate() call."""

    def __init__(self, exc_factory: Callable[[], Exception]) -> None:
        self.exc_factory = exc_factory
        self.call_count = 0

    async def generate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.call_count += 1
        raise self.exc_factory()


class FlakyGenerator:
    """Succeeds after ``fail_times`` failures, raising ``exc_factory``."""

    def __init__(self, exc_factory: Callable[[], Exception], fail_times: int) -> None:
        self.exc_factory = exc_factory
        self.fail_times = fail_times
        self.call_count = 0

    async def generate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise self.exc_factory()
        return {"ok": True}


class AlwaysInvalidValidator:
    """Every validation attempt fails (validation-error retry path)."""

    async def validate(self, content: Any, context: Any = None) -> ValidationResult:
        return ValidationResult(
            is_valid=False,
            errors=["always invalid"],
            retry_prompt="fix it",
            status=ValidatorStatus.FAILED,
        )


class PolicyStep(PipelineStep):
    """Concrete PipelineStep carrying an explicit ExecutionPolicy."""

    def __init__(
        self,
        generator: Any,
        validator: Any = None,
        policy: ExecutionPolicy | None = None,
    ) -> None:
        super().__init__(
            name="w_step",
            generator=generator,
            validator=validator,
            policy=policy or ExecutionPolicy.default(),
        )

    async def generate(self, context: PipelineContext) -> StepOutput[dict[str, Any]]:
        result = await self.generator.generate()
        return StepOutput(data=result, step_name=self.name)


def _ctx() -> PipelineContext:
    return PipelineContext(run_id="run_w", seed=1)


# ── W1: max_retries excludes the first attempt ──────────────────────────────


class TestW1RetryDefinition:
    """The retry budget is ``max_retries + 1`` total attempts."""

    def test_total_attempts_formula(self) -> None:
        assert ExecutionPolicy(max_retries=3).total_attempts() == 4
        assert ExecutionPolicy(max_retries=1).total_attempts() == 2
        assert ExecutionPolicy(max_retries=0).total_attempts() == 1

    @pytest.mark.asyncio
    async def test_pipeline_step_attempts_match_policy(self) -> None:
        """max_retries=2 → exactly 3 attempts, then PipelineError(attempts=3)."""
        gen = RaisingGenerator(lambda: GenerationError("w_step", "boom"))
        step = PolicyStep(gen, policy=ExecutionPolicy(max_retries=2))

        with pytest.raises(PipelineError) as exc:
            await step.run(_ctx())

        assert gen.call_count == 3
        assert exc.value.attempts == 3

    @pytest.mark.asyncio
    async def test_zero_retries_is_single_attempt(self) -> None:
        """max_retries=0 → the first attempt is the only one."""
        gen = RaisingGenerator(lambda: GenerationError("w_step", "boom"))
        step = PolicyStep(gen, policy=ExecutionPolicy(max_retries=0))

        with pytest.raises(PipelineError):
            await step.run(_ctx())

        assert gen.call_count == 1

    @pytest.mark.asyncio
    async def test_batch_attempts_match_policy(self) -> None:
        """BatchScheduler quarantines after exactly max_retries + 1 attempts."""
        calls: list[str] = []

        async def worker(nid: str, node: dict[str, Any], idx: int) -> dict[str, Any]:
            calls.append(nid)
            raise GenerationError("image_generator", "boom")

        scheduler = BatchScheduler(max_concurrency=1, policy=ExecutionPolicy(max_retries=2))
        jobs = [NodeJob(node_id="n1", node={"node_id": "n1"}, index=0)]
        result = await scheduler.run(jobs, worker)

        assert len(calls) == 3
        assert result.failed == 1
        assert result.quarantined["n1"].attempts == 3


# ── W2: terminal errors are never retried ───────────────────────────────────


class TestW2TerminalErrorsNeverRetried:
    """Config/resource/persistence/dependency errors abort on the first attempt."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exc_factory",
        [
            lambda: ConfigurationError("models.yaml", "missing field"),
            lambda: ResourceError("ram", "budget exceeded"),
            lambda: PersistenceError("/tmp/x.json", "disk full"),
            lambda: DependencyError("story_writer", "bible"),
        ],
    )
    async def test_terminal_error_aborts_after_one_attempt(
        self,
        exc_factory: Callable[[], StoryTellerError],
    ) -> None:
        gen = RaisingGenerator(exc_factory)
        step = PolicyStep(gen, policy=ExecutionPolicy(max_retries=3))

        with pytest.raises(type(exc_factory())) as exc:
            await step.run(_ctx())

        # The ORIGINAL terminal error propagates — never a PipelineError.
        assert not isinstance(exc.value, PipelineError)
        assert gen.call_count == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "exc_factory",
        [
            lambda: ConfigurationError("models.yaml", "missing field"),
            lambda: PersistenceError("/tmp/x", "disk full"),
        ],
    )
    async def test_terminal_error_aborts_batch(
        self,
        exc_factory: Callable[[], StoryTellerError],
    ) -> None:
        """Even under QUARANTINE policy, a terminal error aborts the batch."""
        calls: list[str] = []

        async def worker(nid: str, node: dict[str, Any], idx: int) -> dict[str, Any]:
            calls.append(nid)
            raise exc_factory()

        scheduler = BatchScheduler(  # default failure policy is QUARANTINE
            max_concurrency=1,
            policy=ExecutionPolicy(max_retries=3),
        )
        jobs = [NodeJob(node_id="n1", node={"node_id": "n1"}, index=0)]

        with pytest.raises(type(exc_factory())):
            await scheduler.run(jobs, worker)

        assert len(calls) == 1, "Terminal errors must not be retried"


# ── W3: retryable errors retry exactly per policy ───────────────────────────


class TestW3RetryableErrorsPerPolicy:
    """Generation/validation/unknown errors retry exactly max_retries times."""

    @pytest.mark.asyncio
    async def test_generation_error_exact_retries(self) -> None:
        gen = RaisingGenerator(lambda: GenerationError("w_step", "boom"))
        step = PolicyStep(gen, policy=ExecutionPolicy(max_retries=2))

        with pytest.raises(PipelineError):
            await step.run(_ctx())

        assert gen.call_count == 3  # 1 initial + 2 retries

    @pytest.mark.asyncio
    async def test_validation_error_exact_retries(self) -> None:
        gen = FlakyGenerator(
            lambda: GenerationError("w_step", "boom"),
            fail_times=0,
        )
        step = PolicyStep(
            gen,
            validator=AlwaysInvalidValidator(),
            policy=ExecutionPolicy(max_retries=2),
        )

        with pytest.raises(PipelineError):
            await step.run(_ctx())

        assert gen.call_count == 3  # every attempt regenerates + re-validates

    @pytest.mark.asyncio
    async def test_unknown_exception_exact_retries(self) -> None:
        """Unknown (non-StoryTellerError) exceptions use the SAME policy budget."""
        gen = RaisingGenerator(lambda: RuntimeError("transient glitch"))
        step = PolicyStep(gen, policy=ExecutionPolicy(max_retries=2))

        with pytest.raises(PipelineError):
            await step.run(_ctx())

        assert gen.call_count == 3

    @pytest.mark.asyncio
    async def test_recovery_within_budget_succeeds(self) -> None:
        """Failing max_retries times then succeeding completes the step."""
        gen = FlakyGenerator(
            lambda: GenerationError("w_step", "boom"),
            fail_times=2,
        )
        step = PolicyStep(gen, policy=ExecutionPolicy(max_retries=3))

        output = await step.run(_ctx())

        assert output.data == {"ok": True}
        assert gen.call_count == 3

    @pytest.mark.asyncio
    async def test_retryable_classification_matrix(self) -> None:
        """Generation/validation retry; terminal errors never do."""
        assert is_retryable(GenerationError("s", "m"))
        assert is_retryable(ValidationError("s", ["m"]))
        assert not is_retryable(ConfigurationError("c", "m"))
        assert not is_retryable(ResourceError("r", "m"))
        assert not is_retryable(PersistenceError("p", "m"))
        assert not is_retryable(DependencyError("s", "d"))


# ── W4: QUARANTINE applies only to independent item jobs ────────────────────


class TestW4QuarantineScope:
    """Only independent item jobs (image/music nodes) may quarantine."""

    def test_production_plan_makes_every_mandatory_stage_terminal(self) -> None:
        plan = PipelinePlan.production_v2()
        assert all(spec.failure_policy == "abort" for spec in plan.steps)
        assert not any(spec.parallel_per_node for spec in plan.steps)

    @pytest.mark.asyncio
    async def test_batch_quarantines_failed_item_and_continues(self) -> None:
        """A failing retryable item is quarantined; the good item completes."""
        calls: list[str] = []

        async def worker(nid: str, node: dict[str, Any], idx: int) -> dict[str, Any]:
            calls.append(nid)
            if nid == "bad":
                raise GenerationError("image_generator", "boom")
            return {"node_id": nid, "image_path": "/tmp/fake.png"}

        scheduler = BatchScheduler(
            max_concurrency=1,
            policy=ExecutionPolicy(max_retries=2),
        )
        jobs = [
            NodeJob(node_id="bad", node={"node_id": "bad"}, index=0),
            NodeJob(node_id="good", node={"node_id": "good"}, index=1),
        ]
        result = await scheduler.run(jobs, worker)

        assert "good" in result.completed
        assert "bad" in result.quarantined
        assert result.quarantined["bad"].code == "GEN_001"

    @pytest.mark.asyncio
    async def test_sequential_step_failure_aborts(self) -> None:
        """An abort-policy sequential step propagates PipelineError (no quarantine)."""
        gen = RaisingGenerator(lambda: GenerationError("w_step", "boom"))
        step = PolicyStep(
            gen,
            policy=ExecutionPolicy(
                max_retries=1,
                failure_policy=FailurePolicy.ABORT,
            ),
        )

        with pytest.raises(PipelineError):
            await step.run(_ctx())


# ── W5: dependencies and storage failures always abort ──────────────────────


class TestW5DependencyAndStorageAbort:
    """Dependency + persistence errors abort — never retried or quarantined."""

    @pytest.mark.asyncio
    async def test_dependency_error_aborts_step(self) -> None:
        gen = RaisingGenerator(lambda: DependencyError("story_writer", "bible"))
        step = PolicyStep(gen, policy=ExecutionPolicy(max_retries=3))

        with pytest.raises(DependencyError):
            await step.run(_ctx())

        assert gen.call_count == 1

    @pytest.mark.asyncio
    async def test_dependency_error_aborts_batch(self) -> None:
        """A missing upstream artifact aborts the whole batch — no quarantine."""
        calls: list[str] = []

        async def worker(nid: str, node: dict[str, Any], idx: int) -> dict[str, Any]:
            calls.append(nid)
            raise DependencyError("image_generator", "graph")

        scheduler = BatchScheduler(
            max_concurrency=1,
            policy=ExecutionPolicy(max_retries=3),
        )
        jobs = [NodeJob(node_id="n1", node={"node_id": "n1"}, index=0)]

        with pytest.raises(DependencyError):
            await scheduler.run(jobs, worker)

        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_storage_failure_aborts_batch(self) -> None:
        """PersistenceError (disk write failure) aborts, never quarantined."""
        calls: list[str] = []

        async def worker(nid: str, node: dict[str, Any], idx: int) -> dict[str, Any]:
            calls.append(nid)
            raise PersistenceError("/tmp/node.png", "disk full")

        scheduler = BatchScheduler(
            max_concurrency=1,
            policy=ExecutionPolicy(max_retries=3),
        )
        jobs = [NodeJob(node_id="n1", node={"node_id": "n1"}, index=0)]

        with pytest.raises(PersistenceError):
            await scheduler.run(jobs, worker)

        assert len(calls) == 1
