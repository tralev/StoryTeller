#!/usr/bin/env python3
"""Generate the shared deterministic `.story` v2 acceptance corpus."""
from __future__ import annotations

import json
import shutil
import sys
import hashlib
import zipfile
from dataclasses import asdict
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.narrative.media import deterministic_image, generate_score, score_to_midi
from src.storage.package_v2 import V2PackageBuilder, artifact_record, canonical_json
from src.world.views import REQUIRED_KINDS

FIXTURES = ROOT / "tests" / "fixtures" / "v2"
SCHEMAS = ROOT / "schemas" / "v2"
NODE = "node_00000000000000000000000000000001"
REGION = "region_00000000000000000000000000000001"
SITE = "site_00000000000000000000000000000001"


def _schema(title: str, required: list[str] | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://storyteller.local/schemas/v2/{title}.schema.json",
        "title": title, "type": "object",
    }
    if required:
        result["required"] = required
    return result


def generate_schemas() -> None:
    SCHEMAS.mkdir(parents=True, exist_ok=True)
    domains = {
        "manifest": ["package_format", "package_version", "story_id", "artifacts"],
        "artifact-provenance": ["artifact_id", "kind", "path", "sha256", "producer"],
        "world-index": ["width", "height", "present_year", "domains"],
        "terrain": ["chunk_shape"], "hydrology": [], "climate": ["chunk_shape"],
        "biomes": ["chunk_shape"], "resources": [], "regions": ["regions"],
        "routes": ["routes"], "sites": ["sites"], "civilizations": ["civilizations"],
        "history": ["events"], "snapshots": ["snapshots"], "local-map": ["site_id", "chunk_shape"],
        "bible": ["schema_version"], "reconciliation": ["accepted"], "style": [],
        "story": ["schema_version", "scenes"], "graph": ["schema_version", "starting_node", "nodes"],
        "structured-score": ["format_version", "ppq", "notes"], "gm-index": [],
    }
    for name, required in domains.items():
        (SCHEMAS / f"{name}.schema.json").write_bytes(canonical_json(_schema(name, required)))
    id_pattern = "^[a-z][a-z0-9]*_[0-9a-f]{32}$"
    hash_pattern = "^[0-9a-f]{64}$"
    artifact = _schema("artifact-provenance", ["artifact_id", "kind", "path", "sha256",
                                                       "size_bytes", "depends_on", "producer"])
    artifact.update({"additionalProperties": False, "properties": {
        "artifact_id": {"type": "string", "pattern": id_pattern},
        "kind": {"type": "string", "pattern": "^[a-z][a-z0-9_]*$"},
        "path": {"type": "string", "pattern": "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))[^\\\\]+$"},
        "sha256": {"type": "string", "pattern": hash_pattern},
        "size_bytes": {"type": "integer", "minimum": 0},
        "depends_on": {"type": "array", "uniqueItems": True,
                       "items": {"type": "string", "pattern": id_pattern}},
        "producer": {"type": "object", "required": ["component", "algorithm_version", "fingerprint"],
                     "properties": {"component": {"type": "string"},
                                    "algorithm_version": {"type": "integer", "minimum": 1},
                                    "fingerprint": {"type": "string", "pattern": hash_pattern}},
                     "additionalProperties": True}}})
    (SCHEMAS / "artifact-provenance.schema.json").write_bytes(canonical_json(artifact))
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
        "content_hash": {"type": "string", "pattern": hash_pattern}}})
    (SCHEMAS / "manifest.schema.json").write_bytes(canonical_json(manifest))


def build_complete(destination: Path) -> None:
    node_assets = {NODE: {"image": f"assets/images/{NODE}.png",
                          "thumbnail": f"assets/thumbnails/{NODE}.png",
                          "score": f"assets/music/{NODE}.score.json",
                          "midi": f"assets/midi/{NODE}.mid"}}
    builder = V2PackageBuilder("Frozen v2 Reference", 42, NODE)
    schema_ids: list[str] = []
    for path in sorted(SCHEMAS.glob("*.schema.json")):
        schema_ids.append(builder.add("schema", f"schemas/{path.name}", path.read_bytes()))
    source_ids: list[str] = []
    source_rows: list[dict[str, object]] = []
    for name in REQUIRED_KINDS:
        source_path = f"world/source/{name}.json"
        source_artifact_id = f"worldsource_{hashlib.sha256(name.encode()).hexdigest()[:32]}"
        data = canonical_json({"artifact_id": source_artifact_id, "kind": name, "payload": {}})
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
    domains = {
        "world/terrain/index.json": {"chunk_shape": [256, 256], "chunks": ["world/terrain/chunks/0_0.bin"]},
        "world/hydrology.json": {"rivers": [], "lakes": [], "coasts": []},
        "world/climate/index.json": {"chunk_shape": [256, 256], "chunks": ["world/climate/chunks/0_0.bin"]},
        "world/biomes/index.json": {"chunk_shape": [256, 256], "chunks": ["world/biomes/chunks/0_0.bin"]},
        "world/resources.json": {"occurrences": []},
        "world/regions.json": {"regions": [{"region_id": REGION, "cells": [[0, 0]], "adjacent": []}]},
        "world/routes.json": {"routes": []},
        "world/sites.json": {"sites": [{"site_id": SITE, "region_id": REGION, "x": 0, "y": 0}]},
        "world/civilizations.json": {"civilizations": []},
        "world/history/index.json": {"events": ["world/history/events/event_00000000000000000000000000000001.json"],
                                     "snapshots": [f"world/history/snapshots/year_{y:04d}.json" for y in range(0, 501, 10)]},
        "world/local/index.json": {"sites": [SITE]},
        f"world/local/{SITE}/index.json": {"site_id": SITE, "chunk_shape": [32, 32, 16],
                                            "chunks": [f"world/local/{SITE}/chunks/0_0_0.bin"]},
    }
    domain_ids = [builder.add(path.split("/")[-2] if path.endswith("index.json") else path.rsplit("/", 1)[-1][:-5],
                              path, canonical_json(value), depends_on=[root_id])
                  for path, value in domains.items()]
    def chunk_bytes(label: str, size: int) -> bytes:
        return b"".join(hashlib.sha256(f"{label}:{index}".encode()).digest()
                        for index in range((size + 31) // 32))[:size]
    for layer in ("terrain", "climate", "biomes"):
        builder.add(f"{layer}chunk", f"world/{layer}/chunks/0_0.bin",
                    chunk_bytes(layer, 256 * 256 * 4), depends_on=domain_ids)
    builder.add("event", "world/history/events/event_00000000000000000000000000000001.json",
                canonical_json({"event_id": "event_00000000000000000000000000000001", "year": 0,
                                "sequence": 0, "causes": [], "participants": [], "locations": [SITE]}),
                depends_on=domain_ids)
    for year in range(0, 501, 10):
        builder.add("snapshot", f"world/history/snapshots/year_{year:04d}.json",
                    canonical_json({"year": year, "ledger_position": 1, "state_hash": "0" * 64}),
                    depends_on=domain_ids)
    builder.add("localchunk", f"world/local/{SITE}/chunks/0_0_0.bin",
                b"SLM2" + chunk_bytes("local", 256), depends_on=domain_ids)
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
    score = generate_score(44, 80)
    builder.add("score", node_assets[NODE]["score"], canonical_json(asdict(score)), depends_on=domain_ids)
    builder.add("midi", node_assets[NODE]["midi"], score_to_midi(score), depends_on=domain_ids)
    builder.write(destination, node_assets=node_assets,
                  region_maps={REGION: f"assets/maps/regions/{REGION}.png"})


def main() -> None:
    generate_schemas(); FIXTURES.mkdir(parents=True, exist_ok=True)
    build_complete(FIXTURES / "complete.story")
    shutil.copyfile(FIXTURES / "complete.story", FIXTURES / "small.story")
    with zipfile.ZipFile(FIXTURES / "complete.story") as source:
        members = {name: source.read(name) for name in source.namelist()}

    def invalid(name: str, mutate: Callable[[dict[str, bytes]], None]) -> None:
        changed = dict(members)
        mutate(changed)
        with zipfile.ZipFile(FIXTURES / name, "w") as archive:
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
    scenarios = [{"id": "complete", "path": "complete.story", "accepted": True},
                 {"id": "small", "path": "small.story", "accepted": True},
                 {"id": "unsupported-v1", "path": "unsupported-v1.story", "accepted": False,
                  "issue_code": "PACKAGE_UNSUPPORTED_VERSION"},
                 {"id": "corrupt", "path": "corrupt.story", "accepted": False,
                  "issue_code": "PACKAGE_HASH_MISMATCH"},
                 {"id": "dependency-broken", "path": "dependency-broken.story", "accepted": False,
                  "issue_code": "PACKAGE_PROVENANCE_BROKEN"},
                 {"id": "incomplete-world", "path": "incomplete-world.story", "accepted": False,
                  "issue_code": "PACKAGE_MISSING_ARTIFACT"}]
    catalog = {"format": "storyteller.fixture-catalog.v2", "scenarios": scenarios}
    (FIXTURES / "catalog.json").write_bytes(canonical_json(catalog))
    print(json.dumps({"fixtures": len(scenarios), "schemas": len(list(SCHEMAS.glob('*.json')))}, sort_keys=True))


if __name__ == "__main__":
    main()
