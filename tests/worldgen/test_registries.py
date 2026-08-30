from copy import deepcopy

import pytest

from src.domain.run_spec import WorldSpec
from src.worldgen.physical_pipeline import physical_stage_fingerprint
from src.worldgen.registries import PHYSICAL_REGISTRIES, validate_and_hash_physical_registries


def test_physical_registries_are_versioned_unique_and_stable():
    hashes = validate_and_hash_physical_registries()
    assert set(hashes) == {"biomes", "materials", "species", "recipes"}
    assert all(len(value) == 64 for value in hashes.values())
    assert hashes == validate_and_hash_physical_registries()


@pytest.mark.parametrize(
    ("registry", "direct_stage"),
    (
        ("biomes", "biomes"),
        ("materials", "resources"),
        ("species", "species"),
        ("recipes", "world_index"),
    ),
)
def test_registry_changes_invalidate_only_the_direct_physical_producer(registry, direct_stage):
    spec = WorldSpec(
        width=32, height=32, continent_count=1, plate_count=3, minimum_continent_cells=1
    )
    original = validate_and_hash_physical_registries()
    changed = dict(original)
    changed[registry] = "f" * 64 if original[registry] != "f" * 64 else "e" * 64
    stages = ("terrain", "biomes", "resources", "species", "ecology", "world_index")
    differences = {
        stage
        for stage in stages
        if physical_stage_fingerprint(spec, stage, original)
        != physical_stage_fingerprint(spec, stage, changed)
    }
    assert differences == {direct_stage}


def test_registry_validator_rejects_duplicate_ids_and_invalid_versions():
    duplicate = deepcopy(PHYSICAL_REGISTRIES)
    duplicate["recipes"] = {
        "version": 1,
        "entries": (
            {"id": "same"},
            {"id": "same"},
        ),
    }
    with pytest.raises(ValueError, match="WG-REGISTRY-DUPLICATE"):
        validate_and_hash_physical_registries(duplicate)
    unversioned = deepcopy(PHYSICAL_REGISTRIES)
    unversioned["species"]["version"] = 0
    with pytest.raises(ValueError, match="WG-REGISTRY-VERSION"):
        validate_and_hash_physical_registries(unversioned)
