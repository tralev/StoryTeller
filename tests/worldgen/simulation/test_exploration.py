from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import Consequence, ConsequenceKind, EventKind
from src.worldgen.simulation.exploration import project_exploration_discoveries
from src.worldgen.simulation.replay import _event, _state


def test_exploration_is_route_bounded_unowned_and_provenanced(simulated_world):
    physical, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    discoveries = repository.load_verified("exploration_discoveries").payload
    history = {item["event_id"]: item for item in
               repository.load_verified("history").payload}
    owned = {region for civilization in repository.load_verified("civilizations").payload
             for region in civilization["territory"]}
    assert discoveries
    assert len({(item["civilization_id"], item["destination_region_id"])
                for item in discoveries}) == len(discoveries)
    for discovery in discoveries:
        event = history[discovery["event_id"]]
        assert event["kind"] == "exploration"
        assert discovery["route_ids"]
        assert discovery["destination_region_id"] not in owned
        assert any(item["kind"] == "currency_delta"
                   and item["amount"] == -discovery["currency_cost"]
                   for item in event["consequences"])


def test_exploration_projector_rejects_teleportation(simulated_world):
    physical, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    exploration = next(item for item in events if item.kind is EventKind.EXPLORATION)
    forged = replace(
        exploration,
        consequences=tuple(
            replace(item, details=tuple(
                (key, "forged-route") if key == "route_ids" else (key, value)
                for key, value in item.details
            )) if item.kind is ConsequenceKind.REGION_DISCOVERY_ADD else item
            for item in exploration.consequences
        ),
    )
    altered = tuple(forged if item.event_id == forged.event_id else item for item in events)
    state = _state(repository.load_verified("snapshots").payload[-1]["state"])
    physical_repository = WorldArtifactRepository(physical / "artifacts")
    regions = physical_repository.load_verified("regions").payload["regions"]
    routes = physical_repository.load_verified("routes").payload["routes"]
    with pytest.raises(ValueError, match="WG-EXPLORATION"):
        project_exploration_discoveries(
            42, altered, state.civilizations, state.settlements,
            tuple(item["region_id"] for item in regions), tuple(routes),
        )


def test_later_conquest_does_not_retroactively_invalidate_exploration(simulated_world):
    physical, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    exploration = next(item for item in events if item.kind is EventKind.EXPLORATION)
    discovery = next(item for item in exploration.consequences
                     if item.kind is ConsequenceKind.REGION_DISCOVERY_ADD)
    state = _state(repository.load_verified("snapshots").payload[-1]["state"])
    actor = next(item for item in state.civilizations
                 if item.civilization_id == discovery.subject)
    conqueror = next(item for item in state.civilizations
                     if item.civilization_id != actor.civilization_id)
    last = events[-1]
    conquest = replace(
        last,
        consequences=last.consequences + (
            Consequence(ConsequenceKind.TERRITORY_TRANSFER, conqueror.civilization_id,
                        1, value=discovery.target),
        ),
    )
    altered_events = events[:-1] + (conquest,)
    altered_civilizations = tuple(
        replace(item, territory=tuple(sorted(set(item.territory) | {discovery.target})))
        if item.civilization_id == conqueror.civilization_id else item
        for item in state.civilizations
    )
    physical_repository = WorldArtifactRepository(physical / "artifacts")
    regions = physical_repository.load_verified("regions").payload["regions"]
    routes = physical_repository.load_verified("routes").payload["routes"]

    projected = project_exploration_discoveries(
        42, altered_events, altered_civilizations, state.settlements,
        tuple(item["region_id"] for item in regions), tuple(routes),
    )

    assert any(item.event_id == exploration.event_id for item in projected)
