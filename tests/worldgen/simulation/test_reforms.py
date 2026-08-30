from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import ConsequenceKind, EventKind
from src.worldgen.simulation.reforms import project_government_reforms
from src.worldgen.simulation.registries import simulation_registry_entries
from src.worldgen.simulation.replay import _event, _state


def test_reforms_are_typed_non_noop_and_pressure_driven(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    reforms = repository.load_verified("government_reforms").payload
    history = {item["event_id"]: item for item in repository.load_verified("history").payload}
    assert reforms
    for reform in reforms:
        event = history[reform["event_id"]]
        assert event["kind"] == "reform"
        assert reform["prior_government"] != reform["new_government"]
        assert reform["pressure_kind"] in {"scarcity", "instability"}
        assert 0 <= reform["pressure_ppm"] <= 1_000_000
        assert any(
            item["kind"] == "government_set"
            and item["value"] == reform["prior_government"]
            and item["target"] == reform["new_government"]
            for item in event["consequences"]
        )
        assert any(
            item["kind"] == "currency_delta" and item["amount"] == -reform["currency_cost"]
            for item in event["consequences"]
        )


def test_reform_projector_rejects_noop_transition(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    reform = next(item for item in events if item.kind is EventKind.REFORM)
    change = next(
        item for item in reform.consequences if item.kind is ConsequenceKind.GOVERNMENT_SET
    )
    forged = replace(
        reform,
        consequences=tuple(
            replace(item, target=change.value)
            if item.kind is ConsequenceKind.GOVERNMENT_SET
            else item
            for item in reform.consequences
        ),
    )
    altered = tuple(forged if item.event_id == forged.event_id else item for item in events)
    state = _state(repository.load_verified("snapshots").payload[-1]["state"])
    with pytest.raises(ValueError, match="WG-REFORM"):
        project_government_reforms(
            42,
            altered,
            state.civilizations,
            simulation_registry_entries("governments"),
        )
