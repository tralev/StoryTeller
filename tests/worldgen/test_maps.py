import hashlib

from src.worldgen.maps import render_maps


def test_map_pixels_are_deterministic(tmp_path, physical_world):
    terrain, _, _, biomes, _, regions, routes = physical_world
    first = render_maps(tmp_path / "a", terrain, biomes, regions, routes)
    second = render_maps(tmp_path / "b", terrain, biomes, regions, routes)
    assert set(first) == set(second)
    assert {name: hashlib.sha256(path.read_bytes()).digest() for name, path in first.items()} == \
           {name: hashlib.sha256(path.read_bytes()).digest() for name, path in second.items()}
