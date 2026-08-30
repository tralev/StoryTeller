"""P8.C1: generate_schemas must not clobber authored v2 schemas."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.generate_v2_fixtures import (
    SCHEMA_STUB_REQUIRED,
    generate_schemas,
    schema_is_authored,
)
from src.storage.package_v2 import canonical_json


def test_manifest_and_artifact_provenance_are_authored() -> None:
    root = Path("schemas/v2")
    assert schema_is_authored(root / "manifest.schema.json")
    assert schema_is_authored(root / "artifact-provenance.schema.json")
    assert schema_is_authored(root / "history-event.schema.json")
    assert schema_is_authored(root / "snapshots.schema.json")


def test_generate_schemas_preserves_authored_on_disk_bytes() -> None:
    root = Path("schemas/v2")
    before = {
        name: (root / f"{name}.schema.json").read_bytes()
        for name in SCHEMA_STUB_REQUIRED
        if schema_is_authored(root / f"{name}.schema.json")
    }
    skipped = generate_schemas()
    assert set(before) <= set(skipped)
    for name, payload in before.items():
        assert (root / f"{name}.schema.json").read_bytes() == payload


def test_generate_schemas_does_not_overwrite_deepened_schema(tmp_path, monkeypatch) -> None:
    import scripts.generate_v2_fixtures as generator

    schemas = tmp_path / "schemas"
    schemas.mkdir()
    authored = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://storyteller.local/schemas/v2/bible.schema.json",
        "title": "bible",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version"],
        "properties": {"schema_version": {"type": "integer"}},
    }
    (schemas / "bible.schema.json").write_bytes(canonical_json(authored))
    monkeypatch.setattr(generator, "SCHEMAS", schemas)
    skipped = generator.generate_schemas()
    assert "bible" in skipped
    assert json.loads((schemas / "bible.schema.json").read_text()) == authored
    assert schema_is_authored(schemas / "bible.schema.json")
    assert (schemas / "terrain.schema.json").is_file()
    terrain = json.loads((schemas / "terrain.schema.json").read_text())
    assert terrain.get("properties") in (None, {})


def test_check_fails_when_expected_schema_is_missing(tmp_path, monkeypatch) -> None:
    import scripts.generate_v2_fixtures as generator

    monkeypatch.setattr(generator, "SCHEMAS", tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    try:
        generator.check_fixture_corpus()
    except SystemExit as exc:
        assert "missing v2 schemas" in str(exc)
    else:
        raise AssertionError("expected SystemExit for missing schemas")
