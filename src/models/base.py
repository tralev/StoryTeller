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
    StoryTellerError,
    is_retryable,
)
from ..pipeline.policy import ExecutionPolicy  # Phase 5.6G

# Generator type variable — bound by subclasses
T = TypeVar("T")

# Data payload type variable for StepOutput (Phase 5.6N N2)
DataT = TypeVar("DataT")


class StepOutput(Generic[DataT]):
    """Output from a pipeline step.

    Phase 5.6N N2: Generic over the data payload type so steps that
    produce typed artifacts can carry that type through the pipeline
    (e.g. ``StepOutput[ManifestDict]``). Bare ``StepOutput`` remains
    valid and is equivalent to ``StepOutput[dict[str, Any]]``.
    """

    def __init__(
        self,
        data: DataT,
        step_name: str,
        artifact_id: str | None = None,
        validator_status: str | None = None,
    ) -> None:
        self.data: DataT = data
        self.step_name = step_name
        self.artifact_id = artifact_id
        self.validator_status: str | None = validator_status  # Phase 5.6E


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

    Phase 5.6G: MAX_RETRIES and failure_policy now come from ExecutionPolicy,
    not hardcoded constants. The policy is sourced from PipelineConfig.
    """

    # Canonical key used to store output in context.outputs (e.g., "bible", "story")
    output_key: str | None = None

    def __init__(
        self,
        name: str,
        generator: T,
        validator: Validator | None = None,
        config: AppConfig | None = None,
        failure_policy: FailurePolicy = FailurePolicy.ABORT,
        policy: ExecutionPolicy | None = None,  # Phase 5.6G
    ) -> None:
        self.name = name
        self.generator: T = generator
        self.validator = validator
        self.config = config
        self.policy = policy or ExecutionPolicy.default()  # Phase 5.6G
        # The policy is the single source of truth for failure behavior
        # (the legacy failure_policy argument is superseded by it).
        self.failure_policy = self.policy.failure_policy
        self.normalizer = Normalizer()

    @abstractmethod
    async def generate(self, context: PipelineContext) -> StepOutput[dict[str, Any]]:
        """Generate output for this step."""
        ...

    async def validate(
        self, output: StepOutput[dict[str, Any]], context: PipelineContext
    ) -> ValidationResult:
        """Validate the generated output. Default: pass-through (always valid)."""
        if self.validator is None:
            from ..interfaces.validator import ValidatorStatus

            return ValidationResult(
                is_valid=True,
                status=ValidatorStatus.SKIPPED,
            )

        result = await self.validator.validate(
            output.data,
            {"schema": None, "context": context},
        )
        return result

    async def run(self, context: PipelineContext) -> StepOutput[dict[str, Any]]:
        """Execute the full pipeline step with retry logic.

        Flow:
        1. Generate → calls self.generate(context)
        2. Validate → calls self.validate(output, context)
        3. If invalid: retry with error feedback (up to policy.max_retries)
        4. Normalize → self.normalizer.process(data)
        5. Return StepOutput

        Terminal errors (config, resource, persistence) abort immediately.
        Retryable errors (generation, validation) retry with feedback.

        Phase 5.6G: Retry count comes from ExecutionPolicy.max_retries.

        Raises:
            PipelineError: If all retries are exhausted.
            StoryTellerError: For terminal errors (no retry).
        """
        errors: list[str] = []
        max_retries = self.policy.max_retries

        for attempt in range(1, max_retries + 2):
            try:
                # 1. Generate
                output = await self.generate(context)

                # 2. Validate
                validation = await self.validate(output, context)
                output.validator_status = validation.status.value  # Phase 5.6E
                if not validation.is_valid:
                    errors = validation.errors
                    if attempt <= max_retries:
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
                    if attempt <= max_retries:
                        context.add_feedback([str(e)])
                        continue
                    raise PipelineError(self.name, attempt, errors) from e
                else:
                    # Terminal error — abort immediately
                    raise
            except Exception as e:
                # Unknown exceptions: retry (may be transient). Phase 5.6 W3:
                # retry exactly per policy — same budget as typed retryable
                # errors (max_retries excludes the first attempt).
                errors = [str(e)]
                if attempt <= max_retries:
                    context.add_feedback([str(e)])
                    continue
                raise PipelineError(self.name, attempt, errors) from e

        # Should not reach here, but just in case
        raise PipelineError(self.name, max_retries + 1, errors)
