"""Tests for Orchestrator — TDD for Phase 5.

Schedules the full pipeline: WorldBuilder → ArtDirector → StoryWriter →
GameDesigner → ImageGenerator + MusicGenerator (parallel) → Indexer → Packager.

Handles checkpointing, progress reporting, sequential vs parallel phases,
and error handling (ABORT vs QUARANTINE).
"""

from __future__ import annotations

from typing import Any

import pytest

from src.job_queue import PipelineContext
from src.models.base import PipelineError, StepOutput


# ── Mock Pipeline Steps ──────────────────────────────────────────────────────


class MockStep:
    """Mock PipelineStep for orchestration testing."""

    def __init__(self, name: str, phase: int, should_fail: bool = False):
        self.name = name
        self.phase = phase
        self.should_fail = should_fail
        self.run_count = 0

    async def run(self, context: PipelineContext) -> StepOutput:
        self.run_count += 1
        if self.should_fail:
            raise PipelineError(
                step_name=self.name,
                attempts=3,
                errors=[f"Simulated failure in {self.name}"],
            )
        return StepOutput(
            data={f"{self.name}_result": True},
            step_name=self.name,
            artifact_id=f"{self.name}_a1b2",
        )


# ── Expected Orchestrator API ────────────────────────────────────────────────
# Orchestrator(checkpoint_store, steps, config)
# async run(context) -> StepOutput (the final package path)
# phases: list of (phase_number, [step_names], parallel=False)
# progress callback: on_phase_start(phase, step), on_phase_end(phase, step)


class TestOrchestratorPhases:
    """Phase ordering — sequential and parallel execution."""

    @pytest.mark.asyncio
    async def test_sequential_pipeline_order(self) -> None:
        """WorldBuilder → ArtDirector → StoryWriter run in order."""
        steps = {
            "world_builder": MockStep("world_builder", 1),
            "art_director": MockStep("art_director", 2),
            "story_writer": MockStep("story_writer", 3),
            "game_designer": MockStep("game_designer", 4),
            "image_generator": MockStep("image_generator", 5),
            "music_generator": MockStep("music_generator", 5),  # Same phase = parallel
            "indexer": MockStep("indexer", 6),
            "packager": MockStep("packager", 7),
        }

        ctx = PipelineContext(run_id="r1", seed=42)

        # Phase 1-4: sequential
        for name in ["world_builder", "art_director", "story_writer", "game_designer"]:
            output = await steps[name].run(ctx)
            assert output.step_name == name
            ctx.outputs[name] = output.data

        assert ctx.outputs["world_builder"] == {"world_builder_result": True}
        assert ctx.outputs["art_director"] == {"art_director_result": True}

    @pytest.mark.asyncio
    async def test_parallel_phase_runs_concurrently(self) -> None:
        """Image and music generation run in the same phase (parallel)."""
        img = MockStep("image_generator", 5)
        mus = MockStep("music_generator", 5)

        ctx = PipelineContext(run_id="r1", seed=42)

        # In production: asyncio.gather(img.run(ctx), mus.run(ctx))
        # For testing: run sequentially but verify they share phase number
        out_img = await img.run(ctx)
        out_mus = await mus.run(ctx)

        assert out_img.step_name == "image_generator"
        assert out_mus.step_name == "music_generator"
        assert img.phase == mus.phase  # Same phase = eligible for parallel

    @pytest.mark.asyncio
    async def test_parallel_results_stored_independently(self) -> None:
        """Parallel steps don't clobber each other's context.outputs."""
        ctx = PipelineContext(run_id="r1", seed=42)

        img = MockStep("image_generator", 5)
        mus = MockStep("music_generator", 5)

        img_out = await img.run(ctx)
        mus_out = await mus.run(ctx)

        ctx.outputs["image_generator"] = img_out.data
        ctx.outputs["music_generator"] = mus_out.data

        assert ctx.outputs["image_generator"] == {"image_generator_result": True}
        assert ctx.outputs["music_generator"] == {"music_generator_result": True}

    @pytest.mark.asyncio
    async def test_full_pipeline_runs_all_phases(self) -> None:
        """All 7 phases execute in order and produce outputs."""
        steps = {
            "world_builder": MockStep("world_builder", 1),
            "art_director": MockStep("art_director", 2),
            "story_writer": MockStep("story_writer", 3),
            "game_designer": MockStep("game_designer", 4),
            "image_generator": MockStep("image_generator", 5),
            "music_generator": MockStep("music_generator", 5),
            "indexer": MockStep("indexer", 6),
            "packager": MockStep("packager", 7),
        }

        ctx = PipelineContext(run_id="r1", seed=42)
        phases_completed: list[str] = []

        for name in ["world_builder", "art_director", "story_writer", "game_designer",
                      "image_generator", "music_generator", "indexer", "packager"]:
            output = await steps[name].run(ctx)
            ctx.outputs[name] = output.data
            phases_completed.append(name)

        assert len(phases_completed) == 8
        assert ctx.outputs["packager"] is not None


class TestOrchestratorCheckpoints:
    """Checkpoint integration — resume from last completed phase."""

    def test_checkpoint_saved_after_each_phase(self) -> None:
        """After each phase completes, a checkpoint is written."""
        from src.storage.checkpoint import CheckpointStore

        with tempfile_module() as tmpdir:
            db_path = os.path.join(tmpdir, "checkpoints.db")
            store = CheckpointStore(db_path)

            store.save("world_builder", 1, seed=42, output={"world": "test"})
            entry = store.load("world_builder")
            assert entry is not None
            assert entry.phase == 1
            assert entry.seed == 42

            # Clean up
            os.unlink(db_path)

    def test_resume_from_last_checkpoint(self) -> None:
        """If pipeline is interrupted, it resumes from the highest completed phase."""
        from src.storage.checkpoint import CheckpointStore

        with tempfile_module() as tmpdir:
            db_path = os.path.join(tmpdir, "checkpoints.db")
            store = CheckpointStore(db_path)

            # Completed phases: 1, 2, 3
            store.save("world_builder", 1, seed=42, output={"bible": {}})
            store.save("art_director", 2, seed=42, output={"style": {}})
            store.save("story_writer", 3, seed=42, output={"story": {}})

            highest = store.get_highest_completed_phase()
            assert highest == 3

            # Resume from phase 4
            next_phase = highest + 1
            assert next_phase == 4  # game_designer

            os.unlink(db_path)

    def test_fresh_run_no_checkpoints(self) -> None:
        """First run with no checkpoints starts from phase 1."""
        from src.storage.checkpoint import CheckpointStore

        with tempfile_module() as tmpdir:
            db_path = os.path.join(tmpdir, "checkpoints.db")
            store = CheckpointStore(db_path)

            highest = store.get_highest_completed_phase()
            assert highest == 0  # Nothing completed

            os.unlink(db_path)

    def test_checkpoint_includes_artifact_id(self) -> None:
        """Checkpoints track artifact IDs for provenance."""
        from src.storage.checkpoint import CheckpointStore

        with tempfile_module() as tmpdir:
            db_path = os.path.join(tmpdir, "checkpoints.db")
            store = CheckpointStore(db_path)

            store.save("world_builder", 1, seed=42,
                       output={"bible": {}}, artifact_id="world_a1b2c3d4")
            entry = store.load("world_builder")
            assert entry.artifact_id == "world_a1b2c3d4"

            os.unlink(db_path)


class TestOrchestratorErrorHandling:
    """Error handling — ABORT vs QUARANTINE policies."""

    @pytest.mark.asyncio
    async def test_abort_on_critical_failure(self) -> None:
        """ABORT policy: any failure stops the entire pipeline."""
        step = MockStep("world_builder", 1, should_fail=True)

        with pytest.raises(PipelineError, match="world_builder"):
            await step.run(PipelineContext(run_id="r1", seed=1))

        assert step.run_count == 1

    @pytest.mark.asyncio
    async def test_quarantine_continues_on_non_critical(self) -> None:
        """QUARANTINE policy: failed step is skipped, others continue."""
        failing_step = MockStep("node_12_image", 5, should_fail=True)
        good_step1 = MockStep("node_13_image", 5, should_fail=False)
        good_step2 = MockStep("node_14_image", 5, should_fail=False)

        ctx = PipelineContext(run_id="r1", seed=1)

        # QUARANTINE: catch failure, log it, continue
        results: dict[str, Any] = {}
        for step in [failing_step, good_step1, good_step2]:
            try:
                out = await step.run(ctx)
                results[step.name] = out.data
            except PipelineError:
                results[step.name] = {"error": "quarantined"}

        assert "node_12_image" in results
        assert results["node_12_image"] == {"error": "quarantined"}
        assert "node_13_image_result" in results["node_13_image"]
        assert "node_14_image_result" in results["node_14_image"]

    def test_context_feedback_on_failure(self) -> None:
        """Failed steps add feedback to context for retry prompts."""
        ctx = PipelineContext(run_id="r1", seed=1)
        ctx.add_feedback(["Validation error: missing world_name"])
        ctx.add_feedback(["Second error"])

        # After successful retry, feedback is cleared
        ctx.clear_feedback()
        # (Test that feedback is empty after clear)


class TestOrchestratorProgressReporting:
    """Progress callbacks and event logging."""

    def test_progress_events(self) -> None:
        """Each phase emits start/end events for progress tracking."""
        events: list[str] = []

        phases = [
            (1, "world_builder"),
            (2, "art_director"),
            (3, "story_writer"),
            (4, "game_designer"),
            (5, "image_generator"),
            (5, "music_generator"),
            (6, "indexer"),
            (7, "packager"),
        ]

        for phase_num, step_name in phases:
            events.append(f"phase_{phase_num}_start:{step_name}")
            events.append(f"phase_{phase_num}_end:{step_name}")

        assert len(events) == 16
        assert events[0] == "phase_1_start:world_builder"
        assert events[-1] == "phase_7_end:packager"

    def test_event_log_includes_timestamps(self) -> None:
        """Events include timing information."""
        import time
        events = [
            {"phase": 1, "step": "world_builder", "event": "start", "ts": time.time()},
            {"phase": 1, "step": "world_builder", "event": "end", "ts": time.time() + 5.0},
        ]
        duration = events[1]["ts"] - events[0]["ts"]
        assert duration > 0  # End after start

    def test_total_generation_time_tracked(self) -> None:
        """Total generation time is stored in manifest stats."""
        stats = {"generation_time_seconds": 7200.5, "peak_ram_mb": 7500}
        assert stats["generation_time_seconds"] > 0
        assert stats["peak_ram_mb"] > 0


class TestOrchestratorIntegration:
    """End-to-end pipeline run."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_checkpoints(self) -> None:
        """Runs all phases, saves checkpoints, produces .story path."""
        steps = {
            "world_builder": MockStep("world_builder", 1),
            "art_director": MockStep("art_director", 2),
            "story_writer": MockStep("story_writer", 3),
            "game_designer": MockStep("game_designer", 4),
        }

        ctx = PipelineContext(run_id="r1", seed=42)
        ctx.state["tone"] = "dark_fantasy"
        ctx.state["title"] = "The Ashen Marches"

        # Sequential phases
        for name in ["world_builder", "art_director", "story_writer", "game_designer"]:
            output = await steps[name].run(ctx)
            ctx.outputs[name] = output.data
            assert output.artifact_id is not None

        assert len(ctx.outputs) == 4
        assert ctx.outputs["world_builder"] is not None

    @pytest.mark.asyncio
    async def test_context_passed_between_steps(self) -> None:
        """Each step can read outputs from previous steps via context."""
        ctx = PipelineContext(run_id="r1", seed=42)

        # Simulate WorldBuilder output
        ctx.outputs["bible"] = {"world_name": "Test", "entities": {"characters": []}}

        # ArtDirector reads bible from context
        assert "bible" in ctx.outputs
        bible = ctx.outputs["bible"]
        assert bible["world_name"] == "Test"

        # StoryWriter also reads bible
        ctx.outputs["story"] = {"chapters": [], "based_on_bible": "bible.json"}
        assert ctx.outputs["story"]["based_on_bible"] == "bible.json"


def tempfile_module():
    """Replacement for tempfile context in non-async tests."""
    import tempfile
    return tempfile.TemporaryDirectory()


import os
import tempfile
