"""Publish an accepted v2 package from authoritative world/narrative directories."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from ..narrative.media import deterministic_image
from ..worldgen.artifacts import canonical_json
from .package_v2 import V2PackageBuilder, validate_v2_package

_MAX_SAFE_INTEGER = (1 << 53) - 1


def _load(path: Path) -> Any:
    return json.loads(path.read_bytes())


def _interoperable(value: Any) -> Any:
    """Map unsigned 64-bit decision seeds into the frozen signed JSON range."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and abs(value) > _MAX_SAFE_INTEGER:
        width = 2 * _MAX_SAFE_INTEGER + 1
        return ((value + _MAX_SAFE_INTEGER) % width) - _MAX_SAFE_INTEGER
    if isinstance(value, list):
        return [_interoperable(item) for item in value]
    if isinstance(value, dict):
        return {key: _interoperable(item) for key, item in value.items()}
    return value


def package_project_v2(world: str | Path, bible_root: str | Path,
                       project: str | Path, destination: str | Path,
                       *, title: str, seed: int, staged: bool = False,
                       local_root: str | Path | None = None) -> Path:
    """Convert complete immutable stage outputs into the frozen v2 layout.

    All authoritative envelopes are retained under ``world/source/`` even when
    the reader-facing projection uses a more compact index.
    """
    world_root, bible_dir, project_root = Path(world), Path(bible_root), Path(project)
    local_project = project_root if local_root is None else Path(local_root)
    graph = _load(project_root / "graph.json")
    entry = str(graph["starting_node"])
    simulation = _load(world_root / "artifacts" / "simulation_index.json")["payload"]
    physical = _load(world_root / "artifacts" / "world_index.json")["payload"]
    builder = V2PackageBuilder(title, seed, entry,
                               present_year=int(simulation["present_year"]),
                               metres_per_world_cell=int(physical["spec"]["metres_per_world_cell"]))
    schema_ids = [builder.add("schema", f"schemas/{path.name}", path.read_bytes())
                  for path in sorted((Path(__file__).resolve().parents[2] / "schemas" / "v2").glob("*.json"))]
    source_ids: list[str] = []
    source_coverage: list[dict[str, Any]] = []
    for path in sorted((world_root / "artifacts").glob("*.json")):
        data = path.read_bytes(); archive_path = f"world/source/{path.name}"
        source_ids.append(builder.add("worldsource", archive_path, data, depends_on=schema_ids))
        envelope = json.loads(data)
        source_coverage.append({
            "source_name": path.stem, "archive_path": archive_path,
            "artifact_id": envelope.get("artifact_id"),
            "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data),
            "retention": "byte_for_byte",
        })
    from ..world.views import REQUIRED_KINDS
    builder.add("worldcoverage", "world/source/coverage.json", canonical_json({
        "format": "storyteller.world-source-coverage.v1",
        "required_domains": sorted(REQUIRED_KINDS),
        "sources": source_coverage,
    }), depends_on=source_ids)

    regions = _load(world_root / "artifacts" / "regions.json")["payload"]
    sites = _load(world_root / "artifacts" / "sites.json")["payload"]
    civilizations = _load(world_root / "artifacts" / "civilizations.json")["payload"]
    history = _load(world_root / "artifacts" / "history.json")["payload"]
    snapshots = _load(world_root / "artifacts" / "snapshots.json")["payload"]
    region_rows = regions.get("regions", regions) if isinstance(regions, dict) else regions
    site_rows = sites.get("sites", sites) if isinstance(sites, dict) else sites
    root_id = builder.add("world", "world/index.json", canonical_json({
        "width": physical["spec"]["width"], "height": physical["spec"]["height"],
        "present_year": simulation["present_year"],
        "snapshot_years": simulation["snapshot_years"],
        "domains": sorted(path.stem for path in (world_root / "artifacts").glob("*.json")),
        "source_artifact_ids": source_ids,
    }), depends_on=source_ids)
    domain_ids = [root_id]
    projections = {
        "world/regions.json": {"regions": region_rows},
        "world/routes.json": _load(world_root / "artifacts" / "routes.json")["payload"],
        "world/sites.json": {"sites": site_rows},
        "world/civilizations.json": {"civilizations": civilizations},
    }
    for archive_path, value in projections.items():
        domain_ids.append(builder.add(archive_path.split("/")[-1][:-5], archive_path, canonical_json(value), depends_on=[root_id]))
    event_paths: list[str] = []
    for event in history:
        epath = f"world/history/events/{event['event_id']}.json"; event_paths.append(epath)
        builder.add("event", epath, canonical_json(event), depends_on=[root_id])
    snapshot_paths: list[str] = []
    for snapshot in snapshots:
        spath = f"world/history/snapshots/year_{int(snapshot['year']):04d}.json"; snapshot_paths.append(spath)
        builder.add("snapshot", spath, canonical_json(snapshot), depends_on=[root_id])
    builder.add("history", "world/history/index.json",
                canonical_json({"events": event_paths, "snapshots": snapshot_paths}), depends_on=[root_id])
    site_ids = [str(item["site_id"]) for item in site_rows]
    local_index = _load(local_project / "local_index.json")
    local_member_ids: list[str] = []
    local_entries = {str(item["site_id"]): item for item in local_index["entries"]}
    for site_id in site_ids:
        source = local_project / "local_maps" / f"{site_id}.json"
        site_anchor_id = builder.add(
            "localsite", f"world/local/{site_id}/site.json",
            canonical_json({"site_id": site_id}), depends_on=[root_id],
        )
        chunk_ids: list[str] = []
        entry = local_entries[site_id]
        for family, key in (
            ("material", "material_chunk_hashes"),
            ("occupancy", "occupancy_chunk_hashes"),
            ("construction", "construction_chunk_hashes"),
        ):
            for sha256 in entry[key]:
                chunk_source = (
                    local_project / "local_chunks" / site_id / family / f"{sha256}.json"
                )
                chunk_ids.append(builder.add(
                    "localchunk",
                    f"world/local/{site_id}/chunks/{family}/{sha256}.json",
                    chunk_source.read_bytes(), depends_on=[root_id, site_anchor_id],
                ))
        local_member_ids.append(builder.add(
            "localmap", f"world/local/{site_id}/index.json", source.read_bytes(),
            depends_on=[root_id, site_anchor_id, *chunk_ids],
        ))
        local_member_ids.extend((site_anchor_id, *chunk_ids))
    builder.add(
        "local", "world/local/index.json", canonical_json(local_index),
        depends_on=[root_id, *local_member_ids],
    )

    for source_name, archive_name, kind in (
        ("bible.json", "narrative/bible.json", "bible"),
        ("reconciliation.json", "narrative/reconciliation.json", "reconciliation"),
        ("style_bible.json", "narrative/style_bible.json", "style"),
        ("story.json", "narrative/story.json", "story"),
        ("graph.json", "narrative/graph.json", "graph"),
        ("gm_index.json", "narrative/gm_index.json", "gmindex"),
    ):
        source = (bible_dir if source_name in {"bible.json", "reconciliation.json", "style_bible.json"}
                  else project_root) / source_name
        if source_name == "style_bible.json" and not source.is_file():
            from ..world.art_direction import derive_art_direction
            from ..world.models import BibleV2
            from ..world.views import WorldView
            data = canonical_json(derive_art_direction(
                WorldView(world_root), BibleV2.from_dict(_load(bible_dir / "bible.json")),
            ))
        else:
            data = source.read_bytes()
        if source_name in {"story.json", "graph.json", "gm_index.json"}:
            data = canonical_json(_interoperable(json.loads(data)))
        if source_name == "gm_index.json":
            data = canonical_json({"entries": json.loads(data)})
        builder.add(kind, archive_name, data, depends_on=domain_ids)

    node_assets: dict[str, dict[str, str]] = {}
    media = _load(project_root / "media.json")
    for node_id, record in sorted(media.items()):
        paths = {"image": f"assets/images/{node_id}.png",
                 "thumbnail": f"assets/thumbnails/{node_id}.png",
                 "score": f"assets/music/{node_id}.score.json",
                 "midi": f"assets/midi/{node_id}.mid"}
        node_assets[node_id] = paths
        for key, target in paths.items():
            builder.add(key, target, (project_root / record[key]["path"]).read_bytes(), depends_on=domain_ids)
    builder.add("worldmap", "assets/maps/world.png", deterministic_image(seed, 4096, 4096), depends_on=domain_ids)
    region_maps: dict[str, str] = {}
    for index, region in enumerate(region_rows):
        region_id = str(region["region_id"]); target = f"assets/maps/regions/{region_id}.png"
        builder.add("regionmap", target, deterministic_image(seed + index + 1, 1024, 1024), depends_on=domain_ids)
        region_maps[region_id] = target
    if staged:
        result = builder.write_staged(destination, node_assets=node_assets, region_maps=region_maps)
    else:
        result = builder.write(destination, node_assets=node_assets, region_maps=region_maps)
        if not validate_v2_package(result).accepted:
            raise ValueError("published v2 package failed consumer-equivalent acceptance")
    return result
