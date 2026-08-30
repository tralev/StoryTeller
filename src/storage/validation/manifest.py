"""Frozen manifest, provenance DAG, producer, and layout validation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..v2_schemas import draft202012_validator
from .common import PackageV2Error

FORMAT = "storyteller.story"
VERSION = 2
ID_RE = re.compile(r"^[a-z][a-z0-9]*_[0-9a-f]{32}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
FEATURE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REQUIRED_FEATURES = (
    "all_site_local_maps",
    "complete_history",
    "complete_world",
    "embedded_schemas",
    "fixed_media_profile",
    "structured_score_midi",
)
KNOWN_OPTIONAL_FEATURES: frozenset[str] = frozenset()
TRUSTED_SCHEMA_SHA256 = "420369871f9d7852dd854c7dbfc6e695c108a8ebb2a4484138e8552838f72d76"


def validate_manifest_header(manifest: Mapping[str, Any]) -> None:
    if type(manifest.get("package_version")) is not int:
        raise PackageV2Error("PACKAGE_TYPE_COERCION", "manifest format/version types are exact")
    if manifest.get("package_version") != VERSION:
        raise PackageV2Error(
            "PACKAGE_UNSUPPORTED_VERSION",
            "Schema validation failed: only .story v2 is supported; regenerate with current Forge",
        )
    if not isinstance(manifest.get("package_format"), str):
        raise PackageV2Error("PACKAGE_TYPE_COERCION", "manifest format type is exact")
    if manifest.get("package_format") != FORMAT:
        raise PackageV2Error("PACKAGE_UNSUPPORTED_VERSION", "regenerate with current Forge")


def validate_feature_declaration(manifest: Mapping[str, Any]) -> None:
    required = manifest.get("required_features")
    optional = manifest.get("optional_features")
    if (
        not isinstance(required, list)
        or not isinstance(optional, list)
        or any(
            not isinstance(item, str) or not FEATURE_RE.fullmatch(item)
            for item in required + optional
        )
    ):
        raise PackageV2Error("PACKAGE_REQUIRED_FEATURE", "invalid feature declaration")
    if required != sorted(set(required)) or optional != sorted(set(optional)):
        raise PackageV2Error("PACKAGE_FEATURE_ORDER", "features must be sorted and unique")
    if tuple(required) != REQUIRED_FEATURES:
        raise PackageV2Error("PACKAGE_REQUIRED_FEATURE", "required feature set is not frozen v2")
    if set(optional) - KNOWN_OPTIONAL_FEATURES or optional:
        raise PackageV2Error("PACKAGE_OPTIONAL_FEATURE", "unsupported optional feature")


def validate_manifest_schema(manifest: Mapping[str, Any]) -> None:
    try:
        schema_path = Path(__file__).resolve().parents[3] / "schemas/v2/manifest.schema.json"
        schema = json.loads(schema_path.read_bytes())
        errors = sorted(
            draft202012_validator(schema).iter_errors(manifest),
            key=lambda error: list(error.path),
        )
        if errors:
            raise PackageV2Error("PACKAGE_SCHEMA", errors[0].message, "manifest.json")
    except FileNotFoundError as error:
        raise PackageV2Error("PACKAGE_SCHEMA_BUNDLE", "local frozen schema missing") from error


def validate_artifact_dag(records: Mapping[str, Mapping[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(item: str) -> None:
        if item in visiting:
            raise PackageV2Error("PACKAGE_PROVENANCE_CYCLE", "dependency cycle")
        if item in visited:
            return
        visiting.add(item)
        for dependency in records[item].get("depends_on", []):
            if dependency not in records:
                raise PackageV2Error(
                    "PACKAGE_PROVENANCE_BROKEN",
                    "unknown dependency",
                    str(records[item]["path"]),
                )
            visit(dependency)
        visiting.remove(item)
        visited.add(item)

    for item in records:
        visit(item)


def validate_producer(value: Any, path: str) -> None:
    required = {
        "component",
        "algorithm_version",
        "model",
        "prompt_sha256",
        "schema_sha256",
        "code_revision",
        "fingerprint",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise PackageV2Error("PACKAGE_PRODUCER", "producer fields are incomplete", path)
    if (
        not isinstance(value["component"], str)
        or not value["component"]
        or not isinstance(value["algorithm_version"], int)
        or value["algorithm_version"] < 1
        or not HASH_RE.fullmatch(value["schema_sha256"])
        or not HASH_RE.fullmatch(value["fingerprint"])
    ):
        raise PackageV2Error("PACKAGE_PRODUCER", "producer identity is invalid", path)
    if value["schema_sha256"] != TRUSTED_SCHEMA_SHA256:
        raise PackageV2Error("PACKAGE_SCHEMA_IDENTITY", "untrusted v2 schema bundle", path)
    for key in ("model", "prompt_sha256"):
        if value[key] is not None and (
            not isinstance(value[key], str)
            or (key.endswith("sha256") and not HASH_RE.fullmatch(value[key]))
        ):
            raise PackageV2Error("PACKAGE_PRODUCER", f"invalid {key}", path)


def validate_layout(manifest: Mapping[str, Any], names: set[str]) -> None:
    required = {
        "world/index.json",
        "narrative/bible.json",
        "narrative/reconciliation.json",
        "narrative/style_bible.json",
        "narrative/story.json",
        "narrative/graph.json",
        "narrative/gm_index.json",
        "assets/maps/world.png",
    }
    missing = required - names
    if missing:
        raise PackageV2Error(
            "PACKAGE_LAYOUT_MISSING", "required v2 member missing", sorted(missing)[0]
        )
    if any(
        name == "save" or name.startswith("save/") or name.startswith("content/") for name in names
    ):
        raise PackageV2Error(
            "PACKAGE_FORBIDDEN_ENTRY", "v1/save layout is forbidden (layout re-check)"
        )
    graph_nodes = set(manifest.get("node_assets", {}))
    entry = manifest.get("entry_node")
    if entry not in graph_nodes:
        raise PackageV2Error("PACKAGE_ENTRY_NODE", "entry node has no asset set")
    for node, asset_set in manifest.get("node_assets", {}).items():
        expected = {
            "image": f"assets/images/{node}.png",
            "thumbnail": f"assets/thumbnails/{node}.png",
            "score": f"assets/music/{node}.score.json",
            "midi": f"assets/midi/{node}.mid",
        }
        if asset_set != expected or not set(expected.values()) <= names:
            raise PackageV2Error("PACKAGE_MEDIA_COVERAGE", "node media must be exact", node)
    region_maps = manifest.get("region_maps")
    if not isinstance(region_maps, dict) or any(path not in names for path in region_maps.values()):
        raise PackageV2Error("PACKAGE_REGION_MAP_COVERAGE", "region map inventory is incomplete")
