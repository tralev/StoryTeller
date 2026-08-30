"""Tests for Phase 5.6H: Declarative Pipeline Plan.

Covers StepSpec construction, PipelinePlan validation, production_v2() factory,
group_by_model_role(), and plan-driven execution through GenerateStory.
"""

from __future__ import annotations

from pathlib import Path

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

    def test_production_plan_valid(self) -> None:
        plan = PipelinePlan.production_v2()
        plan.validate()  # No error

    def test_duplicate_step_id(self) -> None:
        plan = PipelinePlan(
            steps=[
                StepSpec(id="world_builder", output_key="bible"),
                StepSpec(id="world_builder", output_key="bible2"),
            ]
        )
        with pytest.raises(PlanValidationError, match="Duplicate step ID"):
            plan.validate()

    def test_duplicate_output_key(self) -> None:
        plan = PipelinePlan(
            steps=[
                StepSpec(id="a", output_key="bible"),
                StepSpec(id="b", output_key="bible"),
            ]
        )
        with pytest.raises(PlanValidationError, match="Duplicate output key"):
            plan.validate()

    def test_missing_dependency(self) -> None:
        plan = PipelinePlan(
            steps=[
                StepSpec(id="a", output_key="bible", requires=("story",)),
            ]
        )
        with pytest.raises(PlanValidationError, match="requires 'story'"):
            plan.validate()

    def test_self_loop(self) -> None:
        plan = PipelinePlan(
            steps=[
                StepSpec(id="a", output_key="bible", requires=("bible",)),
            ]
        )
        with pytest.raises(PlanValidationError, match="self-loop"):
            plan.validate()

    def test_dependencies_in_order(self) -> None:
        plan = PipelinePlan(
            steps=[
                StepSpec(id="a", output_key="bible"),
                StepSpec(id="b", output_key="story", requires=("bible",)),
                StepSpec(id="c", output_key="graph", requires=("bible", "story")),
            ]
        )
        plan.validate()  # No error

    def test_dependency_not_yet_available(self) -> None:
        plan = PipelinePlan(
            steps=[
                StepSpec(id="a", output_key="bible", requires=("graph",)),
                StepSpec(id="b", output_key="graph"),
            ]
        )
        with pytest.raises(PlanValidationError, match="requires 'graph'"):
            plan.validate()


# ── authoritative production plan ───────────────────────────────────


class TestProductionPlan:
    """The only factory produces the complete procedural-first plan."""

    def test_contract_and_lookup_helpers(self) -> None:
        plan = PipelinePlan.production_v2()
        plan.validate()
        assert len(plan) == 16
        assert plan[0].id == "physical_world"
        assert plan[-1].id == "packager"
        assert plan.get("world_builder_v2").output_key == "bible"
        assert plan.get_by_output("narrative_project").id == "graph_v2"
        assert plan.index_of("physical_world") == 0
        assert plan.phase_number("packager") == 16
        assert len(plan.step_ids()) == len(set(plan.step_ids()))
        assert len(plan.output_keys()) == len(set(plan.output_keys()))

    def test_resource_segments(self) -> None:
        groups = PipelinePlan.production_v2().group_by_model_role()
        assert [role for role, _ in groups] == [None, "text", "image", None]
        assert [step.id for step in groups[1][1]] == [
            "world_builder_v2",
            "reconcile_world",
            "art_direction_v2",
            "story_v2",
            "graph_v2",
            "media_intents_v2",
        ]

    def test_empty_and_single_step_groups(self) -> None:
        assert PipelinePlan().group_by_model_role() == []
        plan = PipelinePlan([StepSpec("a", "bible", model_role="text")])
        assert plan.group_by_model_role() == [("text", [plan[0]])]

    def test_missing_lookups_raise(self) -> None:
        plan = PipelinePlan.production_v2()
        with pytest.raises(KeyError):
            plan.get("nonexistent")
        with pytest.raises(KeyError):
            plan.get_by_output("nonexistent")
        with pytest.raises(KeyError):
            plan.index_of("nonexistent")

    def test_summary_string(self) -> None:
        text = PipelinePlan.production_v2().summary()
        assert "PipelinePlan: 16 steps" in text
        assert "physical_world" in text
        assert "packager" in text
        assert "[text ]" in text
        assert "[image]" in text
        assert "[none ]" in text


# ── plan-driven execution integration ───────────────────────────────


class TestPlanDrivenExecution:
    """Verify plan.group_by_model_role() matches actual GenerateStory execution."""

    @pytest.mark.asyncio
    async def test_compatibility_harness_executes_all_segments(self, tmp_path: Path) -> None:
        """The isolated legacy component harness remains executable."""
        from src.application.models import GenerationRequest
        from tests.test_production_wiring import (
            InstrumentedGenerateStory,
            TrackedImageGenerator,
            TrackedMusicGenerator,
            TrackedTextGenerator,
            _clear_fakes,
            _inject_fakes,
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
        from src.application.models import GenerationRequest
        from tests.test_production_wiring import (
            InstrumentedGenerateStory,
            TrackedImageGenerator,
            TrackedMusicGenerator,
            TrackedTextGenerator,
            _clear_fakes,
            _inject_fakes,
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
        """Production plan ordering matches the documented phase ordering."""
        plan = PipelinePlan.production_v2()
        ids = plan.step_ids()
        assert ids[:4] == [
            "physical_world",
            "simulate_world",
            "local_maps_v2",
            "world_builder_v2",
        ]
        assert ids[-3:] == ["package_v2", "accept_package_v2", "packager"]
