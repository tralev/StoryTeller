"""Tests for Phase 5.6H: Declarative Pipeline Plan.

Covers StepSpec construction, PipelinePlan validation, standard() factory,
group_by_model_role(), and plan-driven execution through GenerateStory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.pipeline.plan import PipelinePlan, PlanValidationError, StepSpec


# ── StepSpec unit ─────────────────────────────────────────────────────


class TestStepSpec:
    """StepSpec construction and validation."""

    def test_minimal_spec(self) -> None:
        s = StepSpec(id="test", output_key="out")
        assert s.id == "test"
        assert s.output_key == "out"
        assert s.requires == ()
        assert s.model_role is None
        assert s.failure_policy == "abort"
        assert s.checkpoint is True

    def test_full_spec(self) -> None:
        s = StepSpec(
            id="game_designer",
            output_key="graph",
            requires=("bible", "story"),
            model_role="text",
            validation="graph",
            failure_policy="abort",
            description="Convert story into branching CYOA graph",
        )
        assert s.id == "game_designer"
        assert s.output_key == "graph"
        assert s.requires == ("bible", "story")
        assert s.model_role == "text"
        assert s.validation == "graph"
        assert s.failure_policy == "abort"
        assert s.description == "Convert story into branching CYOA graph"

    def test_frozen(self) -> None:
        s = StepSpec(id="x", output_key="y")
        with pytest.raises(Exception):
            s.id = "new"

    def test_empty_id_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            StepSpec(id="", output_key="out")

    def test_empty_output_key_raises(self) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            StepSpec(id="x", output_key="")

    def test_bad_model_role_raises(self) -> None:
        with pytest.raises(ValueError, match="model_role"):
            StepSpec(id="x", output_key="y", model_role="bad_role")

    def test_valid_model_roles(self) -> None:
        for role in ("text", "image", "music", None):
            s = StepSpec(id="x", output_key="y", model_role=role)
            assert s.model_role == role

    def test_bad_failure_policy_raises(self) -> None:
        with pytest.raises(ValueError, match="failure_policy"):
            StepSpec(id="x", output_key="y", failure_policy="retry")


# ── PipelinePlan validation ──────────────────────────────────────────


class TestPlanValidation:
    """PipelinePlan.validate() and error detection."""

    def test_empty_plan_valid(self) -> None:
        plan = PipelinePlan()
        plan.validate()  # No error

    def test_standard_plan_valid(self) -> None:
        plan = PipelinePlan.standard()
        plan.validate()  # No error

    def test_duplicate_step_id(self) -> None:
        plan = PipelinePlan(steps=[
            StepSpec(id="world_builder", output_key="bible"),
            StepSpec(id="world_builder", output_key="bible2"),
        ])
        with pytest.raises(PlanValidationError, match="Duplicate step ID"):
            plan.validate()

    def test_duplicate_output_key(self) -> None:
        plan = PipelinePlan(steps=[
            StepSpec(id="a", output_key="bible"),
            StepSpec(id="b", output_key="bible"),
        ])
        with pytest.raises(PlanValidationError, match="Duplicate output key"):
            plan.validate()

    def test_missing_dependency(self) -> None:
        plan = PipelinePlan(steps=[
            StepSpec(id="a", output_key="bible", requires=("story",)),
        ])
        with pytest.raises(PlanValidationError, match="requires 'story'"):
            plan.validate()

    def test_self_loop(self) -> None:
        plan = PipelinePlan(steps=[
            StepSpec(id="a", output_key="bible", requires=("bible",)),
        ])
        with pytest.raises(PlanValidationError, match="self-loop"):
            plan.validate()

    def test_dependencies_in_order(self) -> None:
        plan = PipelinePlan(steps=[
            StepSpec(id="a", output_key="bible"),
            StepSpec(id="b", output_key="story", requires=("bible",)),
            StepSpec(id="c", output_key="graph", requires=("bible", "story")),
        ])
        plan.validate()  # No error

    def test_dependency_not_yet_available(self) -> None:
        plan = PipelinePlan(steps=[
            StepSpec(id="a", output_key="bible", requires=("graph",)),
            StepSpec(id="b", output_key="graph"),
        ])
        with pytest.raises(PlanValidationError, match="requires 'graph'"):
            plan.validate()


# ── PipelinePlan.standard() ──────────────────────────────────────────


class TestStandardPlan:
    """The standard() factory produces a valid, complete plan."""

    def test_eight_steps(self) -> None:
        plan = PipelinePlan.standard()
        assert len(plan) == 8

    def test_first_step_is_world_builder(self) -> None:
        plan = PipelinePlan.standard()
        assert plan[0].id == "world_builder"
        assert plan[0].output_key == "bible"
        assert plan[0].model_role == "text"
        assert plan[0].requires == ()

    def test_last_step_is_packager(self) -> None:
        plan = PipelinePlan.standard()
        assert plan[-1].id == "packager"
        assert plan[-1].output_key == "package_path"
        assert plan[-1].model_role is None
        assert "bible" in plan[-1].requires
        assert "graph" in plan[-1].requires

    def test_all_ids_unique(self) -> None:
        plan = PipelinePlan.standard()
        ids = [s.id for s in plan]
        assert len(ids) == len(set(ids))

    def test_all_output_keys_unique(self) -> None:
        plan = PipelinePlan.standard()
        keys = [s.output_key for s in plan]
        assert len(keys) == len(set(keys))

    def test_standard_validates(self) -> None:
        plan = PipelinePlan.standard()
        plan.validate()  # No PlanValidationError

    def test_step_ids_method(self) -> None:
        plan = PipelinePlan.standard()
        ids = plan.step_ids()
        assert ids == [
            "world_builder", "art_director", "story_writer",
            "game_designer", "music_generator", "image_generator",
            "indexer", "packager",
        ]

    def test_output_keys_method(self) -> None:
        plan = PipelinePlan.standard()
        keys = plan.output_keys()
        assert keys == [
            "bible", "style_bible", "story", "graph",
            "midi", "images", "gm_index", "package_path",
        ]


# ── model_role grouping ─────────────────────────────────────────────


class TestGroupByModelRole:
    """PipelinePlan.group_by_model_role() segments."""

    def test_three_segments(self) -> None:
        plan = PipelinePlan.standard()
        groups = plan.group_by_model_role()
        assert len(groups) == 3

    def test_segment_roles(self) -> None:
        plan = PipelinePlan.standard()
        groups = plan.group_by_model_role()
        roles = [role for role, _ in groups]
        assert roles == ["text", "image", None]

    def test_text_segment_has_five_steps(self) -> None:
        plan = PipelinePlan.standard()
        groups = plan.group_by_model_role()
        role, steps = groups[0]
        assert role == "text"
        assert len(steps) == 5  # world_builder, art_director, story_writer, game_designer, music

    def test_image_segment_has_one_step(self) -> None:
        plan = PipelinePlan.standard()
        groups = plan.group_by_model_role()
        role, steps = groups[1]
        assert role == "image"
        assert len(steps) == 1
        assert steps[0].id == "image_generator"

    def test_none_segment_has_two_steps(self) -> None:
        plan = PipelinePlan.standard()
        groups = plan.group_by_model_role()
        role, steps = groups[2]
        assert role is None
        assert len(steps) == 2
        assert steps[0].id == "indexer"
        assert steps[1].id == "packager"

    def test_empty_plan_groups(self) -> None:
        plan = PipelinePlan()
        assert plan.group_by_model_role() == []

    def test_single_step_plan(self) -> None:
        plan = PipelinePlan(steps=[
            StepSpec(id="a", output_key="bible", model_role="text"),
        ])
        groups = plan.group_by_model_role()
        assert len(groups) == 1
        assert groups[0][0] == "text"
        assert len(groups[0][1]) == 1


# ── lookup ──────────────────────────────────────────────────────────


class TestLookup:
    """PipelinePlan.get(), get_by_output(), index_of()."""

    def test_get_existing(self) -> None:
        plan = PipelinePlan.standard()
        spec = plan.get("world_builder")
        assert spec.id == "world_builder"

    def test_get_missing(self) -> None:
        plan = PipelinePlan.standard()
        with pytest.raises(KeyError):
            plan.get("nonexistent")

    def test_get_by_output(self) -> None:
        plan = PipelinePlan.standard()
        spec = plan.get_by_output("bible")
        assert spec.id == "world_builder"

    def test_get_by_output_missing(self) -> None:
        plan = PipelinePlan.standard()
        with pytest.raises(KeyError):
            plan.get_by_output("nonexistent")

    def test_index_of(self) -> None:
        plan = PipelinePlan.standard()
        assert plan.index_of("world_builder") == 0
        assert plan.index_of("packager") == 7

    def test_index_of_missing(self) -> None:
        plan = PipelinePlan.standard()
        with pytest.raises(KeyError):
            plan.index_of("nonexistent")

    def test_phase_number(self) -> None:
        plan = PipelinePlan.standard()
        assert plan.phase_number("world_builder") == 1
        assert plan.phase_number("packager") == 8


# ── summary ─────────────────────────────────────────────────────────


class TestSummary:
    """PipelinePlan.summary() output."""

    def test_summary_string(self) -> None:
        plan = PipelinePlan.standard()
        text = plan.summary()
        assert "PipelinePlan: 8 steps" in text
        assert "world_builder" in text
        assert "packager" in text
        assert "[text ]" in text
        assert "[image]" in text
        assert "[none ]" in text


# ── plan-driven execution integration ───────────────────────────────


class TestPlanDrivenExecution:
    """Verify plan.group_by_model_role() matches actual GenerateStory execution."""

    @pytest.mark.asyncio
    async def test_standard_plan_executes_all_segments(self, tmp_path: Path) -> None:
        """Full execution through GenerateStory with the standard plan."""
        from src.application.generate_story import GenerateStory
        from src.application.models import GenerationRequest
        from tests.test_production_wiring import (
            InstrumentedGenerateStory,
            TrackedTextGenerator,
            TrackedImageGenerator,
            TrackedMusicGenerator,
            _inject_fakes,
            _clear_fakes,
        )

        _clear_fakes()
        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        output_dir = str(tmp_path / "output")
        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42,
            title="Plan Test",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
        )
        result = await service.execute(request)
        assert result.errors == [], f"Errors: {result.errors}"
        assert result.package_path
        assert Path(result.package_path).exists()

    @pytest.mark.asyncio
    async def test_model_role_segments_load_correctly(self, tmp_path: Path) -> None:
        """Text steps run under text scope, image under image scope."""
        from src.application.generate_story import GenerateStory
        from src.application.models import GenerationRequest
        from tests.test_production_wiring import (
            InstrumentedGenerateStory,
            TrackedTextGenerator,
            TrackedImageGenerator,
            TrackedMusicGenerator,
            _inject_fakes,
            _clear_fakes,
        )

        _clear_fakes()
        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        output_dir = str(tmp_path / "output")
        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=99,
            title="Model Segment Test",
            tone="heroic_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
        )
        result = await service.execute(request)
        assert result.errors == [], f"Errors: {result.errors}"

        # Text generator was called (5 text steps × 1 generation each min)
        assert text.call_count >= 5, f"Text gen called {text.call_count} times, expected >=5"

        # Image generator was called
        assert image.call_count >= 1, f"Image gen called {image.call_count} times, expected >=1"

    def test_plan_matches_execution_order(self) -> None:
        """Standard plan step ordering matches the documented phase ordering."""
        plan = PipelinePlan.standard()
        ids = plan.step_ids()

        # Phase 1-2: text model, bible + style
        assert ids[0] == "world_builder"
        assert ids[1] == "art_director"

        # Phase 3-4: text model, story + graph
        assert ids[2] == "story_writer"
        assert ids[3] == "game_designer"

        # Phase 5a: text model, music (parallel per-node)
        assert ids[4] == "music_generator"

        # Phase 5b: image model, images (parallel per-node)
        assert ids[5] == "image_generator"

        # Phase 6-7: no model, indexer + packager
        assert ids[6] == "indexer"
        assert ids[7] == "packager"
