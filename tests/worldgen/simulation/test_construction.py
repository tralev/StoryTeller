from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.construction import project_construction
from src.worldgen.simulation.events import ConsequenceKind, EventKind
from src.worldgen.simulation.replay import _event, _state


def test_construction_is_need_driven_provenanced_and_exactly_costed(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    projects = repository.load_verified("construction_projects").payload
    history = repository.load_verified("history").payload
    events = {item["event_id"]: item for item in history}
    assert projects
    for project in projects:
        event = events[project["event_id"]]
        assert event["kind"] == "construction"
        assert project["addressed_need"] in {"grain", "materials", "shelter"}
        assert project["building"] in {
            "grain exchange",
            "masonry storehouse",
            "communal hall",
            "communal storehouse",
        }
        civilization_cost = next(
            item for item in event["consequences"] if item["kind"] == "material_delta"
        )
        inventory_cost = next(
            item
            for item in event["consequences"]
            if item["kind"] == "settlement_inventory_delta" and item["target"] == "materials"
        )
        assert civilization_cost["amount"] == inventory_cost["amount"] == -project["material_cost"]
        for consequence in event["consequences"]:
            assert dict(consequence["details"])["project_id"] == project["project_id"]


def test_construction_projector_rejects_cost_mismatch(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    construction = next(item for item in events if item.kind is EventKind.CONSTRUCTION)
    forged = replace(
        construction,
        consequences=tuple(
            replace(item, amount=item.amount - 1)
            if item.kind is ConsequenceKind.SETTLEMENT_INVENTORY_DELTA
            and item.target == "materials"
            else item
            for item in construction.consequences
        ),
    )
    altered = tuple(forged if item.event_id == forged.event_id else item for item in events)
    state = _state(repository.load_verified("snapshots").payload[-1]["state"])
    with pytest.raises(ValueError, match="WG-CONSTRUCTION-PROVENANCE"):
        project_construction(altered, state.civilizations, state.settlements)
