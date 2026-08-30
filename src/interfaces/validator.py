"""Validator interface — validates generated content against rules and schemas.

Phase 5.6E: Added ValidatorStatus to distinguish skipped/unavailable/failed/valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class ValidatorStatus(Enum):
    """Outcome of a validator run.

    Phase 5.6E: Replaces the simple is_valid boolean with a richer
    status that distinguishes WHY validation didn't produce a definitive
    result.
    """

    SKIPPED = "skipped"  # No validator configured
    UNAVAILABLE = "unavailable"  # Validator model could not be loaded
    FAILED = "failed"  # Validation ran and found errors
    VALID = "valid"  # Validation ran and passed


@dataclass
class ValidationResult:
    """Result of a validation check."""

    is_valid: bool
    status: ValidatorStatus = ValidatorStatus.VALID  # Phase 5.6E
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    retry_prompt: str | None = None  # Feedback to inject into next generation attempt

    def __post_init__(self) -> None:
        """Derive status from is_valid if not explicitly set."""
        if self.status == ValidatorStatus.VALID and not self.is_valid:
            object.__setattr__(self, "status", ValidatorStatus.FAILED)


@dataclass
class ConsistencyReport:
    """Report from a consistency check against the World Bible."""

    is_consistent: bool
    status: ValidatorStatus = ValidatorStatus.VALID
    violations: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Derive status from is_consistent if not explicitly set."""
        if self.status == ValidatorStatus.VALID and not self.is_consistent:
            self.status = ValidatorStatus.FAILED


@runtime_checkable
class Validator(Protocol):
    """Validates generated content against rules, schemas, and cross-references.

    Uses a different model than the generator for independent critique.
    """

    provider: str
    model_name: str
    quantization: str

    async def validate(
        self,
        content: dict[str, Any],
        context: dict[str, Any],
    ) -> ValidationResult:
        """Validate content against its schema and business rules.

        Args:
            content: The generated content to validate.
            context: Validation context including schema, bible, and prior outputs.

        Returns:
            ValidationResult with is_valid flag and error details.
        """
        ...

    async def consistency_check(
        self,
        text: str,
        bible: dict[str, Any],
    ) -> ConsistencyReport:
        """Check if text contradicts the World Bible.

        Args:
            text: The generated text to check.
            bible: The World Bible to check against.

        Returns:
            ConsistencyReport with list of violations and suggestions.
        """
        ...

    async def load(self) -> None:
        """Load the model into memory."""
        ...

    async def unload(self) -> None:
        """Unload the model to free RAM."""
        ...

    @property
    def ram_usage_mb(self) -> int:
        """Estimated RAM usage in MB."""
        ...
