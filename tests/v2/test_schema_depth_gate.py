import json
from pathlib import Path

from scripts.audit_v2_schema_depth import audit_schema_directory, schema_depth_errors


def test_schema_depth_gate_passes_every_v2_schema() -> None:
    failures = audit_schema_directory(Path("schemas/v2"))
    assert failures == {}


def test_p8c1_and_p8c2_are_closed_after_native_parity() -> None:
    roadmap = Path("docs/roadmap.md").read_text()
    assert "closed v2 schemas (P8.C1)" in roadmap
    assert "three-validator parity (P8.C2)" in roadmap
    assert "- [ ] **P8.C1" not in roadmap
    assert "- [ ] **P8.C2" not in roadmap


def test_depth_gate_rejects_untyped_required_fields() -> None:
    errors = schema_depth_errors(
        {"type": "object", "required": ["chunk_shape"], "additionalProperties": False},
        "terrain.schema.json",
    )
    assert any("chunk_shape" in error and "no schema" in error for error in errors)
    assert json.loads(Path("schemas/v2/terrain.schema.json").read_text())["required"]


def test_depth_gate_accepts_root_reference_to_audited_shared_definition() -> None:
    assert (
        schema_depth_errors(
            {"$ref": "https://storyteller.local/schemas/v2/defs.schema.json#/$defs/historyEvent"},
            "history-event.schema.json",
        )
        == ()
    )
