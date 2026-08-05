"""Typed execution context for the v2-ready pipeline boundary."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..artifact_store import ArtifactStore
from ..config import AppConfig
from ..domain.run_spec import RunSpec
from .events import EventSink, NullEventSink


class CancellationToken:
    """Cooperative cancellation shared by runner and long-running steps."""

    def __init__(self) -> None:
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def cancel(self) -> None:
        self._cancelled = True

    def raise_if_cancelled(self) -> None:
        if self._cancelled:
            raise asyncio.CancelledError("generation cancelled")


@dataclass
class RunContext:
    """Single typed value passed to every production pipeline step."""

    run_id: str
    spec: RunSpec
    config: AppConfig | None = None
    output_dir: str | None = None
    artifacts: ArtifactStore = field(default_factory=ArtifactStore)
    events: EventSink = field(default_factory=NullEventSink)
    cancellation: CancellationToken = field(default_factory=CancellationToken)
    feedback: list[str] = field(default_factory=list)
    checkpoint_store: Any = None
    # Operational-only state retained during the v1 packaging island. Generation
    # inputs (title, tone, temperature and world settings) are forbidden here.
    state: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.output_dir is not None:
            self.artifacts = ArtifactStore(output_dir=self.output_dir)

    @property
    def seed(self) -> int:
        return self.spec.seed

    @property
    def title(self) -> str:
        return self.spec.title

    @property
    def tone(self) -> str:
        return self.spec.tone

    @property
    def temperature(self) -> float:
        return self.spec.temperature

    @property
    def outputs(self) -> ArtifactStore:
        return self.artifacts

    def add_feedback(self, errors: list[str]) -> None:
        self.feedback.extend(errors)

    def clear_feedback(self) -> None:
        self.feedback.clear()
