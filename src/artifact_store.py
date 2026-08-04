"""ArtifactStore — disk-backed dict for streaming pipeline artifacts.

Wraps a dict with write-through to disk using atomic writes.
Every __setitem__ writes a JSON file to the output directory via
a .tmp file + os.replace (atomic rename). When output_dir is None,
operates as a pure in-memory dict (used in tests to avoid disk I/O).

This prevents OOM during long pipeline runs by ensuring every
artifact lives on disk the moment it's generated, and prevents
corrupt files if the process crashes mid-write.

Phase 5.5E: Atomic artifact commits — writes go to .json.tmp first,
then atomically renamed to .json. No partial writes survive crashes.

Usage:
    # Tests: pure in-memory (output_dir=None)
    store = ArtifactStore()
    store["bible"] = {"world_name": "Test"}  # only in memory

    # Production: atomic write-through to disk
    store = ArtifactStore(output_dir="output")
    store["bible"] = {"world_name": "The Crystal Accord"}
    # -> writes tmp/output/bible.json.tmp, then os.replace → tmp/output/bible.json

    # Read-back from disk (e.g., after crash/resume)
    store2 = ArtifactStore(output_dir="output")
    bible = store2["bible"]  # loads from tmp/output/bible.json
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

from .pipeline.artifacts import (
    BibleDict,
    GmIndexDict,
    GraphDict,
    ImagesOutputDict,
    ManifestDict,
    MidiOutputDict,
    PackageResultDict,
    StoryDict,
    StyleBibleDict,
)


class ArtifactStore:
    """Dict-like container with atomic write-through to disk.

    Mirrors the dict interface used by PipelineContext.outputs.
    Every __setitem__ writes a corresponding .json file via atomic
    rename when output_dir is set. Reads come from an in-memory cache.

    After a crash/resume, creating a new ArtifactStore with the
    same output_dir lets subsequent steps read pre-existing
    artifacts from disk.
    """

    def __init__(self, output_dir: str | None = None) -> None:
        """Initialize the store.

        Args:
            output_dir: If provided, every write atomically flushes a JSON
                        file to this directory. If None, operates purely
                        in-memory (for tests).
        """
        self.output_dir = Path(output_dir) if output_dir else None
        self._data: dict[str, Any] = {}

        # If output directory exists, pre-load any existing artifacts
        # into the cache for fast reads (resume scenario).
        if self.output_dir and self.output_dir.exists():
            for path in sorted(self.output_dir.glob("*.json")):
                key = path.stem
                try:
                    self._data[key] = json.loads(path.read_text())
                except json.JSONDecodeError:
                    pass

    # ── dict protocol ──────────────────────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            path = self.output_dir / f"{key}.json"
            tmp_path = Path(str(path) + ".tmp")
            # Atomic write: write to .tmp, then os.replace
            with open(tmp_path, "w") as f:
                json.dump(value, f, sort_keys=True, indent=2)
            os.replace(tmp_path, path)

    def __delitem__(self, key: str) -> None:
        del self._data[key]
        if self.output_dir:
            path = self.output_dir / f"{key}.json"
            if path.exists():
                path.unlink()

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        """Return value for key or default (mirrors dict.get)."""
        return self._data.get(key, default)

    def keys(self) -> Any:  # Returns dict_keys
        return self._data.keys()

    def values(self) -> Any:
        return self._data.values()

    def items(self) -> Any:
        return self._data.items()

    def setdefault(self, key: str, default: Any = None) -> Any:
        """Set default value and write-through if key is new."""
        if key not in self._data:
            self[key] = default
        return self._data[key]

    def update(self, other: dict[str, Any]) -> None:
        """Update from another dict, writing each key to disk."""
        for key, value in other.items():
            self[key] = value

    def clear(self) -> None:
        """Remove all keys (does not delete files from disk)."""
        self._data.clear()

    def __repr__(self) -> str:
        disk = f"→ {self.output_dir}" if self.output_dir else "in-memory"
        return f"ArtifactStore({len(self._data)} keys, {disk})"

    # ── Phase 5.6N N5: typed artifact repository methods ───────────────
    #
    # High-value artifacts get typed accessors instead of raw
    # ``context.outputs.get("bible")`` / ``["bible"] = ...`` calls.
    # Runtime behaviour is identical to the dict protocol; the types
    # document the JSON boundary shapes (see pipeline.artifacts).

    @staticmethod
    def _get_typed(
        data: dict[str, Any],
        key: str,
    ) -> dict[str, Any] | None:
        value = data.get(key)
        return value if isinstance(value, dict) else None

    # ── bible ───────────────────────────────────────────────────────────

    def get_bible(self) -> BibleDict | None:
        """Return the World Bible artifact, or None if absent/not a dict."""
        return self._get_typed(self._data, "bible")  # type: ignore[return-value]

    def put_bible(self, value: BibleDict) -> None:
        """Store the World Bible artifact (write-through when disk-backed)."""
        self["bible"] = value

    # ── style_bible ─────────────────────────────────────────────────────

    def get_style_bible(self) -> StyleBibleDict | None:
        """Return the style bible artifact, or None if absent."""
        return self._get_typed(self._data, "style_bible")  # type: ignore[return-value]

    def put_style_bible(self, value: StyleBibleDict) -> None:
        """Store the style bible artifact."""
        self["style_bible"] = value

    # ── story ───────────────────────────────────────────────────────────

    def get_story(self) -> StoryDict | None:
        """Return the story artifact, or None if absent."""
        return self._get_typed(self._data, "story")  # type: ignore[return-value]

    def put_story(self, value: StoryDict) -> None:
        """Store the story artifact."""
        self["story"] = value

    # ── graph ───────────────────────────────────────────────────────────

    def get_graph(self) -> GraphDict | None:
        """Return the CYOA graph artifact, or None if absent."""
        return self._get_typed(self._data, "graph")  # type: ignore[return-value]

    def put_graph(self, value: GraphDict) -> None:
        """Store the CYOA graph artifact."""
        self["graph"] = value

    # ── gm_index ────────────────────────────────────────────────────────

    def get_gm_index(self) -> GmIndexDict | None:
        """Return the GM retrieval index, or None if absent."""
        return self._get_typed(self._data, "gm_index")  # type: ignore[return-value]

    def put_gm_index(self, value: GmIndexDict) -> None:
        """Store the GM retrieval index."""
        self["gm_index"] = value

    # ── manifest ────────────────────────────────────────────────────────

    def get_manifest(self) -> ManifestDict | None:
        """Return the manifest artifact, or None if absent."""
        return self._get_typed(self._data, "manifest")  # type: ignore[return-value]

    def put_manifest(self, value: ManifestDict) -> None:
        """Store the manifest artifact."""
        self["manifest"] = value

    # ── images / midi (aggregated batch outputs) ────────────────────────

    def get_images(self) -> ImagesOutputDict | None:
        """Return the aggregated images output, or None if absent."""
        return self._get_typed(self._data, "images")  # type: ignore[return-value]

    def put_images(self, value: ImagesOutputDict) -> None:
        """Store the aggregated images output."""
        self["images"] = value

    def get_midi(self) -> MidiOutputDict | None:
        """Return the aggregated midi output, or None if absent."""
        return self._get_typed(self._data, "midi")  # type: ignore[return-value]

    def put_midi(self, value: MidiOutputDict) -> None:
        """Store the aggregated midi output."""
        self["midi"] = value

    # ── world_snapshot (Phase 7.5) ──────────────────────────────────────

    def get_world_snapshot(self) -> dict[str, Any] | None:
        """Return the procedural world snapshot, or None if absent."""
        return self._get_typed(self._data, "world_snapshot")

    def put_world_snapshot(self, value: dict[str, Any]) -> None:
        """Store the procedural world snapshot."""
        self["world_snapshot"] = value

    # ── packager result ─────────────────────────────────────────────────

    def get_packager(self) -> PackageResultDict | None:
        """Return the packager result dict, or None if absent."""
        return self._get_typed(self._data, "packager")  # type: ignore[return-value]

    def put_packager(self, value: PackageResultDict) -> None:
        """Store the packager result dict."""
        self["packager"] = value
