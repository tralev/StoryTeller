#!/usr/bin/env python3
"""Generate the shared deterministic `.story` v2 acceptance corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import zipfile
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.narrative.media import deterministic_image, generate_score, score_to_smf_type1
from src.storage.package_v2 import (
    FLAT_WORLD_DOMAINS, GRID_DOMAINS, V2PackageBuilder, artifact_record, build_grid_domain_files,
    canonical_json,
)
from src.world.views import REQUIRED_KINDS
from src.worldgen.grid import (
    DenseGridCatalog, GridSpec, IntGrid, build_grid_manifest, iter_grid_chunks,
)
from src.worldgen.local_chunks import generate_material_chunks

GRID_LAYERS: dict[str, dict[str, tuple[int, ...]]] = {
    "terrain": {"terrain_elevation_mm": (1200,), "terrain_plate_id": (2,)},
    "climate": {"climate_annual_temperature_millic": (15000,)},
    "biomes": {"biome_id": (3,)},
}


def _grid_catalog_and_chunks(
    layers: dict[str, tuple[int, ...]], width: int, height: int, metres_per_world_cell: int,
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


# Expected v2 schema files. generate_schemas() may write stubs for names that
# are not yet authored; it must never overwrite a schema that already has
# `properties` or `$defs` (P8.C1 deepening cannot survive fixture regen).
SCHEMA_STUB_REQUIRED: dict[str, list[str]] = {
    "manifest": ["package_format", "package_version", "story_id", "artifacts"],
    "artifact-provenance": ["artifact_id", "kind", "path", "sha256", "producer"],
    "world-index": ["width", "height", "present_year", "domains"],
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
        "title": title, "type": "object",
    }
    if required:
        result["required"] = required
    return result


def schema_is_authored(path: Path) -> bool:
    """True when the file already declares closed records (must not be stubbed)."""
    if not path.is_file():
        return False
    data = json.loads(path.read_bytes())
    properties = data.get("properties")
    defs = data.get("$defs")
    return (
        isinstance(properties, dict) and bool(properties)
        or isinstance(defs, dict) and bool(defs)
    )


def _defs_ref(name: str) -> dict[str, object]:
    return {"$ref": f"https://storyteller.local/schemas/v2/defs.schema.json#/$defs/{name}"}


def _artifact_provenance_schema() -> dict[str, object]:
    artifact = _schema(
        "artifact-provenance",
        ["artifact_id", "kind", "path", "sha256", "size_bytes", "depends_on", "producer"],
    )
    artifact.update({"additionalProperties": False, "properties": {
        "artifact_id": _defs_ref("entityId"),
        "kind": _defs_ref("kind"),
        "path": _defs_ref("relativePath"),
        "sha256": _defs_ref("sha256"),
        "size_bytes": {"type": "integer", "minimum": 0},
        "depends_on": _defs_ref("entityIdList"),
        "producer": _defs_ref("producer"),
    }})
    return artifact


def _manifest_schema() -> dict[str, object]:
    manifest = _schema("manifest", ["package_format", "package_version", "story_id", "title",
                                    "content_profile", "master_seed", "required_features",
                                    "optional_features", "entry_node", "world", "artifacts",
                                    "node_assets", "region_maps", "content_hash"])
    manifest.update({"additionalProperties": False, "properties": {
        "package_format": {"const": "storyteller.story"}, "package_version": {"const": 2},
        "story_id": {"type": "string", "pattern": "^story_[0-9a-f]{32}$"},
        "title": {"type": "string", "minLength": 1},
        "content_profile": {"const": "mature_dark_fantasy"},
        "master_seed": {"type": "integer"},
        "required_features": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
        "optional_features": {"type": "array", "uniqueItems": True, "items": {"type": "string"}},
        "entry_node": {"type": "string", "pattern": "^node_[0-9a-f]{32}$"},
        "world": {"type": "object"}, "artifacts": {"type": "array"},
        "node_assets": {"type": "object"}, "region_maps": {"type": "object"},
        "content_hash": {"type": "string", "pattern": HASH_PATTERN}}})
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
    node_assets = {NODE: {"image": f"assets/images/{NODE}.png",
                          "thumbnail": f"assets/thumbnails/{NODE}.png",
                          "score": f"assets/music/{NODE}.score.json",
                          "midi": f"assets/midi/{NODE}.mid"}}
    builder = V2PackageBuilder("Frozen v2 Reference", 42, NODE)
    schema_ids: list[str] = []
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema_ids.append(builder.add("schema", f"schemas/{path.name}", path.read_bytes()))

    grid_catalogs: dict[str, DenseGridCatalog] = {}
    grid_chunk_bytes: dict[str, dict[str, dict[tuple[int, int], bytes]]] = {}
    for domain, layers in GRID_LAYERS.items():
        catalog, chunk_map = _grid_catalog_and_chunks(
            layers, width=1, height=1, metres_per_world_cell=1000,
        )
        grid_catalogs[domain] = catalog
        grid_chunk_bytes[domain] = chunk_map
    flat_payloads: dict[str, object] = {
        "hydrology": {"algorithm_version": 4, "lakes": [], "rivers": [], "terminals": []},
        "resources": {"algorithm_version": 2, "deposits": []},
    }
    source_payloads: dict[str, object] = {
        **{kind: asdict(grid_catalogs[domain]) for domain, kind in GRID_DOMAINS.items()},
        **{kind: flat_payloads[domain] for domain, kind in FLAT_WORLD_DOMAINS.items()},
    }

    source_ids: list[str] = []
    source_rows: list[dict[str, object]] = []
    for name in REQUIRED_KINDS:
        source_path = f"world/source/{name}.json"
        source_artifact_id = f"worldsource_{hashlib.sha256(name.encode()).hexdigest()[:32]}"
        payload = source_payloads.get(name, {})
        data = canonical_json({"artifact_id": source_artifact_id, "kind": name, "payload": payload})
        source_ids.append(builder.add("worldsource", source_path, data, depends_on=schema_ids))
        source_rows.append({"source_name": name, "archive_path": source_path,
                            "artifact_id": source_artifact_id, "sha256": hashlib.sha256(data).hexdigest(),
                            "size_bytes": len(data), "retention": "byte_for_byte"})
    builder.add("worldcoverage", "world/source/coverage.json", canonical_json({
        "format": "storyteller.world-source-coverage.v1",
        "required_domains": sorted(REQUIRED_KINDS), "sources": source_rows,
    }), depends_on=source_ids)
    world_index = {"width": 1, "height": 1, "present_year": 500,
                   "surface_chunk_shape": [256, 256], "local_chunk_shape": [32, 32, 16],
                   "snapshot_years": list(range(0, 501, 10)),
                   "domains": sorted(REQUIRED_KINDS), "source_artifact_ids": source_ids}
    root_id = builder.add("world", "world/index.json", canonical_json(world_index), depends_on=source_ids)
    local_map_path = f"world/local/{SITE}/index.json"
    (material_chunk,) = generate_material_chunks(
        width=1, height=1, z_levels=1, surface_height=(0,), strata=(7,),
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
        "world/regions.json": {"regions": [{"region_id": REGION, "cells": [[0, 0]], "adjacent": []}]},
        "world/routes.json": {"routes": []},
        "world/sites.json": {"sites": [{"site_id": SITE, "region_id": REGION, "x": 0, "y": 0}]},
        "world/civilizations.json": {"civilizations": []},
        "world/history/index.json": {"events": ["world/history/events/event_00000000000000000000000000000001.json"],
                                     "snapshots": [f"world/history/snapshots/year_{y:04d}.json" for y in range(0, 501, 10)]},
        "world/local/index.json": {
            "format": "storyteller.local-world-index.v1",
            "selection_policy": "all_registered_sites",
            "sites": [SITE],
            "entries": [local_entry],
        },
        local_map_path: local_map,
    }
    domain_ids = [builder.add(path.split("/")[-2] if path.endswith("index.json") else path.rsplit("/", 1)[-1][:-5],
                              path, canonical_json(value), depends_on=[root_id])
                  for path, value in domains.items()]
    builder.add(
        "localchunk", f"world/local/{SITE}/chunks/material/{material_chunk.sha256}.json",
        canonical_json(material_chunk_dict), depends_on=domain_ids,
    )
    for domain in GRID_DOMAINS:
        def _chunk_bytes(layer: str, chunk_x: int, chunk_y: int, _domain: str = domain) -> bytes:
            return grid_chunk_bytes[_domain][layer][(chunk_x, chunk_y)]
        grid_index, chunk_members = build_grid_domain_files(
            domain, grid_catalogs[domain], _chunk_bytes,
        )
        grid_chunk_ids = [
            builder.add("gridchunk", path, data, depends_on=[root_id])
            for path, data in chunk_members
        ]
        builder.add(
            "griddomain", f"world/{domain}/index.json", canonical_json(grid_index),
            depends_on=[root_id, *grid_chunk_ids],
        )
    for domain, kind in FLAT_WORLD_DOMAINS.items():
        builder.add(
            "worldflat", f"world/{domain}.json", canonical_json(source_payloads[kind]),
            depends_on=[root_id],
        )
    builder.add("event", "world/history/events/event_00000000000000000000000000000001.json",
                canonical_json({"event_id": "event_00000000000000000000000000000001", "year": 0,
                                "sequence": 0, "causes": [], "participants": [], "locations": [SITE]}),
                depends_on=domain_ids)
    for year in range(0, 501, 10):
        builder.add("snapshot", f"world/history/snapshots/year_{year:04d}.json",
                    canonical_json({"year": year, "ledger_position": 1, "state_hash": "0" * 64}),
                    depends_on=domain_ids)
    narrative = {
        "bible": {"schema_version": 2, "title": "Frozen v2 Reference", "world_refs": [root_id]},
        "reconciliation": {"accepted": True, "world_artifact_ids": [root_id], "issues": []},
        "style_bible": {"content_profile": "mature_dark_fantasy"},
        "story": {"schema_version": 2, "scenes": [{"scene_id": "scene_00000000000000000000000000000001"}]},
        "graph": {"schema_version": 2, "starting_node": NODE,
                  "nodes": [{"node_id": NODE, "ending": "complete", "choices": []}]},
        "gm_index": {"entries": [{"knowledge_id": "knowledge_00000000000000000000000000000001",
                                    "source_ids": [root_id], "reveal_after_nodes": [NODE]}]},
    }
    for name, value in narrative.items():
        builder.add(name.replace("_bible", "style"), f"narrative/{name}.json", canonical_json(value),
                    depends_on=domain_ids)
    image = deterministic_image(42)
    builder.add("worldmap", "assets/maps/world.png", deterministic_image(40, 4096, 4096), depends_on=domain_ids)
    builder.add("regionmap", f"assets/maps/regions/{REGION}.png",
                deterministic_image(41, 1024, 1024), depends_on=domain_ids)
    builder.add("image", node_assets[NODE]["image"], image, depends_on=domain_ids)
    builder.add("thumbnail", node_assets[NODE]["thumbnail"], deterministic_image(43, 256, 256), depends_on=domain_ids)
    score = generate_score(44, 80, NODE, tuple(domain_ids), "storyteller.media.fixture.v1")
    builder.add("score", node_assets[NODE]["score"], canonical_json(asdict(score)), depends_on=domain_ids)
    builder.add("midi", node_assets[NODE]["midi"], score_to_smf_type1(score), depends_on=domain_ids)
    builder.write(destination, node_assets=node_assets,
                  region_maps={REGION: f"assets/maps/regions/{REGION}.png"})


def fixture_catalog() -> dict[str, object]:
    scenarios = [
        {"id": "complete", "path": "complete.story", "accepted": True},
        {"id": "small", "path": "small.story", "accepted": True},
        {"id": "unsupported-v1", "path": "unsupported-v1.story", "accepted": False,
         "issue_code": "PACKAGE_UNSUPPORTED_VERSION"},
        {"id": "corrupt", "path": "corrupt.story", "accepted": False,
         "issue_code": "PACKAGE_HASH_MISMATCH"},
        {"id": "dependency-broken", "path": "dependency-broken.story", "accepted": False,
         "issue_code": "PACKAGE_PROVENANCE_BROKEN"},
        {"id": "incomplete-world", "path": "incomplete-world.story", "accepted": False,
         "issue_code": "PACKAGE_MISSING_ARTIFACT"},
    ]
    return {"format": "storyteller.fixture-catalog.v2", "scenarios": scenarios}


def write_fixture_corpus(destination: Path) -> dict[str, object]:
    """Write the shared v2 package corpus into ``destination``. Does not write schemas."""
    destination.mkdir(parents=True, exist_ok=True)
    build_complete(destination / "complete.story")
    shutil.copyfile(destination / "complete.story", destination / "small.story")
    with zipfile.ZipFile(destination / "complete.story") as source:
        members = {name: source.read(name) for name in source.namelist()}

    def invalid(name: str, mutate: Callable[[dict[str, bytes]], None]) -> None:
        changed = dict(members)
        mutate(changed)
        with zipfile.ZipFile(destination / name, "w") as archive:
            for path, data in sorted(changed.items()):
                archive.writestr(path, data)

    def v1(changed: dict[str, bytes]) -> None:
        manifest = json.loads(changed["manifest.json"]); manifest["package_version"] = 1
        changed["manifest.json"] = canonical_json(manifest)
    def corrupt(changed: dict[str, bytes]) -> None:
        changed["narrative/story.json"] += b" "
    def dependency(changed: dict[str, bytes]) -> None:
        manifest = json.loads(changed["manifest.json"])
        record = manifest["artifacts"][0]
        record["depends_on"] = ["missing_00000000000000000000000000000000"]
        replacement = artifact_record(record["kind"], record["path"], changed[record["path"]],
                                      depends_on=record["depends_on"], producer_data=record["producer"])
        record["artifact_id"] = replacement["artifact_id"]
        changed["manifest.json"] = canonical_json(manifest)
    def incomplete(changed: dict[str, bytes]) -> None:
        changed.pop(next(path for path in changed if path.startswith("assets/midi/")))
    invalid("unsupported-v1.story", v1); invalid("corrupt.story", corrupt)
    invalid("dependency-broken.story", dependency); invalid("incomplete-world.story", incomplete)
    catalog = fixture_catalog()
    (destination / "catalog.json").write_bytes(canonical_json(catalog))
    return catalog


def expected_schema_names() -> tuple[str, ...]:
    return ("defs.schema.json",) + tuple(
        f"{name}.schema.json" for name in SCHEMA_STUB_REQUIRED
    )


def _archive_members(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


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
    for scenario in catalog["scenarios"]:
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
        raise SystemExit(
            "generate_v2_fixtures.py --check failed:\n" + "\n".join(errors)
        )
    print(json.dumps({
        "check": "ok",
        "fixtures": len(catalog["scenarios"]),
        "schemas": len(list(SCHEMAS.glob("*.schema.json"))),
    }, sort_keys=True))


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
    print(json.dumps({
        "fixtures": len(catalog["scenarios"]),
        "schemas": len(list(SCHEMAS.glob("*.schema.json"))),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
