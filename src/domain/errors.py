"""Public structured error record independent of exception implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class ErrorRecord:
    code: str
    message: str
    retryable: bool
    scope: Literal["run", "step", "item"] = "run"
    step_id: str | None = None
    item_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_exception(cls, error: BaseException) -> "ErrorRecord":
        from ..pipeline.errors import StoryTellerError
        if isinstance(error, StoryTellerError):
            return cls(
                code=error.code, message=str(error), retryable=error.retryable,
                details=dict(error.details),
            )
        return cls(code="ERR_000", message=str(error), retryable=False)
