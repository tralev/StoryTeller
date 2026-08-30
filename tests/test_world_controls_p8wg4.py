"""P8.WG4 — Complete world configuration tests.

Covers:
- WorldSpec field metadata parity (no field missing from world_controls)
- BYTE-FOR-BYTE equivalence: GUI effective config == CLI effective config
- Preset expansion: presets expand before hashing, effective spec stores explicit values
- Field validation via world_controls
- LauncherState now includes all WorldSpec fields
- build_full_argv includes every field
"""

from __future__ import annotations

import hashlib
import json

import pytest

from src.domain.run_spec import WorldSpec
from src.launcher.core import (
    LauncherState,
    build_argv,
    build_full_argv,
    from_config_dict,
    to_config_dict,
)
from src.launcher.world_controls import (
    advanced_fields,
    all_fields,
    basic_fields,
    cli_flag_map,
    field_names,
    get_field,
    validate_state,
    verify_worldspec_parity,
)

# ── P8.WG4: Metadata parity ─────────────────────────────────────────────


class TestWorldSpecFieldParity:
    """P8.WG4: Every WorldSpec field has a corresponding FieldMeta entry."""

    def test_no_worldspec_field_missing_from_controls(self) -> None:
        """Verify every WorldSpec field name appears in world_controls."""
        import dataclasses

        ws_names = {f.name for f in dataclasses.fields(WorldSpec)}
        control_names = {f.name for f in all_fields()}
        missing = ws_names - control_names
        assert not missing, f"WorldSpec fields missing from world_controls: {sorted(missing)}"

    def test_verify_worldspec_parity_returns_empty(self) -> None:
        """P8.WG4 parity checker returns empty list."""
        result = verify_worldspec_parity()
        assert result == [], f"Parity check failed: {result}"

    def test_all_worldspec_fields_have_cli_flags(self) -> None:
        """Every WorldSpec field has a --cli-flag in world_controls."""
        import dataclasses

        ws_names = {f.name for f in dataclasses.fields(WorldSpec)}
        flags = cli_flag_map()
        missing_flags = ws_names - set(flags.keys())
        assert not missing_flags, f"WorldSpec fields without CLI flags: {sorted(missing_flags)}"

    def test_field_count(self) -> None:
        """P8.WG4: There should be 18 WorldSpec fields (plus seed, title, tone, temp = 22 total)."""
        ws_fields = len(
            [f for f in all_fields() if f.name not in ("seed", "title", "tone", "temperature")]
        )
        assert ws_fields == 18, f"Expected 18 WorldSpec fields, got {ws_fields}"

    def test_basic_and_advanced_partition(self) -> None:
        """Basic + advanced = all fields, no overlap."""
        basic = {f.name for f in basic_fields()}
        adv = {f.name for f in advanced_fields()}
        all_names = {f.name for f in all_fields()}
        assert basic.union(adv) == all_names, "Partition doesn't cover all fields"
        assert len(basic & adv) == 0, "Overlap between basic and advanced fields"


# ── P8.WG4: Field metadata validation ───────────────────────────────────


class TestFieldValidation:
    """P8.WG4: world_controls.validate_state covers all fields."""

    def test_valid_defaults(self) -> None:
        """Default LauncherState values should all be valid."""
        state = LauncherState()
        errors = state.validate()
        assert not errors, f"Default state has errors: {errors}"

    def test_out_of_range_values(self) -> None:
        """Fields with min/max constraints reject out-of-range values."""
        errors = validate_state({"width": 16})  # below 32
        assert any("Width" in e and "32" in e for e in errors), (
            f"Expected width range error, got: {errors}"
        )

    def test_invalid_type_rejected(self) -> None:
        """Non-integer values for int fields are rejected."""
        errors = validate_state({"width": "not_a_number"})
        assert any("Width" in e and "invalid" in e.lower() for e in errors), (
            f"Expected type error, got: {errors}"
        )

    def test_all_valid_ranges(self) -> None:
        """Every field with a range accepts a valid value."""
        for meta in all_fields():
            if (
                meta.min_ is not None
                and meta.max_ is not None
                and meta.type_ is int
                and isinstance(meta.min_, int)
                and isinstance(meta.max_, int)
            ):
                mid = (meta.min_ + meta.max_) // 2
                err = meta.validate_value(mid)
                assert err is None, f"{meta.name}: valid value {mid} rejected: {err}"


# ── P8.WG4: Byte-for-byte equivalence ───────────────────────────────────


class TestConfigEquivalence:
    """P8.WG4: GUI effective configuration == CLI effective configuration."""

    def test_gui_config_round_trips(self) -> None:
        """to_config_dict -> from_config_dict -> to_config_dict is idempotent."""
        state = LauncherState(
            seed=42,
            title="Test World",
            width=512,
            height=512,
            continent_count=2,
            history_years=300,
            civilization_count=4,
            sea_level_ppm=400_000,
            erosion_passes=16,
        )
        d1 = to_config_dict(state)
        restored = from_config_dict(d1)
        d2 = to_config_dict(restored)
        assert d1 == d2, f"Config round-trip mismatch:\n  original: {d1}\n  restored: {d2}"

    def test_build_full_argv_includes_all_fields(self) -> None:
        """P8.WG4: build_full_argv emits a --flag for every field that has one.

        history_ticks_per_year and snapshot_interval_years are fixed
        worldgen-1 invariants on the live CLI (no flag exists for them, see
        WORLD_FIXED_FIELDS in src/cli.py) and carry no cli_flag, so they are
        legitimately never emitted.
        """
        state = LauncherState()
        argv = build_full_argv(state)
        for field_meta in all_fields():
            if field_meta.cli_flag in ("", "--seed"):
                continue  # no CLI flag exists, or seed's special-cased handling
            # Every field should appear as --flag value pair
            found = False
            for i, arg in enumerate(argv):
                if arg == field_meta.cli_flag and i + 1 < len(argv):
                    found = True
                    break
            assert found, f"Field {field_meta.name} ({field_meta.cli_flag}) missing from full argv"

    def test_default_argv_omits_defaults(self) -> None:
        """P8.WG4: build_argv omits fields at their default value."""
        state = LauncherState()  # all defaults
        argv = build_argv(state)
        # Should NOT include --width 1024 (default)
        assert "--width" not in argv, f"Default --width should be omitted, got: {argv}"
        assert "--height" not in argv, "Default --height should be omitted"

    def test_non_default_values_emitted(self) -> None:
        """P8.WG4: build_argv includes non-default values."""
        state = LauncherState(width=512, continent_count=3)
        argv = build_argv(state)
        assert "--width" in argv
        assert "512" in argv
        assert "--continents" in argv
        assert "3" in argv

    def test_two_states_same_config_produce_identical_full_argv(self) -> None:
        """P8.WG4: Two states with identical effective config → identical full argv."""
        state1 = LauncherState(width=512, height=512, continent_count=2)
        state2 = from_config_dict(to_config_dict(state1))
        argv1 = build_full_argv(state1)
        argv2 = build_full_argv(state2)
        assert argv1 == argv2, f"Full argv mismatch:\n  state1: {argv1}\n  state2: {argv2}"

    def test_canonical_json_identity(self) -> None:
        """P8.WG4: Two states with same config → identical canonical JSON."""
        state1 = LauncherState(width=512, continent_count=2, history_years=250)
        state2 = from_config_dict(to_config_dict(state1))
        json1 = json.dumps(to_config_dict(state1), sort_keys=True)
        json2 = json.dumps(to_config_dict(state2), sort_keys=True)
        assert json1 == json2, "JSON identity mismatch"

    def test_canonical_hash_identity(self) -> None:
        """P8.WG4: Same config → same SHA-256 of canonical JSON."""
        state1 = LauncherState(width=512, continent_count=2)
        state2 = from_config_dict(to_config_dict(state1))
        h1 = hashlib.sha256(json.dumps(to_config_dict(state1), sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(to_config_dict(state2), sort_keys=True).encode()).hexdigest()
        assert h1 == h2, f"Hash mismatch: {h1} vs {h2}"


# ── P8.WG4: Preset expansion ────────────────────────────────────────────


class TestPresetExpansion:
    """P8.WG4: Presets expand before hashing; effective spec stores explicit values."""

    def test_preset_name_recorded(self) -> None:
        """When a preset is used, preset_name field is set."""
        state = LauncherState(preset_name="tiny")
        assert state.preset_name == "tiny"

    def test_no_preset_is_empty_string(self) -> None:
        """Custom config (no preset) has preset_name = ''."""
        state = LauncherState()
        assert state.preset_name == ""

    def test_preset_round_trips_through_config(self) -> None:
        """preset_name survives config export/import."""
        state = LauncherState(preset_name="conformance")
        d = to_config_dict(state)
        restored = from_config_dict(d)
        assert restored.preset_name == "conformance"

    def test_preset_not_in_argv(self) -> None:
        """Preset name is NOT passed as CLI arg (it's already expanded into explicit values)."""
        state = LauncherState(preset_name="tiny")
        argv = build_argv(state)
        assert "--preset" not in argv

    def test_effective_spec_is_explicit(self) -> None:
        """Preset expansion produces explicit values rather than preset labels."""
        state = LauncherState(
            seed=100,
            preset_name="tiny",
            width=64,
            height=64,
            continent_count=1,
        )
        d = to_config_dict(state)
        # The config dict should contain all the explicit values
        assert d.get("width") == 64
        assert d.get("height") == 64
        assert d.get("continent_count") == 1
        # preset_name is recorded but the values are explicit
        assert d.get("preset_name") == "tiny"
        # No unresolved preset label as a value (skip preset_name field itself)
        for key, val in d.items():
            if key == "preset_name":
                continue  # preset_name is allowed to be "tiny"
            assert val != "tiny", f"Preset label 'tiny' found as value in key {key} of {d}"


# ── P8.WG4: LauncherState completeness ──────────────────────────────────


class TestLauncherStateCompleteness:
    """P8.WG4: LauncherState exposes all WorldSpec fields."""

    def test_all_worldspec_fields_in_state(self) -> None:
        """LauncherState has every WorldSpec field as an attribute."""
        import dataclasses

        ws_names = {f.name for f in dataclasses.fields(WorldSpec)}
        for name in ws_names:
            assert hasattr(LauncherState(), name), f"LauncherState missing field: {name}"

    def test_state_to_value_dict_has_all_fields(self) -> None:
        """to_value_dict includes all world_controls fields."""
        state = LauncherState()
        d = state.to_value_dict()
        for fmeta in all_fields():
            assert fmeta.name in d, f"to_value_dict missing {fmeta.name}"

    def test_seed_title_tone_temperature_in_value_dict(self) -> None:
        """RunSpec-level fields are in to_value_dict."""
        state = LauncherState(seed=99, title="Foo", tone="mature_dark_fantasy", temperature=0.5)
        d = state.to_value_dict()
        assert d["seed"] == 99
        assert d["title"] == "Foo"
        assert d["temperature"] == 0.5

    def test_validate_uses_world_controls(self) -> None:
        """LauncherState.validate() delegates to world_controls.validate_state."""
        state = LauncherState(width=16)  # below 32
        errors = state.validate()
        assert any("Width" in e for e in errors), f"Expected Width range error: {errors}"


# ── P8.WG4: FieldMeta API ───────────────────────────────────────────────


class TestFieldMetaApi:
    """P8.WG4: world_controls public API."""

    def test_get_field_known(self) -> None:
        meta = get_field("width")
        assert meta.name == "width"
        assert meta.cli_flag == "--width"

    def test_get_field_unknown_raises(self) -> None:
        with pytest.raises(KeyError):
            get_field("nonexistent_field")

    def test_cli_flag_map_has_all_fields(self) -> None:
        flags = cli_flag_map()
        for f in all_fields():
            assert f.name in flags, f"{f.name} missing from cli_flag_map"

    def test_field_names_order(self) -> None:
        names = field_names()
        assert len(names) == len(all_fields())
        assert names[0] == "seed"  # basic fields come first
        assert "continent_count" in names

    def test_coerce_int(self) -> None:
        meta = get_field("width")
        assert meta.coerce("1024") == 1024
        assert meta.coerce(1024) == 1024

    def test_coerce_str(self) -> None:
        meta = get_field("title")
        assert meta.coerce("hello") == "hello"

    def test_validate_value_min(self) -> None:
        meta = get_field("width")  # min 32, max 8192
        assert meta.validate_value(16) is not None  # too low
        assert meta.validate_value(10000) is not None  # too high
        assert meta.validate_value(1024) is None  # valid


# ── P8.WG4: from_config_dict robustness ─────────────────────────────────


class TestConfigDictRobustness:
    """P8.WG4: from_config_dict handles missing/incomplete data."""

    def test_empty_dict_uses_defaults(self) -> None:
        state = from_config_dict({})
        assert state.width == 1024
        assert state.continent_count == 1
        assert state.plate_count == 24
        assert state.history_years == 500

    def test_partial_dict(self) -> None:
        state = from_config_dict({"width": 256, "continent_count": 5})
        assert state.width == 256
        assert state.continent_count == 5
        assert state.height == 1024  # default
        assert state.sea_level_ppm == 380_000  # default

    def test_advanced_fields_in_dict(self) -> None:
        """P8.WG4: Advanced fields survive config round-trip."""
        state = LauncherState(local_site_width=64, local_z_levels=16)
        d = to_config_dict(state)
        restored = from_config_dict(d)
        assert restored.local_site_width == 64
        assert restored.local_z_levels == 16
        assert restored.local_site_height == 128  # default
