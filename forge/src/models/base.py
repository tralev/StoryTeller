"""Abstract PipelineStep — base class for all generation steps.

Each step follows: Generator → Validator → Normalizer → Commit.

PipelineStep is generic over the generator type T.
Subclasses declare their generator type explicitly:
  - PipelineStep[TextGenerator] for text-based steps
  - PipelineStep[ImageGenerator] for image generation
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from ..config import AppConfig
from ..interfaces import ValidationResult, Validator
from ..job_queue import FailurePolicy, PipelineContext
from ..normalizer import Normalizer

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


class PipelineError(Exception):
    """Raised when a pipeline step fails after max retries."""

    def __init__(self, step_name: str, attempts: int, errors: list[str]) -> None:
        self.step_name = step_name
        self.attempts = attempts
        self.errors = errors
        super().__init__(
            f"Step '{step_name}' failed after {attempts} attempts: {errors}"
        )


class PipelineStep(ABC, Generic[T]):
    """Abstract base for all pipeline generation steps.

    Subclasses implement generate() and optionally validate().
    The run() method orchestrates the Generator → Validator → Normalizer → Commit flow
    with retry logic.

    Generic over T: the generator type (TextGenerator, ImageGenerator, etc.).
    """

    MAX_RETRIES = 3

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
        """Generate output for this step.

        Subclasses implement the specific generation logic:
        - Build the prompt from Jinja2 template
        - Call self.generator.generate(prompt, schema)
        - Wrap result in StepOutput

        Args:
            context: Pipeline context with accumulated outputs and state.

        Returns:
            StepOutput with the generated data.
        """
        ...

    async def validate(self, output: StepOutput, context: PipelineContext) -> ValidationResult:
        """Validate the generated output.

        Override in subclasses for step-specific validation.
        Default: no-op (always valid).

        Args:
            output: The generated output to validate.
            context: Pipeline context for cross-reference checking.

        Returns:
            ValidationResult.
        """
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

        Args:
            context: Pipeline context.

        Returns:
            StepOutput with normalized data.

        Raises:
            PipelineError: If all retry attempts fail.
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
                raise
            except Exception as e:
                errors = [str(e)]
                if attempt <= self.MAX_RETRIES:
                    context.add_feedback([str(e)])
                    continue
                raise PipelineError(self.name, attempt, errors) from e

        # Should not reach here, but just in case
        raise PipelineError(self.name, self.MAX_RETRIES + 1, errors)
