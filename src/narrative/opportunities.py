"""Deterministic factual opportunities derived only from world pressures."""
from __future__ import annotations

from ..world.views import WorldView
from ..worldgen.local_index import LocalWorldIndex
from ..worldgen.numeric import identity, stable_id
from .models import StoryOpportunity


def generate_opportunities(
    world: WorldView, local_index: LocalWorldIndex,
) -> tuple[StoryOpportunity, ...]:
    civilizations = world.civilizations()
    routes = world.routes()
    sites = {fact.fact_id: fact for fact in world.sites()}
    material_events = world.events(("war", "peace", "collapse", "recovery", "schism",
                                    "reform", "technology", "exploration"))
    identities = world.identities()
    genealogy = world.repository.load_verified("genealogy")
    people_by_civilization: dict[str, tuple[str, ...]] = {}
    for person in genealogy.payload["people"]:
        civilization_id = str(person["civilization_id"])
        people_by_civilization[civilization_id] = (
            *people_by_civilization.get(civilization_id, ()), str(person["person_id"]),
        )
    religions = tuple(identities.value["religions"])
    local_by_site = {entry.site_id: entry for entry in local_index.entries}
    opportunities: list[StoryOpportunity] = []
    for index, civilization in enumerate(civilizations):
        territory = tuple(civilization.value["territory"])
        capital_region = str(sites[civilization.value["capital_site_id"]].value["region_id"])
        locations = territory[:1] or (capital_region,)
        relevant_routes = tuple(
            route.fact_id for route in routes
            if (route.value["start_region"] in territory
                or route.value["end_region"] in territory)
        )
        relevant_events = tuple(event.fact_id for event in material_events
                                if civilization.fact_id in event.value["participants"])
        source_ids = tuple(dict.fromkeys(civilization.source_ids
                           + tuple(event.source_ids[0] for event in material_events
                                   if event.fact_id in relevant_events)
                           + ((identities.source_ids[0],) if identities.source_ids else ())
                           + (genealogy.artifact_id,)))
        pressure = (
            "unresolved scarcity and contested travel"
            if relevant_routes else "local institutional recovery"
        )
        site_id = str(civilization.value["capital_site_id"])
        local = local_by_site[site_id]
        person_ids = tuple(sorted(people_by_civilization[civilization.fact_id]))[:2]
        belief_ids = tuple(sorted(
            str(religion["religion_id"]) for religion in religions
            if str(religion["holy_site_id"]) == site_id
        ))
        opportunities.append(StoryOpportunity(
            stable_id("opportunity", world.present_year,
                      identity("civilization_id", civilization.fact_id)), pressure,
            (civilization.fact_id,), locations, relevant_routes[:3], source_ids,
            relevant_events[-10:],
            person_ids, belief_ids, (site_id,),
            (local.boundary_id, local.summary_id),
        ))
    result = tuple(opportunities)
    validate_opportunities(world, local_index, result)
    return result


def validate_opportunities(
    world: WorldView, local_index: LocalWorldIndex,
    opportunities: tuple[StoryOpportunity, ...],
) -> None:
    """Reject invented, incomplete, unbounded, or noncanonical opportunity evidence."""
    civilizations = {item.fact_id for item in world.civilizations()}
    routes = {item.fact_id for item in world.routes()}
    regions = {item.fact_id for item in world.regions()}
    sites = {item.fact_id for item in world.sites()}
    events = {item.fact_id for item in world.events()}
    genealogy = world.repository.load_verified("genealogy")
    people = {str(item["person_id"]) for item in genealogy.payload["people"]}
    beliefs = {
        str(item["religion_id"]) for item in world.identities().value["religions"]
    }
    containment = {
        value for entry in local_index.entries for value in (entry.boundary_id, entry.summary_id)
    }
    if (not opportunities
            or len({item.opportunity_id for item in opportunities}) != len(opportunities)):
        raise ValueError(
            "OPPORTUNITY-SHAPE: opportunities must be nonempty and uniquely identified"
        )
    for item in opportunities:
        ordered_sets = (
            item.route_ids, item.person_ids, item.belief_ids, item.site_ids,
            item.local_containment_ids,
        )
        if any(values != tuple(sorted(set(values))) for values in ordered_sets):
            raise ValueError("OPPORTUNITY-ORDER: evidence inventories must be canonical")
        if (not item.pressure or len(item.revealable_fact_ids) > 10
                or not set(item.participant_ids) <= civilizations
                or not set(item.location_ids) <= regions
                or not set(item.route_ids) <= routes
                or not set(item.revealable_fact_ids) <= events
                or not item.person_ids or not set(item.person_ids) <= people
                or not item.belief_ids or not set(item.belief_ids) <= beliefs
                or not item.site_ids or not set(item.site_ids) <= sites
                or len(item.local_containment_ids) != 2
                or not set(item.local_containment_ids) <= containment):
            raise ValueError("OPPORTUNITY-AUTHORITY: incomplete or invented evidence")
