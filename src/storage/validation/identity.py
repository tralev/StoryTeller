"""Authoritative identity indexing for cross-domain package references."""

from __future__ import annotations

import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .common import JsonLoader


@dataclass(frozen=True)
class PackageIdentityIndex:
    """Resolved identity namespace shared by cross-domain package validators."""

    ids: frozenset[str]

    @classmethod
    def build(
        cls,
        archive: zipfile.ZipFile,
        manifest: Mapping[str, Any],
        load_json: JsonLoader,
    ) -> PackageIdentityIndex:
        identities = {record["artifact_id"] for record in manifest["artifacts"]}

        def collect(value: Any, field: str = "") -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    collect(item, key)
            elif isinstance(value, list):
                for item in value:
                    collect(item, field)
            elif isinstance(value, str) and (
                field.endswith("_id")
                or field.endswith("_ids")
                or field in {"authoritative_refs", "source_ids"}
            ):
                identities.add(value)

        for record in manifest["artifacts"]:
            path = record["path"]
            if (path.startswith("world/") or path == "narrative/graph.json") and path.endswith(
                ".json"
            ):
                collect(load_json(archive.read(path), path))
        return cls(frozenset(identities))
