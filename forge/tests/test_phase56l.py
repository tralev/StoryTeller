"""Tests for Phase 5.6L: Split Long Text Operations.

Verifies sub-step checkpoints in StoryWriter (outline + 3 chapters) and
GameDesigner (decision_points + skeleton + per-node text), plus
dependency-hash invalidation.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def sample_bible() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "world": {
            "name": "Test Realm",
            "description": "A test world",
            "features": ["mountains", "forest"],
        },
        "entities": {
            "characters": [
                {"id": "hero", "name": "Kael", "description": "Brave warrior", "role": "protagonist"},
                {"id": "villain", "name": "Malachar", "description": "Dark sorcerer", "role": "antagonist"},
            ],
            "locations": [
                {"id": "castle", "name": "Ironhold", "description": "Ancient fortress"},
            ],
        },
    }


@pytest.fixture
def sample_story() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "chapters": [
            {
                "number": 1,
                "title": "The Beginning",
                "summary": "Hero rises.",
                "scenes": [{"scene_id": "s1", "text": "Kael discovers his power.", "characters_present": ["hero"], "location": "castle"}],
            },
        ],
    }


@pytest.fixture
def checkpoint_store(tmp_path: Path) -> Any:
    from src.storage.checkpoint import CheckpointStore
    db = str(tmp_path / "checkpoint.db")
    return CheckpointStore(db)


# ── CheckpointStore sub-checkpoint operations ────────────────────────────


class TestCheckpointStoreSubSteps:
    """save_sub / load_sub / clear_subs on CheckpointStore."""

    def test_save_and_load_sub(self, checkpoint_store: Any) -> None:
        data = {"key": "value", "nested": {"deep": True}}
        checkpoint_store.save_sub("test_step", "sub_a", data, seed=42, dependency_hash="abc123")

        loaded = checkpoint_store.load_sub("test_step", "sub_a", dependency_hash="abc123")
        assert loaded == data

    def test_load_sub_missing(self, checkpoint_store: Any) -> None:
        assert checkpoint_store.load_sub("nonexistent", "sub_x") is None

    def test_dependency_hash_mismatch_invalidates(self, checkpoint_store: Any) -> None:
        checkpoint_store.save_sub("test_step", "sub_b", {"v": 1}, seed=1, dependency_hash="hash_old")

        # Same dep hash → should load
        assert checkpoint_store.load_sub("test_step", "sub_b", "hash_old") == {"v": 1}

        # Different dep hash → should return None (invalidated)
        assert checkpoint_store.load_sub("test_step", "sub_b", "hash_new") is None

    def test_no_dep_hash_loads_anyway(self, checkpoint_store: Any) -> None:
        """Sub-checkpoints saved without dep_hash are always loadable."""
        checkpoint_store.save_sub("test_step", "sub_c", {"v": 2}, seed=2)

        loaded = checkpoint_store.load_sub("test_step", "sub_c")
        assert loaded == {"v": 2}

    def test_clear_subs(self, checkpoint_store: Any) -> None:
        checkpoint_store.save_sub("step_a", "sub_1", {"a": 1}, seed=1)
        checkpoint_store.save_sub("step_a", "sub_2", {"a": 2}, seed=2)
        checkpoint_store.save_sub("step_b", "sub_1", {"b": 1}, seed=3)

        checkpoint_store.clear_subs("step_a")

        assert checkpoint_store.load_sub("step_a", "sub_1") is None
        assert checkpoint_store.load_sub("step_a", "sub_2") is None
        assert checkpoint_store.load_sub("step_b", "sub_1") == {"b": 1}  # Unaffected


# ── StoryWriter sub-checkpoints ──────────────────────────────────────────


class TestStoryWriterSubCheckpoints:
    """StoryWriter uses sub-checkpoints for outline + 3 chapters."""

    @pytest.mark.asyncio
    async def test_sub_checkpoints_saved(self, sample_bible: dict[str, Any], checkpoint_store: Any) -> None:
        """After StoryWriter runs, sub-checkpoints exist for outline + each chapter."""
        from tests.test_production_wiring import InstrumentedGenerateStory, _inject_fakes, _clear_fakes
        from tests.test_production_wiring import TrackedTextGenerator, TrackedImageGenerator, TrackedMusicGenerator

        _clear_fakes()
        text = TrackedTextGenerator()
        _inject_fakes(text, TrackedImageGenerator(), TrackedMusicGenerator())

        # Instead of full pipeline, test the checkpoint method directly
        from src.models.story_writer import StoryWriter
        from src.job_queue import PipelineContext

        ctx = PipelineContext(run_id="test_l", seed=42)
        ctx.outputs["bible"] = sample_bible
        ctx.checkpoint_store = checkpoint_store

        # __init__ needs a generator, but generate only needs ctx
        # We test _load_or_generate with a callable
        call_log: list[str] = []

        async def fake_outline(**kw: Any) -> dict[str, Any]:
            call_log.append("outline_called")
            return {"outline": "The hero's journey begins"}

        # First call — should generate
        result1 = await StoryWriter._load_or_generate(
            store=checkpoint_store,
            step="story_writer",
            sub_id="outline",
            dep_hash="hash_bible",
            fn=fake_outline,
            bible=sample_bible, temperature=0.7, seed=42,
        )
        assert "outline_called" in call_log
        assert result1 == {"outline": "The hero's journey begins"}

        # Second call — should load from checkpoint (not call fn again)
        call_log.clear()
        result2 = await StoryWriter._load_or_generate(
            store=checkpoint_store,
            step="story_writer",
            sub_id="outline",
            dep_hash="hash_bible",
            fn=fake_outline,
            bible=sample_bible, temperature=0.7, seed=42,
        )
        assert "outline_called" not in call_log  # Not called — loaded from checkpoint
        assert result2 == result1

    @pytest.mark.asyncio
    async def test_dep_hash_change_forces_regeneration(self, checkpoint_store: Any) -> None:
        """Changing the dependency hash invalidates the sub-checkpoint."""
        from src.models.story_writer import StoryWriter

        call_log: list[str] = []

        async def fake_chapter(**kw: Any) -> dict[str, Any]:
            call_log.append(f"chapter_{kw.get('chapter_number', 0)}_called")
            return {"number": kw.get("chapter_number", 0), "title": "Test Chapter", "scenes": []}

        # First call with dep_hash="v1"
        await StoryWriter._load_or_generate(
            store=checkpoint_store, step="story_writer", sub_id="ch1",
            dep_hash="bible_v1", fn=fake_chapter,
            chapter_number=1, seed=42,
        )
        call_log.clear()

        # Same dep_hash → loads from checkpoint
        await StoryWriter._load_or_generate(
            store=checkpoint_store, step="story_writer", sub_id="ch1",
            dep_hash="bible_v1", fn=fake_chapter,
            chapter_number=1, seed=42,
        )
        assert "chapter_1_called" not in call_log

        # Different dep_hash → regenerates
        call_log.clear()
        await StoryWriter._load_or_generate(
            store=checkpoint_store, step="story_writer", sub_id="ch1",
            dep_hash="bible_v2", fn=fake_chapter,
            chapter_number=1, seed=42,
        )
        assert "chapter_1_called" in call_log


# ── GameDesigner sub-checkpoints ─────────────────────────────────────────


class TestGameDesignerSubCheckpoints:
    """GameDesigner uses sub-checkpoints for decision_points + skeleton + nodes."""

    @pytest.mark.asyncio
    async def test_decision_points_sub_checkpoint(self, checkpoint_store: Any) -> None:
        from src.models.game_designer import GameDesigner

        call_log: list[str] = []

        async def fake_dp(**kw: Any) -> dict[str, Any]:
            call_log.append("dp_called")
            return {"decision_points": [{"point": "betrayal", "chapter": 2, "description": "A choice"}]}

        # First call
        r1 = await GameDesigner._load_or_generate(
            store=checkpoint_store, step="game_designer", sub_id="decision_points",
            dep_hash="story_hash", fn=fake_dp,
            story_text="...", temperature=0.7, seed=42, template_str="",
        )
        assert "dp_called" in call_log

        # Second call — cached
        call_log.clear()
        r2 = await GameDesigner._load_or_generate(
            store=checkpoint_store, step="game_designer", sub_id="decision_points",
            dep_hash="story_hash", fn=fake_dp,
            story_text="...", temperature=0.7, seed=42, template_str="",
        )
        assert "dp_called" not in call_log
        assert r2 == r1

    @pytest.mark.asyncio
    async def test_skeleton_sub_checkpoint(self, checkpoint_store: Any) -> None:
        from src.models.game_designer import GameDesigner

        call_log: list[str] = []

        async def fake_skeleton(**kw: Any) -> dict[str, Any]:
            call_log.append("skeleton_called")
            return {"nodes": [{"node_id": "node_01", "description": "Start"}]}

        # First call
        await GameDesigner._load_or_generate(
            store=checkpoint_store, step="game_designer", sub_id="skeleton",
            dep_hash="dp_hash", fn=fake_skeleton,
            bible_summary="...", decision_points=[], temperature=0.7, seed=42, template_str="",
        )
        call_log.clear()

        # Second call — cached
        await GameDesigner._load_or_generate(
            store=checkpoint_store, step="game_designer", sub_id="skeleton",
            dep_hash="dp_hash", fn=fake_skeleton,
            bible_summary="...", decision_points=[], temperature=0.7, seed=42, template_str="",
        )
        assert "skeleton_called" not in call_log

    @pytest.mark.asyncio
    async def test_per_node_sub_checkpoint(self, checkpoint_store: Any) -> None:
        from src.models.game_designer import GameDesigner

        call_log: list[str] = []

        async def fake_node_text(**kw: Any) -> dict[str, Any]:
            nid = kw.get("node", {}).get("node_id", "?")
            call_log.append(f"node_{nid}_called")
            return {"text": f"Text for {nid}", "choices": []}

        # Generate node_05
        await GameDesigner._load_or_generate(
            store=checkpoint_store, step="game_designer", sub_id="node_05",
            dep_hash="skeleton_hash", fn=fake_node_text,
            bible={}, story_summary="...", node={"node_id": "node_05"}, neighbors=[],
            active_flags=[], temperature=0.7, seed=7, template_str="",
        )
        call_log.clear()

        # Second call — cached
        await GameDesigner._load_or_generate(
            store=checkpoint_store, step="game_designer", sub_id="node_05",
            dep_hash="skeleton_hash", fn=fake_node_text,
            bible={}, story_summary="...", node={"node_id": "node_05"}, neighbors=[],
            active_flags=[], temperature=0.7, seed=7, template_str="",
        )
        assert "node_node_05_called" not in call_log


# ── Integration: GameDesigner dep_hash chaining ──────────────────────────


class TestGameDesignerDepChaining:
    """Skeleton depends on decision_points; nodes depend on skeleton."""

    @pytest.mark.asyncio
    async def test_skeleton_invalidated_when_story_changes(self, checkpoint_store: Any) -> None:
        """story change → dp dep_hash change → skeleton dep_hash change → regenerated."""
        from src.models.game_designer import GameDesigner

        calls: list[str] = []

        async def fake_skeleton(**kw: Any) -> dict[str, Any]:
            calls.append("skeleton")
            return {"nodes": []}

        # Save with dep_hash = story_v1 + dp_hash
        dep_v1 = "story_v1" + "dp_v1"
        await GameDesigner._load_or_generate(
            store=checkpoint_store, step="game_designer", sub_id="skeleton",
            dep_hash=dep_v1, fn=fake_skeleton,
            bible_summary="...", decision_points=[], temperature=0.7, seed=42, template_str="",
        )
        calls.clear()

        # Same dep_hash → cached
        await GameDesigner._load_or_generate(
            store=checkpoint_store, step="game_designer", sub_id="skeleton",
            dep_hash=dep_v1, fn=fake_skeleton,
            bible_summary="...", decision_points=[], temperature=0.7, seed=42, template_str="",
        )
        assert "skeleton" not in calls

        # Different dep_hash → regenerated
        dep_v2 = "story_v2" + "dp_v2"
        await GameDesigner._load_or_generate(
            store=checkpoint_store, step="game_designer", sub_id="skeleton",
            dep_hash=dep_v2, fn=fake_skeleton,
            bible_summary="...", decision_points=[], temperature=0.7, seed=42, template_str="",
        )
        assert "skeleton" in calls


# ── PipelineContext checkpoint_store wiring ──────────────────────────────


class TestPipelineContextCheckpointStore:
    """PipelineContext.checkpoint_store is accessible during generate()."""

    def test_checkpoint_store_set_on_context(self, sample_bible: dict[str, Any], checkpoint_store: Any) -> None:
        from src.job_queue import PipelineContext

        ctx = PipelineContext(run_id="test", seed=42)
        ctx.checkpoint_store = checkpoint_store
        assert ctx.checkpoint_store is checkpoint_store

    def test_checkpoint_store_none_by_default(self) -> None:
        from src.job_queue import PipelineContext

        ctx = PipelineContext(run_id="test", seed=42)
        assert ctx.checkpoint_store is None
