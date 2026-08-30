"""WG-LOCAL-006 synchronous conserved water/magma evidence."""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from src.world.views import WorldView
from src.worldgen.local_maps import generate_local_maps, validate_local_map
from src.worldgen.local_physics import (
    HeatCell,
    HeatNonConvergenceError,
    HeatState,
    MagmaCell,
    MagmaNonConvergenceError,
    MagmaSimulation,
    MagmaState,
    StructuralCell,
    StructuralNonConvergenceError,
    StructuralState,
    WaterCell,
    WaterNonConvergenceError,
    WaterState,
    derive_site_heat_simulation,
    derive_site_magma_simulation,
    derive_site_structural_simulation,
    derive_site_water_simulation,
    heat_simulation_from_mapping,
    magma_simulation_from_mapping,
    simulate_heat,
    simulate_magma,
    simulate_structure,
    simulate_water,
    step_water,
    structural_simulation_from_mapping,
    validate_fluid_exclusion,
    validate_heat_simulation,
    validate_magma_simulation,
    validate_structural_simulation,
    validate_water_simulation,
    validate_water_state,
    water_simulation_from_mapping,
)


def _state(*cells: WaterCell) -> WaterState:
    return WaterState(0, True, tuple(sorted(cells)))


def test_water_falls_then_commits_a_stable_conserved_boundary() -> None:
    initial = _state(
        WaterCell((1, 1, 0), 0, 100),
        WaterCell((1, 1, 1), 100, 100),
    )
    simulation = simulate_water(initial, max_iterations=3)
    assert tuple(cell.volume for cell in simulation.final.cells) == (100, 0)
    assert len(simulation.ledgers) == 2
    assert simulation.ledgers[0].before_volume == simulation.ledgers[0].after_volume == 100
    assert simulation.ledgers[-1].transfers == ()
    validate_water_simulation(simulation)


def test_horizontal_equalization_is_integer_exact_and_conserved() -> None:
    initial = _state(
        WaterCell((0, 0, 0), 100, 100),
        WaterCell((1, 0, 0), 0, 100),
    )
    final, ledger = step_water(initial)
    assert tuple(cell.volume for cell in final.cells) == (50, 50)
    assert ledger.before_volume == ledger.after_volume == 100
    assert sum(item.amount for item in ledger.transfers) == 50


def test_competing_proposals_use_frozen_order_without_overfill() -> None:
    initial = _state(
        WaterCell((0, 0, 0), 100, 100),
        WaterCell((1, 0, 0), 0, 60),
        WaterCell((2, 0, 0), 100, 100),
    )
    final, ledger = step_water(initial)
    assert tuple(cell.volume for cell in final.cells) == (50, 60, 90)
    assert tuple(item.source for item in ledger.transfers) == ((0, 0, 0), (2, 0, 0))
    assert sum(cell.volume for cell in final.cells) == 200


def test_water_rejects_open_boundaries_and_invalid_volumes() -> None:
    with pytest.raises(ValueError, match="unsealed"):
        validate_water_state(WaterState(0, False, (WaterCell((0, 0, 0), 1, 1),)))
    with pytest.raises(ValueError, match="invalid cell"):
        validate_water_state(_state(WaterCell((0, 0, 0), 2, 1)))


def test_water_has_stable_nonconvergence_diagnostic() -> None:
    initial = _state(
        WaterCell((0, 0, 0), 100, 100),
        WaterCell((1, 0, 0), 0, 100),
        WaterCell((2, 0, 0), 0, 100),
    )
    with pytest.raises(WaterNonConvergenceError) as captured:
        simulate_water(initial, max_iterations=1)
    assert str(captured.value) == ("WG-LOCAL-WATER-NONCONVERGENCE: iterations=1; volume=100")


def test_water_replay_rejects_ledger_and_final_state_tampering() -> None:
    initial = _state(
        WaterCell((0, 0, 0), 100, 100),
        WaterCell((1, 0, 0), 0, 100),
    )
    simulation = simulate_water(initial, max_iterations=3)
    first = replace(simulation.ledgers[0], after_volume=999)
    with pytest.raises(ValueError, match="ledger divergence"):
        validate_water_simulation(replace(simulation, ledgers=(first, *simulation.ledgers[1:])))
    with pytest.raises(ValueError, match="final state divergence"):
        validate_water_simulation(replace(simulation, final=initial))


@pytest.fixture(scope="module")
def generated_local_maps(phase4_world):
    return generate_local_maps(WorldView(phase4_world))


def test_every_site_derives_and_persists_water_from_occupants(generated_local_maps) -> None:
    for local in generated_local_maps:
        assert local.water_simulation is not None
        assert local.water_simulation == derive_site_water_simulation(
            local.width, local.height, local.z_levels, local.features
        )
        assert local.water_simulation.converged
        assert local.water_simulation.ledgers[-1].transfers == ()
        validate_local_map(local)


def test_site_water_derivation_is_feature_order_independent(generated_local_maps) -> None:
    local = generated_local_maps[0]
    assert derive_site_water_simulation(
        local.width, local.height, local.z_levels, local.features
    ) == derive_site_water_simulation(
        local.width, local.height, local.z_levels, tuple(reversed(local.features))
    )


def test_persisted_water_reader_is_strict_and_replays(generated_local_maps) -> None:
    simulation = generated_local_maps[0].water_simulation
    assert simulation is not None
    payload = asdict(simulation)
    assert water_simulation_from_mapping(payload) == simulation
    with pytest.raises(ValueError, match="WATER-READ"):
        water_simulation_from_mapping({**payload, "invented": True})
    bad_ledger = {**payload["ledgers"][0], "after_volume": 999_999}
    with pytest.raises(ValueError, match="WATER-REPLAY"):
        water_simulation_from_mapping(
            {
                **payload,
                "ledgers": (bad_ledger, *payload["ledgers"][1:]),
            }
        )


def test_magma_is_separately_typed_viscous_and_conserved() -> None:
    initial = MagmaState(
        0,
        True,
        (
            MagmaCell((1, 1, 0), 0, 1_000),
            MagmaCell((1, 1, 1), 1_000, 1_000),
        ),
    )
    simulation = simulate_magma(initial, max_iterations=6)
    assert len(simulation.ledgers) == 5
    assert all(
        transfer.amount <= 250 for ledger in simulation.ledgers for transfer in ledger.transfers
    )
    assert sum(cell.volume for cell in simulation.final.cells) == 1_000
    assert tuple(cell.volume for cell in simulation.final.cells) == (1_000, 0)
    validate_magma_simulation(simulation)


def test_magma_has_stable_nonconvergence_and_replay_diagnostics() -> None:
    initial = MagmaState(
        0,
        True,
        (
            MagmaCell((0, 0, 0), 0, 1_000),
            MagmaCell((0, 0, 1), 1_000, 1_000),
        ),
    )
    with pytest.raises(MagmaNonConvergenceError) as captured:
        simulate_magma(initial, max_iterations=1)
    assert str(captured.value) == ("WG-LOCAL-MAGMA-NONCONVERGENCE: iterations=1; volume=1000")

    simulation = simulate_magma(initial, max_iterations=6)
    forged = replace(simulation.ledgers[0], after_volume=999)
    with pytest.raises(ValueError, match="MAGMA-REPLAY: ledger divergence"):
        validate_magma_simulation(
            replace(
                simulation,
                ledgers=(forged, *simulation.ledgers[1:]),
            )
        )


def test_every_site_persists_geology_derived_magma_without_water_overlap(
    generated_local_maps,
) -> None:
    for local in generated_local_maps:
        assert local.water_simulation is not None
        assert local.magma_simulation is not None
        validate_fluid_exclusion(local.water_simulation, local.magma_simulation)
        payload = asdict(local.magma_simulation)
        assert magma_simulation_from_mapping(payload) == local.magma_simulation


def test_site_magma_derivation_is_order_independent_and_reader_is_strict(
    generated_local_maps,
) -> None:
    local = generated_local_maps[0]
    simulation = derive_site_magma_simulation(
        local.width,
        local.height,
        local.z_levels,
        local.features,
    )
    assert simulation == derive_site_magma_simulation(
        local.width,
        local.height,
        local.z_levels,
        tuple(reversed(local.features)),
    )
    payload = asdict(simulation)
    with pytest.raises(ValueError, match="MAGMA-READ"):
        magma_simulation_from_mapping({**payload, "invented": True})


def test_water_magma_exclusion_checks_every_aligned_tick() -> None:
    water = simulate_water(
        _state(
            WaterCell((0, 0, 0), 100, 100),
            WaterCell((1, 0, 0), 0, 100),
        ),
        max_iterations=3,
    )
    magma_initial = MagmaState(
        0,
        True,
        (
            MagmaCell((0, 0, 0), 100, 100),
            MagmaCell((0, 0, 1), 0, 100),
        ),
    )
    magma = MagmaSimulation(magma_initial, magma_initial, (), True)
    with pytest.raises(ValueError, match="FLUID-EXCLUSION: overlap at tick 0"):
        validate_fluid_exclusion(water, magma)


def test_heat_conducts_synchronously_and_conserves_integer_energy() -> None:
    initial = HeatState(
        0,
        True,
        (
            HeatCell((0, 0, 0), 1_600, 2_000, 1_000),
            HeatCell((0, 0, 1), 200, 2_000, 1_000),
        ),
    )
    simulation = simulate_heat(initial, max_iterations=16)
    assert simulation.converged
    assert sum(cell.energy for cell in simulation.final.cells) == 1_800
    assert simulation.ledgers[-1].transfers == ()
    assert all(
        transfer.amount <= 200 for ledger in simulation.ledgers for transfer in ledger.transfers
    )
    validate_heat_simulation(simulation)


def test_heat_has_stable_nonconvergence_and_replay_diagnostics() -> None:
    initial = HeatState(
        0,
        True,
        (
            HeatCell((0, 0, 0), 1_600, 2_000, 1_000),
            HeatCell((0, 0, 1), 200, 2_000, 1_000),
        ),
    )
    with pytest.raises(HeatNonConvergenceError) as captured:
        simulate_heat(initial, max_iterations=1)
    assert str(captured.value) == ("WG-LOCAL-HEAT-NONCONVERGENCE: iterations=1; energy=1800")
    simulation = simulate_heat(initial, max_iterations=16)
    forged = replace(simulation.ledgers[0], after_energy=999)
    with pytest.raises(ValueError, match="HEAT-REPLAY: ledger divergence"):
        validate_heat_simulation(
            replace(
                simulation,
                ledgers=(forged, *simulation.ledgers[1:]),
            )
        )


def test_every_site_persists_replayable_source_derived_heat(generated_local_maps) -> None:
    for local in generated_local_maps:
        assert local.magma_simulation is not None
        assert local.heat_simulation is not None
        assert local.heat_simulation == derive_site_heat_simulation(
            local.width,
            local.height,
            local.z_levels,
            local.features,
            local.magma_simulation,
        )
        payload = asdict(local.heat_simulation)
        assert heat_simulation_from_mapping(payload) == local.heat_simulation
        with pytest.raises(ValueError, match="HEAT-READ"):
            heat_simulation_from_mapping({**payload, "invented": True})


def test_structure_collapses_in_frozen_cascade_and_conserves_mass() -> None:
    heat = HeatState(0, True, (HeatCell((3, 3, 3), 0, 2_000, 1_000),))
    initial = StructuralState(
        0,
        (
            StructuralCell((0, 0, 0), 500, 1_000, False, False, ("construction",)),
            StructuralCell((0, 0, 1), 500, 1_000, False, False, ("construction",)),
        ),
        (),
    )
    simulation = simulate_structure(initial, heat, max_iterations=4)
    assert tuple(len(ledger.failures) for ledger in simulation.ledgers) == (1, 1, 0)
    assert simulation.ledgers[0].failures[0].coordinate == (0, 0, 0)
    assert simulation.ledgers[1].failures[0].coordinate == (0, 0, 1)
    assert sum(item.mass for item in simulation.final.debris) == 1_000
    assert all(ledger.before_mass == ledger.after_mass for ledger in simulation.ledgers)
    validate_structural_simulation(simulation, heat)


def test_structure_has_stable_bounded_nonconvergence_diagnostic() -> None:
    heat = HeatState(0, True, (HeatCell((3, 3, 3), 0, 2_000, 1_000),))
    initial = StructuralState(
        0,
        tuple(
            StructuralCell((0, 0, z), 500, 1_000, False, False, ("construction",)) for z in range(3)
        ),
        (),
    )
    with pytest.raises(StructuralNonConvergenceError) as captured:
        simulate_structure(initial, heat, max_iterations=1)
    assert str(captured.value) == ("WG-LOCAL-STRUCTURE-NONCONVERGENCE: iterations=1; mass=1500")


def test_heat_weakening_is_explicit_and_replay_rejects_tampering() -> None:
    heat = HeatState(7, True, (HeatCell((0, 0, 0), 1_600, 2_000, 1_000),))
    initial = StructuralState(
        0, (StructuralCell((0, 0, 0), 800, 1_000, True, False, ("support",)),), ()
    )
    simulation = simulate_structure(initial, heat, max_iterations=3)
    assert simulation.ledgers[0].failures[0].mass == 800
    forged = replace(simulation.ledgers[0], after_mass=799)
    with pytest.raises(ValueError, match="STRUCTURE-REPLAY: ledger divergence"):
        validate_structural_simulation(
            replace(
                simulation,
                ledgers=(forged, *simulation.ledgers[1:]),
            ),
            heat,
        )


def test_every_site_persists_source_derived_structure(generated_local_maps) -> None:
    for local in generated_local_maps:
        assert local.heat_simulation is not None
        assert local.structural_simulation is not None
        assert local.structural_simulation == derive_site_structural_simulation(
            local.features,
            local.heat_simulation,
        )
        payload = asdict(local.structural_simulation)
        assert (
            structural_simulation_from_mapping(
                payload,
                local.heat_simulation.final,
            )
            == local.structural_simulation
        )
        with pytest.raises(ValueError, match="STRUCTURE-READ"):
            structural_simulation_from_mapping(
                {**payload, "invented": True},
                local.heat_simulation.final,
            )
