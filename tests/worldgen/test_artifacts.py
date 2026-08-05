import json

from src.domain.run_spec import WorldSpec
from src.worldgen.physical_pipeline import generate_physical_world


def test_all_domains_are_independent_verified_artifacts(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2, climate_relaxation_passes=8)
    first = generate_physical_world(spec, 42, tmp_path / "a")
    second = generate_physical_world(spec, 42, tmp_path / "b")
    assert first["world_index"] == second["world_index"]
    expected = {"plates", "terrain", "geology", "hydrology", "climate", "soil", "biomes",
                "resources", "species", "ecology", "regions", "routes", "maps", "world_index"}
    assert {path.stem for path in (tmp_path / "a" / "artifacts").glob("*.json")} == expected
    index = json.loads((tmp_path / "a" / "artifacts" / "world_index.json").read_text())
    assert set(index["payload"]["artifacts"]) == expected - {"world_index"}
    assert all(len(value["sha256"]) == 64 for value in index["payload"]["artifacts"].values())
