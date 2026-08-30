"""All-site local-map index and chunk-family validation."""

from __future__ import annotations

import hashlib
import zipfile

from ...worldgen.local_chunks import local_voxel_chunk_from_mapping
from ...worldgen.local_construction import construction_chunk_from_mapping
from ...worldgen.local_occupancy import local_occupancy_chunk_from_mapping
from .common import JsonLoader, PackageV2Error


def validate_local_maps(
    archive: zipfile.ZipFile,
    names: set[str],
    site_ids: set[str],
    load_json: JsonLoader,
) -> None:
    index_path = "world/local/index.json"
    local = load_json(archive.read(index_path), index_path)
    if (
        local.get("format") != "storyteller.local-world-index.v1"
        or local.get("selection_policy") != "all_registered_sites"
        or local.get("sites") != sorted(site_ids)
        or not isinstance(local.get("entries"), list)
    ):
        raise PackageV2Error("PACKAGE_LOCAL_MAP_COVERAGE", "every site requires a local map")
    entries = local["entries"]
    if [entry.get("site_id") for entry in entries if isinstance(entry, dict)] != sorted(site_ids):
        raise PackageV2Error("PACKAGE_LOCAL_MAP_COVERAGE", "local entries are incomplete")

    expected_entry_fields = {
        "site_id",
        "archive_path",
        "local_map_sha256",
        "boundary_id",
        "summary_id",
        "material_chunk_hashes",
        "occupancy_chunk_hashes",
        "construction_chunk_hashes",
    }
    parsers = {
        "material": local_voxel_chunk_from_mapping,
        "occupancy": local_occupancy_chunk_from_mapping,
        "construction": construction_chunk_from_mapping,
    }
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != expected_entry_fields:
            raise PackageV2Error("PACKAGE_LOCAL_INDEX", "invalid local entry shape")
        site = entry["site_id"]
        path = f"world/local/{site}/index.json"
        if entry["archive_path"] != path or path not in names:
            raise PackageV2Error("PACKAGE_LOCAL_MAP_COVERAGE", "site local map missing", str(site))
        data = archive.read(path)
        if hashlib.sha256(data).hexdigest() != entry["local_map_sha256"]:
            raise PackageV2Error("PACKAGE_LOCAL_INDEX", "local map hash mismatch", path)
        local_map = load_json(data, path)
        if (
            local_map.get("site_id") != site
            or local_map.get("boundary", {}).get("boundary_id") != entry["boundary_id"]
            or local_map.get("macro_summary", {}).get("summary_id") != entry["summary_id"]
            or [item.get("sha256") for item in local_map.get("chunks", [])]
            != entry["material_chunk_hashes"]
            or [item.get("sha256") for item in local_map.get("occupancy_chunks", [])]
            != entry["occupancy_chunk_hashes"]
            or [item.get("sha256") for item in local_map.get("construction_chunks", [])]
            != entry["construction_chunk_hashes"]
        ):
            raise PackageV2Error("PACKAGE_LOCAL_INDEX", "local chunk inventory mismatch", path)

        for family, key in (
            ("material", "material_chunk_hashes"),
            ("occupancy", "occupancy_chunk_hashes"),
            ("construction", "construction_chunk_hashes"),
        ):
            for chunk_hash in entry[key]:
                chunk_path = f"world/local/{site}/chunks/{family}/{chunk_hash}.json"
                if chunk_path not in names:
                    raise PackageV2Error(
                        "PACKAGE_LOCAL_CHUNK_COVERAGE",
                        "indexed local chunk missing",
                        chunk_path,
                    )
                chunk = load_json(archive.read(chunk_path), chunk_path)
                if chunk.get("sha256") != chunk_hash:
                    raise PackageV2Error(
                        "PACKAGE_LOCAL_CHUNK_HASH",
                        "local chunk identity mismatch",
                        chunk_path,
                    )
                try:
                    parsers[family](chunk)
                except (KeyError, TypeError, ValueError) as error:
                    raise PackageV2Error(
                        "PACKAGE_LOCAL_CHUNK_HASH",
                        "invalid local chunk payload",
                        chunk_path,
                    ) from error
