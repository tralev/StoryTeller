"""P8.C05A step 2-3 — Frozen worldgen-1 profile and named presets.

Every preset expands to a complete WorldSpec before hashing; artifact
fingerprints never contain unresolved preset names.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ...domain.run_spec import (SEED_PLAN_VERSION, WORLD_SPEC_CROSS_FIELD_RULES,
                                WORLD_SPEC_FIELD_RULES, WorldSpec)
from ..artifacts import canonical_json
from ..numeric import STABLE_ID_VERSION

# ── worldgen-1 frozen profile ─────────────────────────────────────────

WORLDGEN_1_PROFILE = {
    "version": "worldgen-1",
    "units": {
        "distance": "metres (integer, world cell); millimetres (integer, local cell)",
        "elevation": "parts per million of configured max elevation",
        "temperature": "millidegrees Celsius",
        "rainfall": "milligrams per square metre",
        "moisture": "parts per million",
        "time": "years × 12 ticks × 1 month per tick",
        "population": "integer heads",
        "probability": "parts per million (0 = impossible, 1_000_000 = certain)",
        "price": "integer base-unit currency",
        "mass": "integer kilograms",
        "energy": "integer kilojoules",
        "capacity": "integer capacity units",
    },
    "rounding": {
        "rule": "round_div(a, b) rounds nearest; exact halves away from zero; b > 0",
        "overflow": "clamp to signed 64-bit; saturate only where explicitly named",
    },
    "prng": {
        "stream": "SplitMix64",
        "seed_derivation": (
            "SHA-256(master_seed \\x1f algorithm_version \\x1f domain "
            "\\x1f stable_entity_id \\x1f decision_label)"
        ),
        "seed_plan_version": SEED_PLAN_VERSION,
    },
    "id_grammar": {
        "entity": "^[a-z][a-z0-9]*_[0-9a-f]{32}$",
        "entity_derivation": "length-framed UTF-8 SHA-256 over typed, labelled canonical components",
        "entity_derivation_version": STABLE_ID_VERSION,
        "artifact": "<kind>_<first 32 hex of SHA-256(identity JCS)>",
        "dependency": "validated full artifact ID; unique canonical sorted tuple",
        "producer_fingerprint": "1..128 ASCII letters/digits followed by letters/digits/._:-",
        "sha256": "^[0-9a-f]{64}$ (full 64 hex, never truncated)",
    },
    "canonical_serialization": {
        "json": "RFC 8785 JCS; no NaN/Infinity; Unicode NFC; sorted keys",
        "coordinate_spaces": "nonnegative world XY, local XYZ, and chunk XY are distinct types",
        "grid_header": "maximum 1024-byte canonical JSON header; row-major signed i32be cells",
        "grid_manifest": "storyteller.dense-grid-manifest.v1; row-major descriptors by chunk Y then X",
        "grid_chunk_hash": "SHA-256 of canonical uncompressed header plus signed-i32be payload",
        "embedded_dense_grid_policy": "migrated fields exist only in verified chunks, never duplicate JSON values",
        "grid_compression": "ZIP DEFLATE only; no nested compression",
        "chunk_size": "256×256 surface; 32×32×16 sparse local; partial only at edges",
        "decoded_chunk_limit": "at most 256×256 signed-int32 cells before container overhead",
    },
    "stage_order": [
        "specification", "seed_plan", "plates", "terrain",
        "terrain_grid_catalog", "geology", "geology_grid_catalog", "hydrology", "hydrology_grid_catalog",
        "climate", "climate_grid_catalog", "soil", "soil_grid_catalog",
        "biomes", "biome_grid_catalog", "resources", "resource_grid_catalog", "species",
        "ecology", "regions", "region_grid_catalog", "routes", "magic_laws", "languages", "peoples",
        "cultures", "religions", "governments", "sites", "civilizations",
        "persons", "cohorts", "economy", "history_events", "history_snapshots",
        "local_maps", "story_opportunities", "map_layers",
        "spatial_index", "reference_index", "validation_report",
    ],
    "required_artifact_kinds": [
        "world_spec", "seed_plan", "plates", "terrain", "terrain_grid_catalog",
        "geology", "geology_grid_catalog", "hydrology", "hydrology_grid_catalog",
        "climate", "climate_grid_catalog", "soil", "soil_grid_catalog", "biomes", "biome_grid_catalog",
        "resources", "resource_grid_catalog", "species", "ecology",
        "regions", "region_grid_catalog", "routes", "local_maps", "history_events", "history_snapshots",
        "spatial_index", "reference_index", "validation_report",
    ],
    "validation_codes": {
        "error_prefix": "WG-",
        "domains": [
            "KERNEL", "PHYS", "ECO", "ROUTE", "SOC", "HIST", "LOCAL", "INTEGRATION",
        ],
    },
    "snapshot_cadence": "year 0, every 10 years, final year",
    "retention_policy": "full — complete ledger, snapshots, and identities retained even when unused",
    "validation_ranges": WORLD_SPEC_FIELD_RULES,
    "cross_field_rules": WORLD_SPEC_CROSS_FIELD_RULES,
    "default_profile": {
        "width": 1024, "height": 1024,
        "continent_count": 1,
        "metres_per_world_cell": 8_000,
        "plate_count": 24,
        "minimum_continent_cells": 4_096,
        "history_years": 500,
        "history_ticks_per_year": 12,
        "civilization_count": 8,
        "sea_level_ppm": 380_000,
        "axial_tilt_millidegrees": 23_500,
        "erosion_passes": 32,
        "climate_relaxation_passes": 64,
        "snapshot_interval_years": 10,
        "local_site_width": 128,
        "local_site_height": 128,
        "local_z_levels": 32,
        "local_cell_millimetres": 2_000,
    },
}


def _spec_hash(spec: WorldSpec) -> str:
    """Stable SHA-256 of the fully expanded specification fields."""
    payload = "|".join(
        f"{k}={v}" for k, v in sorted(asdict(spec).items())
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ── Named profiles ────────────────────────────────────────────────────

PROFILE_TINY = WorldSpec(
    width=32, height=32,
    continent_count=1,
    plate_count=4,
    minimum_continent_cells=1,
    civilization_count=2,
    history_years=20,
    history_ticks_per_year=12,
    erosion_passes=1,
    climate_relaxation_passes=8,
    sea_level_ppm=380_000,
    snapshot_interval_years=10,
    local_site_width=32,
    local_site_height=32,
    local_z_levels=4,
    local_cell_millimetres=2_000,
    axial_tilt_millidegrees=23_500,
    metres_per_world_cell=8_000,
)
"""Tiny fast unit-test profile — ~32×32, minimal passes, 20-year history."""

PROFILE_CONFORMANCE = WorldSpec(
    width=64, height=64,
    continent_count=1,
    plate_count=8,
    minimum_continent_cells=256,
    civilization_count=3,
    history_years=50,
    history_ticks_per_year=12,
    erosion_passes=8,
    climate_relaxation_passes=16,
    sea_level_ppm=380_000,
    snapshot_interval_years=10,
    local_site_width=64,
    local_site_height=64,
    local_z_levels=16,
    local_cell_millimetres=2_000,
    axial_tilt_millidegrees=23_500,
    metres_per_world_cell=8_000,
)
"""Small cross-platform conformance profile — golden vectors for CI."""

PROFILE_DEFAULT = WorldSpec(
    width=1024, height=1024,
    continent_count=1,
    plate_count=24,
    minimum_continent_cells=4_096,
    civilization_count=8,
    history_years=500,
    history_ticks_per_year=12,
    erosion_passes=32,
    climate_relaxation_passes=64,
    sea_level_ppm=380_000,
    snapshot_interval_years=10,
    local_site_width=128,
    local_site_height=128,
    local_z_levels=32,
    local_cell_millimetres=2_000,
    axial_tilt_millidegrees=23_500,
    metres_per_world_cell=8_000,
)
"""Release default — one continent, 500-year history, 8 civilizations."""


_PRESET_MAP: dict[str, WorldSpec] = {
    "tiny": PROFILE_TINY,
    "conformance": PROFILE_CONFORMANCE,
    "default": PROFILE_DEFAULT,
}

FROZEN_CONTRACT_HASHES = {
    "worldgen_1": "58dbcae1ad93b57f6c26a52511c6fcc18017ef4e8e4ff3eb7782703745f7f371",
    "registries": "9351be08c89a0c1850ad6d4a3f2797f12e97c7b11d847357dc7b7f3ed7bc0d8d",
    "schemas": "0ef1ac59b37198873d43e4c54785ff6c0bba937c9f8d05b2291e5f04275e26fc",
}

FROZEN_PROFILE_HASHES = {
    "tiny": "fa67d3e0127732591a3185ecdc2b23fc5d7062ef02ea9b1c15239a46c419e2b8",
    "conformance": "b75ae5eb1a262f6947e9b9018e86dc2c5bae60370efc736962adedc207ac98a8",
    "default": "b4a2c2779d8f940144584cfed98a02aa5203a8f80359158a1189e8f80edf594d",
}


def verify_contract_hashes(schema_root: str | Path | None = None) -> dict[str, str]:
    """Return current hashes or reject drift from the worldgen-1 freeze."""
    actual = contract_hashes(schema_root)
    if actual != FROZEN_CONTRACT_HASHES:
        changed = sorted(key for key in actual if actual[key] != FROZEN_CONTRACT_HASHES[key])
        raise ValueError(f"WG-CONTRACT-HASH-DRIFT: {', '.join(changed)}")
    return actual


def expand_profile(name: str) -> WorldSpec:
    """Expand a named preset to a complete, validated WorldSpec.

    Raises ValueError for unknown preset names. The returned spec is
    fully explicit — artifact fingerprints never contain preset names.

    validate() is called explicitly as a belt-and-suspenders check
    (WorldSpec.__post_init__ already calls it, but defensive re-check
    guards against runtime mutation of frozen fields).
    """
    if name not in _PRESET_MAP:
        raise ValueError(
            f"unknown worldgen profile {name!r}; "
            f"valid: {', '.join(sorted(_PRESET_MAP))}"
        )
    spec = _PRESET_MAP[name]
    spec.validate()
    return spec


def profile_hash(name: str) -> str:
    """Stable fingerprint of the expanded profile (not the preset label)."""
    return _spec_hash(expand_profile(name))


def validate_profile_contract() -> list[str]:
    """Audit complete field/default/range/profile coverage for WorldSpec."""
    from dataclasses import fields

    errors: list[str] = []
    field_names = {item.name for item in fields(WorldSpec)}
    default_fields = set(WORLDGEN_1_PROFILE["default_profile"])
    rule_fields = set(WORLD_SPEC_FIELD_RULES)
    if default_fields != field_names:
        errors.append(f"default profile field drift: {sorted(default_fields ^ field_names)}")
    if rule_fields != field_names:
        errors.append(f"validation rule field drift: {sorted(rule_fields ^ field_names)}")
    if WorldSpec().to_dict() != WORLDGEN_1_PROFILE["default_profile"]:
        errors.append("WorldSpec defaults differ from frozen default profile")
    for name in sorted(_PRESET_MAP):
        spec = expand_profile(name)
        if set(spec.to_dict()) != field_names:
            errors.append(f"incomplete expanded profile: {name}")
        if profile_hash(name) != FROZEN_PROFILE_HASHES[name]:
            errors.append(f"profile hash drift: {name}")
    return errors


def contract_hashes(schema_root: str | Path | None = None) -> dict[str, str]:
    """Hash the frozen worldgen profile, builtin registries, and schema bundle."""
    from ..simulation.registries import validate_and_hash_registries

    root = (Path(schema_root) if schema_root is not None
            else Path(__file__).resolve().parents[3] / "schemas")
    schema_files = sorted(path for path in root.rglob("*.json") if path.is_file())
    if not schema_files:
        raise ValueError(f"WG-SCHEMA-EMPTY: no JSON schemas under {root}")
    schema_digest = hashlib.sha256()
    for path in schema_files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        schema_digest.update(len(relative).to_bytes(4, "big"))
        schema_digest.update(relative)
        schema_digest.update(len(data).to_bytes(8, "big"))
        schema_digest.update(data)

    registry_hashes = validate_and_hash_registries()
    return {
        "worldgen_1": hashlib.sha256(canonical_json(WORLDGEN_1_PROFILE)).hexdigest(),
        "registries": hashlib.sha256(canonical_json(registry_hashes)).hexdigest(),
        "schemas": schema_digest.hexdigest(),
    }
