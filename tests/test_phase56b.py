"""Phase 5.6B: Resume through application service — unit + integration tests.

Verifies:
  1. resume=True with no checkpoint → runs all phases normally
  2. resume=True with checkpoints → skips completed phases
  3. resume=False → clears all checkpoints, starts fresh
  4. Checkpoints saved after every phase (bible, style, story, graph, music, images, indexer, packager)
  5. _restore_checkpoints maps step_name → canonical output_key correctly
  6. _should_skip returns correct boolean
  7. _save_phase_checkpoint writes expected data to SQLite
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from src.application.models import GenerationRequest, GenerationResult
from src.job_queue import PipelineContext
from src.storage.checkpoint import CheckpointStore


# ── shared fakes ─────────────────────────────────────────────────────────────

from .test_production_wiring import (
    InstrumentedGenerateStory,
    TrackedImageGenerator,
    TrackedMusicGenerator,
    TrackedTextGenerator,
    _clear_fakes,
    _inject_fakes,
)


# ── Unit tests: helper methods ────────────────────────────────────────────────


class TestShouldSkip:
    """Unit tests for GenerateStory._should_skip()."""

    def test_skip_false_when_resume_phase_zero(self, tmp_path: Path) -> None:
        """resume_phase=0 always returns False — nothing to skip."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        from src.application.generate_story import GenerateStory
        assert not GenerateStory._should_skip("world_builder", 0, checkpoint)

    def test_skip_false_when_no_checkpoint(self, tmp_path: Path) -> None:
        """No saved checkpoint → don't skip."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        from src.application.generate_story import GenerateStory
        assert not GenerateStory._should_skip("world_builder", 2, checkpoint)

    def test_skip_true_when_checkpoint_exists(self, tmp_path: Path) -> None:
        """Saved checkpoint → skip this step."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        checkpoint.save(
            step_name="world_builder",
            output_key="bible",
            phase=1, seed=42,
            output={"world_name": "Test"},
        )
        from src.application.generate_story import GenerateStory
        assert GenerateStory._should_skip("world_builder", 2, checkpoint)

    def test_skip_false_for_different_step(self, tmp_path: Path) -> None:
        """Checkpoint for step A doesn't skip step B."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        checkpoint.save(
            step_name="world_builder",
            output_key="bible",
            phase=1, seed=42,
            output={"world_name": "Test"},
        )
        from src.application.generate_story import GenerateStory
        assert not GenerateStory._should_skip("story_writer", 2, checkpoint)


class TestRestoreCheckpoints:
    """Unit tests for GenerateStory._restore_checkpoints()."""

    def test_restore_empty_checkpoints_noop(self, tmp_path: Path) -> None:
        """Empty checkpoint store → context unchanged."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))
        from src.application.generate_story import GenerateStory
        GenerateStory._restore_checkpoints(ctx, checkpoint)
        assert ctx.outputs.get("bible") is None

    def test_restore_maps_canonical_keys(self, tmp_path: Path) -> None:
        """world_builder step → restored as ctx.outputs["bible"]."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        bible_data = {"world_name": "Restored World", "entities": {"characters": []}}
        checkpoint.save(
            step_name="world_builder",
            output_key="bible",
            phase=1, seed=42,
            output=bible_data,
        )
        story_data = {"title": "Chapter 1", "scenes": []}
        checkpoint.save(
            step_name="story_writer",
            output_key="story",
            phase=3, seed=42,
            output=story_data,
        )

        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))
        from src.application.generate_story import GenerateStory
        GenerateStory._restore_checkpoints(ctx, checkpoint)

        assert ctx.outputs.get("bible") == bible_data
        assert ctx.outputs.get("story") == story_data
        # world_builder step name should NOT be in outputs
        assert ctx.outputs.get("world_builder") is None

    def test_restore_preserves_existing_keys(self, tmp_path: Path) -> None:
        """Restoring doesn't overwrite keys not in the checkpoint."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        checkpoint.save(
            step_name="world_builder",
            output_key="bible",
            phase=1, seed=42,
            output={"world_name": "Test"},
        )
        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))
        ctx.outputs["preexisting"] = {"key": "value"}

        from src.application.generate_story import GenerateStory
        GenerateStory._restore_checkpoints(ctx, checkpoint)

        assert ctx.outputs.get("preexisting") == {"key": "value"}
        assert ctx.outputs.get("bible") == {"world_name": "Test"}

    def test_restore_skips_empty_output_key(self, tmp_path: Path) -> None:
        """Entries with empty output_key are skipped gracefully."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        checkpoint.save(
            step_name="unknown_step",
            output_key="",
            phase=1, seed=42,
            output={"data": "orphan"},
        )
        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))
        from src.application.generate_story import GenerateStory
        GenerateStory._restore_checkpoints(ctx, checkpoint)
        # Should not crash — just skip the entry with empty key
        assert ctx.outputs.get("") is None


class TestSavePhaseCheckpoint:
    """Unit tests for GenerateStory._save_phase_checkpoint()."""

    def test_saves_bible_with_canonical_key(self, tmp_path: Path) -> None:
        """After world_builder, checkpoint has output_key='bible'."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))
        ctx.outputs["bible"] = {"world_name": "Saved World"}

        from src.application.generate_story import GenerateStory
        GenerateStory._save_phase_checkpoint(
            checkpoint, "world_builder", "fp_abc123", ctx,
        )

        entry = checkpoint.load("world_builder")
        assert entry is not None
        assert entry.output_key == "bible"
        assert entry.phase == 1
        assert entry.seed == 42
        assert json.loads(entry.output_json) == {"world_name": "Saved World"}
        assert entry.run_fingerprint == "fp_abc123"

    def test_saves_all_phase_numbers_correctly(self, tmp_path: Path) -> None:
        """Each step gets its correct phase number."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        ctx = PipelineContext(run_id="test", seed=77, output_dir=str(tmp_path))

        from src.application.generate_story import GenerateStory

        # Phase 1: Bible
        ctx.outputs["bible"] = {"world_name": "P1"}
        GenerateStory._save_phase_checkpoint(checkpoint, "world_builder", "fp", ctx)
        assert checkpoint.load("world_builder").phase == 1
        # Phase 2: Style Bible
        ctx.outputs["style_bible"] = {"art_style": {}}
        GenerateStory._save_phase_checkpoint(checkpoint, "art_director", "fp", ctx)
        assert checkpoint.load("art_director").phase == 2
        # Phase 7: Packager
        ctx.outputs["packager"] = {"package_path": "/tmp/test.story"}
        GenerateStory._save_phase_checkpoint(checkpoint, "packager", "fp", ctx)
        assert checkpoint.load("packager").phase == 7

    def test_noop_when_canonical_data_not_in_context(self, tmp_path: Path) -> None:
        """If context.outputs lacks the canonical key, checkpoint is not saved."""
        checkpoint = CheckpointStore(str(tmp_path / "checkpoint.db"))
        ctx = PipelineContext(run_id="test", seed=42, output_dir=str(tmp_path))
        # No bible or world_builder in context

        from src.application.generate_story import GenerateStory
        GenerateStory._save_phase_checkpoint(
            checkpoint, "world_builder", "fp", ctx,
        )

        assert checkpoint.load("world_builder") is None


# ── Integration tests: resume through GenerateStory ──────────────────────────


class TestResumeThroughGenerateStory:
    """End-to-end resume tests through the full GenerateStory service."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch: Any, tmp_path: Path) -> None:
        import os
        project_root = Path(__file__).resolve().parent.parent
        schemas_dir = str(project_root / "schemas")
        monkeypatch.setenv("STORYTELLER_SCHEMAS_DIR", schemas_dir)
        if not Path(schemas_dir).exists():
            pytest.skip("Schemas directory not found")

    def setup_method(self) -> None:
        _clear_fakes()

    def teardown_method(self) -> None:
        _clear_fakes()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_resume_false_clears_checkpoints(self, tmp_path: Path) -> None:
        """resume=False starts fresh — existing checkpoints are deleted."""
        output_dir = str(tmp_path / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Pre-seed a checkpoint (simulating a previous run)
        checkpoint = CheckpointStore(str(Path(output_dir) / "checkpoint.db"))
        checkpoint.save(
            step_name="world_builder",
            output_key="bible",
            phase=1, seed=42,
            output={"world_name": "Old Run"},
        )

        # Verify checkpoint exists before the run
        assert checkpoint.load("world_builder") is not None

        # Run with resume=False
        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=99,
            title="Fresh Start",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=False,
        )

        result = await service.execute(request)
        assert result.errors == [], f"Errors: {result.errors}"

        # Checkpoint should be overwritten with NEW data (seed=99)
        entry = checkpoint.load("world_builder")
        assert entry is not None
        data = json.loads(entry.output_json)
        assert data["world_name"] != "Old Run"
        # The new bible should have seed=99 World
        assert "Wiring Test World" in data.get("world_name", "")

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_resume_true_skips_completed_text_phases(self, tmp_path: Path) -> None:
        """resume=True with existing checkpoints skips the text phase."""
        output_dir = str(tmp_path / "output")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # ── Run A: Full pipeline, save checkpoints ─────────────────
        text_a = TrackedTextGenerator()
        image_a = TrackedImageGenerator()
        music_a = TrackedMusicGenerator()
        _inject_fakes(text_a, image_a, music_a)

        service = InstrumentedGenerateStory()
        request_a = GenerationRequest(
            seed=42,
            title="Resume Skip Test",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=True,
        )

        result_a = await service.execute(request_a)
        assert result_a.errors == [], f"Run A errors: {result_a.errors}"
        text_calls_a = text_a.call_count
        assert text_calls_a >= 6, f"Expected >=6 text calls, got {text_calls_a}"

        # ── Run B: Resume — text phases should be skipped ─────────
        _clear_fakes()
        text_b = TrackedTextGenerator()
        image_b = TrackedImageGenerator()
        music_b = TrackedMusicGenerator()
        _inject_fakes(text_b, image_b, music_b)

        # Delete images/midi to force regeneration but keep checkpoints
        for d in ["images", "midi", "thumbnails"]:
            dp = Path(output_dir) / d
            if dp.exists():
                import shutil
                shutil.rmtree(dp)

        # Delete old .story
        old_story = Path(result_a.package_path)
        if old_story.exists():
            old_story.unlink()

        service_b = InstrumentedGenerateStory()
        request_b = GenerationRequest(
            seed=42,
            title="Resume Skip Test",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=True,
        )

        result_b = await service_b.execute(request_b)
        assert result_b.errors == [], f"Run B errors: {result_b.errors}"

        # Text calls should be significantly fewer on resume
        # (only music text generation, no bible/style/story/graph)
        assert text_b.call_count < text_calls_a, (
            f"Expected fewer text calls on resume, but got "
            f"{text_b.call_count} >= {text_calls_a}"
        )

        # Checkpoints should still be valid
        checkpoint = CheckpointStore(str(Path(output_dir) / "checkpoint.db"))
        assert checkpoint.load("world_builder") is not None
        assert checkpoint.load("story_writer") is not None
        assert checkpoint.load("game_designer") is not None

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_resume_true_no_checkpoints_runs_full(self, tmp_path: Path) -> None:
        """resume=True with NO checkpoints runs the full pipeline (normal first run)."""
        output_dir = str(tmp_path / "output")

        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42,
            title="First Run",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=True,  # Should behave like normal first run
        )

        result = await service.execute(request)
        assert result.errors == [], f"Errors: {result.errors}"
        assert result.package_path, "No package produced"
        assert Path(result.package_path).exists()

        # All checkpoints should be saved by the end
        checkpoint = CheckpointStore(str(Path(output_dir) / "checkpoint.db"))
        expected_steps = [
            "world_builder", "art_director", "story_writer",
            "game_designer", "music_generator", "image_generator",
            "indexer", "packager",
        ]
        for step in expected_steps:
            assert checkpoint.load(step) is not None, f"Missing checkpoint: {step}"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_checkpoints_saved_after_every_phase(self, tmp_path: Path) -> None:
        """After a full run, all 8 steps have checkpoints with correct phases."""
        output_dir = str(tmp_path / "output")

        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=77,
            title="Checkpoint Coverage",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
        )

        result = await service.execute(request)
        assert result.errors == [], f"Errors: {result.errors}"

        checkpoint = CheckpointStore(str(Path(output_dir) / "checkpoint.db"))
        entries = checkpoint.load_all()

        # Verify all 8 steps
        step_names = {e.step_name for e in entries}
        for expected in [
            "world_builder", "art_director", "story_writer",
            "game_designer", "music_generator", "image_generator",
            "indexer", "packager",
        ]:
            assert expected in step_names, f"Missing {expected} in checkpoints"

        # Verify phase numbers are correct
        phase_map = {e.step_name: e.phase for e in entries}
        assert phase_map["world_builder"] == 1
        assert phase_map["art_director"] == 2
        assert phase_map["story_writer"] == 3
        assert phase_map["game_designer"] == 4
        assert phase_map["music_generator"] in (5, 5)  # Phase 5 (parallel)
        assert phase_map["image_generator"] in (5, 5)  # Phase 5 (parallel)
        assert phase_map["indexer"] == 6
        assert phase_map["packager"] == 7

        # Verify canonical output_keys
        output_key_map = {e.step_name: e.output_key for e in entries}
        assert output_key_map["world_builder"] == "bible"
        assert output_key_map["art_director"] == "style_bible"
        assert output_key_map["story_writer"] == "story"
        assert output_key_map["game_designer"] == "graph"
        assert output_key_map["indexer"] == "gm_index"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_resume_preserves_package_acceptance(self, tmp_path: Path) -> None:
        """Resumed run produces a valid package (PackageAcceptance passes)."""
        output_dir = str(tmp_path / "output")

        # ── Run A ──────────────────────────────────────────────────
        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42,
            title="Acceptance Test",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
            resume=True,
        )
        result = await service.execute(request)
        assert result.errors == [], f"Errors: {result.errors}"

        # ── Run B: Resume (delete images/midi, keep checkpoints) ──
        for d in ["images", "midi", "thumbnails"]:
            dp = Path(output_dir) / d
            if dp.exists():
                import shutil
                shutil.rmtree(dp)
        old_story = Path(result.package_path)
        if old_story.exists():
            old_story.unlink()

        _clear_fakes()
        text2 = TrackedTextGenerator()
        image2 = TrackedImageGenerator()
        music2 = TrackedMusicGenerator()
        _inject_fakes(text2, image2, music2)

        result2 = await service.execute(request)
        assert result2.errors == [], f"Resume errors: {result2.errors}"
        assert result2.package_path, "No package on resume"

        # Package acceptance passes
        from src.storage.package_acceptance import PackageAcceptance
        gate = PackageAcceptance()
        acceptance = gate.validate(result2.package_path)
        assert acceptance.accepted, (
            f"Package acceptance failed on resume:\n{acceptance.format_issues()}"
        )
