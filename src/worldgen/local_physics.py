"""Bounded synchronous integer local-fluid simulation with conservation ledgers."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .numeric import div_floor_exact


@dataclass(frozen=True, order=True)
class WaterCell:
    coordinate: tuple[int, int, int]
    volume: int
    capacity: int


@dataclass(frozen=True)
class WaterState:
    tick: int
    sealed_boundary: bool
    cells: tuple[WaterCell, ...]


@dataclass(frozen=True, order=True)
class WaterTransfer:
    priority: int
    source: tuple[int, int, int]
    target: tuple[int, int, int]
    amount: int


@dataclass(frozen=True)
class WaterLedger:
    tick: int
    before_volume: int
    after_volume: int
    transfers: tuple[WaterTransfer, ...]


@dataclass(frozen=True)
class WaterSimulation:
    initial: WaterState
    final: WaterState
    ledgers: tuple[WaterLedger, ...]
    converged: bool


@dataclass(frozen=True, order=True)
class MagmaCell:
    coordinate: tuple[int, int, int]
    volume: int
    capacity: int


@dataclass(frozen=True)
class MagmaState:
    tick: int
    sealed_boundary: bool
    cells: tuple[MagmaCell, ...]


@dataclass(frozen=True, order=True)
class MagmaTransfer:
    priority: int
    source: tuple[int, int, int]
    target: tuple[int, int, int]
    amount: int


@dataclass(frozen=True)
class MagmaLedger:
    tick: int
    before_volume: int
    after_volume: int
    transfers: tuple[MagmaTransfer, ...]


@dataclass(frozen=True)
class MagmaSimulation:
    initial: MagmaState
    final: MagmaState
    ledgers: tuple[MagmaLedger, ...]
    converged: bool


@dataclass(frozen=True, order=True)
class HeatCell:
    coordinate: tuple[int, int, int]
    energy: int
    capacity: int
    conductivity: int


@dataclass(frozen=True)
class HeatState:
    tick: int
    sealed_boundary: bool
    cells: tuple[HeatCell, ...]


@dataclass(frozen=True, order=True)
class HeatTransfer:
    source: tuple[int, int, int]
    target: tuple[int, int, int]
    amount: int


@dataclass(frozen=True)
class HeatLedger:
    tick: int
    before_energy: int
    after_energy: int
    transfers: tuple[HeatTransfer, ...]


@dataclass(frozen=True)
class HeatSimulation:
    initial: HeatState
    final: HeatState
    ledgers: tuple[HeatLedger, ...]
    converged: bool


@dataclass(frozen=True, order=True)
class StructuralCell:
    coordinate: tuple[int, int, int]
    load: int
    strength: int
    foundation: bool
    failed: bool
    source_ids: tuple[str, ...]


@dataclass(frozen=True, order=True)
class StructuralDebris:
    coordinate: tuple[int, int, int]
    mass: int
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class StructuralState:
    tick: int
    cells: tuple[StructuralCell, ...]
    debris: tuple[StructuralDebris, ...]


@dataclass(frozen=True)
class StructuralLedger:
    tick: int
    before_mass: int
    after_mass: int
    failures: tuple[StructuralDebris, ...]


@dataclass(frozen=True)
class StructuralSimulation:
    initial: StructuralState
    final: StructuralState
    ledgers: tuple[StructuralLedger, ...]
    converged: bool
    heat_final_tick: int


class WaterNonConvergenceError(ValueError):
    def __init__(self, iterations: int, final_volume: int) -> None:
        self.iterations = iterations
        self.final_volume = final_volume
        super().__init__(
            f"WG-LOCAL-WATER-NONCONVERGENCE: iterations={iterations}; "
            f"volume={final_volume}"
        )


class MagmaNonConvergenceError(ValueError):
    def __init__(self, iterations: int, final_volume: int) -> None:
        self.iterations = iterations
        self.final_volume = final_volume
        super().__init__(
            f"WG-LOCAL-MAGMA-NONCONVERGENCE: iterations={iterations}; "
            f"volume={final_volume}"
        )


class HeatNonConvergenceError(ValueError):
    def __init__(self, iterations: int, final_energy: int) -> None:
        self.iterations = iterations
        self.final_energy = final_energy
        super().__init__(
            f"WG-LOCAL-HEAT-NONCONVERGENCE: iterations={iterations}; "
            f"energy={final_energy}"
        )


class StructuralNonConvergenceError(ValueError):
    def __init__(self, iterations: int, final_mass: int) -> None:
        super().__init__(
            f"WG-LOCAL-STRUCTURE-NONCONVERGENCE: iterations={iterations}; "
            f"mass={final_mass}"
        )


def validate_water_state(state: WaterState) -> None:
    if state.tick < 0 or not state.sealed_boundary:
        raise ValueError("WG-LOCAL-WATER-STATE: invalid tick or unsealed boundary")
    if state.cells != tuple(sorted(state.cells)):
        raise ValueError("WG-LOCAL-WATER-STATE: cells must be canonical")
    coordinates = tuple(cell.coordinate for cell in state.cells)
    if len(coordinates) != len(set(coordinates)):
        raise ValueError("WG-LOCAL-WATER-STATE: duplicate coordinate")
    if any(
        cell.capacity <= 0 or cell.volume < 0 or cell.volume > cell.capacity
        or any(value < 0 for value in cell.coordinate)
        for cell in state.cells
    ):
        raise ValueError("WG-LOCAL-WATER-STATE: invalid cell volume, capacity, or coordinate")


def _propose_water(state: WaterState) -> tuple[WaterTransfer, ...]:
    by_coordinate = {cell.coordinate: cell for cell in state.cells}
    proposals: list[WaterTransfer] = []
    for cell in state.cells:
        x, y, z = cell.coordinate
        below = by_coordinate.get((x, y, z - 1)) if z > 0 else None
        if below is not None and cell.volume > 0 and below.volume < below.capacity:
            proposals.append(WaterTransfer(
                0, cell.coordinate, below.coordinate,
                min(cell.volume, below.capacity - below.volume),
            ))
        for neighbor_coordinate in ((x + 1, y, z), (x, y + 1, z)):
            neighbor = by_coordinate.get(neighbor_coordinate)
            if neighbor is None or cell.volume == neighbor.volume:
                continue
            source, target = (cell, neighbor) if cell.volume > neighbor.volume else (neighbor, cell)
            amount = min(
                div_floor_exact(source.volume - target.volume, 2),
                target.capacity - target.volume,
            )
            if amount > 0:
                proposals.append(WaterTransfer(
                    1, source.coordinate, target.coordinate, amount,
                ))
    return tuple(sorted(set(proposals)))


def step_water(state: WaterState) -> tuple[WaterState, WaterLedger]:
    """Resolve proposals from one immutable start state exactly once."""
    validate_water_state(state)
    volumes = {cell.coordinate: cell.volume for cell in state.cells}
    capacities = {cell.coordinate: cell.capacity for cell in state.cells}
    accepted: list[WaterTransfer] = []
    for proposal in _propose_water(state):
        amount = min(
            proposal.amount,
            volumes[proposal.source],
            capacities[proposal.target] - volumes[proposal.target],
        )
        if amount <= 0:
            continue
        volumes[proposal.source] -= amount
        volumes[proposal.target] += amount
        accepted.append(WaterTransfer(
            proposal.priority, proposal.source, proposal.target, amount,
        ))
    cells = tuple(
        WaterCell(cell.coordinate, volumes[cell.coordinate], cell.capacity)
        for cell in state.cells
    )
    result = WaterState(state.tick + 1, True, cells)
    before = sum(cell.volume for cell in state.cells)
    after = sum(cell.volume for cell in result.cells)
    ledger = WaterLedger(state.tick, before, after, tuple(accepted))
    if before != after:
        raise ValueError("WG-LOCAL-WATER-CONSERVATION: water volume changed")
    return result, ledger


def simulate_water(state: WaterState, *, max_iterations: int) -> WaterSimulation:
    """Run until stable within the explicit iteration budget."""
    if max_iterations <= 0:
        raise ValueError("WG-LOCAL-WATER-LIMIT: max_iterations must be positive")
    initial = state
    ledgers: list[WaterLedger] = []
    for _ in range(max_iterations):
        state, ledger = step_water(state)
        ledgers.append(ledger)
        if not ledger.transfers:
            return WaterSimulation(initial, state, tuple(ledgers), True)
    if _propose_water(state):
        raise WaterNonConvergenceError(
            max_iterations, sum(cell.volume for cell in state.cells),
        )
    return WaterSimulation(initial, state, tuple(ledgers), True)


def validate_water_simulation(simulation: WaterSimulation) -> None:
    """Replay every committed tick and reject ledger or final-state forgery."""
    state = simulation.initial
    for expected in simulation.ledgers:
        state, actual = step_water(state)
        if actual != expected:
            raise ValueError("WG-LOCAL-WATER-REPLAY: ledger divergence")
    if not simulation.converged or state != simulation.final:
        raise ValueError("WG-LOCAL-WATER-REPLAY: final state divergence")
    if not simulation.ledgers or simulation.ledgers[-1].transfers:
        raise ValueError("WG-LOCAL-WATER-REPLAY: convergence boundary missing")


def validate_magma_state(state: MagmaState) -> None:
    if state.tick < 0 or not state.sealed_boundary or state.cells != tuple(sorted(state.cells)):
        raise ValueError("WG-LOCAL-MAGMA-STATE: invalid tick, boundary, or ordering")
    coordinates = tuple(cell.coordinate for cell in state.cells)
    if len(coordinates) != len(set(coordinates)) or any(
        cell.capacity <= 0 or not 0 <= cell.volume <= cell.capacity
        or any(value < 0 for value in cell.coordinate)
        for cell in state.cells
    ):
        raise ValueError("WG-LOCAL-MAGMA-STATE: invalid cell")


def _propose_magma(state: MagmaState) -> tuple[MagmaTransfer, ...]:
    by_coordinate = {cell.coordinate: cell for cell in state.cells}
    proposals: list[MagmaTransfer] = []
    for cell in state.cells:
        x, y, z = cell.coordinate
        below = by_coordinate.get((x, y, z - 1)) if z > 0 else None
        if below is not None and cell.volume > 0 and below.volume < below.capacity:
            proposals.append(MagmaTransfer(
                0, cell.coordinate, below.coordinate,
                min(250, cell.volume, below.capacity - below.volume),
            ))
        for neighbor_coordinate in ((x + 1, y, z), (x, y + 1, z)):
            neighbor = by_coordinate.get(neighbor_coordinate)
            if neighbor is None or cell.volume == neighbor.volume:
                continue
            source, target = (cell, neighbor) if cell.volume > neighbor.volume else (neighbor, cell)
            amount = min(
                100, div_floor_exact(source.volume - target.volume, 4),
                target.capacity - target.volume,
            )
            if amount > 0:
                proposals.append(MagmaTransfer(
                    1, source.coordinate, target.coordinate, amount,
                ))
    return tuple(sorted(set(proposals)))


def step_magma(state: MagmaState) -> tuple[MagmaState, MagmaLedger]:
    """Resolve viscous magma proposals from one immutable start state."""
    validate_magma_state(state)
    volumes = {cell.coordinate: cell.volume for cell in state.cells}
    capacities = {cell.coordinate: cell.capacity for cell in state.cells}
    accepted: list[MagmaTransfer] = []
    for proposal in _propose_magma(state):
        amount = min(
            proposal.amount, volumes[proposal.source],
            capacities[proposal.target] - volumes[proposal.target],
        )
        if amount <= 0:
            continue
        volumes[proposal.source] -= amount
        volumes[proposal.target] += amount
        accepted.append(MagmaTransfer(
            proposal.priority, proposal.source, proposal.target, amount,
        ))
    result = MagmaState(state.tick + 1, True, tuple(
        MagmaCell(cell.coordinate, volumes[cell.coordinate], cell.capacity)
        for cell in state.cells
    ))
    before, after = (
        sum(cell.volume for cell in state.cells),
        sum(cell.volume for cell in result.cells),
    )
    if before != after:
        raise ValueError("WG-LOCAL-MAGMA-CONSERVATION: magma volume changed")
    return result, MagmaLedger(state.tick, before, after, tuple(accepted))


def simulate_magma(state: MagmaState, *, max_iterations: int) -> MagmaSimulation:
    if max_iterations <= 0:
        raise ValueError("WG-LOCAL-MAGMA-LIMIT: max_iterations must be positive")
    initial = state
    ledgers: list[MagmaLedger] = []
    for _ in range(max_iterations):
        state, ledger = step_magma(state)
        ledgers.append(ledger)
        if not ledger.transfers:
            return MagmaSimulation(initial, state, tuple(ledgers), True)
    if _propose_magma(state):
        raise MagmaNonConvergenceError(
            max_iterations, sum(cell.volume for cell in state.cells),
        )
    return MagmaSimulation(initial, state, tuple(ledgers), True)


def validate_magma_simulation(simulation: MagmaSimulation) -> None:
    state = simulation.initial
    for expected in simulation.ledgers:
        state, actual = step_magma(state)
        if actual != expected:
            raise ValueError("WG-LOCAL-MAGMA-REPLAY: ledger divergence")
    if (not simulation.converged or state != simulation.final
            or not simulation.ledgers or simulation.ledgers[-1].transfers):
        raise ValueError("WG-LOCAL-MAGMA-REPLAY: final or convergence divergence")


def derive_site_magma_simulation(
    width: int, height: int, z_levels: int, features: Sequence[object],
    *, max_iterations: int = 8,
) -> MagmaSimulation:
    volumes: dict[tuple[int, int, int], int] = {}
    for feature in features:
        if str(getattr(feature, "kind")) != "sealed_magma":
            continue
        for x, y, z in getattr(feature, "cells"):
            if not (0 <= x < width and 0 <= y < height and 0 <= z < z_levels):
                raise ValueError("WG-LOCAL-MAGMA-DERIVE: magma outside local map")
            volumes[(x, y, z)] = 1_000
            if z > 0:
                volumes.setdefault((x, y, z - 1), 0)
    if not volumes:
        raise ValueError("WG-LOCAL-MAGMA-DERIVE: site has no geology-authorized magma")
    state = MagmaState(0, True, tuple(
        MagmaCell(coordinate, volume, 1_000)
        for coordinate, volume in sorted(volumes.items())
    ))
    return simulate_magma(state, max_iterations=max_iterations)


def validate_fluid_exclusion(
    water: WaterSimulation, magma: MagmaSimulation,
) -> None:
    """Reject water/magma co-occupancy at every aligned committed tick."""
    water_states = [water.initial]
    water_state = water.initial
    for _ in water.ledgers:
        water_state, _ = step_water(water_state)
        water_states.append(water_state)
    magma_states = [magma.initial]
    magma_state = magma.initial
    for _ in magma.ledgers:
        magma_state, _ = step_magma(magma_state)
        magma_states.append(magma_state)
    tick_count = max(len(water_states), len(magma_states))
    for tick in range(tick_count):
        water_state = water_states[min(tick, len(water_states) - 1)]
        magma_state = magma_states[min(tick, len(magma_states) - 1)]
        wet = {cell.coordinate for cell in water_state.cells if cell.volume > 0}
        molten = {cell.coordinate for cell in magma_state.cells if cell.volume > 0}
        if wet & molten:
            raise ValueError(f"WG-LOCAL-FLUID-EXCLUSION: overlap at tick {tick}")


def validate_heat_state(state: HeatState) -> None:
    if state.tick < 0 or not state.sealed_boundary or state.cells != tuple(sorted(state.cells)):
        raise ValueError("WG-LOCAL-HEAT-STATE: invalid tick, boundary, or ordering")
    coordinates = tuple(cell.coordinate for cell in state.cells)
    if len(coordinates) != len(set(coordinates)) or any(
        cell.capacity <= 0 or not 0 <= cell.energy <= cell.capacity
        or not 1 <= cell.conductivity <= 1_000
        or any(value < 0 for value in cell.coordinate)
        for cell in state.cells
    ):
        raise ValueError("WG-LOCAL-HEAT-STATE: invalid cell")


def _propose_heat(state: HeatState) -> tuple[HeatTransfer, ...]:
    by_coordinate = {cell.coordinate: cell for cell in state.cells}
    proposals: list[HeatTransfer] = []
    for cell in state.cells:
        x, y, z = cell.coordinate
        for target_coordinate in ((x + 1, y, z), (x, y + 1, z), (x, y, z + 1)):
            neighbor = by_coordinate.get(target_coordinate)
            if neighbor is None or cell.energy == neighbor.energy:
                continue
            source, target = (
                (cell, neighbor) if cell.energy > neighbor.energy else (neighbor, cell)
            )
            conductivity = min(source.conductivity, target.conductivity)
            amount = min(
                200,
                div_floor_exact((source.energy - target.energy) * conductivity, 4_000),
                target.capacity - target.energy,
            )
            if amount > 0:
                proposals.append(HeatTransfer(
                    source.coordinate, target.coordinate, amount,
                ))
    return tuple(sorted(set(proposals)))


def step_heat(state: HeatState) -> tuple[HeatState, HeatLedger]:
    """Resolve conduction proposals from one immutable thermal state."""
    validate_heat_state(state)
    energies = {cell.coordinate: cell.energy for cell in state.cells}
    capacities = {cell.coordinate: cell.capacity for cell in state.cells}
    accepted: list[HeatTransfer] = []
    for proposal in _propose_heat(state):
        amount = min(
            proposal.amount,
            energies[proposal.source],
            capacities[proposal.target] - energies[proposal.target],
        )
        if amount <= 0:
            continue
        energies[proposal.source] -= amount
        energies[proposal.target] += amount
        accepted.append(HeatTransfer(proposal.source, proposal.target, amount))
    result = HeatState(state.tick + 1, True, tuple(
        HeatCell(
            cell.coordinate, energies[cell.coordinate], cell.capacity, cell.conductivity,
        )
        for cell in state.cells
    ))
    before = sum(cell.energy for cell in state.cells)
    after = sum(cell.energy for cell in result.cells)
    if before != after:
        raise ValueError("WG-LOCAL-HEAT-CONSERVATION: thermal energy changed")
    return result, HeatLedger(state.tick, before, after, tuple(accepted))


def simulate_heat(state: HeatState, *, max_iterations: int) -> HeatSimulation:
    if max_iterations <= 0:
        raise ValueError("WG-LOCAL-HEAT-LIMIT: max_iterations must be positive")
    initial = state
    ledgers: list[HeatLedger] = []
    for _ in range(max_iterations):
        state, ledger = step_heat(state)
        ledgers.append(ledger)
        if not ledger.transfers:
            return HeatSimulation(initial, state, tuple(ledgers), True)
    if _propose_heat(state):
        raise HeatNonConvergenceError(
            max_iterations, sum(cell.energy for cell in state.cells),
        )
    return HeatSimulation(initial, state, tuple(ledgers), True)


def validate_heat_simulation(simulation: HeatSimulation) -> None:
    state = simulation.initial
    for expected in simulation.ledgers:
        state, actual = step_heat(state)
        if actual != expected:
            raise ValueError("WG-LOCAL-HEAT-REPLAY: ledger divergence")
    if (not simulation.converged or state != simulation.final
            or not simulation.ledgers or simulation.ledgers[-1].transfers):
        raise ValueError("WG-LOCAL-HEAT-REPLAY: final or convergence divergence")


def derive_site_heat_simulation(
    width: int, height: int, z_levels: int, features: Sequence[object],
    magma: MagmaSimulation, *, max_iterations: int = 32,
) -> HeatSimulation:
    """Derive a closed thermal domain from magma and retained heat-zone facts."""
    cells: dict[tuple[int, int, int], HeatCell] = {}
    for magma_cell in magma.initial.cells:
        if magma_cell.volume > 0:
            cells[magma_cell.coordinate] = HeatCell(
                magma_cell.coordinate, 1_600, 2_000, 1_000,
            )
    for feature in features:
        if str(getattr(feature, "kind")) != "heat_zone":
            continue
        for x, y, z in getattr(feature, "cells"):
            if not (0 <= x < width and 0 <= y < height and 0 <= z < z_levels):
                raise ValueError("WG-LOCAL-HEAT-DERIVE: heat zone outside local map")
            cells.setdefault((x, y, z), HeatCell((x, y, z), 200, 2_000, 500))
    if not cells or not any(cell.energy == 1_600 for cell in cells.values()):
        raise ValueError("WG-LOCAL-HEAT-DERIVE: site has no magma heat source")
    if not any(cell.energy == 200 for cell in cells.values()):
        raise ValueError("WG-LOCAL-HEAT-DERIVE: site has no retained heat zone")
    return simulate_heat(
        HeatState(0, True, tuple(sorted(cells.values()))),
        max_iterations=max_iterations,
    )


def _structural_mass(state: StructuralState) -> int:
    return (
        sum(cell.load for cell in state.cells if not cell.failed)
        + sum(item.mass for item in state.debris)
    )


def validate_structural_state(state: StructuralState) -> None:
    if (state.tick < 0 or state.cells != tuple(sorted(state.cells))
            or state.debris != tuple(sorted(state.debris))):
        raise ValueError("WG-LOCAL-STRUCTURE-STATE: invalid tick or ordering")
    coordinates = tuple(cell.coordinate for cell in state.cells)
    debris_coordinates = tuple(item.coordinate for item in state.debris)
    if len(coordinates) != len(set(coordinates)) or len(debris_coordinates) != len(
        set(debris_coordinates)
    ):
        raise ValueError("WG-LOCAL-STRUCTURE-STATE: duplicate coordinate")
    if any(
        cell.load <= 0 or cell.strength <= 0 or not cell.source_ids
        or cell.source_ids != tuple(sorted(set(cell.source_ids)))
        or any(value < 0 for value in cell.coordinate)
        for cell in state.cells
    ) or any(
        item.mass <= 0 or not item.source_ids
        or item.source_ids != tuple(sorted(set(item.source_ids)))
        or any(value < 0 for value in item.coordinate)
        for item in state.debris
    ):
        raise ValueError("WG-LOCAL-STRUCTURE-STATE: invalid structural record")
    failed = {cell.coordinate for cell in state.cells if cell.failed}
    if failed != set(debris_coordinates):
        raise ValueError("WG-LOCAL-STRUCTURE-STATE: failed/debris mismatch")


def _structural_failures(
    state: StructuralState, heat: HeatState,
) -> tuple[StructuralDebris, ...]:
    live = {cell.coordinate: cell for cell in state.cells if not cell.failed}
    heat_by_coordinate = {cell.coordinate: cell.energy for cell in heat.cells}
    failures: list[StructuralDebris] = []
    for cell in live.values():
        x, y, z = cell.coordinate
        supported = cell.foundation or (z > 0 and (x, y, z - 1) in live)
        thermal_penalty = max(0, heat_by_coordinate.get(cell.coordinate, 0) - 1_000)
        effective_strength = max(0, cell.strength - div_floor_exact(thermal_penalty, 2))
        if not supported or cell.load > effective_strength:
            failures.append(StructuralDebris(
                cell.coordinate, cell.load, cell.source_ids,
            ))
    return tuple(sorted(failures))


def step_structure(
    state: StructuralState, heat: HeatState,
) -> tuple[StructuralState, StructuralLedger]:
    """Commit simultaneous failures selected from one immutable support graph."""
    validate_structural_state(state)
    validate_heat_state(heat)
    failures = _structural_failures(state, heat)
    failed_coordinates = {item.coordinate for item in failures}
    result = StructuralState(
        state.tick + 1,
        tuple(
            StructuralCell(
                cell.coordinate, cell.load, cell.strength, cell.foundation,
                cell.failed or cell.coordinate in failed_coordinates, cell.source_ids,
            )
            for cell in state.cells
        ),
        tuple(sorted((*state.debris, *failures))),
    )
    before = _structural_mass(state)
    after = _structural_mass(result)
    if before != after:
        raise ValueError("WG-LOCAL-STRUCTURE-CONSERVATION: structural mass changed")
    return result, StructuralLedger(state.tick, before, after, failures)


def simulate_structure(
    state: StructuralState, heat: HeatState, *, max_iterations: int,
) -> StructuralSimulation:
    if max_iterations <= 0:
        raise ValueError("WG-LOCAL-STRUCTURE-LIMIT: max_iterations must be positive")
    initial = state
    ledgers: list[StructuralLedger] = []
    for _ in range(max_iterations):
        state, ledger = step_structure(state, heat)
        ledgers.append(ledger)
        if not ledger.failures:
            return StructuralSimulation(
                initial, state, tuple(ledgers), True, heat.tick,
            )
    if _structural_failures(state, heat):
        raise StructuralNonConvergenceError(max_iterations, _structural_mass(state))
    return StructuralSimulation(initial, state, tuple(ledgers), True, heat.tick)


def validate_structural_simulation(
    simulation: StructuralSimulation, heat: HeatState,
) -> None:
    if simulation.heat_final_tick != heat.tick:
        raise ValueError("WG-LOCAL-STRUCTURE-REPLAY: heat checkpoint mismatch")
    state = simulation.initial
    for expected in simulation.ledgers:
        state, actual = step_structure(state, heat)
        if actual != expected:
            raise ValueError("WG-LOCAL-STRUCTURE-REPLAY: ledger divergence")
    if (not simulation.converged or state != simulation.final
            or not simulation.ledgers or simulation.ledgers[-1].failures):
        raise ValueError("WG-LOCAL-STRUCTURE-REPLAY: final or convergence divergence")


def derive_site_structural_simulation(
    features: Sequence[object], heat: HeatSimulation, *, max_iterations: int = 8,
) -> StructuralSimulation:
    """Derive support/load records from already-verified construction features."""
    foundations: dict[tuple[int, int, int], tuple[str, ...]] = {}
    structures: dict[tuple[int, int, int], tuple[str, ...]] = {}
    for feature in features:
        kind = str(getattr(feature, "kind"))
        sources = tuple(sorted(set(str(item) for item in getattr(feature, "source_ids"))))
        if kind == "structural_support":
            for coordinate in getattr(feature, "cells"):
                foundations[tuple(coordinate)] = sources
        elif kind in {"supported_building", "wall", "bridge"}:
            for coordinate in getattr(feature, "cells"):
                structures[tuple(coordinate)] = sources
    if not structures or not foundations:
        raise ValueError("WG-LOCAL-STRUCTURE-DERIVE: missing construction or support")
    cells = tuple(sorted(
        StructuralCell(
            coordinate, 500, 1_000, coordinate in foundations, False,
            tuple(sorted(set((*sources, *foundations.get(coordinate, ())))))
        )
        for coordinate, sources in structures.items()
    ))
    if any(not cell.source_ids for cell in cells):
        raise ValueError("WG-LOCAL-STRUCTURE-DERIVE: missing provenance")
    return simulate_structure(
        StructuralState(0, cells, ()), heat.final, max_iterations=max_iterations,
    )


def derive_site_water_simulation(
    width: int, height: int, z_levels: int, features: Sequence[object],
    *, max_iterations: int = 8,
) -> WaterSimulation:
    """Derive the sealed water domain exclusively from authoritative occupants."""
    water_kinds = {"aquifer_water": 600, "river_water": 1_000, "coast_water": 1_000}
    volumes: dict[tuple[int, int, int], int] = {}
    for feature in features:
        kind = str(getattr(feature, "kind"))
        initial_volume = water_kinds.get(kind)
        if initial_volume is None:
            continue
        for raw in getattr(feature, "cells"):
            coordinate = tuple(raw)
            if (len(coordinate) != 3
                    or not (0 <= coordinate[0] < width and 0 <= coordinate[1] < height
                            and 0 <= coordinate[2] < z_levels)):
                raise ValueError("WG-LOCAL-WATER-DERIVE: water occupant outside local map")
            cell = (int(coordinate[0]), int(coordinate[1]), int(coordinate[2]))
            volumes[cell] = max(volumes.get(cell, 0), initial_volume)
            if kind == "aquifer_water" and cell[2] > 0:
                volumes.setdefault((cell[0], cell[1], cell[2] - 1), 0)
    if not volumes:
        raise ValueError("WG-LOCAL-WATER-DERIVE: site has no authoritative water occupant")
    state = WaterState(0, True, tuple(
        WaterCell(coordinate, volume, 1_000)
        for coordinate, volume in sorted(volumes.items())
    ))
    return simulate_water(state, max_iterations=max_iterations)


def water_simulation_from_mapping(value: Mapping[str, object]) -> WaterSimulation:
    """Strictly decode a persisted water simulation and replay-check it."""
    if set(value) != {"initial", "final", "ledgers", "converged"}:
        raise ValueError("WG-LOCAL-WATER-READ: simulation field set mismatch")

    def integer(source: Mapping[str, object], name: str) -> int:
        item = source[name]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"WG-LOCAL-WATER-READ: {name} must be an integer")
        return item

    def coordinate(raw: object) -> tuple[int, int, int]:
        if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))
                or len(raw) != 3
                or any(isinstance(item, bool) or not isinstance(item, int) for item in raw)):
            raise ValueError("WG-LOCAL-WATER-READ: invalid coordinate")
        return int(raw[0]), int(raw[1]), int(raw[2])

    def state(raw: object) -> WaterState:
        if (not isinstance(raw, Mapping)
                or set(raw) != {"tick", "sealed_boundary", "cells"}
                or not isinstance(raw["sealed_boundary"], bool)
                or not isinstance(raw["cells"], Sequence)):
            raise ValueError("WG-LOCAL-WATER-READ: invalid state shape")
        cells: list[WaterCell] = []
        for item in raw["cells"]:
            if (not isinstance(item, Mapping)
                    or set(item) != {"coordinate", "volume", "capacity"}):
                raise ValueError("WG-LOCAL-WATER-READ: invalid cell shape")
            cells.append(WaterCell(
                coordinate(item["coordinate"]), integer(item, "volume"),
                integer(item, "capacity"),
            ))
        return WaterState(
            integer(raw, "tick"), raw["sealed_boundary"], tuple(cells),
        )

    initial, final, raw_ledgers = state(value["initial"]), state(value["final"]), value["ledgers"]
    if (not isinstance(raw_ledgers, Sequence)
            or isinstance(raw_ledgers, (str, bytes))
            or not isinstance(value["converged"], bool)):
        raise ValueError("WG-LOCAL-WATER-READ: invalid simulation values")
    ledgers: list[WaterLedger] = []
    for raw in raw_ledgers:
        if (not isinstance(raw, Mapping)
                or set(raw) != {"tick", "before_volume", "after_volume", "transfers"}
                or not isinstance(raw["transfers"], Sequence)):
            raise ValueError("WG-LOCAL-WATER-READ: invalid ledger shape")
        transfers: list[WaterTransfer] = []
        for item in raw["transfers"]:
            if (not isinstance(item, Mapping)
                    or set(item) != {"priority", "source", "target", "amount"}):
                raise ValueError("WG-LOCAL-WATER-READ: invalid transfer shape")
            transfers.append(WaterTransfer(
                integer(item, "priority"), coordinate(item["source"]),
                coordinate(item["target"]), integer(item, "amount"),
            ))
        ledgers.append(WaterLedger(
            integer(raw, "tick"), integer(raw, "before_volume"),
            integer(raw, "after_volume"), tuple(transfers),
        ))
    simulation = WaterSimulation(
        initial, final, tuple(ledgers), value["converged"],
    )
    validate_water_simulation(simulation)
    return simulation


def magma_simulation_from_mapping(value: Mapping[str, object]) -> MagmaSimulation:
    """Strictly decode a persisted magma simulation and replay-check it."""
    if set(value) != {"initial", "final", "ledgers", "converged"}:
        raise ValueError("WG-LOCAL-MAGMA-READ: simulation field set mismatch")

    def integer(source: Mapping[str, object], name: str) -> int:
        item = source[name]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"WG-LOCAL-MAGMA-READ: {name} must be an integer")
        return item

    def coordinate(raw: object) -> tuple[int, int, int]:
        if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))
                or len(raw) != 3
                or any(isinstance(item, bool) or not isinstance(item, int) for item in raw)):
            raise ValueError("WG-LOCAL-MAGMA-READ: invalid coordinate")
        return int(raw[0]), int(raw[1]), int(raw[2])

    def state(raw: object) -> MagmaState:
        if (not isinstance(raw, Mapping)
                or set(raw) != {"tick", "sealed_boundary", "cells"}
                or not isinstance(raw["sealed_boundary"], bool)
                or not isinstance(raw["cells"], Sequence)):
            raise ValueError("WG-LOCAL-MAGMA-READ: invalid state shape")
        cells: list[MagmaCell] = []
        for item in raw["cells"]:
            if (not isinstance(item, Mapping)
                    or set(item) != {"coordinate", "volume", "capacity"}):
                raise ValueError("WG-LOCAL-MAGMA-READ: invalid cell shape")
            cells.append(MagmaCell(
                coordinate(item["coordinate"]), integer(item, "volume"),
                integer(item, "capacity"),
            ))
        return MagmaState(integer(raw, "tick"), raw["sealed_boundary"], tuple(cells))

    initial, final, raw_ledgers = state(value["initial"]), state(value["final"]), value["ledgers"]
    if (not isinstance(raw_ledgers, Sequence)
            or isinstance(raw_ledgers, (str, bytes))
            or not isinstance(value["converged"], bool)):
        raise ValueError("WG-LOCAL-MAGMA-READ: invalid simulation values")
    ledgers: list[MagmaLedger] = []
    for raw in raw_ledgers:
        if (not isinstance(raw, Mapping)
                or set(raw) != {"tick", "before_volume", "after_volume", "transfers"}
                or not isinstance(raw["transfers"], Sequence)):
            raise ValueError("WG-LOCAL-MAGMA-READ: invalid ledger shape")
        transfers: list[MagmaTransfer] = []
        for item in raw["transfers"]:
            if (not isinstance(item, Mapping)
                    or set(item) != {"priority", "source", "target", "amount"}):
                raise ValueError("WG-LOCAL-MAGMA-READ: invalid transfer shape")
            transfers.append(MagmaTransfer(
                integer(item, "priority"), coordinate(item["source"]),
                coordinate(item["target"]), integer(item, "amount"),
            ))
        ledgers.append(MagmaLedger(
            integer(raw, "tick"), integer(raw, "before_volume"),
            integer(raw, "after_volume"), tuple(transfers),
        ))
    simulation = MagmaSimulation(initial, final, tuple(ledgers), value["converged"])
    validate_magma_simulation(simulation)
    return simulation


def heat_simulation_from_mapping(value: Mapping[str, object]) -> HeatSimulation:
    """Strictly decode a persisted heat simulation and replay-check it."""
    if set(value) != {"initial", "final", "ledgers", "converged"}:
        raise ValueError("WG-LOCAL-HEAT-READ: simulation field set mismatch")

    def integer(source: Mapping[str, object], name: str) -> int:
        item = source[name]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"WG-LOCAL-HEAT-READ: {name} must be an integer")
        return item

    def coordinate(raw: object) -> tuple[int, int, int]:
        if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))
                or len(raw) != 3
                or any(isinstance(item, bool) or not isinstance(item, int) for item in raw)):
            raise ValueError("WG-LOCAL-HEAT-READ: invalid coordinate")
        return int(raw[0]), int(raw[1]), int(raw[2])

    def state(raw: object) -> HeatState:
        if (not isinstance(raw, Mapping)
                or set(raw) != {"tick", "sealed_boundary", "cells"}
                or not isinstance(raw["sealed_boundary"], bool)
                or not isinstance(raw["cells"], Sequence)):
            raise ValueError("WG-LOCAL-HEAT-READ: invalid state shape")
        cells: list[HeatCell] = []
        for item in raw["cells"]:
            if (not isinstance(item, Mapping)
                    or set(item) != {"coordinate", "energy", "capacity", "conductivity"}):
                raise ValueError("WG-LOCAL-HEAT-READ: invalid cell shape")
            cells.append(HeatCell(
                coordinate(item["coordinate"]), integer(item, "energy"),
                integer(item, "capacity"), integer(item, "conductivity"),
            ))
        return HeatState(integer(raw, "tick"), raw["sealed_boundary"], tuple(cells))

    initial = state(value["initial"])
    final = state(value["final"])
    raw_ledgers = value["ledgers"]
    if (not isinstance(raw_ledgers, Sequence)
            or isinstance(raw_ledgers, (str, bytes))
            or not isinstance(value["converged"], bool)):
        raise ValueError("WG-LOCAL-HEAT-READ: invalid simulation values")
    ledgers: list[HeatLedger] = []
    for raw in raw_ledgers:
        if (not isinstance(raw, Mapping)
                or set(raw) != {"tick", "before_energy", "after_energy", "transfers"}
                or not isinstance(raw["transfers"], Sequence)):
            raise ValueError("WG-LOCAL-HEAT-READ: invalid ledger shape")
        transfers: list[HeatTransfer] = []
        for item in raw["transfers"]:
            if (not isinstance(item, Mapping)
                    or set(item) != {"source", "target", "amount"}):
                raise ValueError("WG-LOCAL-HEAT-READ: invalid transfer shape")
            transfers.append(HeatTransfer(
                coordinate(item["source"]), coordinate(item["target"]),
                integer(item, "amount"),
            ))
        ledgers.append(HeatLedger(
            integer(raw, "tick"), integer(raw, "before_energy"),
            integer(raw, "after_energy"), tuple(transfers),
        ))
    simulation = HeatSimulation(initial, final, tuple(ledgers), value["converged"])
    validate_heat_simulation(simulation)
    return simulation


def structural_simulation_from_mapping(
    value: Mapping[str, object], heat: HeatState,
) -> StructuralSimulation:
    """Strictly decode and replay a persisted structural simulation."""
    expected_fields = {"initial", "final", "ledgers", "converged", "heat_final_tick"}
    if set(value) != expected_fields:
        raise ValueError("WG-LOCAL-STRUCTURE-READ: simulation field set mismatch")

    def integer(source: Mapping[str, object], name: str) -> int:
        item = source[name]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ValueError(f"WG-LOCAL-STRUCTURE-READ: {name} must be an integer")
        return item

    def coordinate(raw: object) -> tuple[int, int, int]:
        if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))
                or len(raw) != 3
                or any(isinstance(item, bool) or not isinstance(item, int) for item in raw)):
            raise ValueError("WG-LOCAL-STRUCTURE-READ: invalid coordinate")
        return int(raw[0]), int(raw[1]), int(raw[2])

    def source_ids(raw: object) -> tuple[str, ...]:
        if (not isinstance(raw, Sequence) or isinstance(raw, (str, bytes))
                or any(not isinstance(item, str) for item in raw)):
            raise ValueError("WG-LOCAL-STRUCTURE-READ: invalid source IDs")
        return tuple(raw)

    def debris(raw: object) -> StructuralDebris:
        if (not isinstance(raw, Mapping)
                or set(raw) != {"coordinate", "mass", "source_ids"}):
            raise ValueError("WG-LOCAL-STRUCTURE-READ: invalid debris shape")
        return StructuralDebris(
            coordinate(raw["coordinate"]), integer(raw, "mass"),
            source_ids(raw["source_ids"]),
        )

    def state(raw: object) -> StructuralState:
        if (not isinstance(raw, Mapping)
                or set(raw) != {"tick", "cells", "debris"}
                or not isinstance(raw["cells"], Sequence)
                or not isinstance(raw["debris"], Sequence)):
            raise ValueError("WG-LOCAL-STRUCTURE-READ: invalid state shape")
        cells: list[StructuralCell] = []
        for item in raw["cells"]:
            if (not isinstance(item, Mapping)
                    or set(item) != {
                        "coordinate", "load", "strength", "foundation", "failed",
                        "source_ids",
                    }
                    or not isinstance(item["foundation"], bool)
                    or not isinstance(item["failed"], bool)):
                raise ValueError("WG-LOCAL-STRUCTURE-READ: invalid cell shape")
            cells.append(StructuralCell(
                coordinate(item["coordinate"]), integer(item, "load"),
                integer(item, "strength"), item["foundation"], item["failed"],
                source_ids(item["source_ids"]),
            ))
        result = StructuralState(
            integer(raw, "tick"), tuple(cells),
            tuple(debris(item) for item in raw["debris"]),
        )
        validate_structural_state(result)
        return result

    initial = state(value["initial"])
    final = state(value["final"])
    raw_ledgers = value["ledgers"]
    if (not isinstance(raw_ledgers, Sequence)
            or isinstance(raw_ledgers, (str, bytes))
            or not isinstance(value["converged"], bool)):
        raise ValueError("WG-LOCAL-STRUCTURE-READ: invalid simulation values")
    ledgers: list[StructuralLedger] = []
    for raw in raw_ledgers:
        if (not isinstance(raw, Mapping)
                or set(raw) != {"tick", "before_mass", "after_mass", "failures"}
                or not isinstance(raw["failures"], Sequence)):
            raise ValueError("WG-LOCAL-STRUCTURE-READ: invalid ledger shape")
        ledgers.append(StructuralLedger(
            integer(raw, "tick"), integer(raw, "before_mass"),
            integer(raw, "after_mass"),
            tuple(debris(item) for item in raw["failures"]),
        ))
    simulation = StructuralSimulation(
        initial, final, tuple(ledgers), value["converged"],
        integer(value, "heat_final_tick"),
    )
    validate_structural_simulation(simulation, heat)
    return simulation
