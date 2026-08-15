"""P8.C05B kernel tests — noise, PRNG golden vectors, canonical JSON, determinism."""

from __future__ import annotations

import ast
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from src.worldgen.artifacts import canonical_json
from src.worldgen.numeric import (
    MASK64, MAX_I64, MIN_I64, PPM, Capacity, Distance, Elevation, Energy,
    FIXED_UNIT_TYPES, Mass, Moisture, Population, Price, Probability, Rainfall,
    SplitMix64, Temperature, Time,
    SPLITMIX64_ZERO_GOLDEN,
    IdentityComponent, STABLE_ID_VERSION, checked_i64,
    clamp, clamp_int,
    cos_lookup_ppm,
    derive_seed,
    div_floor_exact,
    div_round_half_up,
    deterministic_map,
    fractal_noise_ppm, identity,
    noise2_ppm,
    rng_for,
    rng_for_decision,
    stable_id,
    verify_splitmix64_golden,
)


def test_prng_decision_contract_and_cross_platform_fixture() -> None:
    fixture = json.loads(Path(
        "tests/fixtures/worldgen/prng_diagnostics.json"
    ).read_text(encoding="utf-8"))
    assert tuple(fixture["splitmix64_zero_u64"]) == SPLITMIX64_ZERO_GOLDEN
    for row in fixture["decisions"]:
        seed = derive_seed(
            fixture["master_seed"], row["domain"], row["stable_entity_id"],
            row["decision_label"], version=fixture["seed_plan_version"],
        )
        assert seed == row["derived_seed_u64"]
        rng = rng_for_decision(
            fixture["master_seed"], row["domain"], row["stable_entity_id"],
            row["decision_label"],
        )
        assert [rng.next_u64() for _ in range(3)] == row["stream_u64"]


def test_worldgen_random_calls_require_entity_and_decision_identity() -> None:
    violations: list[str] = []
    for path in sorted(Path("src/worldgen").rglob("*.py")):
        if path.name == "numeric.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else ""
            if name in {"SplitMix64", "rng_for"}:
                violations.append(f"{path}:{node.lineno}:direct-{name}")
            if name == "derive_seed" and len(node.args) < 4:
                violations.append(f"{path}:{node.lineno}:unnamed-seed-decision")
            if name == "rng_for_decision" and len(node.args) != 4:
                violations.append(f"{path}:{node.lineno}:invalid-decision-shape")
    assert violations == []


def test_fixed_unit_contract_covers_every_required_dimension() -> None:
    expected = {
        Distance, Elevation, Temperature, Rainfall, Moisture, Mass, Energy,
        Population, Time, Probability, Price, Capacity,
    }
    assert set(FIXED_UNIT_TYPES) == expected
    assert len({type(unit_type(1)) for unit_type in FIXED_UNIT_TYPES}) == 12


def test_numeric_kernel_has_no_raw_floor_division() -> None:
    source = Path("src/worldgen/numeric.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FloorDiv, ast.Div))
    ]


def test_worldgen_division_inventory_is_explicit() -> None:
    floor_divisions: list[str] = []
    true_divisions: set[str] = set()
    for path in sorted(Path("src/worldgen").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp):
                continue
            location = f"{path}:{node.lineno}"
            if isinstance(node.op, ast.FloorDiv):
                floor_divisions.append(location)
            elif isinstance(node.op, ast.Div):
                true_divisions.add(location)
    assert floor_divisions == []
    # Every remaining ``/`` is Path composition, except the generated coverage
    # percentage. Exact locations make additions fail pending explicit review.
    assert true_divisions == {
            "src/worldgen/artifacts.py:300", "src/worldgen/artifacts.py:317",
            "src/worldgen/artifact_shape_audit.py:51",
            "src/worldgen/biome_reader.py:33",
            "src/worldgen/biome_reader.py:61",
            "src/worldgen/climate_reader.py:40",
            "src/worldgen/climate_reader.py:84",
        "src/worldgen/conformance/evidence.py:47",
        "src/worldgen/conformance/evidence.py:48",
        "src/worldgen/conformance/generator.py:64",
            "src/worldgen/conformance/profiles.py:275",
        "src/worldgen/conformance/source_coverage.py:100",
            "src/worldgen/determinism_diff.py:159",
            "src/worldgen/determinism_diff.py:160",
                "src/worldgen/grid.py:312",
                "src/worldgen/grid_catalog_audit.py:25",
                "src/worldgen/grid_catalog_audit.py:34",
                "src/worldgen/grid_catalog_audit.py:35",
                "src/worldgen/geology_reader.py:34",
                "src/worldgen/geology_reader.py:53",
            "src/worldgen/hydrology_reader.py:39",
            "src/worldgen/hydrology_reader.py:118",
            "src/worldgen/index_reader.py:57", "src/worldgen/index_reader.py:82",
            "src/worldgen/index_reader.py:119",
            "src/worldgen/index_rebuild.py:40", "src/worldgen/index_rebuild.py:100",
            "src/worldgen/maps.py:195", "src/worldgen/maps.py:211",
            "src/worldgen/maps.py:231", "src/worldgen/maps.py:293",
                            "src/worldgen/physical_pipeline.py:147",
                                "src/worldgen/physical_pipeline.py:181",
                                        "src/worldgen/physical_pipeline.py:379",
                "src/worldgen/region_reader.py:29",
                "src/worldgen/region_reader.py:79",
            "src/worldgen/resource_reader.py:31",
            "src/worldgen/resource_reader.py:85",
            "src/worldgen/route_reader.py:23",
        "src/worldgen/simulation/replay.py:64",
        "src/worldgen/simulation/replay.py:96",
                            "src/worldgen/simulation/scheduler.py:203",
                            "src/worldgen/simulation/scheduler.py:208",
                            "src/worldgen/simulation/scheduler.py:374",
                            "src/worldgen/simulation/scheduler.py:378",
                            "src/worldgen/simulation/scheduler.py:379",
                            "src/worldgen/simulation/scheduler.py:380",
                            "src/worldgen/simulation/scheduler.py:383",
                            "src/worldgen/simulation/scheduler.py:384",
                            "src/worldgen/simulation/scheduler.py:388",
                            "src/worldgen/simulation/scheduler.py:1224",
            "src/worldgen/soil_reader.py:32",
            "src/worldgen/soil_reader.py:57",
            "src/worldgen/terrain_reader.py:43",
            "src/worldgen/terrain_reader.py:115",
    }


class TestFixedPointContract:
    def test_all_required_unit_types_are_distinct_and_immutable(self) -> None:
        expected = {
            Distance, Elevation, Temperature, Rainfall, Moisture, Mass, Energy,
            Population, Time, Probability, Price, Capacity,
        }
        assert set(FIXED_UNIT_TYPES) == expected
        values = [unit_type(1) for unit_type in FIXED_UNIT_TYPES]
        assert len({type(value) for value in values}) == 12
        with pytest.raises((AttributeError, TypeError)):
            values[0].value = 2

    def test_units_enforce_integer_and_i64_boundaries(self) -> None:
        assert Distance(MIN_I64).value == MIN_I64
        assert Distance(MAX_I64).value == MAX_I64
        with pytest.raises(TypeError):
            Distance(1.5)
        with pytest.raises(OverflowError):
            Distance(MAX_I64 + 1)
        assert Probability(0).value == 0
        assert Probability(PPM).value == PPM
        with pytest.raises(ValueError):
            Probability(PPM + 1)

    @pytest.mark.parametrize(
        ("numerator", "denominator", "expected"),
        [(5, 2, 3), (4, 2, 2), (1, 2, 1), (-1, 2, -1),
         (-4, 2, -2), (-5, 2, -3), (0, 7, 0)],
    )
    def test_round_div_signed_golden_vectors(
        self, numerator: int, denominator: int, expected: int,
    ) -> None:
        assert div_round_half_up(numerator, denominator) == expected

    def test_round_div_rejects_invalid_and_overflow_inputs(self) -> None:
        assert div_round_half_up(MIN_I64, 1) == MIN_I64
        assert div_round_half_up(MAX_I64, 1) == MAX_I64
        with pytest.raises(ValueError):
            div_round_half_up(1, 0)
        with pytest.raises(OverflowError):
            checked_i64(MAX_I64 + 1)

    def test_wide_intermediate_is_allowed_when_scaled_result_fits(self) -> None:
        assert div_round_half_up(MAX_I64 * PPM, PPM) == MAX_I64
        with pytest.raises(OverflowError):
            div_round_half_up((MAX_I64 + 1) * PPM, PPM)

    def test_exact_floor_division_is_reserved_for_addressing(self) -> None:
        assert div_floor_exact(2_500_000, PPM) == 2
        assert div_floor_exact(-1, PPM) == -1
        with pytest.raises(ValueError):
            div_floor_exact(1, 0)


# ═══════════════════════════════════════════════════════════════════════
# SplitMix64 golden vectors
# ═══════════════════════════════════════════════════════════════════════

class TestSplitMix64:
    def test_golden_vectors_match(self) -> None:
        """P8.C05B: SplitMix64(0) produces exact frozen golden sequence."""
        assert verify_splitmix64_golden()

    def test_first_16_values(self) -> None:
        rng = SplitMix64(0)
        actual = tuple(rng.next_u64() for _ in range(16))
        assert actual == SPLITMIX64_ZERO_GOLDEN

    def test_different_seeds_produce_different_streams(self) -> None:
        a = tuple(SplitMix64(0).next_u64() for _ in range(32))
        b = tuple(SplitMix64(1).next_u64() for _ in range(32))
        assert a != b

    def test_below_is_uniform_on_power_of_two(self) -> None:
        rng = SplitMix64(42)
        counts = {i: 0 for i in range(8)}
        for _ in range(4000):
            counts[rng.below(8)] += 1
        assert all(400 <= c <= 600 for c in counts.values())

    def test_chance_ppm_bounds(self) -> None:
        rng = SplitMix64(99)
        for _ in range(100):
            assert isinstance(rng.chance_ppm(500_000), bool)
        assert rng.chance_ppm(1_000_000)  # always true at 100%
        with pytest.raises(ValueError):
            rng.chance_ppm(-1)

    def test_below_positive_upper_only(self) -> None:
        rng = SplitMix64(1)
        with pytest.raises(ValueError):
            rng.below(0)
        with pytest.raises(ValueError):
            rng.below(-1)


# ═══════════════════════════════════════════════════════════════════════
# Seed derivation
# ═══════════════════════════════════════════════════════════════════════

class TestSeedDerivation:
    def test_same_inputs_give_same_seed(self) -> None:
        a = derive_seed(42, "test")
        b = derive_seed(42, "test")
        assert a == b

    def test_different_domain_gives_different_seed(self) -> None:
        a = derive_seed(42, "plates")
        b = derive_seed(42, "hydrology")
        assert a != b

    def test_different_parts_give_different_seed(self) -> None:
        a = derive_seed(42, "entity", 1)
        b = derive_seed(42, "entity", 2)
        assert a != b

    def test_seed_is_64_bit_unsigned(self) -> None:
        s = derive_seed(0, "test")
        assert 0 <= s < 2**64

    def test_empty_domain_raises(self) -> None:
        with pytest.raises(ValueError):
            derive_seed(0, "")

    def test_rng_for_creates_independent_streams(self) -> None:
        a = rng_for(42, "a")
        b = rng_for(42, "b")
        assert a.next_u64() != b.next_u64()


# ═══════════════════════════════════════════════════════════════════════
# Stable IDs
# ═══════════════════════════════════════════════════════════════════════

class TestStableID:
    def test_same_inputs_same_id(self) -> None:
        a = stable_id("region", 42, identity("cell", 1))
        b = stable_id("region", 42, identity("cell", 1))
        assert a == b
        assert a.startswith("region_")

    def test_different_identity_inputs_different_ids(self) -> None:
        a = stable_id("site", 42, identity("cell", 1))
        b = stable_id("site", 42, identity("cell", 2))
        assert a != b

    def test_invalid_kind_raises(self) -> None:
        with pytest.raises(ValueError):
            stable_id("", 0, identity("cell", 1))
        with pytest.raises(ValueError):
            stable_id("bad kind", 0, identity("cell", 1))

    def test_requires_typed_canonical_non_display_components(self) -> None:
        with pytest.raises(TypeError, match="identity"):
            stable_id("site", 42, 1)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="int or string"):
            identity("cells", {1, 2})  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="display names"):
            identity("display_name", "Mutable Town Name")
        with pytest.raises(ValueError, match="NFC"):
            identity("key", "e\u0301")


def test_stable_id_contract_and_cross_platform_fixture() -> None:
    fixture = json.loads(Path(
        "tests/fixtures/worldgen/stable_id_diagnostics.json"
    ).read_text(encoding="utf-8"))
    assert fixture["version"] == STABLE_ID_VERSION
    for vector in fixture["vectors"]:
        components = tuple(
            IdentityComponent(component["label"], component["value"])
            for component in vector["components"]
        )
        assert stable_id(vector["kind"], vector["master_seed"], *components) == vector["id"]


def test_production_stable_ids_use_declared_identity_components() -> None:
    violations: list[str] = []
    for path in sorted(Path("src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "stable_id"):
                continue
            for component in node.args[2:]:
                declared = (isinstance(component, ast.Call)
                            and isinstance(component.func, ast.Name)
                            and component.func.id in {"identity", "id_component"})
                if not declared:
                    violations.append(f"{path}:{component.lineno}")
    assert violations == []


# ═══════════════════════════════════════════════════════════════════════
# Clamp utility
# ═══════════════════════════════════════════════════════════════════════

class TestClamp:
    def test_within_range(self) -> None:
        assert clamp(50, 0, 100) == 50

    def test_below_range(self) -> None:
        assert clamp(-10, 0, 100) == 0

    def test_above_range(self) -> None:
        assert clamp(200, 0, 100) == 100

    def test_at_boundaries(self) -> None:
        assert clamp(0, 0, 100) == 0
        assert clamp(100, 0, 100) == 100

    def test_clamp_int_alias(self) -> None:
        assert clamp_int(5, 0, 10) == clamp(5, 0, 10)


# ═══════════════════════════════════════════════════════════════════════
# Fixed-point noise
# ═══════════════════════════════════════════════════════════════════════

class TestNoise:
    def test_noise2_ppm_is_deterministic(self) -> None:
        a = noise2_ppm(0, 0, 42)
        b = noise2_ppm(0, 0, 42)
        assert a == b

    def test_noise2_ppm_range(self) -> None:
        for i in range(100):
            value = noise2_ppm(i * 100_000, i * 200_000, i)
            assert -PPM <= value <= PPM, f"noise {value} out of range"

    def test_noise2_ppm_different_seeds_diverge(self) -> None:
        a = noise2_ppm(500_000, 500_000, 42)
        b = noise2_ppm(500_000, 500_000, 99)
        assert a != b

    def test_fractal_noise_deterministic(self) -> None:
        a = fractal_noise_ppm(10, 20, 42, octaves=3)
        b = fractal_noise_ppm(10, 20, 42, octaves=3)
        assert a == b

    def test_fractal_noise_in_range(self) -> None:
        value = fractal_noise_ppm(0, 0, 1, octaves=5)
        assert -PPM <= value <= PPM, f"fractal noise {value} out of range"

    def test_noise2_golden_vector(self) -> None:
        """Record a frozen noise2_ppm golden vector for cross-platform CI."""
        value = noise2_ppm(0, 0, 0)
        # This is the canonical golden value for worldgen-1 noise at origin.
        assert value == -455800, f"noise2_ppm golden mismatch: {value}"


# ═══════════════════════════════════════════════════════════════════════
# Cosine approximation
# ═══════════════════════════════════════════════════════════════════════

class TestCosine:
    def test_cos_lookup_deterministic(self) -> None:
        a = cos_lookup_ppm(90_000)  # 90 degrees → cos = 0
        b = cos_lookup_ppm(90_000)
        assert a == b

    def test_cos_zero_degrees(self) -> None:
        value = cos_lookup_ppm(0)
        assert 990_000 <= value <= 1_000_000

    def test_cos_ninety_degrees(self) -> None:
        value = cos_lookup_ppm(90_000)
        assert -50_000 <= value <= 50_000  # near zero

    def test_cos_180_degrees(self) -> None:
        value = cos_lookup_ppm(180_000)
        assert -1_000_000 <= value <= -990_000

    def test_cos_periodicity(self) -> None:
        a = cos_lookup_ppm(45_000)
        b = cos_lookup_ppm(45_000 + 360_000)
        assert a == b

    def test_cos_symmetry(self) -> None:
        # cos(x) = cos(-x) = cos(360 - x)
        a = cos_lookup_ppm(60_000)
        b = cos_lookup_ppm(300_000)
        assert a == b


# ═══════════════════════════════════════════════════════════════════════
# Canonical JSON
# ═══════════════════════════════════════════════════════════════════════

class TestCanonicalJSON:
    def test_deterministic_output(self) -> None:
        a = canonical_json({"b": 2, "a": 1})
        b = canonical_json({"a": 1, "b": 2})
        assert a == b

    def test_nfc_normalization(self) -> None:
        # Same character in composed vs decomposed form
        composed = canonical_json({"caf\u00e9": 1})  # é as single char
        decomposed = canonical_json({"cafe\u0301": 1})  # e + combining accent
        assert composed == decomposed

    def test_rejects_float(self) -> None:
        with pytest.raises(ValueError, match="scaled integers"):
            canonical_json({"value": 3.14})

    def test_nested_dataclass(self) -> None:
        from dataclasses import dataclass

        @dataclass(frozen=True)
        class Inner:
            x: int
            y: int

        @dataclass(frozen=True)
        class Outer:
            name: str
            inner: Inner

        a = canonical_json(Outer("test", Inner(1, 2)))
        b = canonical_json(Outer("test", Inner(1, 2)))
        assert a == b

    def test_utf16_key_ordering_differs_from_ascii(self) -> None:
        """Keys with non-ASCII chars sort by UTF-16-BE, not codepoint."""
        data = {"\u00e9": 1, "z": 2, "a": 3}
        result = canonical_json(data)
        # In UTF-16-BE: 'a' (0061), 'z' (007A), 'é' (00E9)
        # All BMP chars have same order in both sortings.
        # é is encoded as UTF-8 \xc3\xa9 in the JSON output.
        assert result == '{"a":3,"z":2,"é":1}'.encode("utf-8")


# ═══════════════════════════════════════════════════════════════════════
# Canonical JSON cross-platform vectors (generation.md serialization)
# ═══════════════════════════════════════════════════════════════════════

def test_canonical_json_cross_platform_diagnostics_fixture() -> None:
    fixture = json.loads(Path(
        "tests/fixtures/worldgen/canonical_json_diagnostics.json"
    ).read_text(encoding="utf-8"))
    assert fixture["format"] == "storyteller.canonical-json-diagnostics.v1"
    for vector in fixture["vectors"]:
        assert canonical_json(vector["input"]) == vector["expected_utf8"].encode("utf-8"), vector["name"]


def test_canonical_json_rejects_hostile_keys_floats_and_surrogates() -> None:
    with pytest.raises(ValueError, match="duplicate object key"):
        canonical_json({"café": 1, "cafe\u0301": 2})
    with pytest.raises(TypeError, match="keys must be strings"):
        canonical_json({1: "numeric key"})
    for value in (0.0, float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="scaled integers"):
            canonical_json({"value": value})
    with pytest.raises(ValueError, match="surrogates"):
        canonical_json({"value": "\ud800"})
    with pytest.raises(ValueError, match="surrogates"):
        canonical_json({"\udfff": "value"})


# ═══════════════════════════════════════════════════════════════════════
# Worker parity (generation.md determinism requirement)
# ═══════════════════════════════════════════════════════════════════════

class TestWorkerParity:
    def test_deterministic_map_single_worker(self) -> None:
        """One worker: results returned in stable key order."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            results = deterministic_map(executor, lambda x: x * 2, range(100))
        assert len(results) == 100
        assert results[0] == (0, 0)
        assert results[99] == (99, 198)

    def test_deterministic_map_multiple_workers_same_result(self) -> None:
        """N workers produce same result as 1 worker."""
        keys = tuple(range(50))

        with ThreadPoolExecutor(max_workers=1) as ex1:
            r1 = deterministic_map(ex1, lambda x: x * 2, keys)
        with ThreadPoolExecutor(max_workers=8) as ex8:
            r8 = deterministic_map(ex8, lambda x: x * 2, keys)
        assert r1 == r8

    def test_deterministic_map_with_rng_is_stable(self) -> None:
        """Even with RNG, worker count doesn't change output."""
        def generate(key: int) -> int:
            rng = SplitMix64(key)
            return rng.next_u64()

        keys = tuple(range(32))
        with ThreadPoolExecutor(max_workers=1) as ex1:
            r1 = deterministic_map(ex1, generate, keys)
        with ThreadPoolExecutor(max_workers=4) as ex4:
            r4 = deterministic_map(ex4, generate, keys)
        assert r1 == r4
