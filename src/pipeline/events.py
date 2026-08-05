"""Typed domain events for pipeline observability.

Phase 5.5F: Replaces free-form JSON string entries in the event log
with structured dataclasses. Each event type has explicit fields
rather than arbitrary **kwargs. Serialized to JSONL for storage.

Phase 5.6J: EventSink protocol — decouples event emission from storage.
JsonlEventSink writes to disk; InMemoryEventSink captures for tests.

Usage:
    from src.pipeline.events import StepStarted, JsonlEventSink

    sink = JsonlEventSink("tmp/output/pipeline_events.jsonl")
    sink.emit(StepStarted(run_id="run_01", step_id="world_builder"))
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class DomainEvent:
    """Base class for all pipeline events."""

    run_id: str
    sequence: int = 0
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


# ── EventSink protocol & implementations (Phase 5.6J) ────────────────────


@runtime_checkable
class EventSink(Protocol):
    """Protocol for event sinks — anything that can receive DomainEvents.

    Decoupled from storage: JsonlEventSink writes to a file,
    InMemoryEventSink captures for test assertions, and future
    sinks (WebSocket, log aggregator) implement the same interface.
    """

    def emit(self, event: DomainEvent) -> None:
        """Emit a single domain event."""
        ...

    def emit_many(self, events: list[DomainEvent]) -> None:
        """Emit multiple events at once."""
        for e in events:
            self.emit(e)


class JsonlEventSink:
    """Writes domain events to a JSONL file on disk.

    Thread-safe for append-only writes. Creates the parent directory
    if it doesn't exist.

    Usage:
        sink = JsonlEventSink("tmp/output/pipeline_events.jsonl")
        sink.emit(StepStarted(run_id="run_01", step_id="world_builder"))
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._count: int = 0
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def emit(self, event: DomainEvent) -> None:
        self._stamp(event)
        entry = event.to_json()
        with open(self.path, "a") as f:
            f.write(entry + "\n")

    def emit_many(self, events: list[DomainEvent]) -> None:
        if not events:
            return
        with open(self.path, "a") as f:
            for event in events:
                self._stamp(event)
                f.write(event.to_json() + "\n")

    def _stamp(self, event: DomainEvent) -> None:
        self._count += 1
        event.sequence = self._count

    @property
    def event_count(self) -> int:
        return self._count


class InMemoryEventSink:
    """Captures domain events in memory for test assertions.

    Usage:
        sink = InMemoryEventSink()
        sink.emit(StepStarted(run_id="run_01", step_id="world_builder"))
        assert len(sink.events) == 1
        assert sink.events[0].event_type == "step_started"
    """

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def emit(self, event: DomainEvent) -> None:
        event.sequence = len(self.events) + 1
        self.events.append(event)

    def emit_many(self, events: list[DomainEvent]) -> None:
        for event in events:
            self.emit(event)

    def of_type(self, event_type: str) -> list[DomainEvent]:
        """Return all events of a specific type (e.g., 'step_started')."""
        return [e for e in self.events if e.event_type == event_type]

    def clear(self) -> None:
        self.events.clear()


class NullEventSink:
    """Discards all events — used when no sink is configured."""

    def emit(self, event: DomainEvent) -> None:
        pass

    def emit_many(self, events: list[DomainEvent]) -> None:
        pass
