"""Test the abstract PipelineStep base class."""

from __future__ import annotations

import pytest

from src.interfaces import ValidationResult
from src.job_queue import FailurePolicy, PipelineContext
from src.models.base import PipelineError, PipelineStep, StepOutput


class MockGenerator:
    """Mock TextGenerator."""

    def __init__(self, output: dict | None = None, fail_times: int = 0) -> None:
        self.output = output or {"result": "ok"}
        self.fail_times = fail_times
        self.call_count = 0

    async def generate(self, prompt: str = "", schema: dict | None = None, seed: int | None = None) -> dict:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise RuntimeError(f"Mock failure #{self.call_count}")
        return dict(self.output)


class MockValidator:
    """Mock Validator."""

    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.call_count = 0

    async def validate(self, content: dict, context: dict | None = None) -> ValidationResult:
        self.call_count += 1
        if self.call_count <= self.fail_times:
            return ValidationResult(
                is_valid=False,
                errors=[f"Validation error #{self.call_count}"],
                retry_prompt=f"Fix error #{self.call_count}",
            )
        return ValidationResult(is_valid=True)


class SimpleStep(PipelineStep):
    """Concrete PipelineStep for testing."""

    def __init__(self, generator, validator=None, failure_policy=FailurePolicy.ABORT):
        super().__init__(
            name="test_step",
            generator=generator,
            validator=validator,
            failure_policy=failure_policy,
        )

    async def generate(self, context: PipelineContext) -> StepOutput:
        result = await self.generator.generate()
        return StepOutput(data=result, step_name=self.name)


class TestPipelineStep:
    """PipelineStep base class tests."""

    @pytest.mark.asyncio
    async def test_successful_generation(self) -> None:
        """A simple step with a passing generator succeeds."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        step = SimpleStep(generator=MockGenerator({"bible": "ok"}))
        output = await step.run(ctx)
        assert output.data == {"bible": "ok"}

    @pytest.mark.asyncio
    async def test_retry_on_failure(self) -> None:
        """Generator failure triggers retry."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        gen = MockGenerator({"ok": True}, fail_times=1)  # Fail once, then succeed
        step = SimpleStep(generator=gen)
        output = await step.run(ctx)
        assert output.data == {"ok": True}
        assert gen.call_count == 2  # First call failed, second succeeded

    @pytest.mark.asyncio
    async def test_exhaust_retries(self) -> None:
        """Step raises PipelineError after exhausting retries."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        gen = MockGenerator(fail_times=10)  # Always fail
        step = SimpleStep(generator=gen)

        with pytest.raises(PipelineError) as exc:
            await step.run(ctx)

        assert "test_step" in str(exc.value)
        assert gen.call_count == 4  # MAX_RETRIES (3) + 1 initial

    @pytest.mark.asyncio
    async def test_validation_retry(self) -> None:
        """Validation failure triggers retry."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        step = SimpleStep(
            generator=MockGenerator({"ok": True}),
            validator=MockValidator(fail_times=1),  # Fail validation once
        )
        output = await step.run(ctx)
        assert output.data == {"ok": True}

    @pytest.mark.asyncio
    async def test_validation_exhausts_retries(self) -> None:
        """Validator always failing causes PipelineError."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        step = SimpleStep(
            generator=MockGenerator({"ok": True}),
            validator=MockValidator(fail_times=10),  # Always fail validation
        )

        with pytest.raises(PipelineError):
            await step.run(ctx)

    @pytest.mark.asyncio
    async def test_normalization_applied(self) -> None:
        """Output is normalized after successful generation + validation."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        # Data with unsorted keys and unnormalized enums
        data = {
            "z_field": 1,
            "a_field": 2,
            "narrative_rules": {"tone": "DARK-FANTASY"},
            "entities": {
                "characters": [
                    {"id": "char_02", "role": "Wise Healer"},
                    {"id": "char_01", "role": "Reluctant Hero"},
                ]
            },
        }
        step = SimpleStep(generator=MockGenerator(data))
        output = await step.run(ctx)

        # Keys should be sorted
        keys = list(output.data.keys())
        assert keys[0] == "a_field"
        # Tone should be normalized
        assert output.data["narrative_rules"]["tone"] == "dark_fantasy"
        # Characters should be sorted by id
        ids = [c["id"] for c in output.data["entities"]["characters"]]
        assert ids == ["char_01", "char_02"]

    @pytest.mark.asyncio
    async def test_feedback_cleared_on_success(self) -> None:
        """Context feedback is cleared after successful generation."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.add_feedback(["old feedback"])

        step = SimpleStep(generator=MockGenerator({"ok": True}))
        await step.run(ctx)

        assert len(ctx.feedback) == 0

    @pytest.mark.asyncio
    async def test_step_output_has_step_name(self) -> None:
        """StepOutput carries the step name."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        step = SimpleStep(generator=MockGenerator({"ok": True}))
        output = await step.run(ctx)
        assert output.step_name == "test_step"


class TestStepOutput:
    """StepOutput dataclass tests."""

    def test_step_output_defaults(self) -> None:
        output = StepOutput(data={"key": "value"}, step_name="world_builder")
        assert output.data == {"key": "value"}
        assert output.step_name == "world_builder"
        assert output.artifact_id is None

    def test_step_output_with_artifact_id(self) -> None:
        output = StepOutput(
            data={"key": "value"},
            step_name="world_builder",
            artifact_id="world_a1b2c3d4",
        )
        assert output.artifact_id == "world_a1b2c3d4"


class TestPipelineError:
    """PipelineError exception tests."""

    def test_pipeline_error_message(self) -> None:
        error = PipelineError(
            step_name="world_builder",
            attempts=4,
            errors=["Missing field", "Invalid ID"],
        )
        assert "world_builder" in str(error)
        assert "4" in str(error)
        assert error.errors == ["Missing field", "Invalid ID"]
