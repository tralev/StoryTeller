"""P8.C05G — Every-site local 3D generation and reconciliation tests."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from src.world.views import WorldView
from src.worldgen.artifacts import canonical_json
from src.worldgen.local_maps import (
    LocalFeature,
    LocalSiteMap,
    generate_local_maps,
    validate_local_map,
)


def test_local_map_generator_has_no_raw_division_operators() -> None:
    source = Path("src/worldgen/local_maps.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not [node for node in ast.walk(tree) if isinstance(node, (ast.FloorDiv, ast.Div))]


def test_generated_local_maps_have_canonical_golden_vector(phase4_world) -> None:
    maps = generate_local_maps(WorldView(phase4_world))
    assert hashlib.sha256(canonical_json(maps)).hexdigest() == (
        "54e2830cf73a8308081046e70b9eb77cc408f215c0eb00a5e1f40ebfc4e4b553"
    )


class TestLocalSiteMap:
    """P8.C05G: Unit tests for local site maps."""

    def _make_valid(self, site_id: str = "site_1", seed: int = 0) -> LocalSiteMap:
        w, h, z = 16, 16, 8
        strata = tuple((i % 5) + 1 for i in range(z))
        surface = tuple(z // 2 for _ in range(w * h))
        center = (w // 2, h // 2, z // 2)
        road = tuple((x, center[1], center[2]) for x in range(w))
        stairs = tuple((center[0], center[1], zz) for zz in range(center[2] - 2, center[2] + 1))
        cave = tuple((center[0] + dx, center[1] + (dx % 2), center[2] - 3) for dx in range(-2, 3))
        water = tuple((center[0] + dx, center[1] + 4, center[2] - 4) for dx in range(-2, 3))
        building = ((center[0], center[1], center[2]), (center[0] + 1, center[1], center[2]))
        magma = ((center[0], center[1], 1),)
        heat = ((center[0], center[1], 2),)
        features = (
            LocalFeature(f"{site_id}_road", "road", road, ("src_routes",)),
            LocalFeature(f"{site_id}_stairs", "vertical_stairs", stairs, (site_id,)),
            LocalFeature(f"{site_id}_cave", "sealed_cave", cave, ("src_geology",)),
            LocalFeature(f"{site_id}_aquifer", "aquifer_water", water, ("src_hydrology",)),
            LocalFeature(f"{site_id}_building", "supported_building", building, (site_id,)),
            LocalFeature(f"{site_id}_workshop", "workshop", (building[0],), (site_id,)),
            LocalFeature(f"{site_id}_stockpile", "stockpile", (building[1],), (site_id,)),
            LocalFeature(
                f"{site_id}_deposit", "mineral_deposit", (cave[0], cave[-1]), ("src_resources",)
            ),
            LocalFeature(f"{site_id}_magma", "sealed_magma", magma, ("src_geology",)),
            LocalFeature(f"{site_id}_heat", "heat_zone", heat, ("src_climate",)),
            LocalFeature(f"{site_id}_support", "structural_support", building, (site_id,)),
            LocalFeature(
                f"{site_id}_parcel",
                "parcel",
                tuple(
                    (center[0] + dx, center[1] + dy, center[2])
                    for dx in range(-1, 2)
                    for dy in range(-1, 2)
                ),
                (site_id,),
            ),
            LocalFeature(
                f"{site_id}_scar",
                "event_scar",
                ((center[0] - 3, center[1], center[2]),),
                ("src_history",),
            ),
        )
        return LocalSiteMap(1, site_id, w, h, z, 0, strata, surface, features)

    def test_validate_local_map_accepts_valid(self) -> None:
        """P8.C05G: validate_local_map passes for a correctly constructed map."""
        m = self._make_valid()
        validate_local_map(m)  # must not raise

    def test_rejects_incomplete_geometry(self) -> None:
        """P8.C05G: Mismatched surface/strata dimensions fail validation."""
        m = self._make_valid()
        bad = LocalSiteMap(
            1, m.site_id, m.width, m.height, m.z_levels, m.macro_cell, m.strata, (0,), m.features
        )  # wrong surface
        try:
            validate_local_map(bad)
            assert False, "should have raised"
        except ValueError as e:
            assert "COVERAGE" in str(e) or "geometry" in str(e).lower()

    def test_rejects_feature_out_of_bounds(self) -> None:
        """P8.C05G: Feature cells outside map dimensions fail validation."""
        m = self._make_valid()
        bad_features = (
            LocalFeature("bad", "road", ((m.width + 1, 0, 0),), ("src",)),
        ) + m.features[1:]
        bad = LocalSiteMap(
            1,
            m.site_id,
            m.width,
            m.height,
            m.z_levels,
            m.macro_cell,
            m.strata,
            m.surface_height,
            bad_features,
        )
        try:
            validate_local_map(bad)
            assert False, "should have raised"
        except ValueError as e:
            assert "BOUNDS" in str(e) or "outside" in str(e).lower()

    def test_rejects_missing_required_features(self) -> None:
        """P8.C05G: Missing required feature kinds fail validation."""
        m = self._make_valid()
        # Remove "road"
        reduced = tuple(f for f in m.features if f.kind != "road")
        bad = LocalSiteMap(
            1,
            m.site_id,
            m.width,
            m.height,
            m.z_levels,
            m.macro_cell,
            m.strata,
            m.surface_height,
            reduced,
        )
        try:
            validate_local_map(bad)
            assert False, "should have raised"
        except ValueError as e:
            assert "FEATURES" in str(e) or "systems" in str(e).lower()

    def test_rejects_magma_water_overlap(self) -> None:
        """P8.C05G: Overlapping magma and water fail fluid validation."""
        m = self._make_valid()
        overlapped = list(m.features)
        # Replace sealed_magma with cells overlapping aquifer_water
        water_cells = next(f for f in m.features if f.kind == "aquifer_water").cells
        overlapped = [f for f in overlapped if f.kind != "sealed_magma"] + [
            LocalFeature("bad_magma", "sealed_magma", (water_cells[0],), ("src",))
        ]
        bad = LocalSiteMap(
            1,
            m.site_id,
            m.width,
            m.height,
            m.z_levels,
            m.macro_cell,
            m.strata,
            m.surface_height,
            tuple(overlapped),
        )
        try:
            validate_local_map(bad)
            assert False, "should have raised"
        except ValueError as e:
            assert "FLUID" in str(e) or "overlap" in str(e).lower()

    def test_rejects_unsupported_building(self) -> None:
        """P8.C05G: Building cells outside structural support fail validation."""
        m = self._make_valid()
        bad_building = ((0, 0, m.z_levels // 2),)  # not in supports
        overlapped = [f for f in m.features if f.kind != "supported_building"] + [
            LocalFeature("bad_bldg", "supported_building", bad_building, ("src",))
        ]
        bad = LocalSiteMap(
            1,
            m.site_id,
            m.width,
            m.height,
            m.z_levels,
            m.macro_cell,
            m.strata,
            m.surface_height,
            tuple(overlapped),
        )
        try:
            validate_local_map(bad)
            assert False, "should have raised"
        except ValueError as e:
            assert "SUPPORT" in str(e) or "unsupported" in str(e).lower()

    def test_rejects_disconnected_road(self) -> None:
        """P8.C05G: Non-contiguous road cells fail path validation."""
        m = self._make_valid()
        # Skip cell (5,...) to break continuity
        bad_road = tuple((x, m.height // 2, m.z_levels // 2) for x in range(m.width) if x != 5)
        overlapped = [f for f in m.features if f.kind != "road"] + [
            LocalFeature("bad_road", "road", bad_road, ("src",))
        ]
        bad = LocalSiteMap(
            1,
            m.site_id,
            m.width,
            m.height,
            m.z_levels,
            m.macro_cell,
            m.strata,
            m.surface_height,
            tuple(overlapped),
        )
        try:
            validate_local_map(bad)
            assert False, "should have raised"
        except ValueError as e:
            assert "PATH" in str(e) or "disconnected" in str(e).lower()

    def test_local_site_map_is_frozen(self) -> None:
        """P8.C05G: LocalSiteMap is an immutable dataclass."""
        m = self._make_valid()
        try:
            m.site_id = "mutated"
            assert False, "should have raised FrozenInstanceError"
        except Exception:
            pass  # frozen dataclass prevents mutation

    def test_deterministic_generation(self) -> None:
        """P8.C05G: Identical maps yield equal validation results."""
        a = self._make_valid("s1")
        b = self._make_valid("s1")
        validate_local_map(a)
        validate_local_map(b)
        assert a == b
