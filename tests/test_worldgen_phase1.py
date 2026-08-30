from __future__ import annotations

import hashlib
import json
import operator
import struct
from pathlib import Path

import pytest

from src.domain.run_spec import WorldSpec
from src.worldgen.artifacts import (
    MAX_GRID_CHUNK_AXIS,
    MAX_GRID_HEADER_BYTES,
    ArtifactDependency,
    ArtifactId,
    ChunkCoordinate,
    DependencyGraph,
    FrozenMap,
    FrozenSequence,
    GridChunk,
    ProducerFingerprint,
    WorldArtifact,
    WorldArtifactRepository,
    artifact_identity_digest,
    canonical_json,
)
from src.worldgen.grid import LocalCoordinate, WorldCoordinate
from src.worldgen.physical_pipeline import PhysicalStageCommit, PhysicalWorldResult
from src.worldgen.stages import (
    DiagnosticSeverity,
    StageDependencies,
    StageInputs,
    StageOutput,
    StageRunResult,
    StageValidationResult,
    WorldDiagnostic,
    WorldStageRunner,
)


def test_canonical_json_and_envelope_are_order_independent() -> None:
    assert canonical_json({"b": 2, "a": 1}) == b'{"a":1,"b":2}'
    left = WorldArtifact.build("terrain", {"b": 2, "a": 1}, producer_fingerprint="v1")
    right = WorldArtifact.build("terrain", {"a": 1, "b": 2}, producer_fingerprint="v1")
    assert left == right


def test_dependency_closure_and_cycle_detection() -> None:
    graph = DependencyGraph({"terrain": (), "climate": ("terrain",), "biomes": ("climate",)})
    assert graph.invalidation_closure({"terrain"}) == {"terrain", "climate", "biomes"}
    with pytest.raises(ValueError, match="cycle"):
        DependencyGraph({"a": ("b",), "b": ("a",)})


def test_atomic_world_repository_detects_tampering(tmp_path) -> None:
    repository = WorldArtifactRepository(tmp_path)
    artifact = WorldArtifact.build("terrain", {"cells": [1, 2]}, producer_fingerprint="v1")
    path = repository.put(artifact)
    assert repository.load_verified("terrain").artifact_id == artifact.artifact_id
    path.write_text(path.read_text().replace("[1,2]", "[2,1]"))
    with pytest.raises(ValueError, match="WG-HASH"):
        repository.load_verified("terrain")


def test_artifact_payload_is_deeply_immutable_before_and_after_round_trip(tmp_path) -> None:
    source = {"nested": {"values": [1, 2]}}
    artifact = WorldArtifact.build("terrain", source, producer_fingerprint="v1")
    source["nested"]["values"].append(3)
    assert canonical_json(artifact.payload) == b'{"nested":{"values":[1,2]}}'
    assert isinstance(artifact.payload, FrozenMap)
    nested = artifact.payload["nested"]
    assert isinstance(nested, FrozenMap)
    values = nested["values"]
    assert isinstance(values, FrozenSequence)
    with pytest.raises(TypeError):
        operator.setitem(nested, "new", 1)
    with pytest.raises(AttributeError):
        getattr(values, "append")(3)

    repository = WorldArtifactRepository(tmp_path)
    repository.put(artifact)
    loaded = repository.load_verified("terrain")
    assert loaded == artifact
    assert canonical_json(loaded.payload) == canonical_json(artifact.payload)


def test_artifact_identity_dependency_and_producer_contracts() -> None:
    upstream = WorldArtifact.build("terrain", {"width": 32}, producer_fingerprint="terrain-v1")
    artifact = WorldArtifact.build(
        "climate",
        {"temperature": 12_000},
        depends_on=(upstream.artifact_id,),
        producer_fingerprint=ProducerFingerprint("climate-v1"),
    )
    assert isinstance(artifact.artifact_id, ArtifactId)
    assert isinstance(artifact.depends_on[0], ArtifactDependency)
    assert isinstance(artifact.producer_fingerprint, ProducerFingerprint)
    with pytest.raises(ValueError, match="ARTIFACT-ID"):
        ArtifactId("terrain_mutable-name")
    with pytest.raises(ValueError, match="PRODUCER-FINGERPRINT"):
        ProducerFingerprint("contains spaces")
    with pytest.raises(ValueError, match="duplicate"):
        WorldArtifact.build(
            "climate",
            {},
            depends_on=(upstream.artifact_id, upstream.artifact_id),
            producer_fingerprint="climate-v1",
        )


def test_artifact_identity_cross_platform_vectors_and_domain_separation() -> None:
    fixture = json.loads(
        Path("tests/fixtures/worldgen/artifact_identity_diagnostics.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        hashlib.sha256(canonical_json(fixture["payload"])).hexdigest() == fixture["payload_sha256"]
    )
    ids = []
    for vector in fixture["vectors"]:
        digest = artifact_identity_digest(
            vector["kind"],
            fixture["payload_sha256"],
            vector["depends_on"],
            vector["producer_fingerprint"],
        )
        built = WorldArtifact.build(
            vector["kind"],
            fixture["payload"],
            depends_on=tuple(vector["depends_on"]),
            producer_fingerprint=vector["producer_fingerprint"],
        )
        assert digest == vector["identity_sha256"]
        assert built.artifact_id == vector["artifact_id"]
        ids.append(built.artifact_id)
    assert len(ids) == len(set(ids))

    left = "terrain_00000000000000000000000000000000"
    right = "terrain_11111111111111111111111111111111"
    ordered = WorldArtifact.build(
        "climate",
        fixture["payload"],
        depends_on=(left, right),
        producer_fingerprint="producer:v1",
    )
    reversed_dependencies = WorldArtifact.build(
        "climate",
        fixture["payload"],
        depends_on=(right, left),
        producer_fingerprint="producer:v1",
    )
    assert ordered == reversed_dependencies


def test_physical_stage_commit_is_frozen_canonical_input() -> None:
    from dataclasses import FrozenInstanceError

    upstream = WorldArtifact.build("terrain", {}, producer_fingerprint="terrain-v1")
    source = {"cells": [1, 2]}
    stage = PhysicalStageCommit(
        "climate",
        source,
        (upstream,),
        ProducerFingerprint("climate-v1"),
    )
    source["cells"].append(3)
    assert canonical_json(stage.payload) == b'{"cells":[1,2]}'
    with pytest.raises(FrozenInstanceError):
        stage.kind = "weather"


def test_wg_kernel_005_contracts_are_immutable_and_typed() -> None:
    immutable_contracts = (
        WorldSpec,
        StageDependencies,
        StageInputs,
        StageOutput,
        StageRunResult,
        StageValidationResult,
        WorldDiagnostic,
        WorldArtifact,
        PhysicalStageCommit,
        PhysicalWorldResult,
        WorldCoordinate,
        LocalCoordinate,
        ChunkCoordinate,
        GridChunk,
    )
    assert all(contract.__dataclass_params__.frozen for contract in immutable_contracts)
    assert issubclass(ArtifactId, str)
    assert issubclass(ArtifactDependency, ArtifactId)
    assert issubclass(ProducerFingerprint, str)


def test_physical_world_result_is_frozen_mapping() -> None:
    from dataclasses import FrozenInstanceError

    result = PhysicalWorldResult("world_index_abc", 14, 7, 6, 5)
    assert result["world_index"] == "world_index_abc"
    assert {**result} == result.to_dict()
    assert canonical_json(result) == (
        b'{"artifacts":14,"maps":5,"regions":7,"routes":6,"world_index":"world_index_abc"}'
    )
    with pytest.raises(FrozenInstanceError):
        result.maps = 9


def test_grid_chunk_round_trip_is_canonical() -> None:
    chunk = GridChunk("elevation", 2, 3, 2, 2, (-10, 0, 20, 30))
    assert GridChunk.decode(chunk.encode()) == chunk


def test_coordinate_spaces_are_explicit_immutable_and_nonnegative() -> None:
    from dataclasses import FrozenInstanceError

    world = WorldCoordinate(4, 7)
    local = LocalCoordinate(4, 7, 2)
    chunk = ChunkCoordinate(1, 3)
    assert (world.x, local.z, chunk.y) == (4, 2, 3)
    with pytest.raises(FrozenInstanceError):
        world.x = 5
    for constructor, values in (
        (WorldCoordinate, (-1, 0)),
        (LocalCoordinate, (0, 0, -1)),
        (ChunkCoordinate, (0, -1)),
    ):
        with pytest.raises(ValueError, match="coordinate"):
            constructor(*values)


def test_grid_chunk_cross_platform_and_malformed_vectors() -> None:
    fixture = json.loads(
        Path("tests/fixtures/worldgen/grid_chunk_diagnostics.json").read_text(encoding="utf-8")
    )
    valid = fixture["valid"]
    chunk = GridChunk(
        valid["layer"],
        valid["chunk_x"],
        valid["chunk_y"],
        valid["width"],
        valid["height"],
        tuple(valid["values"]),
    )
    encoded = bytes.fromhex(valid["encoded_hex"])
    assert hashlib.sha256(encoded).hexdigest() == valid["sha256"]
    assert chunk.encode() == encoded
    assert GridChunk.decode(encoded) == chunk

    with pytest.raises(ValueError, match="coordinates"):
        GridChunk("elevation", -1, 0, 1, 1, (0,))
    with pytest.raises(ValueError, match="1..256"):
        GridChunk("elevation", 0, 0, MAX_GRID_CHUNK_AXIS + 1, 1, (0,) * (MAX_GRID_CHUNK_AXIS + 1))
    with pytest.raises(ValueError, match="32-bit"):
        GridChunk("elevation", 0, 0, 1, 1, (1 << 31,))
    with pytest.raises(ValueError, match="header exceeds"):
        GridChunk.decode(struct.pack(">I", MAX_GRID_HEADER_BYTES + 1))
    with pytest.raises(ValueError, match="truncated header"):
        GridChunk.decode(b"\x00\x00\x00\x20{}")
    noncanonical_header = json.dumps(
        {
            "format": "storyteller.grid.i32be.v1",
            "layer": "elevation",
            "chunk_x": 0,
            "chunk_y": 0,
            "width": 1,
            "height": 1,
        }
    ).encode("utf-8")
    with pytest.raises(ValueError, match="noncanonical"):
        GridChunk.decode(
            struct.pack(">I", len(noncanonical_header)) + noncanonical_header + struct.pack(">i", 0)
        )


def test_world_stage_checkpoints_skip_matching_work() -> None:
    class Stage:
        id = "terrain"
        requires: tuple[str, ...] = ()
        max_retries = 0
        calls = 0

        def generate(self, inputs: StageInputs):
            self.calls += 1
            assert isinstance(inputs.dependencies, StageDependencies)
            return {"width": inputs.spec.width}

        def validate(self, value, spec) -> StageValidationResult:
            assert value["width"] == spec.width
            return StageValidationResult()

    stage = Stage()
    checkpoints = {}
    runner = WorldStageRunner((stage,), "v1", checkpoints=checkpoints)
    result = runner.run(WorldSpec(width=32, height=32))
    second = runner.run(WorldSpec(width=32, height=32))
    assert stage.calls == 1
    assert isinstance(result, StageRunResult)
    assert result["terrain"] == second["terrain"]


def test_stage_contracts_are_immutable_canonical_and_typed() -> None:
    from dataclasses import FrozenInstanceError

    artifact = WorldArtifact.build("terrain", {"width": 32}, producer_fingerprint="v1")
    dependencies = StageDependencies.from_mapping({"terrain": artifact})
    inputs = StageInputs(WorldSpec(width=32, height=32), dependencies)
    diagnostic = WorldDiagnostic(
        "WG-TERRAIN-COVERAGE",
        DiagnosticSeverity.WARNING,
        "coverage is sparse",
        "cell:7",
    )
    validation = StageValidationResult((diagnostic,))
    assert validation.is_valid
    assert canonical_json(validation) == (
        b'{"diagnostics":[{"code":"WG-TERRAIN-COVERAGE","message":"coverage is sparse",'
        b'"severity":"warning","subject_id":"cell:7"}]}'
    )
    with pytest.raises(FrozenInstanceError):
        inputs.spec = WorldSpec()
    with pytest.raises(TypeError):
        dependencies["terrain"] = artifact  # type: ignore[index]
    with pytest.raises(ValueError, match="canonically sorted"):
        StageValidationResult(
            (
                WorldDiagnostic("WG-Z", DiagnosticSeverity.INFO, "z"),
                WorldDiagnostic("WG-A", DiagnosticSeverity.INFO, "a"),
            )
        )


def test_stage_validation_errors_are_structured() -> None:
    result = StageValidationResult(
        (WorldDiagnostic("WG-TERRAIN-INVALID", DiagnosticSeverity.ERROR, "terrain invalid"),)
    )
    assert not result.is_valid
    with pytest.raises(ValueError, match="WG-TERRAIN-INVALID"):
        result.require_valid("terrain")


def test_world_resource_preflight() -> None:
    spec = WorldSpec(width=32, height=32)
    spec.preflight(max_ram_bytes=spec.estimated_working_set_bytes())
    with pytest.raises(ValueError, match="WG-BUDGET-RAM"):
        spec.preflight(max_ram_bytes=1)
