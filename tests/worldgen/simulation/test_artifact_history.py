from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.artifact_history import project_artifact_histories
from src.worldgen.simulation.events import Consequence, ConsequenceKind, EventKind, HistoryEvent
from src.worldgen.simulation.replay import _event
from src.worldgen.simulation.scheduler import simulate_world


def test_commission_creates_retained_event_sourced_artifact_history(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    entries = project_artifact_histories(42, events)
    persisted = repository.load_verified("legendary_artifact_histories").payload
    artifacts = repository.load_verified("legendary_artifacts").payload

    assert entries and persisted
    assert tuple(item.artifact_id for item in entries if item.transition == "creation") == tuple(
        item["artifact_id"] for item in artifacts
    )
    assert len(persisted) == len(entries)


def test_artifact_history_rejects_forged_predecessor(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    events = tuple(_event(item) for item in repository.load_verified("history").payload)
    creation = next(event for event in events if event.kind is EventKind.COMMISSION)
    created = next(item for item in creation.consequences
                   if item.kind is ConsequenceKind.ARTIFACT_CREATE)
    transition = replace(
        creation,
        event_id="artifact-transition",
        year=creation.year + 10,
        kind=EventKind.ARTIFACT_HISTORY,
        causes=(creation.event_id,),
        consequences=(replace(
            created,
            kind=ConsequenceKind.ARTIFACT_TRANSITION,
            subject=created.subject,
            target=created.target,
            value="",
            details=(("transition", "gift"), ("prior_owner_id", created.target),
                     ("prior_site_id", created.value), ("prior_status", "intact"),
                     ("prior_event_id", "forged"), ("new_site_id", created.value),
                     ("new_status", "intact")),
        ),),
    )
    with pytest.raises(ValueError, match="WG-ARTIFACT-HISTORY"):
        project_artifact_histories(42, (creation, transition))


def test_artifact_history_supports_every_frozen_lifecycle_transition() -> None:
    creation = HistoryEvent(
        "creation", 50, 12, 1, EventKind.COMMISSION, (), ("owner-a",), ("site-a",),
        (Consequence(ConsequenceKind.ARTIFACT_CREATE, "artifact", target="owner-a",
                     value="site-a"),), "created",
    )
    succession = HistoryEvent(
        "succession", 60, 12, 2, EventKind.SUCCESSION, ("creation",),
        ("owner-a", "owner-b"), ("site-a",),
        (Consequence(ConsequenceKind.OFFICEHOLDER_SET, "civilization",
                     target="owner-b", value="owner-a"),), "succeeded",
    )
    transitions = ("gift", "inheritance", "trade", "theft", "loss", "recovery",
                   "destruction")
    events = [creation, succession]
    owner, site, status, prior_event = "owner-a", "site-a", "intact", "creation"
    for index, transition in enumerate(transitions, start=1):
        new_owner = f"owner-{index}"
        new_site = f"site-{index}"
        new_status = "intact"
        if transition == "loss":
            new_owner, new_site, new_status = "", site, "lost"
        elif transition == "destruction":
            new_owner, new_site, new_status = owner, site, "destroyed"
        causes = (prior_event, "succession") if transition == "inheritance" else (prior_event,)
        event = HistoryEvent(
            f"transition-{index}", 60 + index, 12, 2 + index,
            EventKind.ARTIFACT_HISTORY, causes,
            tuple(item for item in ("artifact", owner, new_owner) if item), (new_site,),
            (Consequence(
                ConsequenceKind.ARTIFACT_TRANSITION, "artifact", target=new_owner,
                details=(("transition", transition), ("prior_owner_id", owner),
                         ("prior_site_id", site), ("prior_status", status),
                         ("prior_event_id", prior_event), ("new_site_id", new_site),
                         ("new_status", new_status)),
            ),), transition,
        )
        events.append(event)
        owner, site, status, prior_event = new_owner, new_site, new_status, event.event_id
    projected = project_artifact_histories(42, tuple(events))
    assert tuple(item.transition for item in projected) == ("creation", *transitions)


@pytest.mark.slow
def test_long_history_scheduler_emits_every_artifact_transition(
    simulated_world, tmp_path,
) -> None:
    physical, _, _ = simulated_world
    historical = tmp_path / "historical"
    simulate_world(physical, 125, historical)
    repository = WorldArtifactRepository(historical / "artifacts")
    transitions = {
        item["transition"]
        for item in repository.load_verified("legendary_artifact_histories").payload
    }
    assert transitions >= {
        "creation", "gift", "inheritance", "trade", "theft", "loss", "recovery",
        "destruction",
    }
    retention = repository.load_verified("retention_inventory").payload
    assert retention["destroyed_artifact_ids"]
