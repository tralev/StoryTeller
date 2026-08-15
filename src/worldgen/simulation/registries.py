"""Validated, hashed builtin simulation registries."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping

from ..artifacts import canonical_json
from ..registries import registry_entries

SIMULATION_REGISTRIES: dict[str, dict[str, object]] = {
    "people": {"version": 1, "entries": (
        {"id": "people_human", "needs": ("grain", "shelter")},
        {"id": "people_dwarf", "needs": ("grain", "materials")},
        {"id": "relationship_types_v1", "types": ("spouse", "parent_of", "sibling", "mentor")},
    )},
    "technologies": {"version": 1, "entries": (
        {"id": "agriculture", "requires": ()},
        {"id": "masonry", "requires": ()},
        {"id": "metallurgy", "requires": ("masonry",)},
    )},
    "occupations": {"version": 1, "entries": (
        {"id": "farmer", "technology": "agriculture"},
        {"id": "mason", "technology": "masonry"},
        {"id": "smith", "technology": "metallurgy"},
    )},
    "materials": {"version": 1, "entries": tuple(
        dict(entry) for entry in registry_entries("materials"))},
    "recipes": {"version": 1, "entries": tuple(
        dict(entry) for entry in registry_entries("recipes"))},
    "institutions": {"version": 1, "entries": (
        {"id": "keeper_circle", "role": "religious"},
        {"id": "craft_guild", "role": "economic"},
        {"id": "war_council", "role": "political"},
    )},
    "governments": {"version": 1, "entries": (
        {"id": "council", "stability_ppm": 650_000},
        {"id": "monarchy", "stability_ppm": 700_000},
        {"id": "clan_compact", "stability_ppm": 600_000},
    )},
    "beliefs": {"version": 1, "entries": (
        {"id": "ancestor_roads", "claim": "ancestors guard remembered roads",
         "institution": "keeper_circle", "taboo": "destroying a waystone",
         "rite": "walking the remembered circuit"},
        {"id": "cosmology_v1", "layers": ("mortal sphere", "star road", "remembered shore"),
         "cycles": ({"name": "silver return", "period_months": 18},
                    {"name": "ember conjunction", "period_months": 84}),
         "entity_kinds": ("deity", "spirit", "demon", "saint", "false_entity"),
         "rite": "lighting the circuit stones at conjunction"},
    )},
    "magic_vocabulary": {"version": 1, "entries": (
        {"id": "resonance", "cost": "fatigue", "limit": "cannot create energy",
         "prohibited": ("create_matter", "resurrection", "rewrite_history"),
         "source_kind": "place-bound resonance", "side_effect": "temporary color blindness"},
    )},
    "language": {"version": 1, "entries": (
        {"id": "phonemes_v1", "onsets": ("k", "m", "n", "r", "s", "th", "v", "z"),
         "vowels": ("a", "e", "i", "o", "u", "ae"),
         "codas": ("", "n", "r", "s", "th")},
        {"id": "morphology_v1", "morpheme_count": 8, "name_morphemes": 2},
        {"id": "syllable_patterns_v1", "patterns": ("CV", "CVC", "VC")},
        {"id": "sound_shifts_v1", "rules": (
            {"id": "shift_th_t", "year": 25, "from": "th", "to": "t"},
            {"id": "shift_ae_e", "year": 50, "from": "ae", "to": "e"},
            {"id": "shift_v_f", "year": 100, "from": "v", "to": "f"},
        )},
        {"id": "name_safety_v1", "reserved": ("admin", "unknown", "people", "null"),
         "prohibited_fragments": ("damn", "hell"),
         "confusables": {"0": "o", "1": "i", "l": "i", "5": "s"}},
        {"id": "heraldry_palette_v1", "colors": (
            {"id": "obsidian", "hex_rgb": "#101820", "luminance_ppm": 10_000},
            {"id": "crimson", "hex_rgb": "#A6192E", "luminance_ppm": 90_000},
            {"id": "azure", "hex_rgb": "#1967B3", "luminance_ppm": 140_000},
            {"id": "verdant", "hex_rgb": "#2E8540", "luminance_ppm": 180_000},
            {"id": "gold", "hex_rgb": "#F2C94C", "luminance_ppm": 610_000},
            {"id": "ivory", "hex_rgb": "#FFF8E7", "luminance_ppm": 940_000},
        )},
        {"id": "heraldry_design_v1",
         "divisions": ("plain", "per_pale", "per_fess", "per_bend", "quartered"),
         "motifs": ("tower", "crown", "river", "star", "wolf", "oak"),
         "angles_millidegrees": (-45_000, 0, 45_000, 90_000)},
        {"id": "identity_style_v1", "scripts": ("runes", "glyphs", "knots"),
         "colors": ("ashen", "crimson", "golden", "iron", "verdant", "silver"),
         "symbols": ("tower", "crown", "river", "star", "wolf", "oak"),
         "patterns": ("quartered", "chevron", "wave", "pale")},
        {"id": "culture_traits_v1",
         "biome_traits": {"1": "ice-season memory", "2": "highland stonecraft",
                          "3": "cold-steppe endurance", "4": "dryland waterkeeping",
                          "5": "grassland horsemanship", "6": "woodland stewardship",
                          "7": "rainforest canopy craft", "8": "wetland navigation"},
         "climate_traits": ("cold-weather planning", "seasonal husbandry",
                            "temperate cultivation", "storm-season architecture",
                            "heat-adapted scheduling"),
         "water_trait": "waterside navigation", "route_trait": "crossroads exchange",
         "resource_trait": "resource-specialist craft"},
    )},
    "species": {"version": 1, "entries": tuple(
        dict(entry) for entry in registry_entries("species"))},
}


def simulation_registry_entries(name: str) -> tuple[Mapping[str, object], ...]:
    registry = SIMULATION_REGISTRIES[name]
    entries = registry["entries"]
    if not isinstance(entries, tuple) or not all(isinstance(entry, Mapping) for entry in entries):
        raise ValueError(f"WG-REGISTRY-ENTRIES: {name}")
    return entries


SIMULATION_STAGE_REGISTRIES: dict[str, tuple[str, ...]] = {
    "sites": (),
    "civilizations": ("governments", "institutions", "occupations", "people", "technologies"),
    "settlements": ("institutions", "materials", "occupations", "recipes", "technologies"),
    "economy": ("materials", "occupations", "recipes", "technologies"),
    "identities": ("beliefs", "language", "magic_vocabulary"),
    "peoples": ("people",),
    "legendary_artifacts": ("materials", "people"),
    "history_clock": tuple(sorted(SIMULATION_REGISTRIES)),
    "genealogy": ("people",),
    "religious_patronage": ("beliefs", "institutions"),
    "religious_schisms": ("beliefs", "institutions"),
    "successions": ("governments", "people"),
    "construction_projects": ("materials", "recipes", "technologies"),
    "technology_discoveries": ("technologies",),
    "exploration_discoveries": (),
    "government_reforms": ("governments",),
    "diplomatic_transitions": (),
    "polity_lifecycle": (),
    "history": tuple(sorted(SIMULATION_REGISTRIES)),
    "snapshots": tuple(sorted(SIMULATION_REGISTRIES)),
    "registries": tuple(sorted(SIMULATION_REGISTRIES)),
    "simulation_index": tuple(sorted(SIMULATION_REGISTRIES)),
}


def validate_and_hash_registries(
    registries: Mapping[str, Mapping[str, object]] = SIMULATION_REGISTRIES,
) -> dict[str, str]:
    if set(registries) != set(SIMULATION_REGISTRIES):
        raise ValueError("WG-REGISTRY-SET: simulation registry set mismatch")
    hashes: dict[str, str] = {}
    for name, registry in sorted(registries.items()):
        version, entries = registry.get("version"), registry.get("entries")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError(f"WG-REGISTRY-VERSION: {name}")
        if not isinstance(entries, tuple) or not entries:
            raise ValueError(f"WG-REGISTRY-EMPTY: {name}")
        ids = [entry.get("id") for entry in entries if isinstance(entry, Mapping)]
        if len(ids) != len(entries) or len(ids) != len(set(ids)) or any(item is None for item in ids):
            raise ValueError(f"WG-REGISTRY-DUPLICATE: {name}")
        for entry in entries:
            ratio = entry.get("ratio_ppm")
            if ratio is not None and (isinstance(ratio, bool) or not isinstance(ratio, int)
                                      or not 0 < ratio <= 1_000_000):
                raise ValueError(f"WG-REGISTRY-BALANCE: {entry['id']}")
        hashes[name] = hashlib.sha256(canonical_json(registry)).hexdigest()
    return hashes


def simulation_stage_fingerprint(kind: str, history_years: int,
                                 registry_hashes: Mapping[str, str]) -> str:
    if kind not in SIMULATION_STAGE_REGISTRIES:
        raise ValueError(f"WG-REGISTRY-STAGE: unknown simulation producer {kind}")
    if set(registry_hashes) != set(SIMULATION_REGISTRIES):
        raise ValueError("WG-REGISTRY-SET: simulation hash set mismatch")
    selected = {name: registry_hashes[name] for name in SIMULATION_STAGE_REGISTRIES[kind]}
    return hashlib.sha256(canonical_json({
        "algorithm": "history-v1", "kind": kind, "years": history_years,
        "registries": selected,
    })).hexdigest()
