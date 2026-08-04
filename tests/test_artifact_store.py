"""Tests for ArtifactStore — disk-backed dict with write-through to disk."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.artifact_store import ArtifactStore
from src.job_queue import PipelineContext


class TestArtifactStoreInMemory:
    """ArtifactStore with output_dir=None behaves like a normal dict (tests)."""

    def test_set_get(self) -> None:
        store = ArtifactStore()
        store["bible"] = {"world_name": "Test"}
        assert store["bible"] == {"world_name": "Test"}

    def test_get_with_default(self) -> None:
        store = ArtifactStore()
        assert store.get("missing") is None
        assert store.get("missing", {}) == {}

    def test_contains(self) -> None:
        store = ArtifactStore()
        store["key"] = "val"
        assert "key" in store
        assert "missing" not in store

    def test_len(self) -> None:
        store = ArtifactStore()
        assert len(store) == 0
        store["a"] = 1
        store["b"] = 2
        assert len(store) == 2

    def test_keys_values_items(self) -> None:
        store = ArtifactStore()
        store["a"] = 1
        store["b"] = 2
        assert set(store.keys()) == {"a", "b"}
        assert set(store.values()) == {1, 2}
        assert set(store.items()) == {("a", 1), ("b", 2)}

    def test_delete(self) -> None:
        store = ArtifactStore()
        store["x"] = 42
        del store["x"]
        assert "x" not in store
        assert len(store) == 0

    def test_setdefault(self) -> None:
        store = ArtifactStore()
        store.setdefault("a", 1)
        assert store["a"] == 1
        store.setdefault("a", 99)
        assert store["a"] == 1  # unchanged

    def test_update(self) -> None:
        store = ArtifactStore()
        store.update({"a": 1, "b": 2})
        assert store["a"] == 1
        assert store["b"] == 2

    def test_clear(self) -> None:
        store = ArtifactStore()
        store["a"] = 1
        store.clear()
        assert len(store) == 0
        assert "a" not in store

    def test_iter(self) -> None:
        store = ArtifactStore()
        store["x"] = 1
        store["y"] = 2
        keys = list(store)
        assert sorted(keys) == ["x", "y"]

    def test_repr(self) -> None:
        store = ArtifactStore()
        assert "in-memory" in repr(store)
        store["a"] = 1
        assert "1 keys" in repr(store)


class TestArtifactStoreDiskBacked:
    """ArtifactStore with output_dir writes JSON files to disk."""

    def test_write_through_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(output_dir=tmp)
            store["bible"] = {"world_name": "The Crystal Accord"}

            # File should exist on disk
            path = Path(tmp) / "bible.json"
            assert path.exists()
            data = json.loads(path.read_text())
            assert data == {"world_name": "The Crystal Accord"}

    def test_read_back_from_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Write a file directly
            path = Path(tmp) / "bible.json"
            path.write_text(json.dumps({"world_name": "Disk World"}))

            # New store picks it up
            store = ArtifactStore(output_dir=tmp)
            assert store["bible"] == {"world_name": "Disk World"}

    def test_multiple_keys_write_to_separate_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(output_dir=tmp)
            store["bible"] = {"a": 1}
            store["story"] = {"b": 2}
            store["graph"] = {"c": 3}

            assert (Path(tmp) / "bible.json").exists()
            assert (Path(tmp) / "story.json").exists()
            assert (Path(tmp) / "graph.json").exists()

    def test_delete_removes_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(output_dir=tmp)
            store["temp_key"] = {"data": 42}
            assert (Path(tmp) / "temp_key.json").exists()

            del store["temp_key"]
            assert not (Path(tmp) / "temp_key.json").exists()
            assert "temp_key" not in store

    def test_overwrite_updates_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(output_dir=tmp)
            store["bible"] = {"version": 1}
            store["bible"] = {"version": 2}

            path = Path(tmp) / "bible.json"
            data = json.loads(path.read_text())
            assert data == {"version": 2}

    def test_update_writes_all_to_disk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(output_dir=tmp)
            store.update({"a": 1, "b": 2, "c": 3})

            assert (Path(tmp) / "a.json").exists()
            assert (Path(tmp) / "b.json").exists()
            assert (Path(tmp) / "c.json").exists()

    def test_repr_shows_disk_path(self) -> None:
        store = ArtifactStore(output_dir="/tmp/test")
        assert "/tmp/test" in repr(store)

    def test_json_sorted_keys_for_determinism(self) -> None:
        """Ensure JSON output uses sort_keys for reproducible files."""
        with tempfile.TemporaryDirectory() as tmp:
            store = ArtifactStore(output_dir=tmp)
            store["test"] = {"z": 1, "a": 2}
            path = Path(tmp) / "test.json"
            raw = path.read_text()
            # With sort_keys, "a" should come before "z"
            assert raw.index('"a"') < raw.index('"z"')

    def test_corrupt_json_skipped_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "broken.json").write_text("{not valid json")
            (Path(tmp) / "good.json").write_text('{"ok": true}')

            store = ArtifactStore(output_dir=tmp)
            assert store["good"] == {"ok": True}
            assert "broken" not in store  # skipped


class TestPipelineContextWithArtifactStore:
    """PipelineContext with output_dir uses disk-backed ArtifactStore."""

    def test_default_context_uses_in_memory_store(self) -> None:
        ctx = PipelineContext(run_id="test", seed=42)
        assert isinstance(ctx.outputs, ArtifactStore)
        assert ctx.outputs.output_dir is None  # no disk backing

    def test_context_with_output_dir_uses_disk_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = PipelineContext(
                run_id="test", seed=42, output_dir=tmp,
            )
            assert ctx.outputs.output_dir == Path(tmp)

            ctx.outputs["bible"] = {"world": "Test"}
            assert (Path(tmp) / "bible.json").exists()

    def test_context_outputs_alias(self) -> None:
        """context.outputs and context.artifacts are the same object."""
        ctx = PipelineContext(run_id="test", seed=42)
        assert ctx.outputs is ctx.artifacts

        ctx.outputs["key"] = "value"
        assert ctx.artifacts["key"] == "value"

    def test_context_components_preserved(self) -> None:
        """Existing PipelineContext fields still work."""
        ctx = PipelineContext(run_id="r1", seed=7)
        assert ctx.run_id == "r1"
        assert ctx.seed == 7
        assert ctx.feedback == []
        assert ctx.state == {}
