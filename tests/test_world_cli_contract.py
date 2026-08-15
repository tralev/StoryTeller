"""One-to-one CLI, GenerationRequest, and RunSpec world-control contract."""
from __future__ import annotations

import argparse
from dataclasses import fields

import pytest

from src.application.models import GenerationRequest
from src.cli import (WORLD_CLI_BINDINGS, WORLD_FIXED_FIELDS,
                     add_world_spec_arguments, world_spec_cli_kwargs)
from src.domain.run_spec import WorldSpec


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    add_world_spec_arguments(parser)
    return parser


def test_every_world_field_is_exposed_or_explicitly_fixed() -> None:
    names = {item.name for item in fields(WorldSpec)}
    assert set(WORLD_CLI_BINDINGS).isdisjoint(WORLD_FIXED_FIELDS)
    assert set(WORLD_CLI_BINDINGS) | set(WORLD_FIXED_FIELDS) == names
    assert WORLD_FIXED_FIELDS == {
        "history_ticks_per_year": 12,
        "snapshot_interval_years": 10,
    }


def test_every_cli_world_control_round_trips_to_run_spec() -> None:
    values = {
        "width": 96, "height": 64, "continent_count": 2,
        "metres_per_world_cell": 9000, "plate_count": 7,
        "minimum_continent_cells": 64, "history_years": 80,
        "civilization_count": 5, "sea_level_ppm": 410000,
        "axial_tilt_millidegrees": 22000, "erosion_passes": 6,
        "climate_relaxation_passes": 12, "local_site_width": 64,
        "local_site_height": 96, "local_z_levels": 20,
        "local_cell_millimetres": 1500,
    }
    argv: list[str] = []
    for field_name, (flag, _) in WORLD_CLI_BINDINGS.items():
        argv.extend((flag, str(values[field_name])))
    parsed = _parser().parse_args(argv)
    request = GenerationRequest(seed=17, **world_spec_cli_kwargs(parsed))
    assert request.to_run_spec().world.to_dict() == {**values, **WORLD_FIXED_FIELDS}


def test_canonical_world_mapping_and_cli_are_equivalent() -> None:
    parsed = _parser().parse_args([])
    cli_world = GenerationRequest(seed=17, **world_spec_cli_kwargs(parsed)).to_run_spec().world
    config_world = WorldSpec.from_dict(WorldSpec().to_dict())
    assert cli_world == config_world


def test_fixed_invariants_are_not_silent_cli_options() -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(["--history-ticks-per-year", "13"])


def test_unknown_world_mapping_field_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown world fields"):
        WorldSpec.from_dict({**WorldSpec().to_dict(), "ignored_control": 1})
