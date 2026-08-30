"""Deterministic factual story opportunities projected from authoritative facts."""

from __future__ import annotations

from collections.abc import Mapping

from ..world.views import WorldFact, WorldView
from ..worldgen.local_index import LocalWorldIndex
from ..worldgen.numeric import identity, stable_id
from ..worldgen.simulation.projections import (
    ALL_OPPORTUNITY_KINDS,
    OPPORTUNITY_KINDS,
    OPPORTUNITY_ROLES,
    StoryProjection,
    validate_story_projections,
)
from .models import StoryOpportunity


def _record_id(value: object, field: str) -> str:
    if isinstance(value, Mapping):
        return str(value[field])
    return str(getattr(value, field))


def _route_metric(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, (tuple, list)):
        return sum(int(item) for item in value)
    raise ValueError("OPPORTUNITY-ROUTE: invalid route metric")


def _story_projections(
    world: WorldView,
    local_index: LocalWorldIndex,
) -> tuple[StoryProjection, ...]:
    civilizations = world.civilizations()
    regions = {item.fact_id: item for item in world.regions()}
    routes = world.routes()
    sites = {item.fact_id: item for item in world.sites()}
    events = world.events()
    identities = world.identities()
    genealogy = world.repository.load_verified("genealogy")
    present_year = world.present_year
    available_people = tuple(
        fact
        for fact in world.people()
        if int(fact.value["created_year"]) <= present_year
        and not (
            fact.value["status"] == "dead"
            and fact.value["status_year"] is not None
            and int(fact.value["status_year"]) <= present_year
        )
    )
    religions = tuple(identities.value["religions"])
    local_by_site = {entry.site_id: entry for entry in local_index.entries}
    people_by_civ = {
        civilization.fact_id: tuple(
            sorted(
                fact.fact_id
                for fact in available_people
                if str(fact.value["civilization_id"]) == civilization.fact_id
            )
        )
        for civilization in civilizations
    }
    all_people = tuple(sorted({person_id for ids in people_by_civ.values() for person_id in ids}))

    def require_role_people(role_people: tuple[str, ...], kind: str) -> tuple[str, ...]:
        if not role_people:
            raise ValueError(f"OPPORTUNITY-CAPACITY: no available person exists for {kind}")
        return role_people

    frontier_routes = tuple(
        item
        for item in routes
        if any(
            (item.value["start_region"] in set(civilization.value["territory"]))
            != (item.value["end_region"] in set(civilization.value["territory"]))
            for civilization in civilizations
        )
    )
    chokepoint_routes = tuple(
        sorted(
            routes,
            key=lambda item: (
                -_route_metric(item.value["river_crossings"]),
                -_route_metric(item.value["seasonal_risk_ppm"]),
                _route_metric(item.value["seasonal_capacity"]),
                item.fact_id,
            ),
        )
    )
    event_kinds = {
        "frontier": {"exploration"},
        "chokepoint": {"trade", "war"},
        "contested_resource": {"trade", "war", "crime"},
        "factual_mystery": set(),
        "faction_goal": {"diplomacy", "war", "reform", "succession"},
        "cultural_tension": {"schism", "religion", "reform"},
        "ecological_tension": {"collapse", "recovery", "disaster"},
    }
    resource_holders: dict[str, list[str]] = {}
    for civilization in civilizations:
        resources = {
            str(resource)
            for region_id in civilization.value["territory"]
            for resource in regions[str(region_id)].value["resources"]
        }
        for resource in resources:
            resource_holders.setdefault(resource, []).append(civilization.fact_id)
    contested = next(
        (
            (resource, tuple(sorted(set(holders))))
            for resource, holders in sorted(resource_holders.items())
            if len(set(holders)) >= 2
        ),
        None,
    )

    def projection(kind: str, ordinal: int) -> StoryProjection:
        civilization = civilizations[ordinal % len(civilizations)]
        site_id = str(civilization.value["capital_site_id"])
        region_id = str(sites[site_id].value["region_id"])
        local = local_by_site[site_id]
        territory = set(civilization.value["territory"])
        relevant_routes = tuple(
            item
            for item in routes
            if {
                item.value["start_region"],
                item.value["end_region"],
            }
            & territory
        ) or (routes[ordinal % len(routes)],)
        route = (
            next((item for item in frontier_routes if item in relevant_routes), relevant_routes[0])
            if kind == "frontier"
            else chokepoint_routes[0]
            if kind == "chokepoint"
            else relevant_routes[0]
        )
        allowed_event_kinds = event_kinds[kind]
        event = next(
            (
                item
                for item in reversed(events)
                if civilization.fact_id in item.value["participants"]
                and (
                    str(item.value["kind"]) in allowed_event_kinds
                    or (kind == "factual_mystery" and item.value["causes"])
                )
            ),
            next(
                (
                    item
                    for item in reversed(events)
                    if civilization.fact_id in item.value["participants"]
                ),
                events[-1],
            ),
        )
        religion = next(
            (item for item in religions if _record_id(item, "holy_site_id") == site_id),
            religions[ordinal % len(religions)],
        )
        person_ids = people_by_civ[civilization.fact_id]
        participant_ids = (
            contested[1]
            if kind == "contested_resource" and contested is not None
            else (civilization.fact_id,)
        )
        role_people = require_role_people(
            tuple(
                person_id
                for participant in participant_ids
                for person_id in people_by_civ[participant]
            )
            or person_ids
            or all_people,
            kind,
        )
        assigned = tuple(
            (role, role_people[index % len(role_people)])
            for index, role in enumerate(OPPORTUNITY_ROLES)
        )
        resource = (
            contested[0]
            if kind == "contested_resource" and contested is not None
            else next(iter(regions[region_id].value["resources"]), "regional carrying capacity")
        )
        pressures = {
            "frontier": "a documented frontier links unequal neighbouring territories",
            "chokepoint": "seasonal travel capacity makes an authoritative route a chokepoint",
            "contested_resource": f"access to {resource} creates a bounded material dispute",
            "factual_mystery": "a historical consequence has a discoverable authoritative cause",
            "faction_goal": "a polity goal is constrained by capacity, relations, and travel",
            "cultural_tension": "an attributed belief conflicts with historical institutions",
            "ecological_tension": "settlement demand presses against recorded ecological capacity",
        }
        answer_ids = (
            tuple(sorted((event.fact_id, world.artifact_ids["geology"])))
            if kind == "factual_mystery"
            else ()
        )
        sources = tuple(
            sorted(
                set(
                    civilization.source_ids
                    + regions[region_id].source_ids
                    + route.source_ids
                    + event.source_ids
                    + sites[site_id].source_ids
                    + identities.source_ids
                    + (genealogy.artifact_id, world.artifact_ids["ecology"])
                )
            )
        )
        return StoryProjection(
            kind,
            pressures[kind],
            tuple(sorted(participant_ids)),
            (region_id,),
            (route.fact_id,),
            tuple(sorted(set(role_people))),
            (_record_id(religion, "religion_id"),),
            (site_id,),
            (event.fact_id,),
            tuple(sorted((local.boundary_id, local.summary_id))),
            answer_ids,
            tuple(sorted((*participant_ids, route.fact_id, local.summary_id))),
            assigned,
            sources,
        )

    result = tuple(projection(kind, index) for index, kind in enumerate(OPPORTUNITY_KINDS))

    def optional_projection(
        kind: str,
        pressure: str,
        entity: WorldFact,
        civ: WorldFact,
        region_id: str,
        site_id: str,
        ordinal: int,
    ) -> StoryProjection:
        local = local_by_site[site_id]
        event = next(
            (item for item in reversed(events) if civ.fact_id in item.value["participants"]),
            events[-1],
        )
        religion = religions[ordinal % len(religions)]
        role_people = require_role_people(people_by_civ[civ.fact_id] or all_people, kind)
        assigned = tuple(
            (role, role_people[index % len(role_people)])
            for index, role in enumerate(OPPORTUNITY_ROLES)
        )
        sources = tuple(
            sorted(
                set(
                    entity.source_ids
                    + civ.source_ids
                    + regions[region_id].source_ids
                    + sites[site_id].source_ids
                    + event.source_ids
                    + identities.source_ids
                )
            )
        )
        return StoryProjection(
            kind,
            pressure,
            (civ.fact_id,),
            (region_id,),
            (),
            tuple(sorted(set(role_people))),
            (_record_id(religion, "religion_id"),),
            (site_id,),
            (event.fact_id,),
            tuple(sorted((local.boundary_id, local.summary_id))),
            (),
            tuple(sorted((civ.fact_id, local.summary_id))),
            assigned,
            sources,
        )

    optional: list[StoryProjection] = []
    megabeasts = world.megabeasts()
    if megabeasts:
        ordinal = len(OPPORTUNITY_KINDS)
        beast = megabeasts[ordinal % len(megabeasts)]
        beast_region_id = str(beast.value["region_id"])
        beast_site_id = str(beast.value["lair_site_id"])
        beast_territory = {str(item) for item in beast.value["territory_region_ids"]}
        beast_civ = next(
            (item for item in civilizations if set(item.value["territory"]) & beast_territory),
            civilizations[ordinal % len(civilizations)],
        )
        optional.append(
            optional_projection(
                "legendary_hunt",
                "a rare megabeast threatens or tempts an authoritative territory",
                beast,
                beast_civ,
                beast_region_id,
                beast_site_id,
                ordinal,
            )
        )
    legendary_artifacts = world.legendary_artifacts()
    if legendary_artifacts:
        ordinal = len(OPPORTUNITY_KINDS) + 1
        artifact = legendary_artifacts[ordinal % len(legendary_artifacts)]
        artifact_site_id = str(artifact.value["current_site_id"])
        artifact_region_id = str(sites[artifact_site_id].value["region_id"])
        artifact_civ = next(
            (item for item in civilizations if item.fact_id == str(artifact.value["culture_id"])),
            civilizations[ordinal % len(civilizations)],
        )
        optional.append(
            optional_projection(
                "artifact_recovery",
                "a legendary artifact's authoritative provenance can be recovered or contested",
                artifact,
                artifact_civ,
                artifact_region_id,
                artifact_site_id,
                ordinal,
            )
        )
    result = result + tuple(optional)
    validate_story_projections(result)
    return result


def generate_opportunities(
    world: WorldView,
    local_index: LocalWorldIndex,
) -> tuple[StoryOpportunity, ...]:
    projections = _story_projections(world, local_index)
    opportunities = tuple(
        StoryOpportunity(
            stable_id(
                "opportunity",
                world.present_year,
                identity("kind", item.kind),
                identity("civilization_id", item.civilization_ids[0]),
            ),
            item.pressure,
            item.civilization_ids,
            item.region_ids,
            item.route_ids,
            item.source_ids,
            item.event_ids,
            item.person_ids,
            item.belief_ids,
            item.site_ids,
            item.local_containment_ids,
            item.kind,
            item.answer_fact_ids,
            item.constraint_ids,
            item.role_assignments,
        )
        for item in projections
    )
    validate_opportunities(world, local_index, opportunities)
    return opportunities


def validate_opportunities(
    world: WorldView,
    local_index: LocalWorldIndex,
    opportunities: tuple[StoryOpportunity, ...],
) -> None:
    """Reject invented, incomplete, unbounded, or noncanonical opportunity evidence."""
    civilizations = {item.fact_id for item in world.civilizations()}
    routes = {item.fact_id for item in world.routes()}
    regions = {item.fact_id for item in world.regions()}
    sites = {item.fact_id for item in world.sites()}
    events = {item.fact_id for item in world.events()}
    genealogy = world.repository.load_verified("genealogy")
    people = {_record_id(item, "person_id") for item in genealogy.payload["people"]}
    beliefs = {_record_id(item, "religion_id") for item in world.identities().value["religions"]}
    containment = {
        value for entry in local_index.entries for value in (entry.boundary_id, entry.summary_id)
    }
    known_constraints = civilizations | routes | containment
    known_answers = events | {world.artifact_ids["geology"]}
    kinds = {item.opportunity_kind for item in opportunities}
    if (
        not opportunities
        or len({item.opportunity_id for item in opportunities}) != len(opportunities)
        or not set(OPPORTUNITY_KINDS) <= kinds
        or not kinds <= set(ALL_OPPORTUNITY_KINDS)
    ):
        raise ValueError("OPPORTUNITY-SHAPE: taxonomy must be complete and uniquely identified")
    for item in opportunities:
        ordered_sets = (
            item.route_ids,
            item.person_ids,
            item.belief_ids,
            item.site_ids,
            item.local_containment_ids,
            item.answer_fact_ids,
            item.constraint_ids,
        )
        if any(values != tuple(sorted(set(values))) for values in ordered_sets):
            raise ValueError("OPPORTUNITY-ORDER: evidence inventories must be canonical")
        if (
            not item.pressure
            or len(item.revealable_fact_ids) > 10
            or not set(item.participant_ids) <= civilizations
            or not set(item.location_ids) <= regions
            or not set(item.route_ids) <= routes
            or not set(item.revealable_fact_ids) <= events
            or not item.person_ids
            or not set(item.person_ids) <= people
            or not item.belief_ids
            or not set(item.belief_ids) <= beliefs
            or not item.site_ids
            or not set(item.site_ids) <= sites
            or len(item.local_containment_ids) != 2
            or not set(item.local_containment_ids) <= containment
            or not set(item.constraint_ids) <= known_constraints
            or not set(item.answer_fact_ids) <= known_answers
            or tuple(role for role, _ in item.role_assignments) != OPPORTUNITY_ROLES
            or not {person for _, person in item.role_assignments} <= people
            or (item.opportunity_kind == "factual_mystery" and not item.answer_fact_ids)
        ):
            raise ValueError("OPPORTUNITY-AUTHORITY: incomplete or invented evidence")
