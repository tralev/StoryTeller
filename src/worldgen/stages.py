"""Declarative world stages with immutable inputs, outputs, and diagnostics."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, Protocol, TypeVar

from ..domain.run_spec import WorldSpec
from ..pipeline.context import CancellationToken
from ..pipeline.events import EventSink, NullEventSink, StepCompleted, StepRetrying, StepStarted
from .artifacts import DependencyGraph, ProducerFingerprint, WorldArtifact, canonical_json

T = TypeVar("T")
_DIAGNOSTIC_CODE = re.compile(r"^WG-[A-Z][A-Z0-9-]*$")


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class WorldDiagnostic:
    """Stable machine-readable outcome from stage validation or execution."""

    code: str
    severity: DiagnosticSeverity
    message: str
    subject_id: str | None = None

    def __post_init__(self) -> None:
        if not _DIAGNOSTIC_CODE.fullmatch(self.code):
            raise ValueError("diagnostic code must use the WG-* grammar")
        if not self.message.strip():
            raise ValueError("diagnostic message cannot be empty")


@dataclass(frozen=True)
class StageValidationResult:
    diagnostics: tuple[WorldDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        canonical = tuple(
            sorted(
                self.diagnostics,
                key=lambda item: (
                    item.code,
                    item.severity.value,
                    item.message,
                    item.subject_id or "",
                ),
            )
        )
        if canonical != self.diagnostics:
            raise ValueError("stage diagnostics must be canonically sorted")

    @property
    def is_valid(self) -> bool:
        return not any(item.severity is DiagnosticSeverity.ERROR for item in self.diagnostics)

    def require_valid(self, stage_id: str) -> None:
        if not self.is_valid:
            codes = ",".join(
                item.code for item in self.diagnostics if item.severity is DiagnosticSeverity.ERROR
            )
            raise ValueError(f"WG-STAGE-VALIDATION: {stage_id} failed [{codes}]")


@dataclass(frozen=True)
class StageDependencies(Mapping[str, WorldArtifact[object]]):
    """Canonical immutable dependency collection presented to a stage."""

    artifacts: tuple[tuple[str, WorldArtifact[object]], ...] = ()

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, WorldArtifact[object]],
    ) -> StageDependencies:
        return cls(tuple(sorted(values.items())))

    def __post_init__(self) -> None:
        keys = tuple(key for key, _ in self.artifacts)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("stage dependencies must be unique and canonically sorted")

    def __getitem__(self, key: str) -> WorldArtifact[object]:
        for candidate, artifact in self.artifacts:
            if candidate == key:
                return artifact
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self.artifacts)

    def __len__(self) -> int:
        return len(self.artifacts)


@dataclass(frozen=True)
class StageInputs:
    spec: WorldSpec
    dependencies: StageDependencies = field(default_factory=StageDependencies)


@dataclass(frozen=True)
class StageOutput:
    stage_id: str
    artifact: WorldArtifact[object]
    validation: StageValidationResult = field(default_factory=StageValidationResult)


@dataclass(frozen=True)
class StageRunResult(Mapping[str, WorldArtifact[object]]):
    """Immutable, canonically ordered result of a stage-DAG execution."""

    outputs: tuple[StageOutput, ...]

    def __post_init__(self) -> None:
        keys = tuple(output.stage_id for output in self.outputs)
        if keys != tuple(sorted(keys)) or len(keys) != len(set(keys)):
            raise ValueError("stage outputs must be unique and canonically sorted")

    def __getitem__(self, key: str) -> WorldArtifact[object]:
        for output in self.outputs:
            if output.stage_id == key:
                return output.artifact
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (output.stage_id for output in self.outputs)

    def __len__(self) -> int:
        return len(self.outputs)


class WorldStage(Protocol, Generic[T]):
    id: str
    requires: tuple[str, ...]
    max_retries: int

    def generate(self, inputs: StageInputs) -> T: ...
    def validate(self, value: T, spec: WorldSpec) -> StageValidationResult: ...


@dataclass
class WorldStageRunner:
    stages: tuple[WorldStage[object], ...]
    producer_fingerprint: ProducerFingerprint | str
    events: EventSink = field(default_factory=NullEventSink)
    run_id: str = "worldgen"
    checkpoints: dict[str, WorldArtifact[object]] | None = None

    def __post_init__(self) -> None:
        self.producer_fingerprint = ProducerFingerprint(self.producer_fingerprint)

    def run(
        self,
        spec: WorldSpec,
        *,
        cancellation: CancellationToken | None = None,
    ) -> StageRunResult:
        DependencyGraph({stage.id: stage.requires for stage in self.stages})
        artifacts: dict[str, WorldArtifact[object]] = {}
        validations: dict[str, StageValidationResult] = {}
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
                validations[stage.id] = StageValidationResult()
                continue
            self.events.emit(StepStarted(run_id=self.run_id, step_id=stage.id))
            last_error: Exception | None = None
            for attempt in range(stage.max_retries + 1):
                try:
                    inputs = StageInputs(
                        spec,
                        StageDependencies.from_mapping(
                            {key: artifacts[key] for key in stage.requires}
                        ),
                    )
                    value = stage.generate(inputs)
                    validation = stage.validate(value, spec)
                    validation.require_valid(stage.id)
                    artifacts[stage.id] = WorldArtifact.build(
                        stage.id,
                        value,
                        depends_on=dependency_ids,
                        producer_fingerprint=self.producer_fingerprint,
                    )
                    validations[stage.id] = validation
                    checkpointed[stage.id] = artifacts[stage.id]
                    self.events.emit(
                        StepCompleted(
                            run_id=self.run_id,
                            step_id=stage.id,
                            artifact_key=stage.id,
                        )
                    )
                    break
                except Exception as error:
                    last_error = error
                    if attempt < stage.max_retries:
                        self.events.emit(
                            StepRetrying(
                                run_id=self.run_id,
                                step_id=stage.id,
                                attempt=attempt + 2,
                                feedback=[str(error)],
                            )
                        )
            else:
                raise RuntimeError(f"WG-STAGE: {stage.id} failed") from last_error
        return StageRunResult(
            tuple(
                StageOutput(stage_id, artifacts[stage_id], validations[stage_id])
                for stage_id in sorted(artifacts)
            )
        )
