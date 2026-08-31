#!/usr/bin/env python3
"""Generate the shared deterministic `.story` v2 acceptance corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import sys
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.narrative.media import deterministic_image, generate_score, score_to_smf_type1
from src.storage.package_v2 import (
    FLAT_WORLD_DOMAINS,
    GRID_DOMAINS,
    V2PackageBuilder,
    artifact_record,
    build_grid_domain_files,
    canonical_json,
    content_hash,
)
from src.world.views import REQUIRED_KINDS
from src.worldgen.grid import (
    DenseGridCatalog,
    GridSpec,
    IntGrid,
    build_grid_manifest,
    iter_grid_chunks,
)
from src.worldgen.local_chunks import encode_material_chunk, generate_material_chunks

GRID_LAYERS: dict[str, dict[str, tuple[int, ...]]] = {
    "terrain": {"terrain_elevation_mm": (1200,), "terrain_plate_id": (2,)},
    "geology": {
        "geology_rock_class_id": (2,),
        "geology_strata_id": (1,),
        "geology_parent_material_id": (2,),
        "geology_fault": (0,),
        "geology_volcano": (0,),
        "geology_tectonic_relief_mm": (0,),
    },
    "hydrology": {
        "hydrology_filled_elevation_mm": (1200,),
        "hydrology_flow_to": (-1,),
        "hydrology_accumulation": (1,),
        "hydrology_watershed_id": (0,),
        "hydrology_coastline": (0,),
        "hydrology_aquifer_capacity_mm": (100,),
        "hydrology_salinity_ppm": (0,),
        "hydrology_snowpack_mm": (0,),
        "hydrology_glacier": (0,),
        "hydrology_delta": (0,),
    },
    "climate": {
        "climate_annual_temperature_millic": (15000,),
        "climate_annual_precipitation_mm": (800,),
        "climate_weather_regime": (1,),
        **{
            f"climate_season_00_{field}": (value,)
            for field, value in {
                "temperature_millic": 15000,
                "precipitation_mm": 200,
                "evaporation_mm": 100,
                "snowpack_mm": 0,
                "ice": 0,
                "storm_ppm": 100000,
                "wind_x_mmps": 1000,
                "wind_y_mmps": 0,
                "hazard_ppm": 50000,
            }.items()
        },
    },
    "biomes": {"biome_id": (3,)},
    "resource_grid": {"resource_renewable_yield": (100,)},
}


def _grid_catalog_and_chunks(
    layers: dict[str, tuple[int, ...]],
    width: int,
    height: int,
    metres_per_world_cell: int,
) -> tuple[DenseGridCatalog, dict[str, dict[tuple[int, int], bytes]]]:
    """Build a real, byte-encoded DenseGridCatalog for a small fixture grid."""
    grid_spec = GridSpec(width, height, metres_per_world_cell)
    manifests = []
    chunk_bytes_map: dict[str, dict[tuple[int, int], bytes]] = {}
    for layer in sorted(layers):
        grid = IntGrid(grid_spec, layers[layer])
        manifests.append(build_grid_manifest(layer, grid))
        chunk_bytes_map[layer] = {
            (chunk.chunk_x, chunk.chunk_y): chunk.encode()
            for chunk in iter_grid_chunks(layer, grid)
        }
    catalog = DenseGridCatalog("storyteller.dense-grid-catalog.v1", grid_spec, tuple(manifests))
    return catalog, chunk_bytes_map


FIXTURES = ROOT / "tests" / "fixtures" / "v2"
SCHEMAS = ROOT / "schemas" / "v2"
NODE = "node_00000000000000000000000000000001"
REGION = "region_00000000000000000000000000000001"
SITE = "site_00000000000000000000000000000001"
LANGUAGE = "language_00000000000000000000000000000001"
CIVILIZATION = "civilization_00000000000000000000000000000001"
SCENE = "scene_00000000000000000000000000000001"


# Expected v2 schema files. generate_schemas() may write stubs for names that
# are not yet authored; it must never overwrite a schema that already has
# `properties` or `$defs` (P8.C1 deepening cannot survive fixture regen).
SCHEMA_STUB_REQUIRED: dict[str, list[str]] = {
    "manifest": ["package_format", "package_version", "story_id", "artifacts"],
    "artifact-provenance": ["artifact_id", "kind", "path", "sha256", "producer"],
    "world-index": ["width", "height", "present_year", "domains"],
    "world-source-coverage": ["format", "required_domains", "sources"],
    "terrain": ["chunk_shape"],
    "hydrology": [],
    "climate": ["chunk_shape"],
    "biomes": ["chunk_shape"],
    "resources": [],
    "regions": ["regions"],
    "routes": ["routes"],
    "sites": ["sites"],
    "civilizations": ["civilizations"],
    "history": ["events"],
    "history-event": [],
    "snapshots": ["snapshots"],
    "local-map": ["site_id", "chunk_shape"],
    "bible": ["schema_version"],
    "reconciliation": ["accepted"],
    "style": [],
    "story": ["schema_version", "scenes"],
    "graph": ["schema_version", "starting_node", "nodes"],
    "structured-score": ["schema_version", "node_id", "ppq", "duration", "tracks", "markers"],
    "gm-index": [],
}

ID_PATTERN = "^[a-z][a-z0-9]*_[0-9a-f]{32}$"
HASH_PATTERN = "^[0-9a-f]{64}$"


def _schema(title: str, required: list[str] | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://storyteller.local/schemas/v2/{title}.schema.json",
        "title": title,
        "type": "object",
    }
    if required:
        result["required"] = required
    return result


def schema_is_authored(path: Path) -> bool:
    """True when the file declares records or a root reference (never overwrite it)."""
    if not path.is_file():
        return False
    data = json.loads(path.read_bytes())
    properties = data.get("properties")
    defs = data.get("$defs")
    return (
        isinstance(properties, dict)
        and bool(properties)
        or isinstance(defs, dict)
        and bool(defs)
        or isinstance(data.get("$ref"), str)
    )


def _defs_ref(name: str) -> dict[str, object]:
    return {"$ref": f"https://storyteller.local/schemas/v2/defs.schema.json#/$defs/{name}"}


def _artifact_provenance_schema() -> dict[str, object]:
    artifact = _schema(
        "artifact-provenance",
        ["artifact_id", "kind", "path", "sha256", "size_bytes", "depends_on", "producer"],
    )
    artifact.update(
        {
            "additionalProperties": False,
            "properties": {
                "artifact_id": _defs_ref("entityId"),
                "kind": _defs_ref("kind"),
                "path": _defs_ref("relativePath"),
                "sha256": _defs_ref("sha256"),
                "size_bytes": {"type": "integer", "minimum": 0},
                "depends_on": _defs_ref("entityIdList"),
                "producer": _defs_ref("producer"),
            },
        }
    )
    return artifact


def _manifest_schema() -> dict[str, object]:
    manifest = _schema(
        "manifest",
        [
            "package_format",
            "package_version",
            "story_id",
            "title",
            "content_profile",
            "master_seed",
            "required_features",
            "optional_features",
            "entry_node",
            "world",
            "artifacts",
            "node_assets",
            "region_maps",
            "content_hash",
        ],
    )
    manifest.update(
        {
            "additionalProperties": False,
            "properties": {
                "package_format": {"const": "storyteller.story"},
                "package_version": {"const": 2},
                "story_id": {"type": "string", "pattern": "^story_[0-9a-f]{32}$"},
                "title": {"type": "string", "minLength": 1},
                "content_profile": {"const": "mature_dark_fantasy"},
                "master_seed": {"type": "integer"},
                "required_features": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string"},
                },
                "optional_features": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {"type": "string"},
                },
                "entry_node": {"type": "string", "pattern": "^node_[0-9a-f]{32}$"},
                "world": {"type": "object"},
                "artifacts": {"type": "array"},
                "node_assets": {"type": "object"},
                "region_maps": {"type": "object"},
                "content_hash": {"type": "string", "pattern": HASH_PATTERN},
            },
        }
    )
    return manifest


def generate_schemas() -> tuple[str, ...]:
    """Write stub schemas for missing or unauthored files only.

    Returns the sorted titles skipped because they already have ``properties``
    or ``$defs``. Authored files are left byte-identical.
    """
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    skipped: list[str] = []
    for name, required in SCHEMA_STUB_REQUIRED.items():
        path = SCHEMAS / f"{name}.schema.json"
        if schema_is_authored(path):
            skipped.append(name)
            continue
        if name == "artifact-provenance":
            payload = _artifact_provenance_schema()
        elif name == "manifest":
            payload = _manifest_schema()
        else:
            payload = _schema(name, required or None)
        path.write_bytes(canonical_json(payload))
    return tuple(skipped)


def build_complete(destination: Path) -> None:
    node_assets = {
        NODE: {
            "image": f"assets/images/{NODE}.png",
            "thumbnail": f"assets/thumbnails/{NODE}.png",
            "score": f"assets/music/{NODE}.score.json",
            "midi": f"assets/midi/{NODE}.mid",
        }
    }
    builder = V2PackageBuilder(
        "Frozen v2 Reference",
        42,
        NODE,
        metres_per_world_cell=1000,
    )
    schema_ids: list[str] = []
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema_ids.append(builder.add("schema", f"schemas/{path.name}", path.read_bytes()))

    grid_catalogs: dict[str, DenseGridCatalog] = {}
    grid_chunk_bytes: dict[str, dict[str, dict[tuple[int, int], bytes]]] = {}
    for domain, layers in GRID_LAYERS.items():
        fixture_layers = {name: values * 2 for name, values in layers.items()}
        catalog, chunk_map = _grid_catalog_and_chunks(
            fixture_layers,
            width=2,
            height=1,
            metres_per_world_cell=1000,
        )
        grid_catalogs[domain] = catalog
        grid_chunk_bytes[domain] = chunk_map
    flat_payloads: dict[str, object] = {
        "hydrology": {
            "algorithm_version": 4,
            "lakes": [],
            "rivers": [],
            "terminals": [
                {
                    "terminal_id": "terminal_00000000000000000000000000000001",
                    "cell": 0,
                    "kind": 1,
                    "watershed_id": 0,
                }
            ],
        },
        "resources": {
            "algorithm_version": 2,
            "deposits": [
                {
                    "deposit_id": "deposit_00000000000000000000000000000001",
                    "resource": "iron",
                    "cells": [0, 1],
                    "depth_mm": 10_000,
                    "grade_ppm": 100_000,
                    "quantity_kg": 1_000_000_000,
                    "rock_class_id": 2,
                    "strata_id": 1,
                    "fault_related": False,
                    "volcanic_related": False,
                }
            ],
        },
    }
    source_payloads: dict[str, object] = {
        **{kind: asdict(grid_catalogs[domain]) for domain, kind in GRID_DOMAINS.items()},
        **{kind: flat_payloads[domain] for domain, kind in FLAT_WORLD_DOMAINS.items()},
    }
    source_payloads["climate"] = {"algorithm_version": 1, "season_count": 1}
    source_payloads["identities"] = {"languages": [{"language_id": LANGUAGE}]}

    source_ids: list[str] = []
    source_rows: list[dict[str, object]] = []
    for name in REQUIRED_KINDS:
        source_path = f"world/source/{name}.json"
        source_artifact_id = f"worldsource_{hashlib.sha256(name.encode()).hexdigest()[:32]}"
        payload = source_payloads.get(name, {})
        data = canonical_json({"artifact_id": source_artifact_id, "kind": name, "payload": payload})
        source_ids.append(builder.add("worldsource", source_path, data, depends_on=schema_ids))
        source_rows.append(
            {
                "source_name": name,
                "archive_path": source_path,
                "artifact_id": source_artifact_id,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size_bytes": len(data),
                "retention": "byte_for_byte",
            }
        )
    builder.add(
        "worldcoverage",
        "world/source/coverage.json",
        canonical_json(
            {
                "format": "storyteller.world-source-coverage.v1",
                "required_domains": sorted(REQUIRED_KINDS),
                "sources": source_rows,
            }
        ),
        depends_on=source_ids,
    )
    world_index = {
        "width": 2,
        "height": 1,
        "present_year": 500,
        "surface_chunk_shape": [256, 256],
        "local_chunk_shape": [32, 32, 16],
        "snapshot_years": list(range(0, 501, 10)),
        "domains": sorted(REQUIRED_KINDS),
        "source_artifact_ids": source_ids,
    }
    root_id = builder.add(
        "world", "world/index.json", canonical_json(world_index), depends_on=source_ids
    )
    local_map_path = f"world/local/{SITE}/index.json"
    (material_chunk,) = generate_material_chunks(
        width=1,
        height=1,
        z_levels=1,
        surface_height=(0,),
        strata=(7,),
    )
    material_chunk_dict = asdict(material_chunk)
    local_map: dict[str, Any] = {
        "site_id": SITE,
        "chunk_shape": [32, 32, 16],
        "boundary": {"boundary_id": "boundary_00000000000000000000000000000001"},
        "macro_summary": {"summary_id": "summary_00000000000000000000000000000001"},
        "chunks": [material_chunk_dict],
        "occupancy_chunks": [],
        "construction_chunks": [],
    }
    local_map_bytes = canonical_json(local_map)
    local_entry = {
        "site_id": SITE,
        "archive_path": local_map_path,
        "local_map_sha256": hashlib.sha256(local_map_bytes).hexdigest(),
        "boundary_id": local_map["boundary"]["boundary_id"],
        "summary_id": local_map["macro_summary"]["summary_id"],
        "material_chunk_hashes": [material_chunk.sha256],
        "occupancy_chunk_hashes": [],
        "construction_chunk_hashes": [],
    }
    domains = {
        "world/regions.json": {
            "regions": [
                {
                    "region_id": REGION,
                    "cells": [0, 1],
                    "center": 0,
                    "area_m2": 2_000_000,
                    "boundary_cells": [0, 1],
                    "neighbors": [],
                }
            ]
        },
        "world/routes.json": {"routes": []},
        "world/sites.json": {
            "sites": [
                {
                    "site_id": SITE,
                    "region_id": REGION,
                    "cell": 0,
                    "suitability_ppm": 1_000_000,
                    "water_access": True,
                    "resource_access": True,
                    "score_components": [],
                }
            ]
        },
        "world/civilizations.json": {
            "civilizations": [
                {
                    "civilization_id": CIVILIZATION,
                    "name": "The First Compact",
                    "culture": "river-stone",
                    "government": "council",
                    "language_id": LANGUAGE,
                    "capital_site_id": SITE,
                    "capabilities": ["agriculture"],
                    "needs": ["iron"],
                    "territory": [REGION],
                    "population": 100,
                    "economy": {
                        "grain": 100,
                        "materials": 50,
                        "currency": 25,
                        "price_grain_ppm": 1_000_000,
                    },
                    "active": True,
                }
            ]
        },
        "world/history/index.json": {
            "events": [
                "world/history/events/event_00000000000000000000000000000001.json",
                "world/history/events/event_00000000000000000000000000000002.json",
            ],
            "snapshots": [f"world/history/snapshots/year_{y:04d}.json" for y in range(0, 501, 10)],
        },
        "world/local/index.json": {
            "format": "storyteller.local-world-index.v1",
            "selection_policy": "all_registered_sites",
            "sites": [SITE],
            "entries": [local_entry],
        },
        local_map_path: local_map,
    }
    domain_ids = [
        builder.add(
            path.split("/")[-2] if path.endswith("index.json") else path.rsplit("/", 1)[-1][:-5],
            path,
            canonical_json(value),
            depends_on=[root_id],
        )
        for path, value in domains.items()
    ]
    builder.add(
        "localchunk",
        f"world/local/{SITE}/chunks/material/{material_chunk.sha256}.bin",
        encode_material_chunk(material_chunk),
        depends_on=domain_ids,
    )
    for domain in GRID_DOMAINS:

        def _chunk_bytes(layer: str, chunk_x: int, chunk_y: int, _domain: str = domain) -> bytes:
            return grid_chunk_bytes[_domain][layer][(chunk_x, chunk_y)]

        grid_index, chunk_members = build_grid_domain_files(
            domain,
            grid_catalogs[domain],
            _chunk_bytes,
        )
        grid_chunk_ids = [
            builder.add("gridchunk", path, data, depends_on=[root_id])
            for path, data in chunk_members
        ]
        builder.add(
            "griddomain",
            f"world/{domain}/index.json",
            canonical_json(grid_index),
            depends_on=[root_id, *grid_chunk_ids],
        )
    for domain, kind in FLAT_WORLD_DOMAINS.items():
        builder.add(
            "worldflat",
            f"world/{domain}.json",
            canonical_json(source_payloads[kind]),
            depends_on=[root_id],
        )
    event_one = "event_00000000000000000000000000000001"
    event_two = "event_00000000000000000000000000000002"
    empty_state_hash = hashlib.sha256(canonical_json({})).hexdigest()
    for event in (
        {
            "event_id": event_one,
            "year": 0,
            "month": 1,
            "sequence": 0,
            "kind": "founding",
            "causes": [],
            "participants": [CIVILIZATION],
            "locations": [SITE],
            "consequences": [],
            "summary": "The compact was founded.",
            "envelope_version": "storyteller.history-event.v1",
            "algorithm_version": 1,
            "source_ids": [CIVILIZATION, SITE],
            "before_state_sha256": empty_state_hash,
            "after_state_sha256": empty_state_hash,
        },
        {
            "event_id": event_two,
            "year": 1,
            "month": 1,
            "sequence": 1,
            "kind": "settlement",
            "causes": [event_one],
            "participants": [CIVILIZATION],
            "locations": [SITE],
            "consequences": [],
            "summary": "The compact endured.",
            "envelope_version": "storyteller.history-event.v1",
            "algorithm_version": 1,
            "source_ids": [CIVILIZATION, SITE],
            "before_state_sha256": empty_state_hash,
            "after_state_sha256": empty_state_hash,
        },
    ):
        builder.add(
            "event",
            f"world/history/events/{event['event_id']}.json",
            canonical_json(event),
            depends_on=domain_ids,
        )
    for year in range(0, 501, 10):
        builder.add(
            "snapshot",
            f"world/history/snapshots/year_{year:04d}.json",
            canonical_json(
                {
                    "year": year,
                    "ledger_position": 1 if year == 0 else 2,
                    "state_hash": hashlib.sha256(canonical_json({})).hexdigest(),
                    "state": {},
                }
            ),
            depends_on=domain_ids,
        )
    world_records = [record for record in builder.records if record["path"].startswith("world/")]
    world_ids = {record["path"]: record["artifact_id"] for record in world_records}
    world_hashes = {record["path"]: record["sha256"] for record in world_records}
    bible = {
        "schema_version": "2-pre1",
        "title": "Frozen v2 Reference",
        "present_year": 500,
        "authoritative_refs": sorted(world_ids.values()),
        "regions": [
            {
                "region_id": REGION,
                "center": 0,
                "biome_id": 3,
                "climate_regime": 1,
                "resources": ["iron"],
                "neighbors": [],
            }
        ],
        "routes": [],
        "sites": [
            {
                "site_id": SITE,
                "region_id": REGION,
                "cell": 0,
                "water_access": True,
                "resource_access": True,
            }
        ],
        "civilizations": [
            {
                "civilization_id": CIVILIZATION,
                "name": "The First Compact",
                "government": "council",
                "territory": [REGION],
            }
        ],
        "people": [],
        "history": [
            {
                "event_id": "event_00000000000000000000000000000001",
                "year": 0,
                "causes": [],
                "participants": [CIVILIZATION],
            },
            {
                "event_id": "event_00000000000000000000000000000002",
                "year": 1,
                "causes": ["event_00000000000000000000000000000001"],
                "participants": [CIVILIZATION],
            },
        ],
        "local_entities": [],
        "magic_claims": [],
        "interpretations": [],
        "megabeasts": [],
        "legendary_artifacts": [],
    }
    reconciliation = {
        "accepted": True,
        "world_artifact_ids": world_ids,
        "world_file_hashes": world_hashes,
        "ruleset_version": 1,
        "issues": [],
    }
    event_two = "event_00000000000000000000000000000002"
    authority = sorted([CIVILIZATION, SITE, event_two])
    narrative = {
        "bible": bible,
        "reconciliation": reconciliation,
        "style_bible": {"content_profile": "mature_dark_fantasy"},
        "story": {
            "schema_version": "2-pre1",
            "title": "Frozen v2 Reference",
            "world_artifact_ids": [root_id],
            "bible_hash": hashlib.sha256(canonical_json(bible)).hexdigest(),
            "reconciliation_hash": hashlib.sha256(canonical_json(reconciliation)).hexdigest(),
            "scenes": [
                {
                    "scene_id": SCENE,
                    "title": "The First Compact",
                    "summary": "A compact endures beside the river.",
                    "location_id": SITE,
                    "participant_ids": [CIVILIZATION],
                    "opportunity_id": event_two,
                    "authoritative_refs": authority,
                    "world_year": 1,
                }
            ],
        },
        "graph": {
            "schema_version": "2-pre1",
            "starting_node": NODE,
            "flags": [],
            "nodes": [
                {
                    "node_id": NODE,
                    "scene_id": SCENE,
                    "location_id": SITE,
                    "participant_ids": [CIVILIZATION],
                    "opportunity_id": event_two,
                    "authoritative_refs": authority,
                    "text": "The compact gathers at the river stones.",
                    "choices": [],
                    "media_intent": {
                        "image_prompt": "A river-stone council",
                        "music_mood": "solemn",
                        "tempo_bpm": 80,
                        "image_seed": 42,
                        "music_seed": 44,
                        "authoritative_refs": authority,
                    },
                    "ending": "complete",
                    "world_year": 1,
                }
            ],
        },
        "gm_index": {
            "entries": [
                {
                    "entry_id": "knowledge_00000000000000000000000000000001",
                    "kind": "civilization",
                    "normalized_text": "the first compact gathers at the eastern gate",
                    "source_ids": sorted(world_ids.values()),
                    "incoming_refs": [],
                    "outgoing_refs": [],
                    "reveal_after_nodes": [NODE],
                }
            ]
        },
    }
    for name, value in narrative.items():
        builder.add(
            name.replace("_bible", "style"),
            f"narrative/{name}.json",
            canonical_json(value),
            depends_on=domain_ids,
        )
    gm_fixture = cast(dict[str, Any], narrative["gm_index"])
    knowledge_entry = cast(dict[str, Any], gm_fixture["entries"][0])
    knowledge_payload = canonical_json(knowledge_entry)
    knowledge_path = "chunks/knowledge_00000000000000000000000000000001.json"
    knowledge_chunk_id = builder.add(
        "knowledgechunk",
        f"narrative/knowledge/{knowledge_path}",
        knowledge_payload,
        depends_on=domain_ids,
    )
    builder.add(
        "knowledgeindex",
        "narrative/knowledge/index.json",
        canonical_json(
            {
                "entries": [
                    {
                        "entry_id": knowledge_entry["entry_id"],
                        "tokens": ["compact", "eastern", "first", "gate", "gathers", "the"],
                        "reveal_after_nodes": knowledge_entry["reveal_after_nodes"],
                        "path": knowledge_path,
                        "sha256": hashlib.sha256(knowledge_payload).hexdigest(),
                        "size_bytes": len(knowledge_payload),
                    }
                ]
            }
        ),
        depends_on=[*domain_ids, knowledge_chunk_id],
    )
    image = deterministic_image(42)
    builder.add(
        "worldmap",
        "assets/maps/world.png",
        deterministic_image(40, 4096, 4096),
        depends_on=domain_ids,
    )
    builder.add(
        "regionmap",
        f"assets/maps/regions/{REGION}.png",
        deterministic_image(41, 1024, 1024),
        depends_on=domain_ids,
    )
    builder.add("image", node_assets[NODE]["image"], image, depends_on=domain_ids)
    builder.add(
        "thumbnail",
        node_assets[NODE]["thumbnail"],
        deterministic_image(43, 256, 256),
        depends_on=domain_ids,
    )
    score = generate_score(44, 80, NODE, tuple(domain_ids), "storyteller.media.fixture.v1")
    builder.add(
        "score", node_assets[NODE]["score"], canonical_json(asdict(score)), depends_on=domain_ids
    )
    builder.add("midi", node_assets[NODE]["midi"], score_to_smf_type1(score), depends_on=domain_ids)
    builder.write(
        destination,
        node_assets=node_assets,
        region_maps={REGION: f"assets/maps/regions/{REGION}.png"},
    )


def fixture_catalog() -> dict[str, object]:
    scenarios = [
        {"id": "complete", "path": "complete.story", "accepted": True},
        {"id": "small", "path": "small.story", "accepted": True},
        {
            "id": "unsupported-v1",
            "path": "unsupported-v1.story",
            "accepted": False,
            "issue_code": "PACKAGE_UNSUPPORTED_VERSION",
        },
        {
            "id": "corrupt",
            "path": "corrupt.story",
            "accepted": False,
            "issue_code": "PACKAGE_HASH_MISMATCH",
        },
        {
            "id": "dependency-broken",
            "path": "dependency-broken.story",
            "accepted": False,
            "issue_code": "PACKAGE_PROVENANCE_BROKEN",
        },
        {
            "id": "incomplete-world",
            "path": "incomplete-world.story",
            "accepted": False,
            "issue_code": "PACKAGE_MISSING_ARTIFACT",
        },
        {
            "id": "noncanonical-path-order",
            "path": "noncanonical-path-order.story",
            "accepted": False,
            "issue_code": "PACKAGE_PATH_ORDER",
        },
        {
            "id": "symlink-entry",
            "path": "symlink-entry.story",
            "accepted": False,
            "issue_code": "PACKAGE_LINK",
        },
        {
            "id": "noncanonical-metadata",
            "path": "noncanonical-metadata.story",
            "accepted": False,
            "issue_code": "PACKAGE_ZIP_METADATA",
        },
        {
            "id": "secondary-compression",
            "path": "secondary-compression.story",
            "accepted": False,
            "issue_code": "PACKAGE_SECONDARY_COMPRESSION",
        },
        {
            "id": "json-depth",
            "path": "json-depth.story",
            "accepted": False,
            "issue_code": "PACKAGE_JSON_DEPTH",
        },
        {
            "id": "json-bom",
            "path": "json-bom.story",
            "accepted": False,
            "issue_code": "PACKAGE_JSON_BOM",
        },
        {
            "id": "json-invalid-utf8",
            "path": "json-invalid-utf8.story",
            "accepted": False,
            "issue_code": "PACKAGE_JSON_UTF8",
        },
        {
            "id": "json-duplicate-key",
            "path": "json-duplicate-key.story",
            "accepted": False,
            "issue_code": "PACKAGE_JSON_DUPLICATE_KEY",
        },
        {
            "id": "json-malformed",
            "path": "json-malformed.story",
            "accepted": False,
            "issue_code": "PACKAGE_INVALID_JSON",
        },
        {
            "id": "json-number-profile",
            "path": "json-number-profile.story",
            "accepted": False,
            "issue_code": "PACKAGE_NUMBER_PROFILE",
        },
        {
            "id": "json-number-range",
            "path": "json-number-range.story",
            "accepted": False,
            "issue_code": "PACKAGE_NUMBER_RANGE",
        },
        {
            "id": "json-noncanonical-whitespace",
            "path": "json-noncanonical-whitespace.story",
            "accepted": False,
            "issue_code": "PACKAGE_JSON_NONCANONICAL",
        },
        {
            "id": "json-noncanonical-escape",
            "path": "json-noncanonical-escape.story",
            "accepted": False,
            "issue_code": "PACKAGE_JSON_NONCANONICAL",
        },
        {
            "id": "json-noncanonical-key-order",
            "path": "json-noncanonical-key-order.story",
            "accepted": False,
            "issue_code": "PACKAGE_JSON_NONCANONICAL",
        },
        {
            "id": "feature-order",
            "path": "feature-order.story",
            "accepted": False,
            "issue_code": "PACKAGE_FEATURE_ORDER",
        },
        {
            "id": "unknown-required-feature",
            "path": "unknown-required-feature.story",
            "accepted": False,
            "issue_code": "PACKAGE_REQUIRED_FEATURE",
        },
        {
            "id": "optional-feature",
            "path": "optional-feature.story",
            "accepted": False,
            "issue_code": "PACKAGE_OPTIONAL_FEATURE",
        },
        {
            "id": "schema-identity",
            "path": "schema-identity.story",
            "accepted": False,
            "issue_code": "PACKAGE_SCHEMA_IDENTITY",
        },
        {
            "id": "schema-invalid-manifest",
            "path": "schema-invalid-manifest.story",
            "accepted": False,
            "issue_code": "PACKAGE_SCHEMA",
        },
        {
            "id": "manifest-type-coercion",
            "path": "manifest-type-coercion.story",
            "accepted": False,
            "issue_code": "PACKAGE_TYPE_COERCION",
        },
        {
            "id": "world-index-type-confusion",
            "path": "world-index-type-confusion.story",
            "accepted": False,
            "issue_code": "PACKAGE_REGION_PARTITION",
        },
        {
            "id": "inventory-undeclared",
            "path": "inventory-undeclared.story",
            "accepted": False,
            "issue_code": "PACKAGE_UNDECLARED_ENTRY",
        },
        {
            "id": "artifact-wrong-size",
            "path": "artifact-wrong-size.story",
            "accepted": False,
            "issue_code": "PACKAGE_HASH_MISMATCH",
        },
        {
            "id": "artifact-wrong-hash",
            "path": "artifact-wrong-hash.story",
            "accepted": False,
            "issue_code": "PACKAGE_HASH_MISMATCH",
        },
        {
            "id": "artifact-duplicate-id",
            "path": "artifact-duplicate-id.story",
            "accepted": False,
            "issue_code": "PACKAGE_DUPLICATE_ID",
        },
        {
            "id": "artifact-duplicate-path",
            "path": "artifact-duplicate-path.story",
            "accepted": False,
            "issue_code": "PACKAGE_DUPLICATE_ID",
        },
        {
            "id": "artifact-id-derivation",
            "path": "artifact-id-derivation.story",
            "accepted": False,
            "issue_code": "PACKAGE_ARTIFACT_ID",
        },
        {
            "id": "dependency-cycle",
            "path": "dependency-cycle.story",
            "accepted": False,
            "issue_code": "PACKAGE_PROVENANCE_CYCLE",
        },
        {
            "id": "content-identity",
            "path": "content-identity.story",
            "accepted": False,
            "issue_code": "PACKAGE_CONTENT_ID",
        },
        {
            "id": "forbidden-script",
            "path": "forbidden-script.story",
            "accepted": False,
            "issue_code": "PACKAGE_FORBIDDEN_ENTRY",
        },
        {
            "id": "source-coverage-missing-row",
            "path": "source-coverage-missing-row.story",
            "accepted": False,
            "issue_code": "PACKAGE_WORLD_SOURCE_COVERAGE",
        },
        {
            "id": "source-coverage-byte-identity",
            "path": "source-coverage-byte-identity.story",
            "accepted": False,
            "issue_code": "PACKAGE_WORLD_SOURCE_COVERAGE",
        },
        {
            "id": "grid-chunk-encoding",
            "path": "grid-chunk-encoding.story",
            "accepted": False,
            "issue_code": "PACKAGE_GRID_CHUNK_HASH",
        },
        {
            "id": "grid-boundary-shape",
            "path": "grid-boundary-shape.story",
            "accepted": False,
            "issue_code": "PACKAGE_GRID_DOMAIN",
        },
        {
            "id": "climate-season-layers",
            "path": "climate-season-layers.story",
            "accepted": False,
            "issue_code": "PACKAGE_CLIMATE_LAYERS",
        },
        {
            "id": "region-partition",
            "path": "region-partition.story",
            "accepted": False,
            "issue_code": "PACKAGE_REGION_PARTITION",
        },
        {
            "id": "site-references",
            "path": "site-references.story",
            "accepted": False,
            "issue_code": "PACKAGE_SITE_REGION",
        },
        {
            "id": "route-topology",
            "path": "route-topology.story",
            "accepted": False,
            "issue_code": "PACKAGE_ROUTE_TOPOLOGY",
        },
        {
            "id": "hydrology-catalog",
            "path": "hydrology-catalog.story",
            "accepted": False,
            "issue_code": "PACKAGE_HYDROLOGY_CATALOG",
        },
        {
            "id": "hydrology-grid-layers",
            "path": "hydrology-grid-layers.story",
            "accepted": False,
            "issue_code": "PACKAGE_HYDROLOGY_CATALOG",
        },
        {
            "id": "resource-grid-layers",
            "path": "resource-grid-layers.story",
            "accepted": False,
            "issue_code": "PACKAGE_RESOURCE_CATALOG",
        },
        {
            "id": "deposit-geology",
            "path": "deposit-geology.story",
            "accepted": False,
            "issue_code": "PACKAGE_DEPOSIT_GEOLOGY",
        },
        {
            "id": "civilization-references",
            "path": "civilization-references.story",
            "accepted": False,
            "issue_code": "PACKAGE_CIVILIZATION_REFERENCES",
        },
        {
            "id": "event-order",
            "path": "event-order.story",
            "accepted": False,
            "issue_code": "PACKAGE_EVENT_ORDER",
        },
        {
            "id": "snapshot-integrity",
            "path": "snapshot-integrity.story",
            "accepted": False,
            "issue_code": "PACKAGE_SNAPSHOT_CADENCE",
        },
        {
            "id": "history-replay-hash",
            "path": "history-replay-hash.story",
            "accepted": False,
            "issue_code": "PACKAGE_HISTORY_REPLAY",
        },
        {
            "id": "earlier-causes",
            "path": "earlier-causes.story",
            "accepted": False,
            "issue_code": "PACKAGE_EVENT_ORDER",
        },
        {
            "id": "graph-semantics",
            "path": "graph-semantics.story",
            "accepted": False,
            "issue_code": "PACKAGE_GRAPH_SEMANTICS",
        },
        {
            "id": "story-graph-references",
            "path": "story-graph-references.story",
            "accepted": False,
            "issue_code": "PACKAGE_STORY_GRAPH_REFERENCES",
        },
        {
            "id": "bible-authority",
            "path": "bible-authority.story",
            "accepted": False,
            "issue_code": "PACKAGE_BIBLE_AUTHORITY",
        },
        {
            "id": "reconciliation-inputs",
            "path": "reconciliation-inputs.story",
            "accepted": False,
            "issue_code": "PACKAGE_RECONCILIATION_INPUTS",
        },
        {
            "id": "reference-resolution",
            "path": "reference-resolution.story",
            "accepted": False,
            "issue_code": "PACKAGE_REFERENCE_RESOLUTION",
        },
        {
            "id": "score-references",
            "path": "score-references.story",
            "accepted": False,
            "issue_code": "PACKAGE_SCORE_REFERENCES",
        },
        {
            "id": "score-beat-arithmetic",
            "path": "score-beat-arithmetic.story",
            "accepted": False,
            "issue_code": "PACKAGE_SCORE_BEAT_ARITHMETIC",
        },
        {
            "id": "score-event-shape",
            "path": "score-event-shape.story",
            "accepted": False,
            "issue_code": "PACKAGE_SCORE_EVENT_SHAPE",
        },
        {
            "id": "score-event-order",
            "path": "score-event-order.story",
            "accepted": False,
            "issue_code": "PACKAGE_SCORE_EVENT_ORDER",
        },
        {
            "id": "score-marker-order",
            "path": "score-marker-order.story",
            "accepted": False,
            "issue_code": "PACKAGE_SCORE_MARKER_ORDER",
        },
        {
            "id": "score-track-program",
            "path": "score-track-program.story",
            "accepted": False,
            "issue_code": "PACKAGE_SCORE_TRACK_PROGRAM",
        },
        {
            "id": "score-midi-hash",
            "path": "score-midi-hash.story",
            "accepted": False,
            "issue_code": "PACKAGE_SCORE_MIDI_HASH",
        },
        {
            "id": "midi-profile",
            "path": "midi-profile.story",
            "accepted": False,
            "issue_code": "PACKAGE_MIDI_PROFILE",
        },
        {
            "id": "media-coverage",
            "path": "media-coverage.story",
            "accepted": False,
            "issue_code": "PACKAGE_MEDIA_COVERAGE",
        },
        {
            "id": "media-mandatory",
            "path": "media-mandatory.story",
            "accepted": False,
            "issue_code": "PACKAGE_SCHEMA",
        },
        {
            "id": "gm-coverage",
            "path": "gm-coverage.story",
            "accepted": False,
            "issue_code": "PACKAGE_GM_COVERAGE",
        },
        {
            "id": "knowledge-index-reveal",
            "path": "knowledge-index-reveal.story",
            "accepted": False,
            "issue_code": "PACKAGE_KNOWLEDGE_INDEX",
        },
        {
            "id": "knowledge-chunk-identity",
            "path": "knowledge-chunk-identity.story",
            "accepted": False,
            "issue_code": "PACKAGE_KNOWLEDGE_CHUNK",
        },
        {
            "id": "knowledge-locator-coverage",
            "path": "knowledge-locator-coverage.story",
            "accepted": False,
            "issue_code": "PACKAGE_KNOWLEDGE_COVERAGE",
        },
        {
            "id": "local-chunk-binary",
            "path": "local-chunk-binary.story",
            "accepted": False,
            "issue_code": "PACKAGE_LOCAL_CHUNK_HASH",
        },
        {
            "id": "canonical-array-order",
            "path": "canonical-array-order.story",
            "accepted": False,
            "issue_code": "PACKAGE_ARRAY_ORDER",
        },
        {
            "id": "acceptance-order",
            "path": "acceptance-order.story",
            "accepted": False,
            "issue_code": "PACKAGE_PATH_ORDER",
        },
        {
            "id": "png-profile",
            "path": "png-profile.story",
            "accepted": False,
            "issue_code": "PACKAGE_PNG_PROFILE",
        },
        {
            "id": "png-map-profile",
            "path": "png-map-profile.story",
            "accepted": False,
            "issue_code": "PACKAGE_PNG_PROFILE",
        },
    ]
    return {"format": "storyteller.fixture-catalog.v2", "scenarios": scenarios}


def write_fixture_corpus(destination: Path) -> dict[str, object]:
    """Write the shared v2 package corpus into ``destination``. Does not write schemas."""
    destination.mkdir(parents=True, exist_ok=True)
    build_complete(destination / "complete.story")
    shutil.copyfile(destination / "complete.story", destination / "small.story")
    with zipfile.ZipFile(destination / "complete.story") as source:
        members = {name: source.read(name) for name in source.namelist()}

    def write_member(
        archive: zipfile.ZipFile,
        path: str,
        data: bytes,
        *,
        date_time: tuple[int, int, int, int, int, int] = (1980, 1, 1, 0, 0, 0),
        mode: int = stat.S_IFREG | 0o644,
    ) -> None:
        info = zipfile.ZipInfo(path, date_time)
        info.create_system = 3
        info.external_attr = mode << 16
        info.compress_type = zipfile.ZIP_STORED if path.endswith(".png") else zipfile.ZIP_DEFLATED
        archive.writestr(info, data)

    def invalid(name: str, mutate: Callable[[dict[str, bytes]], None]) -> None:
        changed = dict(members)
        mutate(changed)
        with zipfile.ZipFile(destination / name, "w") as archive:
            for path, data in sorted(changed.items()):
                write_member(archive, path, data)

    def v1(changed: dict[str, bytes]) -> None:
        manifest = json.loads(changed["manifest.json"])
        manifest["package_version"] = 1
        changed["manifest.json"] = canonical_json(manifest)

    def corrupt(changed: dict[str, bytes]) -> None:
        binary_path = next(path for path in sorted(changed) if path.endswith(".bin"))
        changed[binary_path] += b"\0"

    def dependency(changed: dict[str, bytes]) -> None:
        manifest = json.loads(changed["manifest.json"])
        record = manifest["artifacts"][0]
        record["depends_on"] = ["missing_00000000000000000000000000000000"]
        replacement = artifact_record(
            record["kind"],
            record["path"],
            changed[record["path"]],
            depends_on=record["depends_on"],
            producer_data=record["producer"],
        )
        record["artifact_id"] = replacement["artifact_id"]
        changed["manifest.json"] = canonical_json(manifest)

    def incomplete(changed: dict[str, bytes]) -> None:
        changed.pop(next(path for path in changed if path.startswith("assets/midi/")))

    invalid("unsupported-v1.story", v1)
    invalid("corrupt.story", corrupt)
    invalid("dependency-broken.story", dependency)
    invalid("incomplete-world.story", incomplete)
    media_coverage_members = dict(members)
    media_coverage_manifest = json.loads(media_coverage_members["manifest.json"])
    media_coverage_manifest["node_assets"][NODE]["midi"] = f"assets/midi/{NODE}_alternate.mid"
    media_coverage_members["manifest.json"] = canonical_json(media_coverage_manifest)
    with zipfile.ZipFile(destination / "media-coverage.story", "w") as archive:
        for path, data in sorted(media_coverage_members.items()):
            write_member(archive, path, data)
    media_mandatory_members = dict(members)
    media_mandatory_manifest = json.loads(media_mandatory_members["manifest.json"])
    del media_mandatory_manifest["node_assets"][NODE]["midi"]
    media_mandatory_members["manifest.json"] = canonical_json(media_mandatory_manifest)
    with zipfile.ZipFile(destination / "media-mandatory.story", "w") as archive:
        for path, data in sorted(media_mandatory_members.items()):
            write_member(archive, path, data)
    array_order_members = dict(members)
    array_order_manifest = json.loads(array_order_members["manifest.json"])
    array_order_manifest["artifacts"].reverse()
    array_order_members["manifest.json"] = canonical_json(array_order_manifest)
    with zipfile.ZipFile(destination / "canonical-array-order.story", "w") as archive:
        for path, data in sorted(array_order_members.items()):
            write_member(archive, path, data)
    with zipfile.ZipFile(destination / "noncanonical-path-order.story", "w") as archive:
        for path in sorted(members, reverse=True):
            write_member(archive, path, members[path])
    acceptance_members = dict(members)
    acceptance_manifest = json.loads(acceptance_members["manifest.json"])
    acceptance_manifest["package_version"] = 1
    acceptance_members["manifest.json"] = canonical_json(acceptance_manifest)
    with zipfile.ZipFile(destination / "acceptance-order.story", "w") as archive:
        for path in sorted(acceptance_members, reverse=True):
            write_member(archive, path, acceptance_members[path])
    symlink_path = next(path for path in sorted(members) if path != "manifest.json")
    with zipfile.ZipFile(destination / "symlink-entry.story", "w") as archive:
        for path in sorted(members):
            if path == symlink_path:
                write_member(archive, path, members[path], mode=stat.S_IFLNK | 0o777)
            else:
                write_member(archive, path, members[path])
    with zipfile.ZipFile(destination / "noncanonical-metadata.story", "w") as archive:
        for index, path in enumerate(sorted(members)):
            date_time = (1981, 1, 1, 0, 0, 0) if index == 0 else (1980, 1, 1, 0, 0, 0)
            write_member(archive, path, members[path], date_time=date_time)
    nested_members = dict(members)
    binary_path = next(path for path in sorted(nested_members) if path.endswith(".bin"))
    nested_members[binary_path] = b"\x1f\x8b" + nested_members[binary_path]
    with zipfile.ZipFile(destination / "secondary-compression.story", "w") as archive:
        for path, data in sorted(nested_members.items()):
            write_member(archive, path, data)
    deep_members = dict(members)
    deep_manifest = json.loads(deep_members["manifest.json"])
    deep_manifest["depth_probe"] = json.loads("[" * 129 + "0" + "]" * 129)
    deep_members["manifest.json"] = json.dumps(
        deep_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    with zipfile.ZipFile(destination / "json-depth.story", "w") as archive:
        for path, data in sorted(deep_members.items()):
            write_member(archive, path, data)
    for fixture_name, prefix in (
        ("json-bom.story", b"\xef\xbb\xbf"),
        ("json-invalid-utf8.story", b"\xff"),
    ):
        encoded_members = dict(members)
        encoded_members["manifest.json"] = prefix + encoded_members["manifest.json"]
        with zipfile.ZipFile(destination / fixture_name, "w") as archive:
            for path, data in sorted(encoded_members.items()):
                write_member(archive, path, data)
    duplicate_members = dict(members)
    duplicate_members["manifest.json"] = (
        b'{"package\\u005fformat":"storyteller.story",' + duplicate_members["manifest.json"][1:]
    )
    with zipfile.ZipFile(destination / "json-duplicate-key.story", "w") as archive:
        for path, data in sorted(duplicate_members.items()):
            write_member(archive, path, data)
    for fixture_name, probe in (
        ("json-malformed.story", b'"probe":true,}'),
        ("json-number-profile.story", b'"probe":1.5}'),
        ("json-number-range.story", b'"probe":9007199254740992}'),
    ):
        profile_members = dict(members)
        profile_members["manifest.json"] = profile_members["manifest.json"][:-1] + b"," + probe
        with zipfile.ZipFile(destination / fixture_name, "w") as archive:
            for path, data in sorted(profile_members.items()):
                write_member(archive, path, data)
    noncanonical_manifests = {
        "json-noncanonical-whitespace.story": members["manifest.json"].replace(b":", b": ", 1),
        "json-noncanonical-escape.story": members["manifest.json"].replace(
            b'"storyteller.story"', b'"storyteller\\u002estory"', 1
        ),
        "json-noncanonical-key-order.story": json.dumps(
            dict(reversed(list(json.loads(members["manifest.json"]).items()))),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8"),
    }
    for fixture_name, manifest_bytes in noncanonical_manifests.items():
        noncanonical_members = dict(members)
        noncanonical_members["manifest.json"] = manifest_bytes
        with zipfile.ZipFile(destination / fixture_name, "w") as archive:
            for path, data in sorted(noncanonical_members.items()):
                write_member(archive, path, data)

    def feature_fixture(name: str, mutate: Callable[[dict[str, Any]], None]) -> None:
        feature_members = dict(members)
        feature_manifest = json.loads(feature_members["manifest.json"])
        mutate(feature_manifest)
        feature_members["manifest.json"] = canonical_json(feature_manifest)
        with zipfile.ZipFile(destination / name, "w") as archive:
            for path, data in sorted(feature_members.items()):
                write_member(archive, path, data)

    feature_fixture(
        "feature-order.story",
        lambda manifest: manifest.update(
            required_features=list(reversed(manifest["required_features"]))
        ),
    )
    feature_fixture(
        "unknown-required-feature.story",
        lambda manifest: manifest.update(
            required_features=sorted(manifest["required_features"][:-1] + ["unknown_feature"])
        ),
    )
    feature_fixture(
        "optional-feature.story",
        lambda manifest: manifest.update(optional_features=["future_feature"]),
    )
    schema_members = dict(members)
    schema_manifest = json.loads(schema_members["manifest.json"])
    schema_manifest["artifacts"][0]["producer"]["schema_sha256"] = "0" * 64
    schema_members["manifest.json"] = canonical_json(schema_manifest)
    with zipfile.ZipFile(destination / "schema-identity.story", "w") as archive:
        for path, data in sorted(schema_members.items()):
            write_member(archive, path, data)
    invalid_schema_members = dict(members)
    invalid_schema_manifest = json.loads(invalid_schema_members["manifest.json"])
    invalid_schema_manifest["schema_probe"] = True
    invalid_schema_members["manifest.json"] = canonical_json(invalid_schema_manifest)
    with zipfile.ZipFile(destination / "schema-invalid-manifest.story", "w") as archive:
        for path, data in sorted(invalid_schema_members.items()):
            write_member(archive, path, data)
    coercion_members = dict(members)
    coercion_manifest = json.loads(coercion_members["manifest.json"])
    coercion_manifest["package_version"] = "2"
    coercion_members["manifest.json"] = canonical_json(coercion_manifest)
    with zipfile.ZipFile(destination / "manifest-type-coercion.story", "w") as archive:
        for path, data in sorted(coercion_members.items()):
            write_member(archive, path, data)
    undeclared_members = dict(members)
    undeclared_members["zz_inventory_probe.txt"] = b"undeclared"
    with zipfile.ZipFile(destination / "inventory-undeclared.story", "w") as archive:
        for path, data in sorted(undeclared_members.items()):
            write_member(archive, path, data)

    def inventory_fixture(name: str, mutate: Callable[[dict[str, Any]], None]) -> None:
        inventory_members = dict(members)
        inventory_manifest = json.loads(inventory_members["manifest.json"])
        mutate(inventory_manifest)
        inventory_members["manifest.json"] = canonical_json(inventory_manifest)
        with zipfile.ZipFile(destination / name, "w") as archive:
            for path, data in sorted(inventory_members.items()):
                write_member(archive, path, data)

    inventory_fixture(
        "artifact-wrong-size.story",
        lambda manifest: manifest["artifacts"][0].update(
            size_bytes=manifest["artifacts"][0]["size_bytes"] + 1
        ),
    )
    inventory_fixture(
        "artifact-wrong-hash.story",
        lambda manifest: manifest["artifacts"][0].update(sha256="0" * 64),
    )
    inventory_fixture(
        "artifact-duplicate-id.story",
        lambda manifest: manifest["artifacts"][1].update(
            artifact_id=manifest["artifacts"][0]["artifact_id"]
        ),
    )
    inventory_fixture(
        "artifact-duplicate-path.story",
        lambda manifest: manifest["artifacts"][1].update(path=manifest["artifacts"][0]["path"]),
    )
    inventory_fixture(
        "artifact-id-derivation.story",
        lambda manifest: manifest["artifacts"][0].update(
            artifact_id="invalid_00000000000000000000000000000000"
        ),
    )

    def cycle(manifest: dict[str, Any]) -> None:
        first, second = manifest["artifacts"][:2]
        first["depends_on"] = [second["artifact_id"]]
        second["depends_on"] = [first["artifact_id"]]

    inventory_fixture("dependency-cycle.story", cycle)
    inventory_fixture(
        "content-identity.story",
        lambda manifest: manifest.update(
            content_hash="0" * 64,
            story_id="story_00000000000000000000000000000000",
        ),
    )
    forbidden_members = dict(members)
    forbidden_members["zz_payload.sh"] = b"#!/bin/sh\n"
    with zipfile.ZipFile(destination / "forbidden-script.story", "w") as archive:
        for path, data in sorted(forbidden_members.items()):
            write_member(archive, path, data)

    def coverage_fixture(name: str, mutate: Callable[[dict[str, Any]], None]) -> None:
        coverage_members = dict(members)
        coverage_path = "world/source/coverage.json"
        coverage = json.loads(coverage_members[coverage_path])
        mutate(coverage)
        coverage_members[coverage_path] = canonical_json(coverage)
        manifest = json.loads(coverage_members["manifest.json"])
        record = next(item for item in manifest["artifacts"] if item["path"] == coverage_path)
        replacement = artifact_record(
            record["kind"],
            coverage_path,
            coverage_members[coverage_path],
            depends_on=record["depends_on"],
            producer_data=record["producer"],
        )
        record.update(replacement)
        manifest["content_hash"] = content_hash(manifest["artifacts"])
        manifest["story_id"] = f"story_{manifest['content_hash'][:32]}"
        coverage_members["manifest.json"] = canonical_json(manifest)
        with zipfile.ZipFile(destination / name, "w") as archive:
            for path, data in sorted(coverage_members.items()):
                write_member(archive, path, data)

    coverage_fixture(
        "source-coverage-missing-row.story", lambda coverage: coverage["sources"].pop()
    )
    coverage_fixture(
        "source-coverage-byte-identity.story",
        lambda coverage: coverage["sources"][0].update(sha256="0" * 64),
    )

    def resign_record(
        manifest: dict[str, Any],
        path: str,
        data: bytes,
        *,
        new_path: str | None = None,
    ) -> tuple[str, str]:
        record = next(item for item in manifest["artifacts"] if item["path"] == path)
        old_id = record["artifact_id"]
        replacement = artifact_record(
            record["kind"],
            new_path or path,
            data,
            depends_on=record["depends_on"],
            producer_data=record["producer"],
        )
        record.update(replacement)
        return old_id, record["artifact_id"]

    binary_members = dict(members)
    binary_manifest = json.loads(binary_members["manifest.json"])
    terrain_index_path = "world/terrain/index.json"
    terrain_index = json.loads(binary_members[terrain_index_path])
    layer_name = next(iter(terrain_index["layers"]))
    descriptor = terrain_index["layers"][layer_name]["chunks"][0]
    old_chunk_path = f"world/terrain/chunks/{layer_name}/{descriptor['sha256']}.bin"
    invalid_chunk = binary_members.pop(old_chunk_path)[:-1]
    new_chunk_hash = hashlib.sha256(invalid_chunk).hexdigest()
    new_chunk_path = f"world/terrain/chunks/{layer_name}/{new_chunk_hash}.bin"
    binary_members[new_chunk_path] = invalid_chunk
    old_chunk_id, new_chunk_id = resign_record(
        binary_manifest,
        old_chunk_path,
        invalid_chunk,
        new_path=new_chunk_path,
    )
    descriptor["sha256"] = new_chunk_hash
    binary_members[terrain_index_path] = canonical_json(terrain_index)
    index_record = next(
        item for item in binary_manifest["artifacts"] if item["path"] == terrain_index_path
    )
    index_record["depends_on"] = [
        new_chunk_id if dependency == old_chunk_id else dependency
        for dependency in index_record["depends_on"]
    ]
    resign_record(binary_manifest, terrain_index_path, binary_members[terrain_index_path])
    binary_manifest["content_hash"] = content_hash(binary_manifest["artifacts"])
    binary_manifest["story_id"] = f"story_{binary_manifest['content_hash'][:32]}"
    binary_members["manifest.json"] = canonical_json(binary_manifest)
    with zipfile.ZipFile(destination / "grid-chunk-encoding.story", "w") as archive:
        for path, data in sorted(binary_members.items()):
            write_member(archive, path, data)

    boundary_members = dict(members)
    boundary_manifest = json.loads(boundary_members["manifest.json"])
    boundary_index = json.loads(boundary_members[terrain_index_path])
    boundary_index["width"] += 1
    boundary_members[terrain_index_path] = canonical_json(boundary_index)
    resign_record(boundary_manifest, terrain_index_path, boundary_members[terrain_index_path])
    boundary_manifest["content_hash"] = content_hash(boundary_manifest["artifacts"])
    boundary_manifest["story_id"] = f"story_{boundary_manifest['content_hash'][:32]}"
    boundary_members["manifest.json"] = canonical_json(boundary_manifest)
    with zipfile.ZipFile(destination / "grid-boundary-shape.story", "w") as archive:
        for path, data in sorted(boundary_members.items()):
            write_member(archive, path, data)
    climate_members = dict(members)
    climate_manifest = json.loads(climate_members["manifest.json"])
    climate_index_path = "world/climate/index.json"
    climate_index = json.loads(climate_members[climate_index_path])
    climate_index["layers"].pop("climate_season_00_hazard_ppm")
    climate_members[climate_index_path] = canonical_json(climate_index)
    resign_record(climate_manifest, climate_index_path, climate_members[climate_index_path])
    climate_manifest["content_hash"] = content_hash(climate_manifest["artifacts"])
    climate_manifest["story_id"] = f"story_{climate_manifest['content_hash'][:32]}"
    climate_members["manifest.json"] = canonical_json(climate_manifest)
    with zipfile.ZipFile(destination / "climate-season-layers.story", "w") as archive:
        for path, data in sorted(climate_members.items()):
            write_member(archive, path, data)

    def resigned_domain_fixture(
        fixture_name: str,
        domain_path: str,
        mutate: Callable[[dict[str, Any]], None],
    ) -> None:
        changed_members = dict(members)
        changed_manifest = json.loads(changed_members["manifest.json"])
        domain = json.loads(changed_members[domain_path])
        mutate(domain)
        changed_members[domain_path] = canonical_json(domain)
        original = {record["artifact_id"]: dict(record) for record in changed_manifest["artifacts"]}
        rebuilt: dict[str, dict[str, Any]] = {}

        def rebuild(old_id: str) -> dict[str, Any]:
            if old_id in rebuilt:
                return rebuilt[old_id]
            record = original[old_id]
            dependencies = [rebuild(item)["artifact_id"] for item in record["depends_on"]]
            replacement = artifact_record(
                record["kind"],
                record["path"],
                changed_members[record["path"]],
                depends_on=dependencies,
                producer_data=record["producer"],
            )
            rebuilt[old_id] = replacement
            return replacement

        changed_manifest["artifacts"] = [
            rebuild(record["artifact_id"]) for record in changed_manifest["artifacts"]
        ]
        changed_manifest["content_hash"] = content_hash(changed_manifest["artifacts"])
        changed_manifest["story_id"] = f"story_{changed_manifest['content_hash'][:32]}"
        changed_members["manifest.json"] = canonical_json(changed_manifest)
        with zipfile.ZipFile(destination / fixture_name, "w") as archive:
            for path, data in sorted(changed_members.items()):
                write_member(archive, path, data)

    def resigned_members_fixture(fixture_name: str, replacements: dict[str, bytes]) -> None:
        changed_members = dict(members)
        changed_members.update(replacements)
        changed_manifest = json.loads(changed_members["manifest.json"])
        original = {record["artifact_id"]: dict(record) for record in changed_manifest["artifacts"]}
        rebuilt: dict[str, dict[str, Any]] = {}

        def rebuild(old_id: str) -> dict[str, Any]:
            if old_id in rebuilt:
                return rebuilt[old_id]
            record = original[old_id]
            dependencies = [rebuild(item)["artifact_id"] for item in record["depends_on"]]
            replacement = artifact_record(
                record["kind"],
                record["path"],
                changed_members[record["path"]],
                depends_on=dependencies,
                producer_data=record["producer"],
            )
            rebuilt[old_id] = replacement
            return replacement

        changed_manifest["artifacts"] = [
            rebuild(record["artifact_id"]) for record in changed_manifest["artifacts"]
        ]
        changed_manifest["content_hash"] = content_hash(changed_manifest["artifacts"])
        changed_manifest["story_id"] = f"story_{changed_manifest['content_hash'][:32]}"
        changed_members["manifest.json"] = canonical_json(changed_manifest)
        with zipfile.ZipFile(destination / fixture_name, "w") as archive:
            for path, data in sorted(changed_members.items()):
                write_member(archive, path, data)

    resigned_domain_fixture(
        "world-index-type-confusion.story",
        "world/index.json",
        lambda world: world.update(width="one"),
    )

    resigned_domain_fixture(
        "region-partition.story",
        "world/regions.json",
        lambda domain: domain["regions"][0].update(cells=[]),
    )
    resigned_domain_fixture(
        "site-references.story",
        "world/sites.json",
        lambda domain: domain["sites"][0].update(cell=2),
    )

    def add_broken_route(domain: dict[str, Any]) -> None:
        domain["routes"].append(
            {
                "route_id": "route_00000000000000000000000000000001",
                "start_region": REGION,
                "end_region": "region_00000000000000000000000000000002",
                "cells": [0],
                "distance_m": 0,
                "terrain_cost": 0,
                "river_crossings": 0,
                "seasonal_risk_ppm": [0, 0, 0, 0],
                "seasonal_capacity": [1, 1, 1, 1],
                "route_kind": 1,
                "seasonal_cells": [[0], [0], [0], [0]],
                "traversable_seasons": [True, True, True, True],
                "cost_unit": "fixed",
                "annual_maintenance": 0,
                "source_ids": [],
            }
        )

    resigned_domain_fixture("route-topology.story", "world/routes.json", add_broken_route)
    resigned_domain_fixture(
        "hydrology-catalog.story",
        "world/hydrology.json",
        lambda domain: domain["terminals"][0].update(cell=2),
    )
    resigned_domain_fixture(
        "hydrology-grid-layers.story",
        "world/hydrology/index.json",
        lambda domain: domain["layers"].pop("hydrology_delta"),
    )
    resigned_domain_fixture(
        "resource-grid-layers.story",
        "world/resource_grid/index.json",
        lambda domain: domain["layers"].pop("resource_renewable_yield"),
    )
    resigned_domain_fixture(
        "deposit-geology.story",
        "world/resources.json",
        lambda domain: domain["deposits"][0].update(strata_id=2),
    )
    resigned_domain_fixture(
        "civilization-references.story",
        "world/civilizations.json",
        lambda domain: domain["civilizations"][0].update(
            capital_site_id="site_00000000000000000000000000000002",
        ),
    )
    resigned_domain_fixture(
        "event-order.story",
        "world/history/index.json",
        lambda domain: domain.update(events=list(reversed(domain["events"]))),
    )
    resigned_domain_fixture(
        "snapshot-integrity.story",
        "world/history/snapshots/year_0000.json",
        lambda snapshot: snapshot.update(state_hash="0" * 64),
    )
    resigned_domain_fixture(
        "history-replay-hash.story",
        "world/history/events/event_00000000000000000000000000000002.json",
        lambda event: event.update(before_state_sha256="0" * 64),
    )
    resigned_domain_fixture(
        "earlier-causes.story",
        "world/history/events/event_00000000000000000000000000000001.json",
        lambda event: event.update(
            causes=["event_00000000000000000000000000000002"],
        ),
    )
    resigned_domain_fixture(
        "graph-semantics.story",
        "narrative/graph.json",
        lambda graph: graph.update(
            starting_node="node_00000000000000000000000000000002",
        ),
    )
    resigned_domain_fixture(
        "story-graph-references.story",
        "narrative/story.json",
        lambda story: story["scenes"][0].update(
            location_id="site_00000000000000000000000000000002",
        ),
    )
    resigned_domain_fixture(
        "bible-authority.story",
        "narrative/bible.json",
        lambda bible: bible["authoritative_refs"].pop(),
    )

    def corrupt_reconciliation(reconciliation: dict[str, Any]) -> None:
        first = next(iter(reconciliation["world_file_hashes"]))
        reconciliation["world_file_hashes"][first] = "0" * 64

    resigned_domain_fixture(
        "reconciliation-inputs.story",
        "narrative/reconciliation.json",
        corrupt_reconciliation,
    )
    resigned_domain_fixture(
        "reference-resolution.story",
        "narrative/bible.json",
        lambda bible: bible["sites"][0].update(
            region_id="region_00000000000000000000000000000002",
        ),
    )
    reference_members = dict(members)
    reference_manifest = json.loads(reference_members["manifest.json"])
    reference_bible = json.loads(reference_members["narrative/bible.json"])
    reference_bible["sites"][0]["region_id"] = "region_00000000000000000000000000000002"
    reference_members["narrative/bible.json"] = canonical_json(reference_bible)
    reference_story = json.loads(reference_members["narrative/story.json"])
    reference_story["bible_hash"] = hashlib.sha256(
        reference_members["narrative/bible.json"],
    ).hexdigest()
    reference_members["narrative/story.json"] = canonical_json(reference_story)
    original = {record["artifact_id"]: dict(record) for record in reference_manifest["artifacts"]}
    rebuilt: dict[str, dict[str, Any]] = {}

    def rebuild_reference(old_id: str) -> dict[str, Any]:
        if old_id in rebuilt:
            return rebuilt[old_id]
        record = original[old_id]
        replacement = artifact_record(
            record["kind"],
            record["path"],
            reference_members[record["path"]],
            depends_on=[rebuild_reference(item)["artifact_id"] for item in record["depends_on"]],
            producer_data=record["producer"],
        )
        rebuilt[old_id] = replacement
        return replacement

    reference_manifest["artifacts"] = [
        rebuild_reference(record["artifact_id"]) for record in reference_manifest["artifacts"]
    ]
    reference_manifest["content_hash"] = content_hash(reference_manifest["artifacts"])
    reference_manifest["story_id"] = f"story_{reference_manifest['content_hash'][:32]}"
    reference_members["manifest.json"] = canonical_json(reference_manifest)
    with zipfile.ZipFile(destination / "reference-resolution.story", "w") as archive:
        for path, data in sorted(reference_members.items()):
            write_member(archive, path, data)
    score_path = f"assets/music/{NODE}.score.json"
    resigned_domain_fixture(
        "score-references.story",
        score_path,
        lambda score: score.update(source_ids=["unknown_00000000000000000000000000000000"]),
    )
    resigned_domain_fixture(
        "score-beat-arithmetic.story",
        score_path,
        lambda score: score["duration"].update(denominator=7),
    )
    resigned_domain_fixture(
        "score-event-shape.story",
        score_path,
        lambda score: score["tracks"][0]["events"][0].update(pitches=[]),
    )
    resigned_domain_fixture(
        "score-event-order.story",
        score_path,
        lambda score: score["tracks"][0].update(
            events=list(reversed(score["tracks"][0]["events"])),
        ),
    )
    resigned_domain_fixture(
        "score-marker-order.story",
        score_path,
        lambda score: score["markers"]["LOOP_START"].update(numerator=10),
    )
    resigned_domain_fixture(
        "score-track-program.story",
        score_path,
        lambda score: score["tracks"][0].update(gm_program=127),
    )
    resigned_domain_fixture(
        "score-midi-hash.story",
        score_path,
        lambda score: score.update(expected_midi_sha256="0" * 64),
    )
    resigned_domain_fixture(
        "gm-coverage.story",
        "narrative/gm_index.json",
        lambda gm: gm["entries"][0].update(source_ids=gm["entries"][0]["source_ids"][1:]),
    )
    knowledge_index_path = "narrative/knowledge/index.json"
    knowledge_chunk_path = (
        "narrative/knowledge/chunks/knowledge_00000000000000000000000000000001.json"
    )
    changed_index = json.loads(members[knowledge_index_path])
    changed_index["entries"][0]["reveal_after_nodes"] = []
    resigned_members_fixture(
        "knowledge-index-reveal.story", {knowledge_index_path: canonical_json(changed_index)}
    )
    changed_chunk = json.loads(members[knowledge_chunk_path])
    changed_chunk["normalized_text"] = "different bounded text"
    resigned_members_fixture(
        "knowledge-chunk-identity.story", {knowledge_chunk_path: canonical_json(changed_chunk)}
    )
    empty_index = json.loads(members[knowledge_index_path])
    empty_index["entries"] = []
    resigned_members_fixture(
        "knowledge-locator-coverage.story", {knowledge_index_path: canonical_json(empty_index)}
    )
    local_chunk_path = next(
        path
        for path in sorted(members)
        if path.startswith("world/local/") and path.endswith(".bin")
    )
    invalid_local_chunk = b"BADMAGIC" + members[local_chunk_path][8:]
    resigned_members_fixture(
        "local-chunk-binary.story", {local_chunk_path: invalid_local_chunk}
    )
    midi_path = json.loads(members["manifest.json"])["node_assets"][NODE]["midi"]
    invalid_midi = bytearray(members[midi_path])
    invalid_midi[12:14] = (959).to_bytes(2, "big")
    invalid_score = json.loads(members[score_path])
    invalid_score["expected_midi_sha256"] = hashlib.sha256(invalid_midi).hexdigest()
    resigned_members_fixture(
        "midi-profile.story",
        {midi_path: bytes(invalid_midi), score_path: canonical_json(invalid_score)},
    )
    image_path = json.loads(members["manifest.json"])["node_assets"][NODE]["image"]
    invalid_png = bytearray(members[image_path])
    invalid_png[24] = 16
    invalid_png[29:33] = (zlib.crc32(invalid_png[12:29]) & 0xFFFFFFFF).to_bytes(4, "big")
    resigned_members_fixture("png-profile.story", {image_path: bytes(invalid_png)})
    invalid_map = bytearray(members["assets/maps/world.png"])
    invalid_map[24] = 16
    invalid_map[29:33] = (zlib.crc32(invalid_map[12:29]) & 0xFFFFFFFF).to_bytes(4, "big")
    resigned_members_fixture("png-map-profile.story", {"assets/maps/world.png": bytes(invalid_map)})
    catalog = fixture_catalog()
    (destination / "catalog.json").write_bytes(canonical_json(catalog))
    return catalog


def expected_schema_names() -> tuple[str, ...]:
    return ("defs.schema.json",) + tuple(f"{name}.schema.json" for name in SCHEMA_STUB_REQUIRED)


def _archive_members(path: Path) -> list[tuple[str, int, bytes]]:
    with zipfile.ZipFile(path) as archive:
        return [
            (info.filename, info.external_attr, archive.read(info.filename))
            for info in archive.infolist()
        ]


def check_fixture_corpus() -> None:
    """Compare a fresh corpus to disk. Writes only under ``tmp/``; never schemas."""
    missing = [name for name in expected_schema_names() if not (SCHEMAS / name).is_file()]
    if missing:
        raise SystemExit("missing v2 schemas: " + ", ".join(missing))
    staging = ROOT / "tmp" / "v2-fixture-check"
    if staging.exists():
        shutil.rmtree(staging)
    catalog = write_fixture_corpus(staging)
    errors: list[str] = []
    on_disk_catalog = FIXTURES / "catalog.json"
    if not on_disk_catalog.is_file():
        errors.append("tests/fixtures/v2/catalog.json is missing")
    elif on_disk_catalog.read_bytes() != (staging / "catalog.json").read_bytes():
        errors.append("tests/fixtures/v2/catalog.json drifted")
    scenarios = catalog.get("scenarios")
    if not isinstance(scenarios, list):
        raise SystemExit("generated v2 fixture catalog has no scenario list")
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        relative = str(scenario["path"])
        generated = staging / relative
        existing = FIXTURES / relative
        if not existing.is_file():
            errors.append(f"missing fixture {relative}")
        elif _archive_members(generated) != _archive_members(existing):
            errors.append(f"fixture drifted: {relative}")
    shutil.rmtree(staging, ignore_errors=True)
    if errors:
        raise SystemExit("generate_v2_fixtures.py --check failed:\n" + "\n".join(errors))
    print(
        json.dumps(
            {
                "check": "ok",
                "fixtures": len(catalog["scenarios"]),
                "schemas": len(list(SCHEMAS.glob("*.schema.json"))),
            },
            sort_keys=True,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail on missing schemas or drifted fixtures; do not write schemas/",
    )
    args = parser.parse_args()
    if args.check:
        check_fixture_corpus()
        return
    generate_schemas()
    catalog = write_fixture_corpus(FIXTURES)
    print(
        json.dumps(
            {
                "fixtures": len(catalog["scenarios"]),
                "schemas": len(list(SCHEMAS.glob("*.schema.json"))),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
