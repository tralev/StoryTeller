"""Immutable history proposals with deterministic exactly-once conflict resolution."""

from __future__ import annotations

from dataclasses import dataclass

from .events import Consequence, EventKind


@dataclass(frozen=True)
class HistoryProposal:
    proposal_id: str
    year: int
    month: int
    kind: EventKind
    actor_id: str
    participants: tuple[str, ...]
    locations: tuple[str, ...]
    consequences: tuple[Consequence, ...]
    summary: str
    causes: tuple[str, ...]
    conflict_keys: tuple[str, ...]
    priority: int


@dataclass(frozen=True)
class ProposalDecision:
    proposal_id: str
    accepted: bool
    conflict_keys: tuple[str, ...]
    blocked_by: tuple[str, ...]
    conflict_sort_key: tuple[str, ...]


def conflict_sort_key(proposal: HistoryProposal) -> tuple[object, ...]:
    """Frozen total ordering used before any proposal is applied."""
    return (
        proposal.year,
        proposal.month,
        proposal.priority,
        proposal.kind.value,
        proposal.actor_id,
        proposal.proposal_id,
    )


def resolve_proposals(
    proposals: tuple[HistoryProposal, ...],
) -> tuple[tuple[HistoryProposal, ...], tuple[ProposalDecision, ...]]:
    """Accept each unclaimed conflict key once, independent of input ordering."""
    proposal_ids = [item.proposal_id for item in proposals]
    if len(proposal_ids) != len(set(proposal_ids)):
        raise ValueError("WG-PROPOSAL-ID: duplicate proposal identity")
    for proposal in proposals:
        if (
            not proposal.proposal_id
            or not proposal.participants
            or not proposal.locations
            or not proposal.consequences
            or proposal.priority < 0
            or not proposal.conflict_keys
            or proposal.conflict_keys != tuple(sorted(set(proposal.conflict_keys)))
        ):
            raise ValueError(f"WG-PROPOSAL-SHAPE: {proposal.proposal_id}")
    accepted: list[HistoryProposal] = []
    decisions: list[ProposalDecision] = []
    claimed_by: dict[str, str] = {}
    for proposal in sorted(proposals, key=conflict_sort_key):
        blockers = tuple(
            sorted({claimed_by[key] for key in proposal.conflict_keys if key in claimed_by})
        )
        is_accepted = not blockers
        if is_accepted:
            accepted.append(proposal)
            for key in proposal.conflict_keys:
                claimed_by[key] = proposal.proposal_id
        decisions.append(
            ProposalDecision(
                proposal.proposal_id,
                is_accepted,
                proposal.conflict_keys,
                blockers,
                tuple(str(item) for item in conflict_sort_key(proposal)),
            )
        )
    return tuple(accepted), tuple(decisions)
