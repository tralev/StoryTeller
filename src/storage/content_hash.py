"""Canonical identity hashing for frozen v2 and legacy v1 archives."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any


def compute_content_hash(
    artifacts: dict[str, bytes],
    *,
    exclude: frozenset[str] = frozenset({"manifest.json"}),
) -> str:
    """Compute SHA256 of all content artifacts.

    Algorithm (deterministic):
      1. Sort artifact keys alphabetically
      2. For each key: hash key bytes, then hash value bytes
      3. Exclude operational files (manifest.json) from the hash

    This is the single canonical implementation. Both ManifestBuilder
    and Packager use this function so content_hash is consistent.

    Args:
        artifacts: Dict of ZIP path → bytes.
        exclude: Set of paths to exclude (default: manifest.json).

    Returns:
        64-character hex SHA256 digest.
    """
    hasher = hashlib.sha256()
    for name in sorted(artifacts.keys()):
        if name in exclude:
            continue
        hasher.update(name.encode())
        hasher.update(artifacts[name])
    return hasher.hexdigest()


def compute_zip_content_hash(zip_path: str | Path) -> str:
    """Recompute package identity from member paths and bytes, never ZIP bytes.

    Package v2 uses its frozen artifact-record identity algorithm with hashes
    and sizes recomputed from archive members. Legacy v1 archives retain the
    historical ``content/*`` algorithm for compatibility diagnostics.
    """
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = [info.filename for info in archive.infolist() if not info.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError("duplicate ZIP entry cannot be hashed canonically")
        try:
            manifest = json.loads(archive.read("manifest.json"))
        except (KeyError, json.JSONDecodeError):
            manifest = {}
        if (
            manifest.get("package_format") == "storyteller.story"
            and manifest.get("package_version") == 2
        ):
            from .package_v2 import content_hash

            records: list[dict[str, Any]] = []
            for declared in manifest.get("artifacts", []):
                path = declared["path"]
                try:
                    data = archive.read(path)
                except KeyError as error:
                    raise ValueError(f"declared package member is missing: {path}") from error
                record = dict(declared)
                record["sha256"] = hashlib.sha256(data).hexdigest()
                record["size_bytes"] = len(data)
                records.append(record)
            return content_hash(records)

        artifacts: dict[str, bytes] = {}
        for info in archive.infolist():
            name = info.filename
            if info.is_dir() or not name.startswith("content/"):
                continue
            artifacts[name] = archive.read(info)
    return compute_content_hash(artifacts, exclude=frozenset())
