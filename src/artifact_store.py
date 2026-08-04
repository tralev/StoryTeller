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
