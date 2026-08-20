from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import Consequence, ConsequenceKind, EventKind
from src.worldgen.simulation.proposals import HistoryProposal, resolve_proposals


def _proposal(proposal_id: str, priority: int, conflict_key: str) -> HistoryProposal:
    return HistoryProposal(
        proposal_id, 40, 12, EventKind.CONSTRUCTION, "civilization",
        ("civilization",), ("site",),
        (Consequence(ConsequenceKind.MATERIAL_DELTA, "civilization", -20),),
        "A construction proposal.", ("cause",), (conflict_key,), priority,
    )


def test_conflict_resolution_is_order_independent_and_exactly_once() -> None:
    proposals = (
        _proposal("proposal-c", 200, "construction-slot:settlement:40"),
        _proposal("proposal-a", 100, "construction-slot:settlement:40"),
        _proposal("proposal-b", 100, "construction-slot:settlement:40"),
    )
    accepted, decisions = resolve_proposals(proposals)
    reversed_accepted, reversed_decisions = resolve_proposals(tuple(reversed(proposals)))

    assert [item.proposal_id for item in accepted] == ["proposal-a"]
    assert accepted == reversed_accepted
    assert decisions == reversed_decisions
    assert sum(item.accepted for item in decisions) == 1
    assert all(item.blocked_by == ("proposal-a",) for item in decisions if not item.accepted)


def test_resolver_rejects_duplicate_or_noncanonical_proposals() -> None:
    proposal = _proposal("duplicate", 1, "resource")
    with pytest.raises(ValueError, match="WG-PROPOSAL-ID"):
        resolve_proposals((proposal, proposal))
    with pytest.raises(ValueError, match="WG-PROPOSAL-SHAPE"):
        resolve_proposals((replace(proposal, conflict_keys=("z", "a")),))


def test_construction_candidates_are_retained_with_one_winner(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    decisions = repository.load_verified("proposal_resolutions").payload
    history = repository.load_verified("history").payload
    construction_events = [item for item in history if item["kind"] == "construction"]

    assert construction_events
    assert len(decisions) >= len(construction_events) * 2
    for event in construction_events:
        proposal_id = dict(event["consequences"][0]["details"])["proposal_id"]
        conflict_key = dict(event["consequences"][0]["details"])["conflict_key"]
        family = [item for item in decisions if conflict_key in item["conflict_keys"]]
        assert len(family) >= 2
        assert [item["proposal_id"] for item in family if item["accepted"]] == [proposal_id]
