from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import ConsequenceKind, EventKind
from src.worldgen.simulation.registries import simulation_registry_entries
from src.worldgen.simulation.replay import _event, _state
from src.worldgen.simulation.technology import project_technology_discoveries


def test_technology_unlocks_registry_capability_with_provenance(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    discoveries = repository.load_verified("technology_discoveries").payload
    history = {item["event_id"]: item for item in repository.load_verified("history").payload}
    civilizations = {
        item["civilization_id"]: item for item in repository.load_verified("civilizations").payload
    }
    assert discoveries
    for discovery in discoveries:
        event = history[discovery["event_id"]]
        assert event["kind"] == "technology"
        assert (
            discovery["technology_id"]
            in civilizations[discovery["civilization_id"]]["capabilities"]
        )
        assert discovery["workshop_id"] and discovery["settlement_id"]
        assert any(
            item["kind"] == "capability_add" and item["target"] == discovery["technology_id"]
            for item in event["consequences"]
        )
        assert any(
            item["kind"] == "material_delta" and item["amount"] == -discovery["material_cost"]
            for item in event["consequences"]
        )


def test_technology_projector_rejects_forged_prerequisite(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    technology = next(item for item in events if item.kind is EventKind.TECHNOLOGY)
    forged = replace(
        technology,
        consequences=tuple(
            replace(
                item,
                details=tuple(
                    (key, "forged") if key == "prerequisites" else (key, value)
                    for key, value in item.details
                ),
            )
            if item.kind is ConsequenceKind.CAPABILITY_ADD
            else item
            for item in technology.consequences
        ),
    )
    altered = tuple(forged if item.event_id == forged.event_id else item for item in events)
    state = _state(repository.load_verified("snapshots").payload[-1]["state"])
    with pytest.raises(ValueError, match="WG-TECHNOLOGY"):
        project_technology_discoveries(
            42,
            altered,
            state.civilizations,
            state.settlements,
            simulation_registry_entries("technologies"),
        )
