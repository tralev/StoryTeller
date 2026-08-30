"""Shared v2 $defs primitives used by later domain schemas."""

from __future__ import annotations

from pathlib import Path

from scripts.audit_v2_schema_depth import audit_schema_directory
from src.storage.v2_schemas import draft202012_validator, load_v2_schemas, resolve_ref


def test_defs_catalog_is_authored_and_closed() -> None:
    failures = audit_schema_directory(Path("schemas/v2"))
    assert "defs.schema.json" not in failures
    assert "artifact-provenance.schema.json" not in failures


def test_artifact_record_resolves_closed_producer() -> None:
    schemas = load_v2_schemas()
    record = schemas["artifact-provenance.schema.json"]
    producer = resolve_ref(
        str(record["properties"]["producer"]["$ref"]),
        record,
        schemas,
    )
    assert producer["additionalProperties"] is False
    assert set(producer["required"]) == {
        "component",
        "algorithm_version",
        "model",
        "prompt_sha256",
        "schema_sha256",
        "code_revision",
        "fingerprint",
    }


def test_minimal_artifact_record_validates() -> None:
    schema = load_v2_schemas()["artifact-provenance.schema.json"]
    document = {
        "artifact_id": "terrain_" + "a" * 32,
        "kind": "terrain",
        "path": "world/terrain/index.json",
        "sha256": "a" * 64,
        "size_bytes": 1,
        "depends_on": [],
        "producer": {
            "component": "terrain_generator",
            "algorithm_version": 2,
            "model": None,
            "prompt_sha256": None,
            "schema_sha256": "b" * 64,
            "code_revision": "working-tree",
            "fingerprint": "c" * 64,
        },
    }
    draft202012_validator(schema).validate(document)


def test_producer_rejects_extra_properties() -> None:
    schema = load_v2_schemas()["artifact-provenance.schema.json"]
    document = {
        "artifact_id": "terrain_" + "a" * 32,
        "kind": "terrain",
        "path": "world/terrain/index.json",
        "sha256": "a" * 64,
        "size_bytes": 1,
        "depends_on": [],
        "producer": {
            "component": "terrain_generator",
            "algorithm_version": 2,
            "model": None,
            "prompt_sha256": None,
            "schema_sha256": "b" * 64,
            "code_revision": "working-tree",
            "fingerprint": "c" * 64,
            "extra": True,
        },
    }
    errors = list(draft202012_validator(schema).iter_errors(document))
    assert errors
