"""Frozen `.story` v2 archive, identity, provenance, and acceptance contract.

The ZIP is transport only: identity is always derived from the hashes of its
declared members.  This module deliberately has no dependency on the v1
pipeline or its ``content/`` layout.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Iterable, Mapping

from ..worldgen.grid import DenseGridCatalog
from .fs import atomic_write_bytes

GRID_DOMAINS: dict[str, str] = {
    "terrain": "terrain_grid_catalog",
    "climate": "climate_grid_catalog",
    "biomes": "biome_grid_catalog",
}
FLAT_WORLD_DOMAINS: dict[str, str] = {
    "hydrology": "hydrology",
    "resources": "resources",
}

FORMAT = "storyteller.story"
VERSION = 2
ID_RE = re.compile(r"^[a-z][a-z0-9]*_[0-9a-f]{32}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
FEATURE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
REQUIRED_FEATURES = (
    "all_site_local_maps", "complete_history", "complete_world",
    "embedded_schemas", "fixed_media_profile", "structured_score_midi",
)
KNOWN_OPTIONAL_FEATURES: frozenset[str] = frozenset()
MAX_ENTRIES = 100_000
MAX_MEMBER_BYTES = 4 * 1024 * 1024 * 1024
MAX_TOTAL_DECLARED_BYTES = 1 << 45
MAX_COMPRESSION_RATIO = 1_000
MAX_JSON_DEPTH = 128
MAX_SAFE_INTEGER = (1 << 53) - 1


class PackageV2Error(ValueError):
    """A stable-code package failure."""

    def __init__(self, code: str, message: str, path: str = "manifest.json") -> None:
        self.code, self.path = code, path
        super().__init__(f"{code}: {path}: {message}")


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


def canonical_json(value: object) -> bytes:
    """Canonical UTF-8 JSON for the frozen integer-domain JCS profile."""
    def check(item: object, depth: int = 0) -> None:
        if depth > MAX_JSON_DEPTH:
            raise PackageV2Error("PACKAGE_JSON_DEPTH", "JSON nesting exceeds limit")
        if isinstance(item, bool) or item is None or isinstance(item, str):
            return
        if isinstance(item, int):
            if abs(item) > MAX_SAFE_INTEGER:
                raise PackageV2Error("PACKAGE_NUMBER_RANGE", "integer exceeds interoperable range")
            return
        if isinstance(item, float):
            raise PackageV2Error("PACKAGE_NUMBER_PROFILE", "authoritative JSON uses integers")
        if isinstance(item, list) or isinstance(item, tuple):
            for child in item: check(child, depth + 1)
            return
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise PackageV2Error("PACKAGE_JSON_KEY", "object keys must be strings")
            for child in item.values(): check(child, depth + 1)
            return
        raise PackageV2Error("PACKAGE_JSON_TYPE", f"unsupported value {type(item).__name__}")
    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_grid_domain_files(
    domain: str, catalog: DenseGridCatalog, chunk_bytes: Callable[[str, int, int], bytes],
) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    """Build a frozen ``world/<domain>/index.json`` payload plus its chunk members.

    ``catalog`` layers are already canonically sorted and gap-free (enforced by
    ``DenseGridManifest``/``DenseGridCatalog``). Each layer keeps its own chunk
    grid because real catalogs are not one-layer-per-domain (e.g. terrain has
    six layers, climate has one per season plus three annual aggregates).
    """
    layers: dict[str, Any] = {}
    members: list[tuple[str, bytes]] = []
    for manifest in catalog.manifests:
        chunks: list[dict[str, Any]] = []
        for descriptor in manifest.chunks:
            data = chunk_bytes(manifest.layer, descriptor.chunk_x, descriptor.chunk_y)
            if sha256(data) != descriptor.sha256:
                raise PackageV2Error(
                    "PACKAGE_GRID_CHUNK_HASH", f"{domain}/{manifest.layer} chunk hash mismatch",
                )
            path = f"world/{domain}/chunks/{manifest.layer}/{descriptor.sha256}.bin"
            members.append((path, data))
            chunks.append({
                "chunk_x": descriptor.chunk_x, "chunk_y": descriptor.chunk_y,
                "width": descriptor.width, "height": descriptor.height,
                "sha256": descriptor.sha256,
            })
        layers[manifest.layer] = {
            "chunk_width": manifest.chunk_width, "chunk_height": manifest.chunk_height,
            "chunks": chunks,
        }
    index = {
        "format": "storyteller.grid-domain-index.v1",
        "width": catalog.grid.width, "height": catalog.grid.height,
        "layers": layers,
    }
    return index, members


def confined_path(path: str) -> str:
    pure = PurePosixPath(path)
    if (not path or "\\" in path or pure.is_absolute() or
            any(part in ("", ".", "..") for part in pure.parts)):
        raise PackageV2Error("PACKAGE_UNSAFE_PATH", "path is not normalized", path)
    return pure.as_posix()


def producer(component: str, version: str = "2") -> dict[str, Any]:
    fingerprint = sha256(canonical_json({"component": component, "version": version}))
    return {"component": component, "algorithm_version": 2, "model": None,
            "prompt_sha256": None, "schema_sha256": sha256(b"storyteller.schemas.v2"),
            "code_revision": "working-tree", "fingerprint": fingerprint}


def artifact_record(kind: str, path: str, data: bytes, *,
                    depends_on: Iterable[str] = (), producer_data: Mapping[str, Any] | None = None
                    ) -> dict[str, Any]:
    path = confined_path(path)
    deps = sorted(set(depends_on))
    prod = dict(producer_data or producer(kind))
    fingerprint = prod.get("fingerprint")
    if not isinstance(fingerprint, str) or not HASH_RE.fullmatch(fingerprint):
        raise PackageV2Error("PACKAGE_PRODUCER", "invalid producer fingerprint", path)
    content_digest = sha256(data)
    derivation = sha256(canonical_json({"depends_on": deps, "kind": kind,
                                        "producer_fingerprint": fingerprint,
                                        "sha256": content_digest}))
    prefix = re.sub(r"[^a-z0-9]", "", kind.lower())
    if not prefix or not prefix[0].isalpha():
        raise PackageV2Error("PACKAGE_KIND", "kind cannot form an ID prefix", path)
    return {"artifact_id": f"{prefix}_{derivation[:32]}", "kind": kind, "path": path,
            "sha256": content_digest, "size_bytes": len(data), "depends_on": deps,
            "producer": prod}


def content_hash(records: Iterable[Mapping[str, Any]]) -> str:
    reduced = [{"artifact_id": r["artifact_id"], "kind": r["kind"], "path": r["path"],
                "sha256": r["sha256"], "size_bytes": r["size_bytes"],
                "depends_on": sorted(r["depends_on"]),
                "producer_fingerprint": r["producer"]["fingerprint"]}
               for r in sorted(records, key=lambda item: str(item["path"]).encode("utf-8"))]
    return sha256(canonical_json(reduced))


@dataclass
class V2PackageBuilder:
    """In-memory deterministic builder; publishes only an accepted archive."""
    title: str
    master_seed: int
    entry_node: str
    present_year: int = 500
    metres_per_world_cell: int = 8000
    members: dict[str, bytes] = field(default_factory=dict)
    records: list[dict[str, Any]] = field(default_factory=list)

    def add(self, kind: str, path: str, data: bytes, *, depends_on: Iterable[str] = (),
            producer_data: Mapping[str, Any] | None = None) -> str:
        path = confined_path(path)
        if path == "manifest.json" or path in self.members:
            raise PackageV2Error("PACKAGE_DUPLICATE_PATH", "duplicate/reserved path", path)
        record = artifact_record(kind, path, data, depends_on=depends_on,
                                 producer_data=producer_data)
        self.members[path] = data
        self.records.append(record)
        return str(record["artifact_id"])

    def manifest(self, *, node_assets: Mapping[str, Any],
                 region_maps: Mapping[str, str]) -> dict[str, Any]:
        digest = content_hash(self.records)
        return {"package_format": FORMAT, "package_version": VERSION,
                "story_id": f"story_{digest[:32]}", "title": self.title,
                "content_profile": "mature_dark_fantasy", "master_seed": self.master_seed,
                "required_features": list(REQUIRED_FEATURES), "optional_features": [],
                "entry_node": self.entry_node,
                "world": {"index": "world/index.json", "present_year": self.present_year,
                          "coordinate_system": "world_cell_xy",
                          "metres_per_world_cell": self.metres_per_world_cell},
                "artifacts": sorted(self.records, key=lambda r: str(r["path"]).encode("utf-8")),
                "node_assets": dict(sorted(node_assets.items())),
                "region_maps": dict(sorted(region_maps.items())), "content_hash": digest}

    def write(self, destination: str | Path, *, node_assets: Mapping[str, Any],
              region_maps: Mapping[str, str]) -> Path:
        """Compatibility API: stage, accept, then atomically publish."""
        destination = Path(destination)
        staged = destination.with_name(destination.name + ".staging")
        try:
            self.write_staged(staged, node_assets=node_assets, region_maps=region_maps)
            result = validate_v2_package(staged)
            if not result.accepted:
                issue = result.issues[0]
                raise PackageV2Error(issue.code, issue.message, issue.path)
            return publish_staged_package(staged, destination)
        finally:
            staged.unlink(missing_ok=True)

    def write_staged(self, destination: str | Path, *, node_assets: Mapping[str, Any],
                     region_maps: Mapping[str, str]) -> Path:
        """Construct an unpublished archive without performing acceptance."""
        destination = Path(destination)
        manifest = self.manifest(node_assets=node_assets, region_maps=region_maps)
        members = dict(self.members); members["manifest.json"] = canonical_json(manifest)
        tmp = destination.with_name(destination.name + ".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(tmp, "w", allowZip64=True) as archive:
                for path in sorted(members, key=lambda item: item.encode("utf-8")):
                    info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
                    info.create_system = 3; info.external_attr = (stat.S_IFREG | 0o644) << 16
                    info.compress_type = zipfile.ZIP_STORED if path.endswith(".png") else zipfile.ZIP_DEFLATED
                    archive.writestr(info, members[path])
            os.replace(tmp, destination)
            _fsync_directory(destination.parent)
        finally:
            tmp.unlink(missing_ok=True)
        return destination


def publish_staged_package(staged: str | Path, destination: str | Path) -> Path:
    """Atomically publish a previously accepted same-filesystem archive."""
    staged_path, destination_path = Path(staged), Path(destination)
    if not staged_path.is_file():
        raise PackageV2Error("PACKAGE_STAGING_MISSING", "staged package is missing", str(staged_path))
    if staged_path.parent.resolve() != destination_path.parent.resolve():
        raise PackageV2Error("PACKAGE_STAGING_FILESYSTEM",
                             "staged package must share the destination directory",
                             str(staged_path))
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged_path, destination_path)
    _fsync_directory(destination_path.parent)
    return destination_path


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
    except OSError:
        pass


def _json_no_duplicates(data: bytes, path: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise PackageV2Error("PACKAGE_JSON_DUPLICATE_KEY", key, path)
            result[key] = value
        return result
    try:
        if data.startswith(b"\xef\xbb\xbf"):
            raise PackageV2Error("PACKAGE_JSON_BOM", "UTF-8 BOM is forbidden", path)
        return json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except PackageV2Error:
        raise
    except Exception as error:
        raise PackageV2Error("PACKAGE_INVALID_JSON", str(error), path) from error


def validate_v2_package(package: str | Path) -> V2Acceptance:
    """Consumer-equivalent v2 validation without extracting the archive."""
    issues: list[V2Issue] = []
    manifest: dict[str, Any] | None = None
    try:
        with zipfile.ZipFile(package) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_ENTRIES:
                raise PackageV2Error("PACKAGE_ENTRY_LIMIT", "too many entries")
            names: set[str] = set(); total = 0
            for info in infos:
                name = confined_path(info.filename)
                if name in names: raise PackageV2Error("PACKAGE_DUPLICATE_PATH", "duplicate entry", name)
                names.add(name); total += info.file_size
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode): raise PackageV2Error("PACKAGE_LINK", "links are forbidden", name)
                if info.file_size > MAX_MEMBER_BYTES or total > MAX_TOTAL_DECLARED_BYTES:
                    raise PackageV2Error("PACKAGE_SIZE_LIMIT", "declared size exceeds security limit", name)
                if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                    raise PackageV2Error("PACKAGE_COMPRESSION_LIMIT", "compression amplification", name)
            if any(name == "save" or name.startswith("save/") or name.startswith("content/") for name in names):
                raise PackageV2Error("PACKAGE_FORBIDDEN_ENTRY", "v1/save layout is forbidden")
            if "manifest.json" not in names:
                raise PackageV2Error("PACKAGE_MISSING_MANIFEST", "manifest is required")
            parsed = _json_no_duplicates(archive.read("manifest.json"), "manifest.json")
            if not isinstance(parsed, dict): raise PackageV2Error("PACKAGE_MANIFEST_TYPE", "must be object")
            manifest = parsed
            if manifest.get("package_format") != FORMAT or manifest.get("package_version") != VERSION:
                raise PackageV2Error("PACKAGE_UNSUPPORTED_VERSION",
                                     "Schema validation failed: only .story v2 is supported; "
                                     "regenerate with current Forge")
            _validate_manifest_schema(manifest)
            required = manifest.get("required_features")
            optional = manifest.get("optional_features")
            if required != sorted(set(required or [])) or tuple(required) != REQUIRED_FEATURES:
                raise PackageV2Error("PACKAGE_REQUIRED_FEATURE", "required feature set is not frozen v2")
            if optional != sorted(set(optional or [])) or any(not FEATURE_RE.fullmatch(x) for x in optional or []):
                raise PackageV2Error("PACKAGE_OPTIONAL_FEATURE", "optional features must be sorted and unique")
            unknown_required = set(required) - set(REQUIRED_FEATURES)
            if unknown_required: raise PackageV2Error("PACKAGE_REQUIRED_FEATURE", "unknown required feature")
            records = manifest.get("artifacts")
            if not isinstance(records, list): raise PackageV2Error("PACKAGE_INVENTORY", "artifacts must be array")
            by_id: dict[str, dict[str, Any]] = {}; declared: set[str] = {"manifest.json"}
            for record in records:
                if not isinstance(record, dict): raise PackageV2Error("PACKAGE_INVENTORY", "invalid record")
                path = confined_path(record.get("path", "")); artifact_id = record.get("artifact_id", "")
                if not ID_RE.fullmatch(artifact_id) or not HASH_RE.fullmatch(record.get("sha256", "")):
                    raise PackageV2Error("PACKAGE_IDENTITY", "invalid artifact ID or SHA-256", path)
                if path in declared or artifact_id in by_id:
                    raise PackageV2Error("PACKAGE_DUPLICATE_ID", "duplicate path or ID", path)
                if path not in names: raise PackageV2Error("PACKAGE_MISSING_ARTIFACT", "declared file missing", path)
                data = archive.read(path)
                if len(data) != record.get("size_bytes") or sha256(data) != record["sha256"]:
                    raise PackageV2Error("PACKAGE_HASH_MISMATCH", "artifact bytes do not match", path)
                expected = artifact_record(record["kind"], path, data,
                                           depends_on=record.get("depends_on", ()),
                                           producer_data=record.get("producer"))
                _validate_producer(record.get("producer"), path)
                if expected["artifact_id"] != artifact_id:
                    raise PackageV2Error("PACKAGE_ARTIFACT_ID", "artifact ID derivation mismatch", path)
                if path.endswith(".json") or path.endswith(".schema.json"):
                    value = _json_no_duplicates(data, path)
                    if canonical_json(value) != data:
                        raise PackageV2Error("PACKAGE_JSON_NONCANONICAL", "JSON is not canonical JCS", path)
                declared.add(path); by_id[artifact_id] = record
            if names != declared:
                raise PackageV2Error("PACKAGE_UNDECLARED_ENTRY", "archive has undeclared entries",
                                     sorted(names - declared)[0])
            _validate_dag(by_id)
            actual_hash = content_hash(records)
            if manifest.get("content_hash") != actual_hash or manifest.get("story_id") != f"story_{actual_hash[:32]}":
                raise PackageV2Error("PACKAGE_CONTENT_ID", "content/story identity mismatch")
            _validate_layout(manifest, names)
            _validate_binary_media(archive, manifest)
            _validate_world_contract(archive, manifest, names)
    except PackageV2Error as error:
        issues.append(V2Issue(error.code, error.path, str(error).split(": ", 2)[-1]))
    except (OSError, zipfile.BadZipFile) as error:
        issues.append(V2Issue("PACKAGE_INVALID_ZIP", str(package), str(error)))
    return V2Acceptance(not issues, tuple(issues), manifest)


def _validate_dag(records: Mapping[str, Mapping[str, Any]]) -> None:
    visiting: set[str] = set(); visited: set[str] = set()
    def visit(item: str) -> None:
        if item in visiting: raise PackageV2Error("PACKAGE_PROVENANCE_CYCLE", "dependency cycle")
        if item in visited: return
        visiting.add(item)
        for dependency in records[item].get("depends_on", []):
            if dependency not in records:
                raise PackageV2Error("PACKAGE_PROVENANCE_BROKEN", "unknown dependency",
                                     str(records[item]["path"]))
            visit(dependency)
        visiting.remove(item); visited.add(item)
    for item in records: visit(item)


def _validate_producer(value: Any, path: str) -> None:
    required = {"component", "algorithm_version", "model", "prompt_sha256",
                "schema_sha256", "code_revision", "fingerprint"}
    if not isinstance(value, dict) or set(value) != required:
        raise PackageV2Error("PACKAGE_PRODUCER", "producer fields are incomplete", path)
    if (not isinstance(value["component"], str) or not value["component"] or
            not isinstance(value["algorithm_version"], int) or value["algorithm_version"] < 1 or
            not HASH_RE.fullmatch(value["schema_sha256"]) or
            not HASH_RE.fullmatch(value["fingerprint"])):
        raise PackageV2Error("PACKAGE_PRODUCER", "producer identity is invalid", path)
    for key in ("model", "prompt_sha256"):
        if value[key] is not None and (not isinstance(value[key], str) or
                                       (key.endswith("sha256") and not HASH_RE.fullmatch(value[key]))):
            raise PackageV2Error("PACKAGE_PRODUCER", f"invalid {key}", path)


def _validate_manifest_schema(manifest: Mapping[str, Any]) -> None:
    try:
        from jsonschema import Draft202012Validator
        schema_path = Path(__file__).resolve().parents[2] / "schemas/v2/manifest.schema.json"
        schema = json.loads(schema_path.read_bytes())
        errors = sorted(Draft202012Validator(schema).iter_errors(manifest), key=lambda error: list(error.path))
        if errors:
            raise PackageV2Error("PACKAGE_SCHEMA", errors[0].message, "manifest.json")
    except FileNotFoundError as error:
        raise PackageV2Error("PACKAGE_SCHEMA_BUNDLE", "local frozen schema missing") from error


def _validate_layout(manifest: Mapping[str, Any], names: set[str]) -> None:
    required = {"world/index.json", "narrative/bible.json", "narrative/reconciliation.json",
                "narrative/style_bible.json", "narrative/story.json", "narrative/graph.json",
                "narrative/gm_index.json", "assets/maps/world.png"}
    missing = required - names
    if missing: raise PackageV2Error("PACKAGE_LAYOUT_MISSING", "required v2 member missing", sorted(missing)[0])
    if any(name == "save" or name.startswith("save/") or name.startswith("content/") for name in names):
        raise PackageV2Error("PACKAGE_FORBIDDEN_ENTRY", "v1/save layout is forbidden (layout re-check)")
    graph_nodes = set(manifest.get("node_assets", {}))
    entry = manifest.get("entry_node")
    if entry not in graph_nodes: raise PackageV2Error("PACKAGE_ENTRY_NODE", "entry node has no asset set")
    for node, asset_set in manifest.get("node_assets", {}).items():
        expected = {"image": f"assets/images/{node}.png",
                    "thumbnail": f"assets/thumbnails/{node}.png",
                    "score": f"assets/music/{node}.score.json", "midi": f"assets/midi/{node}.mid"}
        if asset_set != expected or not set(expected.values()) <= names:
            raise PackageV2Error("PACKAGE_MEDIA_COVERAGE", "node media must be exact", node)
    region_maps = manifest.get("region_maps")
    if not isinstance(region_maps, dict) or any(path not in names for path in region_maps.values()):
        raise PackageV2Error("PACKAGE_REGION_MAP_COVERAGE", "region map inventory is incomplete")


def _validate_binary_media(archive: zipfile.ZipFile, manifest: Mapping[str, Any]) -> None:
    from ..narrative.media import (FULL_SIZE, THUMB_SIZE, validate_midi,
                                   validate_png, validate_score)
    from ..narrative.pipeline import _score_from_dict
    try:
        validate_png(archive.read("assets/maps/world.png"), (4096, 4096))
        for path in manifest["region_maps"].values():
            validate_png(archive.read(path), (1024, 1024))
    except (ValueError, KeyError, TypeError) as error:
        raise PackageV2Error("PACKAGE_BINARY_MAP", str(error), "assets/maps") from error
    for node, assets in manifest["node_assets"].items():
        try:
            validate_png(archive.read(assets["image"]), FULL_SIZE)
            validate_png(archive.read(assets["thumbnail"]), THUMB_SIZE)
            score = _score_from_dict(_json_no_duplicates(archive.read(assets["score"]), assets["score"]))
            validate_score(score)
            validate_midi(archive.read(assets["midi"]), score)
        except (ValueError, KeyError, TypeError) as error:
            raise PackageV2Error("PACKAGE_BINARY_MEDIA", str(error), str(node)) from error


def _validate_world_contract(archive: zipfile.ZipFile, manifest: Mapping[str, Any],
                             names: set[str]) -> None:
    """Cross-file invariants a Player relies on before publishing content."""
    graph = _json_no_duplicates(archive.read("narrative/graph.json"), "narrative/graph.json")
    nodes = {item.get("node_id") for item in graph.get("nodes", [])}
    if graph.get("starting_node") != manifest.get("entry_node") or nodes != set(manifest["node_assets"]):
        raise PackageV2Error("PACKAGE_GRAPH_INVENTORY", "graph nodes and manifest assets differ")
    regions = _json_no_duplicates(archive.read("world/regions.json"), "world/regions.json")
    region_ids = {item.get("region_id") for item in regions.get("regions", [])}
    if region_ids != set(manifest["region_maps"]):
        raise PackageV2Error("PACKAGE_REGION_MAP_COVERAGE", "every region requires exactly one map")
    sites = _json_no_duplicates(archive.read("world/sites.json"), "world/sites.json")
    site_ids = {item.get("site_id") for item in sites.get("sites", [])}
    if any(item.get("region_id") not in region_ids for item in sites.get("sites", [])):
        raise PackageV2Error("PACKAGE_SITE_REGION", "site references unknown region")
    local = _json_no_duplicates(archive.read("world/local/index.json"), "world/local/index.json")
    if (local.get("format") != "storyteller.local-world-index.v1"
            or local.get("selection_policy") != "all_registered_sites"
            or local.get("sites") != sorted(site_ids)
            or not isinstance(local.get("entries"), list)):
        raise PackageV2Error("PACKAGE_LOCAL_MAP_COVERAGE", "every site requires a local map")
    entries = local["entries"]
    if [entry.get("site_id") for entry in entries if isinstance(entry, dict)] != sorted(site_ids):
        raise PackageV2Error("PACKAGE_LOCAL_MAP_COVERAGE", "local entries are incomplete")
    expected_entry_fields = {
        "site_id", "archive_path", "local_map_sha256", "boundary_id", "summary_id",
        "material_chunk_hashes", "occupancy_chunk_hashes", "construction_chunk_hashes",
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
        local_map = _json_no_duplicates(data, path)
        if (local_map.get("site_id") != site
                or local_map.get("boundary", {}).get("boundary_id") != entry["boundary_id"]
                or local_map.get("macro_summary", {}).get("summary_id") != entry["summary_id"]
                or [item.get("sha256") for item in local_map.get("chunks", [])]
                != entry["material_chunk_hashes"]
                or [item.get("sha256") for item in local_map.get("occupancy_chunks", [])]
                != entry["occupancy_chunk_hashes"]
                or [item.get("sha256") for item in local_map.get("construction_chunks", [])]
                != entry["construction_chunk_hashes"]):
            raise PackageV2Error("PACKAGE_LOCAL_INDEX", "local chunk inventory mismatch", path)
        for family, key in (
            ("material", "material_chunk_hashes"),
            ("occupancy", "occupancy_chunk_hashes"),
            ("construction", "construction_chunk_hashes"),
        ):
            for sha256 in entry[key]:
                chunk_path = f"world/local/{site}/chunks/{family}/{sha256}.json"
                if chunk_path not in names:
                    raise PackageV2Error(
                        "PACKAGE_LOCAL_CHUNK_COVERAGE", "indexed local chunk missing", chunk_path,
                    )
                chunk = _json_no_duplicates(archive.read(chunk_path), chunk_path)
                if chunk.get("sha256") != sha256:
                    raise PackageV2Error(
                        "PACKAGE_LOCAL_CHUNK_HASH", "local chunk identity mismatch", chunk_path,
                    )
                try:
                    from ..worldgen.local_chunks import local_voxel_chunk_from_mapping
                    from ..worldgen.local_construction import construction_chunk_from_mapping
                    from ..worldgen.local_occupancy import local_occupancy_chunk_from_mapping
                    {
                        "material": local_voxel_chunk_from_mapping,
                        "occupancy": local_occupancy_chunk_from_mapping,
                        "construction": construction_chunk_from_mapping,
                    }[family](chunk)
                except (KeyError, TypeError, ValueError) as exc:
                    raise PackageV2Error(
                        "PACKAGE_LOCAL_CHUNK_HASH", "invalid local chunk payload", chunk_path,
                    ) from exc
    history = _json_no_duplicates(archive.read("world/history/index.json"), "world/history/index.json")
    if not set(history.get("events", [])) <= names or not set(history.get("snapshots", [])) <= names:
        raise PackageV2Error("PACKAGE_HISTORY_INVENTORY", "history member missing")
    years = {int(PurePosixPath(path).stem.removeprefix("year_")) for path in history.get("snapshots", [])}
    expected_years = set(range(0, int(manifest["world"]["present_year"]) + 1, 10))
    expected_years.add(int(manifest["world"]["present_year"]))
    if years != expected_years:
        raise PackageV2Error("PACKAGE_SNAPSHOT_CADENCE", "year 0, ten-year, and final snapshots required")
    for domain in GRID_DOMAINS:
        _validate_grid_domain(archive, names, domain)
    for domain in FLAT_WORLD_DOMAINS:
        _validate_flat_world_domain(archive, names, domain)
    _validate_world_source_coverage(archive, names)


def _validate_grid_domain(archive: zipfile.ZipFile, names: set[str], domain: str) -> None:
    """Prove a chunked reader-facing grid projection matches its declared chunks."""
    index_path = f"world/{domain}/index.json"
    if index_path not in names:
        raise PackageV2Error("PACKAGE_GRID_DOMAIN", "grid domain index is missing", index_path)
    index = _json_no_duplicates(archive.read(index_path), index_path)
    if (not isinstance(index, dict)
            or index.get("format") != "storyteller.grid-domain-index.v1"
            or not isinstance(index.get("width"), int)
            or not isinstance(index.get("height"), int)
            or not isinstance(index.get("layers"), dict)
            or not index["layers"]):
        raise PackageV2Error(
            "PACKAGE_GRID_DOMAIN", "grid domain index shape is invalid", index_path,
        )
    layers = index["layers"]
    if list(layers) != sorted(layers):
        raise PackageV2Error("PACKAGE_GRID_DOMAIN", "layers must be canonically sorted", index_path)
    for layer, entry in layers.items():
        if (not isinstance(entry, dict)
                or set(entry) != {"chunk_width", "chunk_height", "chunks"}
                or not isinstance(entry["chunks"], list) or not entry["chunks"]):
            raise PackageV2Error(
                "PACKAGE_GRID_DOMAIN", f"{domain}/{layer} shape is invalid", index_path,
            )
        previous: tuple[int, int] | None = None
        for descriptor in entry["chunks"]:
            if (not isinstance(descriptor, dict)
                    or set(descriptor) != {"chunk_x", "chunk_y", "width", "height", "sha256"}):
                raise PackageV2Error(
                    "PACKAGE_GRID_DOMAIN", f"{domain}/{layer} chunk descriptor invalid", index_path,
                )
            order = (descriptor["chunk_y"], descriptor["chunk_x"])
            if previous is not None and order <= previous:
                raise PackageV2Error(
                    "PACKAGE_GRID_DOMAIN", f"{domain}/{layer} chunks must be canonically ordered",
                    index_path,
                )
            previous = order
            chunk_path = f"world/{domain}/chunks/{layer}/{descriptor['sha256']}.bin"
            if chunk_path not in names:
                raise PackageV2Error(
                    "PACKAGE_GRID_CHUNK_COVERAGE", "indexed grid chunk missing", chunk_path,
                )
            data = archive.read(chunk_path)
            if sha256(data) != descriptor["sha256"]:
                raise PackageV2Error(
                    "PACKAGE_GRID_CHUNK_HASH", "grid chunk identity mismatch", chunk_path,
                )
            try:
                from ..worldgen.artifacts import GridChunk
                chunk = GridChunk.decode(data)
            except (KeyError, TypeError, ValueError) as exc:
                raise PackageV2Error(
                    "PACKAGE_GRID_CHUNK_HASH", "invalid grid chunk payload", chunk_path,
                ) from exc
            if (chunk.layer != layer or chunk.chunk_x != descriptor["chunk_x"]
                    or chunk.chunk_y != descriptor["chunk_y"] or chunk.width != descriptor["width"]
                    or chunk.height != descriptor["height"]):
                raise PackageV2Error(
                    "PACKAGE_GRID_CHUNK_HASH", "grid chunk header mismatch", chunk_path,
                )


def _validate_flat_world_domain(archive: zipfile.ZipFile, names: set[str], domain: str) -> None:
    """Prove a flat reader-facing world projection is a byte-exact source payload."""
    path = f"world/{domain}.json"
    source_path = f"world/source/{FLAT_WORLD_DOMAINS[domain]}.json"
    if path not in names or source_path not in names:
        raise PackageV2Error("PACKAGE_WORLD_FLAT_DOMAIN", f"{domain} projection missing", path)
    envelope = _json_no_duplicates(archive.read(source_path), source_path)
    if not isinstance(envelope, dict) or "payload" not in envelope:
        raise PackageV2Error(
            "PACKAGE_WORLD_FLAT_DOMAIN", "source envelope is malformed", source_path,
        )
    if archive.read(path) != canonical_json(envelope["payload"]):
        raise PackageV2Error(
            "PACKAGE_WORLD_FLAT_DOMAIN", f"{domain} projection differs from source envelope", path,
        )


def _validate_world_source_coverage(archive: zipfile.ZipFile, names: set[str]) -> None:
    """Prove every declared authoritative envelope is retained byte-for-byte."""
    from ..world.views import REQUIRED_KINDS
    coverage_path = "world/source/coverage.json"
    if coverage_path not in names:
        raise PackageV2Error("PACKAGE_WORLD_SOURCE_COVERAGE", "coverage ledger is missing", coverage_path)
    ledger = _json_no_duplicates(archive.read(coverage_path), coverage_path)
    if (not isinstance(ledger, dict)
            or ledger.get("format") != "storyteller.world-source-coverage.v1"
            or ledger.get("required_domains") != sorted(REQUIRED_KINDS)
            or not isinstance(ledger.get("sources"), list)):
        raise PackageV2Error("PACKAGE_WORLD_SOURCE_COVERAGE", "coverage ledger shape is invalid", coverage_path)
    source_names = {name for name in names
                    if name.startswith("world/source/") and name.endswith(".json")
                    and name != coverage_path}
    rows = ledger["sources"]
    row_paths = [row.get("archive_path") for row in rows if isinstance(row, dict)]
    if len(row_paths) != len(set(row_paths)) or set(row_paths) != source_names:
        raise PackageV2Error("PACKAGE_WORLD_SOURCE_COVERAGE",
                             "ledger must cover every source member exactly once", coverage_path)
    index = _json_no_duplicates(archive.read("world/index.json"), "world/index.json")
    domains = index.get("domains") if isinstance(index, dict) else None
    if not isinstance(domains, list) or set(domains) != {PurePosixPath(path).stem for path in source_names}:
        raise PackageV2Error("PACKAGE_WORLD_SOURCE_COVERAGE",
                             "world index domains differ from retained sources", "world/index.json")
    if not set(REQUIRED_KINDS) <= set(domains):
        raise PackageV2Error("PACKAGE_WORLD_SOURCE_COVERAGE",
                             "required authoritative domain is missing", "world/index.json")
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "source_name", "archive_path", "artifact_id", "sha256", "size_bytes", "retention",
        }:
            raise PackageV2Error("PACKAGE_WORLD_SOURCE_COVERAGE", "source row is invalid", coverage_path)
        path = row["archive_path"]
        data = archive.read(path)
        envelope = _json_no_duplicates(data, path)
        if (row["source_name"] != PurePosixPath(path).stem
                or row["retention"] != "byte_for_byte"
                or row["size_bytes"] != len(data)
                or row["sha256"] != sha256(data)
                or not isinstance(envelope, dict)
                or row["artifact_id"] != envelope.get("artifact_id")):
            raise PackageV2Error("PACKAGE_WORLD_SOURCE_COVERAGE",
                                 "source bytes or identity differ from ledger", path)


def inspect_v2_package(package: str | Path) -> dict[str, Any]:
    result = validate_v2_package(package)
    if not result.accepted:
        issue = result.issues[0]
        raise PackageV2Error(issue.code, issue.message, issue.path)
    assert result.manifest is not None
    manifest = result.manifest
    return {"accepted": True, "package_format": manifest["package_format"],
            "package_version": manifest["package_version"], "story_id": manifest["story_id"],
            "title": manifest["title"], "content_hash": manifest["content_hash"],
            "artifacts": len(manifest["artifacts"]), "nodes": len(manifest["node_assets"]),
            "regions": len(manifest["region_maps"])}
