"""Pipeline layer — error taxonomy, domain events, and execution contracts.

Phase 5.5F: Structured error types distinguish retryable generation errors
from terminal configuration/resource defects. Typed domain events provide
observability without free-form string parsing.
"""

from __future__ import annotations

from .errors import (
    ConfigurationError,
    DependencyError,
    GenerationError,
    ModelLoadError,
    PackageValidationError,
    PersistenceError,
    ResourceError,
    StoryTellerError,
    ValidationError,
    is_retryable,
    is_terminal,
)
from .events import (
    ArtifactCommitted,
    CheckpointSaved,
    DomainEvent,
    EventSink,
    InMemoryEventSink,
    ItemQuarantined,
    JsonlEventSink,
    ModelLoaded,
    ModelUnloaded,
    NullEventSink,
    PipelineCompleted,
    PipelineFailed,
    PipelineStarted,
    StepCompleted,
    StepFailed,
    StepRetrying,
    StepStarted,
    ValidationFailed,
)

__all__ = [
    # Errors
    "StoryTellerError",
    "ConfigurationError",
    "DependencyError",
    "ResourceError",
    "GenerationError",
    "ModelLoadError",
    "ValidationError",
    "PersistenceError",
    "PackageValidationError",
    "is_retryable",
    "is_terminal",
    # Events
    "DomainEvent",
    "PipelineStarted",
    "PipelineCompleted",
    "PipelineFailed",
    "ModelLoaded",
    "ModelUnloaded",
    "StepStarted",
    "StepCompleted",
    "StepFailed",
    "StepRetrying",
    "ValidationFailed",
    "ArtifactCommitted",
    "ItemQuarantined",
    "CheckpointSaved",
    # EventSink (Phase 5.6J)
    "EventSink",
    "JsonlEventSink",
    "InMemoryEventSink",
    "NullEventSink",
]
