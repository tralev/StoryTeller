import json
from pathlib import Path

from scripts.audit_v2_schema_depth import audit_schema_directory


def test_schema_depth_gate_keeps_p8c1_open_while_narrative_schemas_are_shallow() -> None:
    failures = audit_schema_directory(Path("schemas/v2"))
    representative = {"bible.schema.json", "graph.schema.json", "gm-index.schema.json"}
    assert representative <= failures.keys()
    roadmap = Path("docs/roadmap.md").read_text()
    assert "- [ ] **P8.C1 —" in roadmap


def test_world_domain_schemas_pass_the_depth_gate() -> None:
    failures = audit_schema_directory(Path("schemas/v2"))
    world = {
        "world-index.schema.json", "terrain.schema.json", "hydrology.schema.json",
        "climate.schema.json", "biomes.schema.json", "resources.schema.json",
        "regions.schema.json", "routes.schema.json", "sites.schema.json",
        "civilizations.schema.json", "history.schema.json", "snapshots.schema.json",
        "local-map.schema.json", "defs.schema.json", "artifact-provenance.schema.json",
    }
    assert world.isdisjoint(failures.keys())


def test_required_fields_cannot_be_untyped() -> None:
    bible = json.loads(Path("schemas/v2/bible.schema.json").read_text())
    errors = audit_schema_directory(Path("schemas/v2"))["bible.schema.json"]
    assert bible["required"] == ["schema_version"]
    assert any("schema_version" in error and "no schema" in error for error in errors)
