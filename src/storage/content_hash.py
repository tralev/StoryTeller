"""Canonical content hash — single algorithm used by ManifestBuilder and Packager.

Phase 5.6 A5: Previously ManifestBuilder hashed bible+style_bible+story+graph+gm_index
(sorted by key), while Packager hashed all ZIP artifact names+bytes (sorted by name).
These produced DIFFERENT hashes for the same content.

This module provides ONE algorithm used everywhere.
"""

from __future__ import annotations

import hashlib
import json
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


def compute_json_content_hash(
    json_artifacts: dict[str, dict[str, Any]],
) -> str:
    """Compute SHA256 of JSON artifacts for pre-package content hashing.

    Used by ManifestBuilder before packaging. Serializes each JSON dict
    with sorted keys to bytes, then delegates to compute_content_hash.

    Args:
        json_artifacts: Dict of key → JSON-serializable dict.

    Returns:
        64-character hex SHA256 digest.
    """
    byte_artifacts: dict[str, bytes] = {}
    for key, data in json_artifacts.items():
        byte_artifacts[f"content/{key}.json"] = json.dumps(
            data, sort_keys=True,
        ).encode()
    return compute_content_hash(byte_artifacts, exclude=frozenset())
