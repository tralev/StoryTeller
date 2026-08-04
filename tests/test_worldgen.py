"""Tests for Phase 7.5: Procedural World Generation.

Covers every module in src/worldgen/:
  models, terrain, climate, biomes, regions, civilizations,
  generator, adapter, step.

Each test class exercises one module with determinism verification.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.worldgen.adapter import snapshot_dict_to_bible_context
from src.worldgen.biomes import classify_biomes
from src.worldgen.civilizations import generate_civilizations
from src.worldgen.climate import generate_climate
from src.worldgen.generator import generate_world
from src.worldgen.models import (
    Biome, Civilization, GridCell, Region, Site, WorldRNG, WorldSnapshot,
)
from src.worldgen.regions import segment_regions
from src.worldgen.step import ProceduralWorldStep
from src.worldgen.terrain import generate_terrain


# ── Models tests ─────────────────────────────────────────────────────


class TestWorldRNG:
    """Deterministic RNG produces reproducible sequences."""

    def test_same_seed_same_sequence(self) -> None:
        rng1 = WorldRNG(42)
        rng2 = WorldRNG(42)
        seq1 = [rng1.uniform() for _ in range(100)]
        seq2 = [rng2.uniform() for _ in range(100)]
        assert seq1 == seq2

    def test_different_seed_different_sequence(self) -> None:
        rng1 = WorldRNG(42)
        rng2 = WorldRNG(99)
        seq1 = [rng1.uniform() for _ in range(10)]
        seq2 = [rng2.uniform() for _ in range(10)]
        assert seq1 != seq2

    def test_uniform_range(self) -> None:
        rng = WorldRNG(7)
        for _ in range(1000):
            v = rng.uniform(-1.0, 2.0)
            assert -1.0 <= v < 2.0

    def test_randint_range(self) -> None:
        rng = WorldRNG(7)
        for _ in range(100):
            v = rng.randint(0, 5)
            assert 0 <= v <= 5

    def test_choice_from_list(self) -> None:
        rng = WorldRNG(1)
        for _ in range(20):
            v = rng.choice(["a", "b", "c"])
            assert v in ("a", "b", "c")

    def test_choose_weighted(self) -> None:
        rng = WorldRNG(1)
        weighted = [("a", 0.9), ("b", 0.1)]
        # With high weight on "a", it should appear most often
        results = [rng.choose_weighted(weighted) for _ in range(100)]
        assert results.count("a") > 50

    def test_sample_without_replacement(self) -> None:
        rng = WorldRNG(42)
        items = ["a", "b", "c", "d", "e"]
        result = rng.sample(items, 3)
        assert len(result) == 3
        assert len(set(result)) == 3  # All unique
        for v in result:
            assert v in items

    def test_noise_2d_deterministic(self) -> None:
        rng1 = WorldRNG(42)
        rng2 = WorldRNG(42)
        for x in range(10):
            for y in range(10):
                assert rng1.noise_2d(x, y) == rng2.noise_2d(x, y)

    def test_noise_2d_range(self) -> None:
        rng = WorldRNG(42)
        for _ in range(500):
            v = rng.noise_2d(rng.randint(0, 100), rng.randint(0, 100))
            assert -1.0 <= v <= 1.0

    def test_noise_2d_smooth_range(self) -> None:
        rng = WorldRNG(42)
        for _ in range(500):
            v = rng.noise_2d_smooth(rng.randint(0, 100), rng.randint(0, 100))
            assert -1.0 <= v <= 1.0


class TestGridCell:
    """GridCell defaults and construction."""

    def test_defaults(self) -> None:
        cell = GridCell()
        assert cell.elevation == 0.0
        assert cell.biome == ""

    def test_custom_values(self) -> None:
        cell = GridCell(elevation=0.5, temperature=-0.3, biome="tundra", is_coastal=True)
        assert cell.elevation == 0.5
        assert cell.temperature == -0.3
        assert cell.biome == "tundra"
        assert cell.is_coastal is True


class TestWorldSnapshot:
    """WorldSnapshot serialization."""

    def test_minimal_to_dict(self) -> None:
        snap = WorldSnapshot(seed=42)
        d = snap.to_dict()
        assert d["schema_version"] == 1
        assert d["seed"] == 42
        assert d["regions"] == []
        assert d["civilizations"] == []

    def test_full_to_dict(self) -> None:
        snap = WorldSnapshot(
            seed=42,
            dimensions={"width": 64, "height": 48},
            regions=[
                Region(id="region_01", name="Test Vale", biome="temperate_forest",
                       elevation="lowland", climate="temperate_wet", prosperity=0.75,
                       neighbors=["region_02"], sites=["site_01"]),
            ],
            sites=[Site(id="site_01", region_id="region_01", site_type="capital",
                        population=1000, name="Testhold")],
            civilizations=[Civilization(id="civ_01", name="Testers", race="human",
                                        government="monarchy",
                                        controlled_regions=["region_01"])],
        )
        d = snap.to_dict()
        assert d["regions"][0]["name"] == "Test Vale"
        assert d["regions"][0]["prosperity"] == 0.75
        assert d["sites"][0]["population"] == 1000
        assert d["civilizations"][0]["race"] == "human"

    def test_to_dict_valid_json(self) -> None:
        snap = generate_world(seed=42, width=16, height=16, max_civs=2, history_years=10)
        d = snap.to_dict()
        # Must be JSON-serializable
        json.dumps(d)
        # Must match schema structure
        assert "schema_version" in d
        assert d["schema_version"] == 1


# ── Terrain tests ───────────────────────────────────────────────────


class TestTerrainGeneration:
    """Terrain module produces valid grids."""

    def test_grid_dimensions(self) -> None:
        grid = generate_terrain(32, 24, seed=42)
        assert len(grid) == 24
        assert len(grid[0]) == 32

    def test_deterministic(self) -> None:
        g1 = generate_terrain(16, 16, seed=42)
        g2 = generate_terrain(16, 16, seed=42)
        for y in range(16):
            for x in range(16):
                assert g1[y][x].elevation == g2[y][x].elevation
                assert g1[y][x].temperature == g2[y][x].temperature

    def test_elevation_range(self) -> None:
        grid = generate_terrain(20, 20, seed=7)
        for row in grid:
            for cell in row:
                assert -1.0 <= cell.elevation <= 1.0

    def test_temperature_range(self) -> None:
        grid = generate_terrain(20, 20, seed=7)
        for row in grid:
            for cell in row:
                assert -1.0 <= cell.temperature <= 1.0

    def test_land_fraction_affects_water(self) -> None:
        g_low = generate_terrain(16, 16, seed=42, land_fraction=0.2)
        g_high = generate_terrain(16, 16, seed=42, land_fraction=0.6)
        land_low = sum(1 for row in g_low for c in row if c.elevation > 0)
        land_high = sum(1 for row in g_high for c in row if c.elevation > 0)
        assert land_high > land_low


# ── Climate tests ───────────────────────────────────────────────────


class TestClimateGeneration:
    """Climate module sets precipitation and drainage."""

    def test_precipitation_set(self) -> None:
        grid = generate_terrain(16, 16, seed=42)
        generate_climate(grid, seed=42)
        for row in grid:
            for cell in row:
                assert 0.0 <= cell.precipitation <= 1.0

    def test_deterministic(self) -> None:
        g1 = generate_terrain(16, 16, seed=42)
        g2 = generate_terrain(16, 16, seed=42)
        generate_climate(g1, 42)
        generate_climate(g2, 42)
        for y in range(16):
            for x in range(16):
                assert g1[y][x].precipitation == g2[y][x].precipitation
                assert g1[y][x].drainage == g2[y][x].drainage

    def test_rivers_exist(self) -> None:
        grid = generate_terrain(32, 32, seed=42)
        generate_climate(grid, seed=42)
        rivers = sum(1 for row in grid for c in row if c.is_river)
        assert rivers > 0, "Expected at least one river cell"

    def test_coastal_cells_marked(self) -> None:
        grid = generate_terrain(32, 32, seed=42)
        generate_climate(grid, seed=42)
        coastal = sum(1 for row in grid for c in row if c.is_coastal)
        assert coastal > 0, "Expected at least one coastal cell"


# ── Biomes tests ────────────────────────────────────────────────────


class TestBiomeClassification:
    """Biome module classifies each cell."""

    def test_all_land_cells_classified(self) -> None:
        grid = generate_terrain(32, 32, seed=42)
        generate_climate(grid, seed=42)
        classify_biomes(grid)
        for row in grid:
            for cell in row:
                if cell.elevation > 0:
                    assert cell.biome != "", f"Land cell at ({cell.elevation:.2f}) has no biome"

    def test_water_cells_empty_biome(self) -> None:
        grid = generate_terrain(32, 32, seed=42)
        generate_climate(grid, seed=42)
        classify_biomes(grid)
        water_no_biome = 0
        for row in grid:
            for cell in row:
                if cell.elevation <= -0.05:
                    if cell.biome != "":
                        water_no_biome += 1
        # Small tolerance — some water cells at exact boundary may get biomes
        assert water_no_biome < 5

    def test_deterministic(self) -> None:
        g1 = generate_terrain(16, 16, seed=42)
        g2 = generate_terrain(16, 16, seed=42)
        generate_climate(g1, 42)
        generate_climate(g2, 42)
        classify_biomes(g1)
        classify_biomes(g2)
        for y in range(16):
            for x in range(16):
                assert g1[y][x].biome == g2[y][x].biome

    def test_valid_biome_values(self) -> None:
        valid = {b.value for b in Biome}
        valid.add("")  # Water cells
        grid = generate_terrain(32, 32, seed=42)
        generate_climate(grid, seed=42)
        classify_biomes(grid)
        for row in grid:
            for cell in row:
                assert cell.biome in valid, f"Invalid biome: {cell.biome}"


# ── Regions tests ───────────────────────────────────────────────────


class TestRegionSegmentation:
    """Region module groups cells into named regions."""

    def test_regions_created(self) -> None:
        grid = generate_terrain(32, 32, seed=42)
        generate_climate(grid, seed=42)
        classify_biomes(grid)
        regions = segment_regions(grid, seed=42)
        assert len(regions) >= 2, f"Expected >=2 regions, got {len(regions)}"

    def test_region_has_name_and_id(self) -> None:
        grid = generate_terrain(32, 32, seed=42)
        generate_climate(grid, seed=42)
        classify_biomes(grid)
        regions = segment_regions(grid, seed=42)
        for r in regions:
            assert r.id.startswith("region_")
            assert len(r.name) > 0
            assert r.biome != ""
            assert r.elevation != ""

    def test_region_has_neighbors(self) -> None:
        grid = generate_terrain(32, 32, seed=42)
        generate_climate(grid, seed=42)
        classify_biomes(grid)
        regions = segment_regions(grid, seed=42)
        # Most regions should have at least one neighbor
        with_neighbors = sum(1 for r in regions if r.neighbors)
        assert with_neighbors >= len(regions) // 2

    def test_region_prosperity_in_range(self) -> None:
        grid = generate_terrain(32, 32, seed=42)
        generate_climate(grid, seed=42)
        classify_biomes(grid)
        regions = segment_regions(grid, seed=42)
        for r in regions:
            assert 0.0 <= r.prosperity <= 1.0

    def test_deterministic(self) -> None:
        def make_regions(seed: int) -> list[Region]:
            g = generate_terrain(16, 16, seed=seed)
            generate_climate(g, seed)
            classify_biomes(g)
            return segment_regions(g, seed)

        r1 = make_regions(42)
        r2 = make_regions(42)
        assert len(r1) == len(r2)
        for a, b in zip(r1, r2):
            assert a.id == b.id
            assert a.name == b.name
            assert a.biome == b.biome


# ── Civilizations tests ─────────────────────────────────────────────


class TestCivilizationGeneration:
    """Civilization placement, race/government, simulation."""

    @staticmethod
    def _make_regions(seed: int) -> list[Region]:
        g = generate_terrain(32, 32, seed=seed)
        generate_climate(g, seed)
        classify_biomes(g)
        return segment_regions(g, seed)

    def test_civs_created(self) -> None:
        regions = self._make_regions(42)
        civs, sites, history = generate_civilizations(regions, seed=42, max_civs=3, history_years=50)
        assert len(civs) >= 1
        assert len(sites) >= 1

    def test_each_civ_has_capital(self) -> None:
        regions = self._make_regions(42)
        civs, sites, history = generate_civilizations(regions, seed=42, max_civs=3, history_years=50)
        capitals = [s for s in sites if s.site_type == "capital"]
        assert len(capitals) == len(civs)

    def test_civs_control_regions(self) -> None:
        regions = self._make_regions(42)
        civs, sites, history = generate_civilizations(regions, seed=42, max_civs=3, history_years=50)
        for civ in civs:
            assert len(civ.controlled_regions) >= 1

    def test_history_events_generated(self) -> None:
        regions = self._make_regions(42)
        civs, sites, history = generate_civilizations(regions, seed=42, max_civs=3, history_years=50)
        assert len(history) > 0

    def test_deterministic(self) -> None:
        regions = self._make_regions(42)
        c1, s1, h1 = generate_civilizations(regions, seed=42, max_civs=3, history_years=50)
        c2, s2, h2 = generate_civilizations(regions, seed=42, max_civs=3, history_years=50)
        assert len(c1) == len(c2)
        for a, b in zip(c1, c2):
            assert a.id == b.id
            assert a.race == b.race
            assert a.government == b.government

    def test_valid_races(self) -> None:
        valid = {"human", "elf", "dwarf", "orc", "halfling", "gnome", "goblin", "lizardfolk", "tiefling"}
        regions = self._make_regions(42)
        civs, _, _ = generate_civilizations(regions, seed=42, max_civs=4, history_years=10)
        for civ in civs:
            assert civ.race in valid


# ── Generator tests ────────────────────────────────────────────────


class TestWorldGenerator:
    """End-to-end procedural world generation."""

    def test_generate_returns_snapshot(self) -> None:
        snap = generate_world(seed=42, width=16, height=16, max_civs=2, history_years=10)
        assert isinstance(snap, WorldSnapshot)
        assert snap.seed == 42
        assert snap.dimensions == {"width": 16, "height": 16}

    def test_deterministic_full_pipeline(self) -> None:
        s1 = generate_world(seed=42, width=20, height=20, max_civs=2, history_years=20)
        s2 = generate_world(seed=42, width=20, height=20, max_civs=2, history_years=20)
        assert s1.to_dict() == s2.to_dict()

    def test_different_seeds_different_output(self) -> None:
        s1 = generate_world(seed=42, width=16, height=16, max_civs=2, history_years=10)
        s2 = generate_world(seed=99, width=16, height=16, max_civs=2, history_years=10)
        assert s1.to_dict() != s2.to_dict()

    def test_minimal_grid(self) -> None:
        snap = generate_world(seed=1, width=16, height=16, max_civs=1, history_years=0)
        assert len(snap.regions) >= 1
        assert len(snap.civilizations) == 1

    def test_max_civs_respected(self) -> None:
        snap = generate_world(seed=42, width=32, height=32, max_civs=2, history_years=10)
        assert len(snap.civilizations) <= 2

    def test_output_is_json_serializable(self) -> None:
        snap = generate_world(seed=42, width=16, height=16, max_civs=2, history_years=10)
        d = snap.to_dict()
        json.dumps(d)  # Must not raise


# ── Adapter tests ──────────────────────────────────────────────────


class TestAdapter:
    """Adapter maps snapshot to LLM constraints."""

    def test_context_string_contains_regions(self) -> None:
        snap = generate_world(seed=42, width=20, height=20, max_civs=2, history_years=20)
        text = snapshot_dict_to_bible_context(snap.to_dict())
        assert "PROCEDURAL WORLD CONSTRAINTS" in text
        assert "Geography" in text
        assert len(text) > 200

    def test_context_contains_civilizations(self) -> None:
        snap = generate_world(seed=42, width=20, height=20, max_civs=2, history_years=20)
        text = snapshot_dict_to_bible_context(snap.to_dict())
        assert "Civilizations" in text

    def test_context_contains_rules(self) -> None:
        snap = generate_world(seed=42, width=16, height=16, max_civs=1, history_years=5)
        text = snapshot_dict_to_bible_context(snap.to_dict())
        assert "RULES" in text
        assert "Do NOT invent" in text


# ── Step tests ─────────────────────────────────────────────────────


class TestProceduralWorldStep:
    """ProceduralWorldStep as a PipelineStep."""

    @pytest.mark.asyncio
    async def test_step_generates_snapshot(self) -> None:
        from src.job_queue import PipelineContext
        step = ProceduralWorldStep()
        ctx = PipelineContext(run_id="test", seed=42, output_dir=None)
        output = await step.run(ctx)
        assert output.step_name == "procedural_world"
        data = output.data
        assert isinstance(data, dict)
        assert data["schema_version"] == 1
        assert data["seed"] == 42

    @pytest.mark.asyncio
    async def test_step_stores_in_context(self) -> None:
        from src.job_queue import JobQueue, PipelineContext
        step = ProceduralWorldStep()
        ctx = PipelineContext(run_id="test", seed=42, output_dir=None)
        queue = JobQueue()
        await queue.execute_step(step, ctx, "procedural_world")
        # Phase 7.5: The key map in JobQueue doesn't know about procedural_world,
        # so it stores output under the job_id. The step's output_key is "world_snapshot"
        # but that's used when running via PipelineStep directly, not via JobQueue.
        snap = ctx.outputs.get("procedural_world")
        if snap is None:
            snap = ctx.outputs.get("world_snapshot")
        assert snap is not None, f"Keys available: {list(ctx.outputs.keys())}"
        assert isinstance(snap, dict)
        assert snap["schema_version"] == 1

    @pytest.mark.asyncio
    async def test_deterministic(self) -> None:
        from src.job_queue import PipelineContext
        step1 = ProceduralWorldStep()
        ctx1 = PipelineContext(run_id="a", seed=42, output_dir=None)
        out1 = await step1.run(ctx1)

        step2 = ProceduralWorldStep()
        ctx2 = PipelineContext(run_id="b", seed=42, output_dir=None)
        out2 = await step2.run(ctx2)

        assert out1.data == out2.data

    @pytest.mark.asyncio
    async def test_different_seed_different_output(self) -> None:
        from src.job_queue import PipelineContext
        step1 = ProceduralWorldStep()
        ctx1 = PipelineContext(run_id="a", seed=42, output_dir=None)
        out1 = await step1.run(ctx1)

        step2 = ProceduralWorldStep()
        ctx2 = PipelineContext(run_id="b", seed=99, output_dir=None)
        out2 = await step2.run(ctx2)

        assert out1.data != out2.data

    @pytest.mark.asyncio
    async def test_world_size_from_state(self) -> None:
        from src.job_queue import PipelineContext
        step = ProceduralWorldStep()
        ctx = PipelineContext(run_id="test", seed=42, output_dir=None)
        ctx.state["world_size"] = (32, 24)
        output = await step.run(ctx)
        assert output.data["dimensions"] == {"width": 32, "height": 24}

    @pytest.mark.asyncio
    async def test_max_civs_from_state(self) -> None:
        from src.job_queue import PipelineContext
        step = ProceduralWorldStep()
        ctx = PipelineContext(run_id="test", seed=42, output_dir=None)
        ctx.state["max_civs"] = 1
        output = await step.run(ctx)
        assert len(output.data["civilizations"]) == 1


# ── Schema validation ───────────────────────────────────────────────


class TestWorldSnapshotSchema:
    """Generated snapshots validate against world_snapshot.schema.json."""

    @pytest.mark.integration
    def test_snapshot_validates_against_schema(self) -> None:
        from src.validators.schema_validator import SchemaValidator
        import os

        schemas_dir = os.environ.get(
            "STORYTELLER_SCHEMAS_DIR",
            str(Path(__file__).resolve().parent.parent / "docs" / "schemas"),
        )
        sv = SchemaValidator(schemas_dir)
        snap = generate_world(seed=42, width=16, height=16, max_civs=2, history_years=10)
        result = sv.validate(snap.to_dict(), "world_snapshot")
        assert result.is_valid, f"Schema validation failed: {result.format_for_retry()}"
