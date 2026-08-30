"""Typed bounded projections from authoritative simulation facts to story candidates."""

from __future__ import annotations

from dataclasses import dataclass

from .events import HistoryEvent
from .state import SimulationState

OPPORTUNITY_KINDS = (
    "chokepoint",
    "contested_resource",
    "cultural_tension",
    "ecological_tension",
    "faction_goal",
    "factual_mystery",
    "frontier",
)
# Anchored on entities (megabeasts, legendary artifacts) that are not guaranteed
# to exist in every world, so they cannot join the mandatory taxonomy above.
CONDITIONAL_OPPORTUNITY_KINDS = ("legendary_hunt", "artifact_recovery")
ALL_OPPORTUNITY_KINDS = OPPORTUNITY_KINDS + CONDITIONAL_OPPORTUNITY_KINDS
OPPORTUNITY_ROLES = ("antagonist", "patron", "protagonist", "witness")
MAX_STORY_PROJECTIONS = 16


@dataclass(frozen=True)
class StoryProjection:
    """A selective factual candidate; never an authoritative-world mutation."""

    kind: str
    pressure: str
    civilization_ids: tuple[str, ...]
    region_ids: tuple[str, ...]
    route_ids: tuple[str, ...]
    person_ids: tuple[str, ...]
    belief_ids: tuple[str, ...]
    site_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    local_containment_ids: tuple[str, ...]
    answer_fact_ids: tuple[str, ...]
    constraint_ids: tuple[str, ...]
    role_assignments: tuple[tuple[str, str], ...]
    source_ids: tuple[str, ...]


def validate_story_projections(projections: tuple[StoryProjection, ...]) -> None:
    """Enforce the frozen taxonomy, bounds, canonical sets, and social-role vocabulary."""
    if not projections or len(projections) > MAX_STORY_PROJECTIONS:
        raise ValueError("WG-PROJECTION-BOUND: projection count is outside the frozen budget")
    kinds = {item.kind for item in projections}
    if len(kinds) != len(projections):
        raise ValueError("WG-PROJECTION-TAXONOMY: emit at most one candidate per kind")
    if not set(OPPORTUNITY_KINDS) <= kinds or not kinds <= set(ALL_OPPORTUNITY_KINDS):
        raise ValueError("WG-PROJECTION-TAXONOMY: mandatory kind missing or kind is unknown")
    for item in projections:
        inventories = (
            item.civilization_ids,
            item.region_ids,
            item.route_ids,
            item.person_ids,
            item.belief_ids,
            item.site_ids,
            item.event_ids,
            item.local_containment_ids,
            item.answer_fact_ids,
            item.constraint_ids,
            item.source_ids,
        )
        if (
            item.kind not in ALL_OPPORTUNITY_KINDS
            or not item.pressure
            or any(values != tuple(sorted(set(values))) for values in inventories)
            or tuple(role for role, _ in item.role_assignments) != OPPORTUNITY_ROLES
            or any(not person_id for _, person_id in item.role_assignments)
        ):
            raise ValueError("WG-PROJECTION-SHAPE: noncanonical story projection")


def history_summary(
    state: SimulationState,
    ledger: tuple[HistoryEvent, ...],
    limit: int = 100,
) -> dict[str, object]:
    """Read-only bounded prompt projection; never an authoritative history store.

    Always reports whether it was truncated (`projection_is_complete`) so a
    caller can never mistake this bounded view for the full causal ledger.
    """
    if limit < 0:
        raise ValueError("summary limit must be nonnegative")
    selected = ledger[-limit:] if limit else ()
    return {
        "present_year": state.year,
        "civilizations": tuple(
            (c.civilization_id, c.name, c.population) for c in state.civilizations
        ),
        "recent_events": tuple((e.event_id, e.year, e.kind.value, e.summary) for e in selected),
        "authoritative_event_count": len(ledger),
        "projection_is_complete": len(selected) == len(ledger),
    }
