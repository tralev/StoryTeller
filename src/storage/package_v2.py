"""Frozen `.story` v2 archive, identity, provenance, and acceptance contract.

The ZIP is transport only: identity is always derived from the hashes of its
declared members.  This module deliberately has no dependency on the v1
pipeline or its ``content/`` layout.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn

from .package_writer import V2PackageBuilder as V2PackageBuilder
from .package_writer import artifact_record as artifact_record
from .package_writer import build_grid_domain_files as build_grid_domain_files
from .package_writer import canonical_json as canonical_json
from .package_writer import confined_path as confined_path
from .package_writer import content_hash as content_hash
from .package_writer import has_extraction_space as has_extraction_space
from .package_writer import producer as producer
from .package_writer import publish_staged_package as publish_staged_package
from .package_writer import sha256 as sha256
from .validation import (
    PackageIdentityIndex,
    inspect_archive_security,
    validate_artifact_inventory,
    validate_binary_media,
    validate_canonical_json_members,
    validate_civilization_references,
    validate_climate_layers,
    validate_event_order,
    validate_feature_declaration,
    validate_flat_world_domain,
    validate_gm_coverage,
    validate_grid_domain,
    validate_history_inventory_and_snapshots,
    validate_history_replay,
    validate_hydrology_catalog,
    validate_layout,
    validate_local_maps,
    validate_manifest_header,
    validate_manifest_schema,
    validate_narrative_authority,
    validate_physical_layer_sets,
    validate_region_site_topology,
    validate_resource_geology,
    validate_route_topology,
    validate_story_graph_references,
    validate_structured_scores,
    validate_world_source_coverage,
)
from .validation import PackageV2Error as PackageV2Error
from .validation.manifest import (
    FORMAT as FORMAT,
)
from .validation.manifest import (
    HASH_RE as HASH_RE,
)
from .validation.manifest import (
    ID_RE as ID_RE,
)
from .validation.manifest import (
    REQUIRED_FEATURES as REQUIRED_FEATURES,
)
from .validation.manifest import (
    TRUSTED_SCHEMA_SHA256 as TRUSTED_SCHEMA_SHA256,
)
from .validation.manifest import (
    VERSION as VERSION,
)

GRID_DOMAINS: dict[str, str] = {
    "terrain": "terrain_grid_catalog",
    "geology": "geology_grid_catalog",
    "hydrology": "hydrology_grid_catalog",
    "climate": "climate_grid_catalog",
    "biomes": "biome_grid_catalog",
    "resource_grid": "resource_grid_catalog",
}
FLAT_WORLD_DOMAINS: dict[str, str] = {
    "hydrology": "hydrology",
    "resources": "resources",
}

MAX_SAFE_INTEGER = (1 << 53) - 1


@dataclass(frozen=True)
class V2Issue:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class V2Acceptance:
    accepted: bool
    issues: tuple[V2Issue, ...] = ()
    manifest: Mapping[str, Any] | None = None
    required_bytes: int = 0


def _json_no_duplicates(data: bytes, path: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise PackageV2Error("PACKAGE_JSON_DUPLICATE_KEY", key, path)
            result[key] = value
        return result

    def integer(value: str) -> int:
        parsed = int(value)
        if abs(parsed) > MAX_SAFE_INTEGER:
            raise PackageV2Error("PACKAGE_NUMBER_RANGE", value, path)
        return parsed

    def non_integer(value: str) -> NoReturn:
        raise PackageV2Error("PACKAGE_NUMBER_PROFILE", value, path)

    try:
        if data.startswith(b"\xef\xbb\xbf"):
            raise PackageV2Error("PACKAGE_JSON_BOM", "UTF-8 BOM is forbidden", path)
        return json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_int=integer,
            parse_float=non_integer,
            parse_constant=non_integer,
        )
    except PackageV2Error:
        raise
    except Exception as error:
        raise PackageV2Error("PACKAGE_INVALID_JSON", str(error), path) from error


def validate_v2_package(package: str | Path) -> V2Acceptance:
    """Consumer-equivalent v2 validation without extracting the archive."""
    issues: list[V2Issue] = []
    manifest: dict[str, Any] | None = None
    total = 0
    try:
        with zipfile.ZipFile(package) as archive:
            inspection = inspect_archive_security(
                archive,
                confined_path,
                _json_no_duplicates,
            )
            names = set(inspection.names)
            total = inspection.total_bytes
            parsed = _json_no_duplicates(archive.read("manifest.json"), "manifest.json")
            if not isinstance(parsed, dict):
                raise PackageV2Error("PACKAGE_MANIFEST_TYPE", "must be object")
            manifest = parsed
            validate_manifest_header(manifest)
            validate_canonical_json_members(
                archive,
                _json_no_duplicates,
                canonical_json,
            )
            validate_feature_declaration(manifest)
            validate_manifest_schema(manifest)
            validate_artifact_inventory(
                archive,
                names,
                manifest,
                confined_path,
                _json_no_duplicates,
                canonical_json,
                artifact_record,
                content_hash,
            )
            validate_layout(manifest, names)
            identities = PackageIdentityIndex.build(archive, manifest, _json_no_duplicates)
            _validate_world_contract(archive, manifest, names, identities)
            validate_structured_scores(archive, manifest, identities, _json_no_duplicates)
            validate_binary_media(archive, manifest, _json_no_duplicates)
    except PackageV2Error as error:
        issues.append(V2Issue(error.code, error.path, str(error).split(": ", 2)[-1]))
    except (OSError, zipfile.BadZipFile) as error:
        issues.append(V2Issue("PACKAGE_INVALID_ZIP", str(package), str(error)))
    return V2Acceptance(not issues, tuple(issues), manifest, total if not issues else 0)


def _validate_world_contract(
    archive: zipfile.ZipFile,
    manifest: Mapping[str, Any],
    names: set[str],
    identities: PackageIdentityIndex,
) -> None:
    """Cross-file invariants a Player relies on before publishing content."""
    graph = _json_no_duplicates(archive.read("narrative/graph.json"), "narrative/graph.json")
    validate_story_graph_references(
        archive,
        manifest,
        graph,
        identities,
        _json_no_duplicates,
    )
    regions = _json_no_duplicates(archive.read("world/regions.json"), "world/regions.json")
    region_ids = {item.get("region_id") for item in regions.get("regions", [])}
    if region_ids != set(manifest["region_maps"]):
        raise PackageV2Error("PACKAGE_REGION_MAP_COVERAGE", "every region requires exactly one map")
    sites = _json_no_duplicates(archive.read("world/sites.json"), "world/sites.json")
    site_ids = {item.get("site_id") for item in sites.get("sites", [])}
    if any(item.get("region_id") not in region_ids for item in sites.get("sites", [])):
        raise PackageV2Error("PACKAGE_SITE_REGION", "site references unknown region")
    validate_local_maps(archive, names, site_ids, _json_no_duplicates)
    validate_history_inventory_and_snapshots(
        archive,
        names,
        manifest,
        _json_no_duplicates,
        canonical_json,
    )
    validate_physical_layer_sets(archive, _json_no_duplicates)
    for domain in GRID_DOMAINS:
        validate_grid_domain(archive, names, domain, _json_no_duplicates)
    validate_climate_layers(archive, _json_no_duplicates)
    validate_region_site_topology(archive, _json_no_duplicates)
    validate_route_topology(archive, manifest, _json_no_duplicates)
    validate_hydrology_catalog(archive, _json_no_duplicates)
    validate_resource_geology(archive, manifest, _json_no_duplicates)
    validate_civilization_references(archive, _json_no_duplicates)
    validate_event_order(archive, _json_no_duplicates)
    validate_history_replay(archive, _json_no_duplicates, canonical_json)
    for domain in FLAT_WORLD_DOMAINS:
        validate_flat_world_domain(
            archive,
            names,
            domain,
            FLAT_WORLD_DOMAINS[domain],
            _json_no_duplicates,
            canonical_json,
        )
    validate_world_source_coverage(archive, names, _json_no_duplicates)
    validate_narrative_authority(archive, manifest, _json_no_duplicates)
    validate_gm_coverage(archive, manifest, graph, identities, _json_no_duplicates)


def inspect_v2_package(package: str | Path) -> dict[str, Any]:
    result = validate_v2_package(package)
    if not result.accepted:
        issue = result.issues[0]
        raise PackageV2Error(issue.code, issue.message, issue.path)
    assert result.manifest is not None
    manifest = result.manifest
    return {
        "accepted": True,
        "package_format": manifest["package_format"],
        "package_version": manifest["package_version"],
        "story_id": manifest["story_id"],
        "title": manifest["title"],
        "content_hash": manifest["content_hash"],
        "artifacts": len(manifest["artifacts"]),
        "nodes": len(manifest["node_assets"]),
        "regions": len(manifest["region_maps"]),
    }
