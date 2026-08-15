"""Civilization generation — placement, race/government assignment, and
population simulation over time.

Civilizations start in prosperous regions, expand to neighbors, and
compete for territory. A simple time-stepped simulation grows
populations and records history events.
"""

from __future__ import annotations

from .models import Civilization, HistoryEvent, Region, Site, SiteType, WorldRNG
from ..domain.run_spec import derive_seed
from .numeric import div_round_half_up

# Race options with weights
_RACES: list[tuple[str, float]] = [
    ("human", 0.35),
    ("elf", 0.15),
    ("dwarf", 0.15),
    ("orc", 0.10),
    ("halfling", 0.08),
    ("gnome", 0.05),
    ("goblin", 0.05),
    ("lizardfolk", 0.04),
    ("tiefling", 0.03),
]

# Government types by race
_GOVERNMENTS: dict[str, list[str]] = {
    "human": ["feudal_monarchy", "republic", "theocracy", "empire", "city_state"],
    "elf": ["elder_council", "magocracy", "enclave"],
    "dwarf": ["clan_council", "monarchy", "meritocracy"],
    "orc": ["warchief", "tribal_council", "horde"],
    "halfling": ["mayoral", "informal_council", "mercantile"],
    "gnome": ["guild_council", "technocracy", "collective"],
    "goblin": ["boss_rule", "tribal_horde", "cunning_cabal"],
    "lizardfolk": ["shaman_council", "alpha_hierarchy", "sun_cult"],
    "tiefling": ["infernal_pact", "hidden_council", "outsider_assembly"],
}

# Culture flavors by race
_CULTURES: dict[str, list[str]] = {
    "human": ["martial", "mercantile", "agrarian", "scholarly", "nomadic"],
    "elf": ["arboreal", "arcane", "isolationist", "guardian"],
    "dwarf": ["underground", "smithing", "ancestral", "fortress"],
    "orc": ["raiding", "honor_bound", "survivalist", "shamanic"],
    "halfling": ["pastoral", "culinary", "river_trade", "hidden"],
    "gnome": ["inventive", "prankster", "gemcraft", "subterranean"],
    "goblin": ["scavenger", "tunnel", "alchemical", "infiltrator"],
    "lizardfolk": ["swamp_dwelling", "sun_worship", "cold_blooded", "ambush"],
    "tiefling": ["infernal_heritage", "mistrusted", "charismatic", "vengeful"],
}


def generate_civilizations(
    regions: list[Region],
    seed: int,
    max_civs: int = 4,
    history_years: int = 100,
) -> tuple[list[Civilization], list[Site], list[HistoryEvent]]:
    """Place civilizations in prosperous regions and simulate expansion.

    Args:
        regions: Regions from region segmentation.
        seed: Deterministic seed.
        max_civs: Maximum number of civilizations to generate.
        history_years: Years of history to simulate.

    Returns:
        Tuple of (civilizations, sites, history_events).
    """
    rng = WorldRNG(seed + 777001)
    civs: list[Civilization] = []
    sites: list[Site] = []
    history: list[HistoryEvent] = []
    site_counter = 0

    # Sort regions by prosperity, pick top ones as starting locations
    candidates = sorted(regions, key=lambda r: -r.prosperity)
    num_civs = min(max_civs, len(candidates))

    for i in range(num_civs):
        region = candidates[i]
        civ_id = f"civ_{(i + 1):02d}"

        race = rng.choose_weighted(_RACES)
        government = rng.choice(_GOVERNMENTS.get(race, ["tribal"]))
        culture = rng.choice(_CULTURES.get(race, ["generic"]))

        # Create capital site
        site_counter += 1
        site_id = f"site_{site_counter:02d}"
        capital = Site(
            id=site_id,
            region_id=region.id,
            site_type=SiteType.CAPITAL.value,
            civilization_id=civ_id,
            population=rng.randint(500, 3000),
            name=f"{race.capitalize()}-{_site_name_suffix(rng)}",
            x=region.center_x,
            y=region.center_y,
        )
        sites.append(capital)
        region.sites.append(site_id)

        civ = Civilization(
            id=civ_id,
            name=f"{rng.choice(_NAME_PREFIX)} {race.capitalize()} {government.replace('_', ' ').title()}",
            race=race,
            government=government,
            controlled_regions=[region.id],
            capital_site=site_id,
            culture=culture,
            population=capital.population,
        )
        civs.append(civ)

    # ── Expansion simulation ──────────────────────────────────────────
    # Simple model: each year, try to expand into one unowned neighbor
    region_owner: dict[str, str] = {r.id: c.id for c in civs for r_id in c.controlled_regions for r in regions if r.id == r_id}
    region_map: dict[str, Region] = {r.id: r for r in regions}

    for year in range(1, history_years + 1):
        for civ in civs:
            # Each civilization/year owns an independent stream. Adding another
            # civilization cannot perturb existing histories.
            civ_rng = WorldRNG(derive_seed(
                seed, "legacy.civilization", f"{civ.id}:year:{year}",
                "annual_actions",
            ))
            # Population growth
            growth = int(civ.population * civ_rng.uniform(0.01, 0.05))
            civ.population += growth

            # Expansion attempt
            owned = set(civ.controlled_regions)
            neighbors: set[str] = set()
            for rid in owned:
                if rid in region_map:
                    neighbors.update(region_map[rid].neighbors)

            unowned = [n for n in neighbors if n not in region_owner and n not in owned]
            if unowned:
                target_rid = civ_rng.choice(sorted(unowned))
                civ.controlled_regions.append(target_rid)
                region_owner[target_rid] = civ.id

                # Create a settlement in the new region
                target_region = region_map.get(target_rid)
                if target_region:
                    site_counter += 1
                    settlers = min(
                        civ_rng.randint(50, 300),
                        max(0, div_round_half_up(civ.population, 4)),
                    )
                    capital_site = next((site for site in sites if site.id == civ.capital_site), None)
                    if capital_site is not None:
                        settlers = min(settlers, capital_site.population)
                        capital_site.population -= settlers
                    new_site = Site(
                        id=f"site_{site_counter:02d}",
                        region_id=target_rid,
                        site_type=SiteType.SETTLEMENT.value,
                        civilization_id=civ.id,
                        population=settlers,
                        name=f"{civ.race.capitalize()}-{_site_name_suffix(civ_rng)}",
                        x=target_region.center_x + civ_rng.randint(-2, 2),
                        y=target_region.center_y + civ_rng.randint(-2, 2),
                    )
                    sites.append(new_site)
                    target_region.sites.append(new_site.id)

                    history.append(HistoryEvent(
                        year=year,
                        event=f"{civ.name} expanded into {target_region.name}",
                        participants=[civ.id],
                        location=target_rid,
                    ))

            # Border conflicts: two civs share a neighbor → possible conflict
            for other in civs:
                if other.id <= civ.id:
                    continue
                if _borders_overlap(civ, other, region_map):
                    conflict_rng = WorldRNG(derive_seed(
                        seed, "legacy.border_conflict",
                        f"{civ.id}:{other.id}:year:{year}", "outbreak",
                    ))
                    if conflict_rng.uniform() < 0.15:  # 15% chance per year
                        history.append(HistoryEvent(
                            year=year,
                            event=f"Border skirmish between {civ.name} and {other.name}",
                            participants=[civ.id, other.id],
                            location="",
                        ))

    return civs, sites, history


def _borders_overlap(
    civ_a: Civilization, civ_b: Civilization,
    region_map: dict[str, Region],
) -> bool:
    """Check if two civilizations share a border or contested territory."""
    for ra in civ_a.controlled_regions:
        if ra not in region_map:
            continue
        for rb in civ_b.controlled_regions:
            if rb not in region_map:
                continue
            if rb in region_map[ra].neighbors:
                return True
    return False


_NAME_PREFIX: list[str] = [
    "Kingdom of the", "Dominion of", "Realm of", "Empire of the",
    "Free", "Sovereign", "Eternal", "Radiant", "Shadowed",
    "Crimson", "Iron", "Golden", "Thunder",
]


def _site_name_suffix(rng: WorldRNG) -> str:
    parts = [
        "fall", "hold", "vale", "gate", "rest", "watch",
        "crossing", "haven", "ford", "bury", "stead", "shire",
    ]
    return rng.choice(parts)
