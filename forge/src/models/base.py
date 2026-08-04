"""Abstract PipelineStep — base class for all generation steps.

Each step follows: Generator → Validator → Normalizer → Commit.

PipelineStep is generic over the generator type T.
Subclasses declare their generator type explicitly:
  - PipelineStep[TextGenerator] for text-based steps
  - PipelineStep[ImageGenerator] for image generation

Phase 5.5F: run() now uses structured error types from pipeline.errors
to distinguish retryable generation/validation errors from terminal
configuration/resource defects. Terminal errors abort immediately
without wasting retries.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from ..config import AppConfig
from ..interfaces import ValidationResult, Validator
from ..job_queue import FailurePolicy, PipelineContext
from ..normalizer import Normalizer
from ..pipeline.errors import (
    GenerationError,
    StoryTellerError,
    ValidationError,
    is_retryable,
)

# Generator type variable — bound by subclasses
T = TypeVar("T")


class StepOutput:
    """Output from a pipeline step."""

    def __init__(
        self,
        data: dict[str, Any],
        step_name: str,
        artifact_id: str | None = None,
    ) -> None:
        self.data = data
        self.step_name = step_name
        self.artifact_id = artifact_id


class PipelineError(StoryTellerError):
    """Raised when a pipeline step fails after max retries."""

    def __init__(self, step_name: str, attempts: int, errors: list[str]) -> None:
        self.step_name = step_name
        self.attempts = attempts
        self.errors = errors
        super().__init__(
            f"Step '{step_name}' failed after {attempts} attempts: {errors}",
            code="PIP_001",
            retryable=False,
            details={"step": step_name, "attempts": attempts, "errors": errors},
        )


class PipelineStep(ABC, Generic[T]):
    """Abstract base for all pipeline generation steps.

    Generates, validates, normalizes, and commits with retry logic.
    Uses structured error types: retryable errors get retried,
    terminal errors abort immediately.

    Generic over T: the generator type (TextGenerator, ImageGenerator, etc.).
    """

    MAX_RETRIES = 3

    # Canonical key used to store output in context.outputs (e.g., "bible", "story")
    output_key: str | None = None

    def __init__(
        self,
        name: str,
        generator: T,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.ABORT,
    ) -> None:
        self.name = name
        self.generator: T = generator
        self.validator = validator
        self.config = config
        self.failure_policy = failure_policy
        self.normalizer = Normalizer()

    @abstractmethod
    async def generate(self, context: PipelineContext) -> StepOutput:
        """Generate output for this step."""
        ...

    async def validate(self, output: StepOutput, context: PipelineContext) -> ValidationResult:
        """Validate the generated output. Default: pass-through (always valid)."""
        if self.validator is None:
            return ValidationResult(is_valid=True)

        return await self.validator.validate(
            output.data,
            {"schema": None, "context": context},
        )

    async def run(self, context: PipelineContext) -> StepOutput:
        """Execute the full pipeline step with retry logic.

        Flow:
        1. Generate → calls self.generate(context)
        2. Validate → calls self.validate(output, context)
        3. If invalid: retry with error feedback (up to MAX_RETRIES)
        4. Normalize → self.normalizer.process(data)
        5. Return StepOutput

        Terminal errors (config, resource, persistence) abort immediately.
        Retryable errors (generation, validation) retry with feedback.

        Raises:
            PipelineError: If all retries are exhausted.
            StoryTellerError: For terminal errors (no retry).
        """
        errors: list[str] = []

        for attempt in range(1, self.MAX_RETRIES + 2):
            try:
                # 1. Generate
                output = await self.generate(context)

                # 2. Validate
                validation = await self.validate(output, context)
                if not validation.is_valid:
                    errors = validation.errors
                    if attempt <= self.MAX_RETRIES:
                        context.add_feedback(validation.errors)
                        continue
                    else:
                        raise PipelineError(self.name, attempt, errors)

                # 3. Normalize
                output.data = self.normalizer.process(output.data)

                # 4. Clear feedback on success
                context.clear_feedback()

                return output

            except PipelineError:
                raise  # Already terminal — don't retry
            except StoryTellerError as e:
                if is_retryable(e):
                    # Generation/validation error — retry with feedback
                    errors = [str(e)]
                    if attempt <= self.MAX_RETRIES:
                        context.add_feedback([str(e)])
                        continue
                    raise PipelineError(self.name, attempt, errors) from e
                else:
                    # Terminal error — abort immediately
                    raise
            except Exception as e:
                # Unknown exceptions: retry (may be transient)
                errors = [str(e)]
                if attempt <= self.MAX_RETRIES:
                    context.add_feedback([str(e)])
                    continue
                raise PipelineError(self.name, attempt, errors) from e

        # Should not reach here, but just in case
        raise PipelineError(self.name, self.MAX_RETRIES + 1, errors)
