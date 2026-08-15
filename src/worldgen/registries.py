"""Canonical versioned rule registries used by physical-world producers."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping

from .artifacts import canonical_json

PHYSICAL_REGISTRIES: dict[str, dict[str, object]] = {
    "biomes": {
        "version": 1,
        "entries": (
            {"id": 0, "name": "ocean"}, {"id": 1, "name": "ice"},
            {"id": 2, "name": "mountain"}, {"id": 3, "name": "tundra"},
            {"id": 4, "name": "desert"}, {"id": 5, "name": "grassland"},
            {"id": 6, "name": "forest"}, {"id": 7, "name": "rainforest"},
            {"id": 8, "name": "wetland"},
        ),
        "rule_order": ("ocean", "ice", "mountain", "tundra", "desert", "wetland",
                       "grassland", "rainforest", "forest"),
    },
    "materials": {
        "version": 1,
        "entries": (
            {"id": "iron", "density_kg_m2": 5_000, "renewable": False},
            {"id": "copper", "density_kg_m2": 3_000, "renewable": False},
            {"id": "tin", "density_kg_m2": 2_000, "renewable": False},
            {"id": "coal", "density_kg_m2": 1_500, "renewable": False},
            {"id": "flux_stone", "density_kg_m2": 4_000, "renewable": False},
            {"id": "gems", "density_kg_m2": 250, "renewable": False},
            {"id": "grain", "renewable": True}, {"id": "timber", "renewable": True},
            {"id": "stone", "renewable": False},
        ),
    },
    "species": {
        "version": 1,
        "entries": (
            {"id": "herbivore", "trophic_level": 1, "energy_divisor": 1},
            {"id": "mesopredator", "trophic_level": 2, "energy_divisor": 10},
            {"id": "apex_predator", "trophic_level": 3, "energy_divisor": 100},
            {"id": "pack_animal", "role": "transport"},
            {"id": "crop", "role": "food"},
        ),
    },
    "recipes": {
        "version": 1,
        "entries": (
            {"id": "food", "input": "grain", "output": "food", "ratio_ppm": 800_000},
        ),
    },
}


def registry_entries(name: str) -> tuple[Mapping[str, object], ...]:
    entries = PHYSICAL_REGISTRIES[name]["entries"]
    if not isinstance(entries, tuple) or not all(isinstance(entry, Mapping) for entry in entries):
        raise ValueError(f"WG-REGISTRY-ENTRIES: {name}")
    return entries


def biome_rule_order() -> tuple[str, ...]:
    values = PHYSICAL_REGISTRIES["biomes"]["rule_order"]
    if not isinstance(values, tuple) or not all(isinstance(value, str) for value in values):
        raise ValueError("WG-REGISTRY-RULES: biomes")
    return values


def material_densities() -> dict[str, int]:
    result: dict[str, int] = {}
    for entry in registry_entries("materials"):
        value = entry.get("density_kg_m2")
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f"WG-REGISTRY-DENSITY: {entry['id']}")
        result[str(entry["id"])] = value
    return result


def validate_and_hash_physical_registries(
    registries: Mapping[str, Mapping[str, object]] = PHYSICAL_REGISTRIES,
) -> dict[str, str]:
    required = {"biomes", "materials", "species", "recipes"}
    if set(registries) != required:
        raise ValueError("WG-REGISTRY-SET: physical registry set mismatch")
    hashes: dict[str, str] = {}
    for name, registry in sorted(registries.items()):
        version, entries = registry.get("version"), registry.get("entries")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError(f"WG-REGISTRY-VERSION: {name}")
        if not isinstance(entries, tuple) or not entries:
            raise ValueError(f"WG-REGISTRY-EMPTY: {name}")
        ids = [entry["id"] for entry in entries if isinstance(entry, Mapping) and "id" in entry]
        if len(ids) != len(entries) or len(ids) != len(set(ids)):
            raise ValueError(f"WG-REGISTRY-DUPLICATE: {name}")
        for entry in entries:
            ratio = entry.get("ratio_ppm") if isinstance(entry, Mapping) else None
            if ratio is not None and (not isinstance(ratio, int) or not 0 < ratio <= 1_000_000):
                raise ValueError(f"WG-REGISTRY-BALANCE: {entry['id']}")
        hashes[name] = hashlib.sha256(canonical_json(registry)).hexdigest()
    return hashes
