"""Pipeline context and failure policy — shared across all pipeline steps.

The JobQueue / worker-pool architecture is retired. PipelineStep.run()
handles Generator → Validator → Normalizer → Commit directly, and the
Orchestrator schedules steps sequentially or via asyncio.gather.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .config import AppConfig


class FailurePolicy(Enum):
    """What to do when a step fails after max retries."""

    ABORT = "abort"  # Stop entire pipeline (default for sequential phases)
    QUARANTINE = "quarantine"  # Skip failed item, continue with others


@dataclass
class PipelineContext:
    """Context passed through every pipeline step. Accumulates outputs and state."""

    run_id: str
    seed: int
    config: AppConfig | None = None
    outputs: dict[str, Any] = field(default_factory=dict)
    feedback: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)

    def add_feedback(self, errors: list[str]) -> None:
        """Accumulate validation errors for retry feedback."""
        self.feedback.extend(errors)

    def clear_feedback(self) -> None:
        """Clear feedback after a successful generation."""
        self.feedback.clear()
