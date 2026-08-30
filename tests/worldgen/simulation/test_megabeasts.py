from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import ConsequenceKind, EventKind
from src.worldgen.simulation.megabeasts import Megabeast, project_megabeast_history
from src.worldgen.simulation.replay import _event


def test_megabeasts_are_rare_persistent_and_have_complete_histories(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    payload = repository.load_verified("megabeasts").payload
    entities = tuple(Megabeast(**item) for item in payload["entities"])
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    history = project_megabeast_history(42, events, entities)

    assert 0 < len(entities) <= 2
    assert sum(item.carrying_cost for item in entities) <= 2
    assert {item.transition for item in history} >= {"movement", "encounter", "hunt", "death"}
    assert len(payload["history"]) == len(history)
    dead = {item.megabeast_id for item in history if item.new_condition == "dead"}
    assert dead
    assert dead <= {item.megabeast_id for item in entities}


def test_megabeast_history_rejects_post_death_transition(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    payload = repository.load_verified("megabeasts").payload
    entities = tuple(Megabeast(**item) for item in payload["entities"])
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    death = next(event for event in events if event.kind is EventKind.MEGABEAST_DEATH)
    consequence = next(
        item for item in death.consequences if item.kind is ConsequenceKind.MEGABEAST_TRANSITION
    )
    forged = replace(
        death,
        event_id="post-death",
        year=death.year + 1,
        kind=EventKind.MEGABEAST_ENCOUNTER,
        causes=(death.event_id,),
        consequences=(
            replace(
                consequence,
                value="wounded",
                details=tuple(
                    (key, "encounter")
                    if key == "transition"
                    else (key, death.event_id)
                    if key == "prior_event_id"
                    else (key, "dead")
                    if key == "prior_condition"
                    else (key, value)
                    for key, value in consequence.details
                ),
            ),
        ),
    )
    with pytest.raises(ValueError, match="WG-MEGABEAST-HISTORY"):
        project_megabeast_history(42, events + (forged,), entities)
