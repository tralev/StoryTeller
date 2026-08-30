from dataclasses import replace

import pytest

from src.worldgen.artifacts import WorldArtifactRepository
from src.worldgen.simulation.events import Consequence, ConsequenceKind, EventKind, HistoryEvent
from src.worldgen.simulation.polity_lifecycle import project_polity_lifecycle
from src.worldgen.simulation.replay import _state
from src.worldgen.simulation.state import SettlementStatus


def _cycle(state):
    civilization = state.civilizations[0]
    settlement = next(
        item for item in state.settlements if item.civilization_id == civilization.civilization_id
    )
    collapse_keys = ",".join(
        sorted(
            (
                f"institution-polity:{civilization.civilization_id}:0200",
                f"institution-settlement:{settlement.settlement_id}:0200",
            )
        )
    )
    collapse_details = (
        ("prior_polity_state", "active"),
        ("new_polity_state", "inactive"),
        ("prior_settlement_status", "inhabited"),
        ("new_settlement_status", "abandoned"),
        ("settlement_id", settlement.settlement_id),
        ("proposal_id", "history_proposal_test_collapse"),
        ("conflict_keys", collapse_keys),
        ("snapshot", "0200:12"),
    )
    collapse = HistoryEvent(
        "collapse-event",
        200,
        12,
        1,
        EventKind.COLLAPSE,
        (),
        (civilization.civilization_id,),
        (civilization.capital_site_id,),
        (
            Consequence(
                ConsequenceKind.ACTIVE_SET,
                civilization.civilization_id,
                value="inactive",
                details=collapse_details,
            ),
            Consequence(
                ConsequenceKind.SETTLEMENT_STATUS_SET,
                settlement.settlement_id,
                value=SettlementStatus.ABANDONED.value,
                details=collapse_details,
            ),
        ),
        "The polity collapsed.",
    )
    recovery_keys = ",".join(
        sorted(
            (
                f"institution-polity:{civilization.civilization_id}:0210",
                f"institution-settlement:{settlement.settlement_id}:0210",
            )
        )
    )
    recovery_details = (
        ("prior_polity_state", "inactive"),
        ("new_polity_state", "active"),
        ("prior_settlement_status", "abandoned"),
        ("new_settlement_status", "inhabited"),
        ("settlement_id", settlement.settlement_id),
        ("collapse_event_id", collapse.event_id),
        ("proposal_id", "history_proposal_test_recovery"),
        ("conflict_keys", recovery_keys),
        ("snapshot", "0210:12"),
    )
    recovery = HistoryEvent(
        "recovery-event",
        210,
        12,
        2,
        EventKind.RECOVERY,
        (collapse.event_id,),
        (civilization.civilization_id,),
        (civilization.capital_site_id,),
        (
            Consequence(
                ConsequenceKind.ACTIVE_SET,
                civilization.civilization_id,
                value="active",
                details=recovery_details,
            ),
            Consequence(
                ConsequenceKind.SETTLEMENT_STATUS_SET,
                settlement.settlement_id,
                value=SettlementStatus.INHABITED.value,
                details=recovery_details,
            ),
        ),
        "The polity recovered.",
    )
    return collapse, recovery


def test_collapse_recovery_cycle_is_typed_causal_and_identity_preserving(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    state = _state(repository.load_verified("snapshots").payload[0]["state"])
    collapse, recovery = _cycle(state)
    from src.worldgen.simulation.events import apply_event

    collapsed = apply_event(state, collapse)
    recovered = apply_event(collapsed, recovery)

    transitions = project_polity_lifecycle(
        42,
        (collapse, recovery),
        state.civilizations,
        state.settlements,
        recovered.civilizations,
        recovered.settlements,
    )
    assert [item.new_polity_state for item in transitions] == ["inactive", "active"]
    assert transitions[1].collapse_event_id == collapse.event_id
    assert transitions[0].civilization_id == transitions[1].civilization_id
    assert transitions[0].settlement_id == transitions[1].settlement_id


def test_recovery_must_cite_the_collapse_it_reverses(simulated_world):
    _, historical, _ = simulated_world
    repository = WorldArtifactRepository(historical / "artifacts")
    state = _state(repository.load_verified("snapshots").payload[0]["state"])
    collapse, recovery = _cycle(state)
    malformed = replace(recovery, causes=("unrelated-event",))
    with pytest.raises(ValueError, match="WG-POLITY-LIFECYCLE"):
        project_polity_lifecycle(
            42,
            (collapse, malformed),
            state.civilizations,
            state.settlements,
            state.civilizations,
            state.settlements,
        )


def test_short_history_publishes_empty_verified_lifecycle(simulated_world):
    _, historical, _ = simulated_world
    payload = (
        WorldArtifactRepository(historical / "artifacts").load_verified("polity_lifecycle").payload
    )
    assert payload == ()
