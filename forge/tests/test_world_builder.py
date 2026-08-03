"""Tests for WorldBuilder PipelineStep."""

from __future__ import annotations

import pytest

from src.job_queue import PipelineContext
from src.models.base import StepOutput
from src.models.world_builder import WorldBuilder


class MockGenerator:
    """Mock TextGenerator that returns a minimal valid bible."""

    model_name: str = "test-model"
    quantization: str = "Q4_K_M"

    def __init__(self, output: dict | None = None) -> None:
        self.output = output or _make_minimal_bible()
        self.call_count = 0
        self.last_prompt: str = ""

    async def generate(
        self,
        prompt: str = "",
        schema: dict | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        self.call_count += 1
        self.last_prompt = prompt
        return dict(self.output)


def _make_minimal_bible() -> dict:
    """Return a minimal bible dict the generator would return."""
    return {
        "world_name": "Test World",
        "narrative_rules": {
            "tone": "dark_fantasy",
            "forbidden": ["resurrection"],
            "required_themes": ["sacrifice", "decay"],
            "mortality": "moderate",
            "knowledge_level": "superstitious",
        },
        "entities": {
            "characters": [
                {"id": "char_01", "name": "Hero", "aliases": [], "description": "A hero.", "role": "protagonist", "archetype": "reluctant_hero", "motivation": "Save the world", "flaw": "Pride", "strength": "Courage", "relationships": [], "status": "alive"},
            ],
            "locations": [
                {"id": "loc_01", "name": "Village", "aliases": [], "description": "A small village.", "type": "village", "mood": "peaceful"},
            ],
            "factions": [
                {"id": "fac_01", "name": "The Order", "aliases": [], "description": "A secret order.", "type": "order", "goal": "Peace", "methods": "Diplomacy", "members": ["char_01"]},
            ],
            "creatures": [
                {"id": "cre_01", "name": "Beast", "aliases": [], "description": "A creature.", "type": "beast", "habitat": ["loc_01"], "danger": "low", "behavior": "Roams"},
            ],
            "artifacts": [
                {"id": "art_01", "name": "Sword", "aliases": [], "description": "A magic sword.", "origin": "Ancient forge", "location": "loc_01", "power": "Cuts anything"},
            ],
            "events": [
                {"id": "evt_01", "name": "The Fall", "aliases": [], "description": "A great fall.", "era": "ancient", "consequence": "Changed everything"},
            ],
        },
        "systems": {
            "magic": {"source": "The Void", "rules": ["Magic fades at dawn"], "costs": ["Memory loss"], "limitations": "Cannot resurrect"},
            "politics": {"power_structure": "Monarchy", "conflicts": []},
            "religion": {"gods": [{"name": "Old One", "domain": "Death", "status": "sleeping"}], "afterlife": "Unknown"},
        },
    }


class TestWorldBuilder:
    """WorldBuilder PipelineStep tests."""

    @pytest.mark.asyncio
    async def test_generates_bible_with_metadata(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.state["tone"] = "dark_fantasy"
        ctx.state["title"] = "Test World"

        builder = WorldBuilder(generator=MockGenerator())
        output = await builder.run(ctx)

        assert isinstance(output, StepOutput)
        assert output.step_name == "world_builder"
        assert output.data["world_name"] == "Test World"
        assert output.data["schema_version"] == 1
        assert output.data["seed"] == 42
        assert "generation_params" in output.data
        assert output.data["generation_params"]["tone"] == "dark_fantasy"
        assert output.data["generation_params"]["title"] == "Test World"

    @pytest.mark.asyncio
    async def test_generates_artifact_id(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.state["tone"] = "dark_fantasy"
        ctx.state["title"] = "Test"

        builder = WorldBuilder(generator=MockGenerator())
        output = await builder.run(ctx)

        assert output.artifact_id is not None
        assert output.artifact_id.startswith("world_")
        assert len(output.artifact_id) == 14  # "world_" + 8 hex chars

    @pytest.mark.asyncio
    async def test_uses_tone_and_title_from_context(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.state["tone"] = "heroic_fantasy"
        ctx.state["title"] = "The Iron Schism"

        gen = MockGenerator()
        builder = WorldBuilder(generator=gen)
        await builder.run(ctx)

        assert "heroic_fantasy" in gen.last_prompt
        assert "The Iron Schism" in gen.last_prompt

    @pytest.mark.asyncio
    async def test_defaults_when_state_missing(self) -> None:
        ctx = PipelineContext(run_id="run_01", seed=1)

        gen = MockGenerator()
        builder = WorldBuilder(generator=gen)
        output = await builder.run(ctx)

        assert "dark_fantasy" in gen.last_prompt
        assert "Untitled World" in gen.last_prompt
        assert output.data["generation_params"]["tone"] == "dark_fantasy"

    @pytest.mark.asyncio
    async def test_deterministic_artifact_id(self) -> None:
        """Same data → same artifact_id."""
        ctx1 = PipelineContext(run_id="r1", seed=42)
        ctx1.state["tone"] = "dark_fantasy"
        ctx1.state["title"] = "X"

        gen = MockGenerator()
        out1 = await WorldBuilder(generator=gen).run(ctx1)
        out2 = await WorldBuilder(generator=gen).run(ctx1)

        assert out1.artifact_id == out2.artifact_id

    @pytest.mark.asyncio
    async def test_normalization_applied(self) -> None:
        """Output is normalized after generation."""
        ctx = PipelineContext(run_id="run_01", seed=42)
        ctx.state["tone"] = "dark_fantasy"
        ctx.state["title"] = "Test"

        # Data with unsorted keys
        data = _make_minimal_bible()
        data["z_extra"] = 1
        data["a_extra"] = 2

        builder = WorldBuilder(generator=MockGenerator(data))
        output = await builder.run(ctx)

        keys = list(output.data.keys())
        # Keys should be sorted alphabetically after normalization
        assert keys[0] == "a_extra"
