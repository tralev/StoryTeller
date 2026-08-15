import json
from pathlib import Path

from scripts.audit_v2_schema_depth import audit_schema_directory


def test_schema_depth_gate_keeps_p8c1_open_while_domain_schemas_are_shallow() -> None:
    failures = audit_schema_directory(Path("schemas/v2"))
    representative = {"terrain.schema.json", "history.schema.json", "local-map.schema.json"}
    assert representative <= failures.keys()
    roadmap = Path("docs/roadmap.md").read_text()
    assert "- [ ] **P8.C1 —" in roadmap


def test_required_fields_cannot_be_untyped() -> None:
    terrain = json.loads(Path("schemas/v2/terrain.schema.json").read_text())
    errors = audit_schema_directory(Path("schemas/v2"))["terrain.schema.json"]
    assert terrain["required"] == ["chunk_shape"]
    assert any("chunk_shape" in error and "no schema" in error for error in errors)
