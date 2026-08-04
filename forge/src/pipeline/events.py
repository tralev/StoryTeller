"""Typed domain events for pipeline observability.

Phase 5.5F: Replaces free-form JSON string entries in the event log
with structured dataclasses. Each event type has explicit fields
rather than arbitrary **kwargs. Serialized to JSONL for storage.

Usage:
    from src.pipeline.events import StepStarted, StepCompleted

    event = StepStarted(run_id="run_01", step_id="world_builder", attempt=1)
    logger.log(event.to_json())  # → {"type": "step_started", ...}
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DomainEvent:
    """Base class for all pipeline events."""

    run_id: str
    timestamp: str = field(default_factory=lambda: time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(),
    ))

    @property
    def event_type(self) -> str:
        """Derive event type from the class name: StepStarted → step_started."""
        import re
        name = type(self).__name__
        return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSONL output."""
        result = {"type": self.event_type, **self.__dict__}
        # Remove internal fields
        return {k: v for k, v in result.items() if not k.startswith("_")}

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)


# ── Pipeline lifecycle ──────────────────────────────────────────────────


@dataclass
class PipelineStarted(DomainEvent):
    """Pipeline execution has begun."""

    seed: int = 0
    title: str = ""
    tone: str = ""


@dataclass
class PipelineCompleted(DomainEvent):
    """Pipeline finished successfully."""

    package_path: str = ""
    content_hash: str = ""
    total_duration_s: float = 0.0


@dataclass
class PipelineFailed(DomainEvent):
    """Pipeline terminated with errors."""

    errors: list[str] = field(default_factory=list)


# ── Model lifecycle ─────────────────────────────────────────────────────


@dataclass
class ModelLoaded(DomainEvent):
    """A model was loaded into memory."""

    model_name: str = ""
    ram_mb: int = 0


@dataclass
class ModelUnloaded(DomainEvent):
    """A model was unloaded from memory."""

    model_name: str = ""


# ── Step execution ──────────────────────────────────────────────────────


@dataclass
class StepStarted(DomainEvent):
    """A pipeline step has started executing."""

    step_id: str = ""
    attempt: int = 1


@dataclass
class StepCompleted(DomainEvent):
    """A pipeline step completed successfully."""

    step_id: str = ""
    artifact_key: str = ""
    duration_s: float = 0.0


@dataclass
class StepFailed(DomainEvent):
    """A pipeline step failed."""

    step_id: str = ""
    error_code: str = "ERR_000"
    error_message: str = ""
    retryable: bool = False


@dataclass
class StepRetrying(DomainEvent):
    """A pipeline step is being retried after failure."""

    step_id: str = ""
    attempt: int = 1
    feedback: list[str] = field(default_factory=list)


@dataclass
class ValidationFailed(DomainEvent):
    """Validation rejected generated content."""

    step_id: str = ""
    error_count: int = 0
    errors: list[str] = field(default_factory=list)


# ── Artifact & checkpoint ───────────────────────────────────────────────


@dataclass
class ArtifactCommitted(DomainEvent):
    """An artifact was committed to storage."""

    step_id: str = ""
    artifact_key: str = ""
    artifact_id: str = ""


@dataclass
class ItemQuarantined(DomainEvent):
    """A single item was quarantined (batch processing)."""

    step_id: str = ""
    item_id: str = ""
    reason: str = ""


@dataclass
class CheckpointSaved(DomainEvent):
    """A checkpoint was saved."""

    step_id: str = ""
    phase: int = 0
