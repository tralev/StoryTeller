"""Deterministic factual opportunities derived only from world pressures."""
from __future__ import annotations

from ..world.views import WorldView
from ..worldgen.numeric import identity, stable_id
from .models import StoryOpportunity


def generate_opportunities(world: WorldView) -> tuple[StoryOpportunity, ...]:
    civilizations = world.civilizations()
    routes = world.routes()
    sites = {fact.fact_id: fact for fact in world.sites()}
    material_events = world.events(("war", "peace", "collapse", "recovery", "schism",
                                    "reform", "technology", "exploration"))
    identities = world.identities()
    opportunities: list[StoryOpportunity] = []
    for index, civilization in enumerate(civilizations):
        territory = tuple(civilization.value["territory"])
        capital_region = str(sites[civilization.value["capital_site_id"]].value["region_id"])
        locations = territory[:1] or (capital_region,)
        relevant_routes = tuple(route.fact_id for route in routes
                                if route.value["start_region"] in territory or route.value["end_region"] in territory)
        relevant_events = tuple(event.fact_id for event in material_events
                                if civilization.fact_id in event.value["participants"])
        source_ids = tuple(dict.fromkeys(civilization.source_ids
                           + tuple(event.source_ids[0] for event in material_events
                                   if event.fact_id in relevant_events)
                           + ((identities.source_ids[0],) if identities.source_ids else ())))
        pressure = "unresolved scarcity and contested travel" if relevant_routes else "local institutional recovery"
        opportunities.append(StoryOpportunity(
            stable_id("opportunity", world.present_year,
                      identity("civilization_id", civilization.fact_id)), pressure,
            (civilization.fact_id,), locations, relevant_routes[:3], source_ids,
            relevant_events[-10:],
        ))
    return tuple(opportunities)
