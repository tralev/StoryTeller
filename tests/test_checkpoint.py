"""Tests for CheckpointStore — save, load, resume, clear."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from src.storage.checkpoint import CheckpointStore


@pytest.fixture
def store() -> CheckpointStore:
    """Create a temporary checkpoint store."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    store = CheckpointStore(path)
    yield store
    os.unlink(path)


class TestSaveLoad:
    """Basic save and load operations."""

    def test_save_and_load(self, store: CheckpointStore) -> None:
        store.save("world_builder", phase=1, seed=42, output={"bible": "data"})
        entry = store.load("world_builder")
        assert entry is not None
        assert entry.step_name == "world_builder"
        assert entry.phase == 1
        assert entry.seed == 42
        assert entry.artifact_id == ""
        assert entry.attempt_count == 1

    def test_load_nonexistent_returns_none(self, store: CheckpointStore) -> None:
        assert store.load("nonexistent") is None

    def test_save_overwrites(self, store: CheckpointStore) -> None:
        store.save("step", phase=1, seed=42, output={"v": 1})
        store.save("step", phase=1, seed=42, output={"v": 2})
        entry = store.load("step")
        assert entry is not None
        assert json.loads(entry.output_json) == {"v": 2}

    def test_save_with_artifact_id(self, store: CheckpointStore) -> None:
        store.save("step", phase=1, seed=42, output={"x": 1}, artifact_id="world_abc")
        entry = store.load("step")
        assert entry is not None
        assert entry.artifact_id == "world_abc"

    def test_save_with_attempt_count(self, store: CheckpointStore) -> None:
        store.save("step", phase=1, seed=42, output={"x": 1}, attempt_count=3)
        entry = store.load("step")
        assert entry is not None
        assert entry.attempt_count == 3


class TestLoadAll:
    """Loading all checkpoints."""

    def test_load_all_ordered_by_phase(self, store: CheckpointStore) -> None:
        store.save("step_c", phase=3, seed=42, output={"c": 3})
        store.save("step_a", phase=1, seed=42, output={"a": 1})
        store.save("step_b", phase=2, seed=42, output={"b": 2})

        entries = store.load_all()
        assert len(entries) == 3
        assert entries[0].phase == 1
        assert entries[1].phase == 2
        assert entries[2].phase == 3

    def test_load_all_empty(self, store: CheckpointStore) -> None:
        assert store.load_all() == []


class TestPhaseTracking:
    """Tracking completed phases for resume."""

    def test_get_completed_phases(self, store: CheckpointStore) -> None:
        store.save("a", phase=1, seed=42, output={})
        store.save("b", phase=2, seed=42, output={})
        store.save("c", phase=3, seed=42, output={})
        assert store.get_completed_phases() == [1, 2, 3]

    def test_highest_completed_phase(self, store: CheckpointStore) -> None:
        assert store.get_highest_completed_phase() == 0
        store.save("a", phase=1, seed=42, output={})
        store.save("b", phase=5, seed=42, output={})
        assert store.get_highest_completed_phase() == 5

    def test_duplicate_phases(self, store: CheckpointStore) -> None:
        store.save("a", phase=1, seed=42, output={})
        store.save("a2", phase=1, seed=42, output={})
        assert store.get_completed_phases() == [1]


class TestDeleteClear:
    """Delete and clear operations."""

    def test_delete_single(self, store: CheckpointStore) -> None:
        store.save("a", phase=1, seed=42, output={})
        store.save("b", phase=2, seed=42, output={})
        store.delete("a")
        assert store.load("a") is None
        assert store.load("b") is not None

    def test_clear_all(self, store: CheckpointStore) -> None:
        store.save("a", phase=1, seed=42, output={})
        store.save("b", phase=2, seed=42, output={})
        store.clear()
        assert store.load_all() == []
        assert store.get_highest_completed_phase() == 0


class TestOutputForStep:
    """Convenience method to get parsed output dict."""

    def test_output_for_step(self, store: CheckpointStore) -> None:
        store.save("step", phase=1, seed=42, output={"key": "value", "nested": {"a": 1}})
        output = store.output_for_step("step")
        assert output == {"key": "value", "nested": {"a": 1}}

    def test_output_for_nonexistent(self, store: CheckpointStore) -> None:
        assert store.output_for_step("nope") is None
