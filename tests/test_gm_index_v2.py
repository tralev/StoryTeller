import json

from src.world.views import WorldView
from src.worldgen.local_maps import LocalFeature, LocalSiteMap, generate_local_maps, validate_local_map


def test_complete_gm_source_and_local_map_coverage(phase5_project):
    world_path, _, phase5 = phase5_project
    entries = json.loads((phase5 / "gm_index.json").read_text())
    sources = {source for entry in entries for source in entry["source_ids"]}
    assert set(WorldView(world_path).artifact_ids.values()) <= sources
    assert sum(entry["kind"] == "local_map" for entry in entries) == len(WorldView(world_path).sites())
    assert any(entry["kind"] == "event" for entry in entries)
    assert all("incoming_refs" in entry and "outgoing_refs" in entry for entry in entries)


def test_every_site_local_map_has_required_3d_systems(phase5_project):
    world_path, _, phase5 = phase5_project
    paths = sorted((phase5 / "local_maps").glob("*.json"))
    assert len(paths) == len(WorldView(world_path).sites())
    for path in paths:
        item = json.loads(path.read_text())
        local = LocalSiteMap(item["algorithm_version"], item["site_id"], item["width"], item["height"],
                             item["z_levels"], item["macro_cell"], tuple(item["strata"]),
                             tuple(item["surface_height"]),
                             tuple(LocalFeature(feature["feature_id"], feature["kind"],
                                                tuple(tuple(cell) for cell in feature["cells"]),
                                                tuple(feature["source_ids"])) for feature in item["features"]))
        validate_local_map(local)
    assert generate_local_maps(WorldView(world_path)) == generate_local_maps(WorldView(world_path))
