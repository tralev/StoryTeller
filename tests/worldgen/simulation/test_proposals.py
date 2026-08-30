from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import Consequence, ConsequenceKind, EventKind
from src.worldgen.simulation.proposals import HistoryProposal, resolve_proposals


def _proposal(proposal_id: str, priority: int, conflict_key: str) -> HistoryProposal:
    return HistoryProposal(
        proposal_id,
        40,
        12,
        EventKind.CONSTRUCTION,
        "civilization",
        ("civilization",),
        ("site",),
        (Consequence(ConsequenceKind.MATERIAL_DELTA, "civilization", -20),),
        "A construction proposal.",
        ("cause",),
        (conflict_key,),
        priority,
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


def test_trade_candidates_resolve_shared_stock_and_route_claims_once(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    decisions = repository.load_verified("proposal_resolutions").payload
    history = repository.load_verified("history").payload
    trades = [item for item in history if item["kind"] == "trade"]
    trade_decisions = [
        item for item in decisions if any(key.startswith("trade-") for key in item["conflict_keys"])
    ]

    assert trades and trade_decisions
    accepted_ids = {item["proposal_id"] for item in trade_decisions if item["accepted"]}
    event_ids = {dict(event["consequences"][0]["details"])["proposal_id"] for event in trades}
    assert event_ids == accepted_ids
    claimed: set[str] = set()
    for decision in (item for item in trade_decisions if item["accepted"]):
        keys = set(decision["conflict_keys"])
        assert claimed.isdisjoint(keys)
        claimed.update(keys)
    assert all(item["blocked_by"] for item in trade_decisions if not item["accepted"])


def test_resource_extraction_uses_immutable_month_start_claims(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    decisions = repository.load_verified("proposal_resolutions").payload
    history = repository.load_verified("history").payload
    resource_decisions = [
        item
        for item in decisions
        if any(key.startswith("resource-stock:") for key in item["conflict_keys"])
    ]
    extraction_events = [
        event
        for event in history
        if event["kind"] == "monthly_demography"
        and any(
            item["kind"] == "resource_stock_delta" and item["amount"] < 0
            for item in event["consequences"]
        )
    ]

    assert resource_decisions and extraction_events
    accepted_ids = {item["proposal_id"] for item in resource_decisions if item["accepted"]}
    event_ids = {
        dict(
            next(
                item
                for item in event["consequences"]
                if item["kind"] == "resource_stock_delta" and item["amount"] < 0
            )["details"]
        )["proposal_id"]
        for event in extraction_events
    }
    assert event_ids == accepted_ids
    claims_by_tick: dict[str, set[str]] = {}
    for decision in (item for item in resource_decisions if item["accepted"]):
        for key in decision["conflict_keys"]:
            _, stock_id, year, month = key.split(":")
            tick = f"{year}:{month}"
            assert stock_id not in claims_by_tick.setdefault(tick, set())
            claims_by_tick[tick].add(stock_id)


def test_demographic_batch_is_complete_and_reversed_order_stable(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    decisions = repository.load_verified("proposal_resolutions").payload
    raw_events = repository.load_verified("history").payload
    events = [event for event in raw_events if event["kind"] == "monthly_demography"]
    demographic_decisions = [
        item
        for item in decisions
        if any(key.startswith("demography:") for key in item["conflict_keys"])
    ]

    assert events and len(demographic_decisions) == len(events)
    assert all(item["accepted"] and not item["blocked_by"] for item in demographic_decisions)
    rebuilt = tuple(
        HistoryProposal(
            dict(event["consequences"][0]["details"])["proposal_id"],
            event["year"],
            event["month"],
            EventKind.MONTHLY_DEMOGRAPHY,
            event["participants"][0],
            tuple(event["participants"]),
            tuple(event["locations"]),
            tuple(
                Consequence(
                    ConsequenceKind(item["kind"]),
                    item["subject"],
                    item["amount"],
                    item["target"],
                    item["value"],
                    tuple(tuple(pair) for pair in item["details"]),
                )
                for item in event["consequences"]
            ),
            event["summary"],
            tuple(event["causes"]),
            (dict(event["consequences"][0]["details"])["conflict_key"],),
            0,
        )
        for event in events
    )
    accepted, forward = resolve_proposals(rebuilt)
    reversed_accepted, backward = resolve_proposals(tuple(reversed(rebuilt)))
    assert accepted == reversed_accepted
    assert forward == backward


def test_disaster_and_crime_share_one_immutable_risk_batch(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    decisions = repository.load_verified("proposal_resolutions").payload
    history = repository.load_verified("history").payload
    risk_decisions = [
        item for item in decisions if any(key.startswith("risk-") for key in item["conflict_keys"])
    ]
    risk_events = [item for item in history if item["kind"] in {"disaster", "crime"}]

    assert risk_decisions and risk_events
    assert {item["proposal_id"] for item in risk_decisions if item["accepted"]} == {
        dict(event["consequences"][0]["details"])["proposal_id"] for event in risk_events
    }
    claims_by_tick: dict[str, set[str]] = {}
    for decision in (item for item in risk_decisions if item["accepted"]):
        for key in decision["conflict_keys"]:
            parts = key.split(":")
            tick = ":".join(parts[-2:])
            claim = ":".join(parts[:-2])
            assert claim not in claims_by_tick.setdefault(tick, set())
            claims_by_tick[tick].add(claim)


def test_ageing_and_relationships_share_one_annual_social_snapshot(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    decisions = repository.load_verified("proposal_resolutions").payload
    history = repository.load_verified("history").payload
    social_decisions = [
        item
        for item in decisions
        if any(key.startswith("social-") for key in item["conflict_keys"])
    ]
    social_events = [
        item for item in history if item["kind"] in {"ageing", "relationship", "person_status"}
    ]

    assert social_decisions and social_events
    assert {item["proposal_id"] for item in social_decisions if item["accepted"]} == {
        dict(event["consequences"][0]["details"])["proposal_id"] for event in social_events
    }
    assert all(not item["blocked_by"] for item in social_decisions if item["accepted"])
    assert all(item["blocked_by"] for item in social_decisions if not item["accepted"])
    for event in social_events:
        details = dict(event["consequences"][0]["details"])
        assert details["snapshot"].endswith(":12")
        assert details["conflict_keys"]


def test_migration_and_diplomacy_share_one_annual_polity_snapshot(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    decisions = repository.load_verified("proposal_resolutions").payload
    history = repository.load_verified("history").payload
    annual_decisions = [
        item
        for item in decisions
        if any(key.startswith("annual-") for key in item["conflict_keys"])
    ]
    polity_events = [
        item for item in history if item["kind"] in {"migration", "diplomacy", "war", "peace"}
    ]

    assert annual_decisions and polity_events
    assert all(item["accepted"] and not item["blocked_by"] for item in annual_decisions)
    assert {item["proposal_id"] for item in annual_decisions if item["accepted"]} == {
        dict(event["consequences"][0]["details"])["proposal_id"] for event in polity_events
    }
    for event in polity_events:
        details = dict(event["consequences"][0]["details"])
        assert details["snapshot"] == f"{event['year']:04d}:12"
        keys = tuple(details["conflict_keys"].split(","))
        assert keys == tuple(sorted(set(keys)))
        if event["kind"] == "migration":
            assert len([key for key in keys if key.startswith("annual-population:")]) == 2
        else:
            assert any(key.startswith("annual-relation:") for key in keys)

    proposal_by_war = {
        event["event_id"]: dict(event["consequences"][0]["details"])["proposal_id"]
        for event in polity_events
        if event["kind"] == "war"
    }
    conquests = [item for item in history if item["kind"] == "conquest"]
    assert conquests
    for conquest in conquests:
        assert (
            dict(conquest["consequences"][0]["details"])["proposal_id"]
            == (proposal_by_war[conquest["causes"][0]])
        )


def test_institutional_changes_resolve_from_one_immutable_snapshot(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    decisions = repository.load_verified("proposal_resolutions").payload
    history = repository.load_verified("history").payload
    institutional_decisions = [
        item
        for item in decisions
        if any(key.startswith("institution-") for key in item["conflict_keys"])
    ]
    institutional_events = [
        item for item in history if item["kind"] in {"collapse", "recovery", "succession", "reform"}
    ]

    assert institutional_decisions and institutional_events
    accepted_ids = {item["proposal_id"] for item in institutional_decisions if item["accepted"]}
    assert accepted_ids == {
        dict(event["consequences"][0]["details"])["proposal_id"] for event in institutional_events
    }
    claimed_by_year: dict[str, set[str]] = {}
    for decision in (item for item in institutional_decisions if item["accepted"]):
        for key in decision["conflict_keys"]:
            year = key.rsplit(":", 1)[-1]
            claim = key.rsplit(":", 1)[0]
            assert claim not in claimed_by_year.setdefault(year, set())
            claimed_by_year[year].add(claim)
    for event in institutional_events:
        details = dict(event["consequences"][0]["details"])
        assert details["snapshot"] == f"{event['year']:04d}:12"
        assert details["proposal_id"] in accepted_ids


def test_all_scheduler_proposals_are_decided_and_traceable(simulated_world) -> None:
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    decisions = repository.load_verified("proposal_resolutions").payload
    history = repository.load_verified("history").payload
    accepted_ids = {item["proposal_id"] for item in decisions if item["accepted"]}
    event_proposal_ids = {
        details["proposal_id"]
        for event in history
        for consequence in event["consequences"]
        if "proposal_id" in (details := dict(consequence["details"]))
    }

    assert accepted_ids == event_proposal_ids
    assert all(item["conflict_keys"] == sorted(set(item["conflict_keys"])) for item in decisions)
    assert all(item["blocked_by"] for item in decisions if not item["accepted"])
    assert any(
        any(key.startswith("knowledge-") for key in item["conflict_keys"]) for item in decisions
    )
    assert any(
        any(key.startswith("content-") for key in item["conflict_keys"]) for item in decisions
    )
