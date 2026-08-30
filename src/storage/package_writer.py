"""Deterministic v2 package construction, identity, staging, and publication."""

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
from .validation import PackageV2Error
from .validation.manifest import (
    FORMAT,
    HASH_RE,
    REQUIRED_FEATURES,
    TRUSTED_SCHEMA_SHA256,
    VERSION,
)

MAX_JSON_DEPTH = 128
MAX_SAFE_INTEGER = (1 << 53) - 1


def has_extraction_space(required_bytes: int, free_bytes: int) -> bool:
    """Return whether atomic staging can hold every declared uncompressed member."""
    if required_bytes < 0 or free_bytes < 0:
        raise ValueError("extraction byte counts must be non-negative")
    return free_bytes >= required_bytes


def canonical_json(value: object) -> bytes:
    """Canonical UTF-8 JSON for the frozen integer-domain JCS profile."""
    def check(item: object, depth: int = 0) -> None:
        if depth > MAX_JSON_DEPTH:
            raise PackageV2Error("PACKAGE_JSON_DEPTH", "JSON nesting exceeds limit")
        if isinstance(item, bool) or item is None or isinstance(item, str):
            return
        if isinstance(item, int):
            if abs(item) > MAX_SAFE_INTEGER:
                raise PackageV2Error(
                    "PACKAGE_NUMBER_RANGE", "integer exceeds interoperable range"
                )
            return
        if isinstance(item, float):
            raise PackageV2Error(
                "PACKAGE_NUMBER_PROFILE", "authoritative JSON uses integers"
            )
        if isinstance(item, (list, tuple)):
            for child in item:
                check(child, depth + 1)
            return
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise PackageV2Error(
                    "PACKAGE_JSON_KEY", "object keys must be strings"
                )
            for child in item.values():
                check(child, depth + 1)
            return
        raise PackageV2Error(
            "PACKAGE_JSON_TYPE", f"unsupported value {type(item).__name__}"
        )

    def ordered(item: object) -> object:
        if isinstance(item, dict):
            return {
                key: ordered(item[key])
                for key in sorted(item, key=lambda value: value.encode("utf-16-be"))
            }
        if isinstance(item, (list, tuple)):
            return [ordered(child) for child in item]
        return item

    check(value)
    return json.dumps(
        ordered(value),
        ensure_ascii=False,
        sort_keys=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_grid_domain_files(
    domain: str,
    catalog: DenseGridCatalog,
    chunk_bytes: Callable[[str, int, int], bytes],
) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    """Build a frozen grid-domain index plus content-addressed chunk members."""
    layers: dict[str, Any] = {}
    members: list[tuple[str, bytes]] = []
    for manifest in catalog.manifests:
        chunks: list[dict[str, Any]] = []
        for descriptor in manifest.chunks:
            data = chunk_bytes(
                manifest.layer, descriptor.chunk_x, descriptor.chunk_y
            )
            if sha256(data) != descriptor.sha256:
                raise PackageV2Error(
                    "PACKAGE_GRID_CHUNK_HASH",
                    f"{domain}/{manifest.layer} chunk hash mismatch",
                )
            path = (
                f"world/{domain}/chunks/{manifest.layer}/{descriptor.sha256}.bin"
            )
            members.append((path, data))
            chunks.append(
                {
                    "chunk_x": descriptor.chunk_x,
                    "chunk_y": descriptor.chunk_y,
                    "width": descriptor.width,
                    "height": descriptor.height,
                    "sha256": descriptor.sha256,
                }
            )
        layers[manifest.layer] = {
            "chunk_width": manifest.chunk_width,
            "chunk_height": manifest.chunk_height,
            "chunks": chunks,
        }
    return {
        "format": "storyteller.grid-domain-index.v1",
        "width": catalog.grid.width,
        "height": catalog.grid.height,
        "layers": layers,
    }, members


def confined_path(path: str) -> str:
    pure = PurePosixPath(path)
    if (
        not path
        or "\\" in path
        or pure.is_absolute()
        or any(part in ("", ".", "..") for part in pure.parts)
    ):
        raise PackageV2Error("PACKAGE_UNSAFE_PATH", "path is not normalized", path)
    return pure.as_posix()


def producer(component: str, version: str = "2") -> dict[str, Any]:
    fingerprint = sha256(
        canonical_json({"component": component, "version": version})
    )
    return {
        "component": component,
        "algorithm_version": 2,
        "model": None,
        "prompt_sha256": None,
        "schema_sha256": TRUSTED_SCHEMA_SHA256,
        "code_revision": "working-tree",
        "fingerprint": fingerprint,
    }


def artifact_record(
    kind: str,
    path: str,
    data: bytes,
    *,
    depends_on: Iterable[str] = (),
    producer_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    path = confined_path(path)
    dependencies = sorted(set(depends_on))
    producer_record = dict(producer_data or producer(kind))
    fingerprint = producer_record.get("fingerprint")
    if not isinstance(fingerprint, str) or not HASH_RE.fullmatch(fingerprint):
        raise PackageV2Error(
            "PACKAGE_PRODUCER", "invalid producer fingerprint", path
        )
    content_digest = sha256(data)
    derivation = sha256(
        canonical_json(
            {
                "depends_on": dependencies,
                "kind": kind,
                "producer_fingerprint": fingerprint,
                "sha256": content_digest,
            }
        )
    )
    prefix = re.sub(r"[^a-z0-9]", "", kind.lower())
    if not prefix or not prefix[0].isalpha():
        raise PackageV2Error("PACKAGE_KIND", "kind cannot form an ID prefix", path)
    return {
        "artifact_id": f"{prefix}_{derivation[:32]}",
        "kind": kind,
        "path": path,
        "sha256": content_digest,
        "size_bytes": len(data),
        "depends_on": dependencies,
        "producer": producer_record,
    }


def content_hash(records: Iterable[Mapping[str, Any]]) -> str:
    reduced = [
        {
            "artifact_id": record["artifact_id"],
            "kind": record["kind"],
            "path": record["path"],
            "sha256": record["sha256"],
            "size_bytes": record["size_bytes"],
            "depends_on": sorted(record["depends_on"]),
            "producer_fingerprint": record["producer"]["fingerprint"],
        }
        for record in sorted(
            records, key=lambda item: str(item["path"]).encode("utf-8")
        )
    ]
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

    def add(
        self,
        kind: str,
        path: str,
        data: bytes,
        *,
        depends_on: Iterable[str] = (),
        producer_data: Mapping[str, Any] | None = None,
    ) -> str:
        path = confined_path(path)
        if path == "manifest.json" or path in self.members:
            raise PackageV2Error(
                "PACKAGE_DUPLICATE_PATH", "duplicate/reserved path", path
            )
        record = artifact_record(
            kind,
            path,
            data,
            depends_on=depends_on,
            producer_data=producer_data,
        )
        self.members[path] = data
        self.records.append(record)
        return str(record["artifact_id"])

    def manifest(
        self, *, node_assets: Mapping[str, Any], region_maps: Mapping[str, str]
    ) -> dict[str, Any]:
        digest = content_hash(self.records)
        return {
            "package_format": FORMAT,
            "package_version": VERSION,
            "story_id": f"story_{digest[:32]}",
            "title": self.title,
            "content_profile": "mature_dark_fantasy",
            "master_seed": self.master_seed,
            "required_features": list(REQUIRED_FEATURES),
            "optional_features": [],
            "entry_node": self.entry_node,
            "world": {
                "index": "world/index.json",
                "present_year": self.present_year,
                "coordinate_system": "world_cell_xy",
                "metres_per_world_cell": self.metres_per_world_cell,
            },
            "artifacts": sorted(
                self.records, key=lambda record: str(record["path"]).encode("utf-8")
            ),
            "node_assets": dict(sorted(node_assets.items())),
            "region_maps": dict(sorted(region_maps.items())),
            "content_hash": digest,
        }

    def write(
        self,
        destination: str | Path,
        *,
        node_assets: Mapping[str, Any],
        region_maps: Mapping[str, str],
    ) -> Path:
        """Stage, accept with the public validator, then atomically publish."""
        from .package_v2 import validate_v2_package

        destination = Path(destination)
        staged = destination.with_name(destination.name + ".staging")
        try:
            self.write_staged(
                staged, node_assets=node_assets, region_maps=region_maps
            )
            result = validate_v2_package(staged)
            if not result.accepted:
                issue = result.issues[0]
                raise PackageV2Error(issue.code, issue.message, issue.path)
            return publish_staged_package(staged, destination)
        finally:
            staged.unlink(missing_ok=True)

    def write_staged(
        self,
        destination: str | Path,
        *,
        node_assets: Mapping[str, Any],
        region_maps: Mapping[str, str],
    ) -> Path:
        """Construct an unpublished archive without performing acceptance."""
        destination = Path(destination)
        manifest = self.manifest(node_assets=node_assets, region_maps=region_maps)
        members = dict(self.members)
        members["manifest.json"] = canonical_json(manifest)
        temporary = destination.with_name(destination.name + ".tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(temporary, "w", allowZip64=True) as archive:
                for path in sorted(members, key=lambda item: item.encode("utf-8")):
                    info = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    info.compress_type = (
                        zipfile.ZIP_STORED
                        if path.endswith(".png")
                        else zipfile.ZIP_DEFLATED
                    )
                    archive.writestr(info, members[path])
            os.replace(temporary, destination)
            _fsync_directory(destination.parent)
        finally:
            temporary.unlink(missing_ok=True)
        return destination


def publish_staged_package(staged: str | Path, destination: str | Path) -> Path:
    """Atomically publish a previously accepted same-filesystem archive."""
    staged_path = Path(staged)
    destination_path = Path(destination)
    if not staged_path.is_file():
        raise PackageV2Error(
            "PACKAGE_STAGING_MISSING", "staged package is missing", str(staged_path)
        )
    if staged_path.parent.resolve() != destination_path.parent.resolve():
        raise PackageV2Error(
            "PACKAGE_STAGING_FILESYSTEM",
            "staged package must share the destination directory",
            str(staged_path),
        )
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged_path, destination_path)
    _fsync_directory(destination_path.parent)
    return destination_path


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError:
        pass
