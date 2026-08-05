"""Declarative, retry-bounded world generation stage protocol and runner."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Generic, Protocol, TypeVar

from ..domain.run_spec import WorldSpec
from ..pipeline.context import CancellationToken
from ..pipeline.events import EventSink, NullEventSink, StepCompleted, StepRetrying, StepStarted
from .artifacts import DependencyGraph, WorldArtifact, canonical_json

T = TypeVar("T")


class WorldStage(Protocol, Generic[T]):
    id: str
    requires: tuple[str, ...]
    max_retries: int

    def generate(self, spec: WorldSpec, dependencies: dict[str, WorldArtifact[object]]) -> T: ...
    def validate(self, value: T, spec: WorldSpec) -> None: ...


@dataclass
class WorldStageRunner:
    stages: tuple[WorldStage[object], ...]
    producer_fingerprint: str
    events: EventSink = field(default_factory=NullEventSink)
    run_id: str = "worldgen"
    checkpoints: dict[str, WorldArtifact[object]] | None = None

    def run(
        self, spec: WorldSpec, *, cancellation: CancellationToken | None = None,
    ) -> dict[str, WorldArtifact[object]]:
        DependencyGraph({stage.id: stage.requires for stage in self.stages})
        artifacts: dict[str, WorldArtifact[object]] = {}
        checkpointed = self.checkpoints if self.checkpoints is not None else {}
        spec_id = "world_spec_" + hashlib.sha256(canonical_json(spec)).hexdigest()[:32]
        token = cancellation or CancellationToken()
        for stage in self.stages:
            token.raise_if_cancelled()
            missing = [key for key in stage.requires if key not in artifacts]
            if missing:
                raise ValueError(f"WG-DEPENDENCY: {stage.id} missing {missing}")
            dependency_ids = (spec_id,) + tuple(
                artifacts[key].artifact_id for key in stage.requires
            )
            saved = checkpointed.get(stage.id)
            if (
                saved is not None
                and saved.depends_on == tuple(sorted(dependency_ids))
                and saved.producer_fingerprint == self.producer_fingerprint
            ):
                artifacts[stage.id] = saved
                continue
            self.events.emit(StepStarted(run_id=self.run_id, step_id=stage.id))
            last_error: Exception | None = None
            for attempt in range(stage.max_retries + 1):
                try:
                    value = stage.generate(spec, artifacts)
                    stage.validate(value, spec)
                    artifacts[stage.id] = WorldArtifact.build(
                        stage.id, value,
                        depends_on=dependency_ids,
                        producer_fingerprint=self.producer_fingerprint,
                    )
                    checkpointed[stage.id] = artifacts[stage.id]
                    self.events.emit(StepCompleted(
                        run_id=self.run_id, step_id=stage.id,
                        artifact_key=stage.id,
                    ))
                    break
                except Exception as error:
                    last_error = error
                    if attempt < stage.max_retries:
                        self.events.emit(StepRetrying(
                            run_id=self.run_id, step_id=stage.id,
                            attempt=attempt + 2, feedback=[str(error)],
                        ))
            else:
                raise RuntimeError(f"WG-STAGE: {stage.id} failed") from last_error
        return artifacts
