"""Adapter — maps WorldSnapshot to structured constraints for WorldBuilder.

The adapter does NOT pass the raw grid or full snapshot to the LLM
(that would overwhelm the context window). Instead, it summarizes
regions, civilizations, borders, and conflicts into a concise
constraint block that tells the LLM: "write lore for THIS world,
don't invent geography from scratch."
"""

from __future__ import annotations

from typing import Any

from .models import Civilization, Region, Site, WorldSnapshot


def snapshot_to_bible_context(snapshot: WorldSnapshot) -> str:
    """Convert a WorldSnapshot into a structured text block for the LLM prompt."""
    return _format_bible_context(
        regions=snapshot.regions,
        sites=snapshot.sites,
        civilizations=snapshot.civilizations,
        history=snapshot.history,
    )


def snapshot_dict_to_bible_context(snapshot_dict: dict[str, Any]) -> str:
    """Convert a snapshot DICT (from context.outputs) into a text block.

    This avoids reconstructing full model objects when the snapshot
    is already serialized in the pipeline context.
    """
    regions = [
        Region(
            id=r["id"], name=r["name"], biome=r["biome"],
            elevation=r["elevation"], climate=r["climate"],
            prosperity=r.get("prosperity", 0.5),
            neighbors=r.get("neighbors", []),
            sites=r.get("sites", []),
        )
        for r in snapshot_dict.get("regions", [])
    ]
    sites = [
        Site(
            id=s["id"], region_id=s["region_id"], site_type=s["type"],
            civilization_id=s.get("civilization_id", ""),
            population=s.get("population", 0), name=s.get("name", ""),
        )
        for s in snapshot_dict.get("sites", [])
    ]
    civilizations = [
        Civilization(
            id=c["id"], name=c["name"], race=c["race"],
            government=c["government"],
            controlled_regions=c.get("controlled_regions", []),
            capital_site=c.get("capital_site", ""),
            culture=c.get("culture", ""), population=c.get("population", 0),
        )
        for c in snapshot_dict.get("civilizations", [])
    ]
    history = _parse_history(snapshot_dict.get("history", []))

    return _format_bible_context(
        regions=regions, sites=sites,
        civilizations=civilizations, history=history,
    )


def snapshot_to_rich_context(snapshot: WorldSnapshot) -> dict[str, Any]:
    """Return structured data for non-prompt use (graph validation, etc.)."""
    region_ids = {r.id for r in snapshot.regions}
    civ_ids = {c.id for c in snapshot.civilizations}
    site_ids = {s.id for s in snapshot.sites}
    borders: dict[str, set[str]] = {r.id: set(r.neighbors) for r in snapshot.regions}
    prosperity: dict[str, float] = {r.id: r.prosperity for r in snapshot.regions}

    return {
        "region_ids": region_ids,
        "civilization_ids": civ_ids,
        "site_ids": site_ids,
        "borders": borders,
        "region_prosperity": prosperity,
    }


# ── internals ──────────────────────────────────────────────────────────


class _HistEvent:
    def __init__(self, **kw: Any) -> None:
        self.year = kw.get("year", 0)
        self.event = kw.get("event", "")
        self.participants = kw.get("participants", [])
        self.location = kw.get("location", "")


def _parse_history(raw: list[dict[str, Any]]) -> list[Any]:
    return [_HistEvent(**h) for h in raw]


def _format_bible_context(
    regions: list[Region],
    sites: list[Site],
    civilizations: list[Civilization],
    history: list[Any],
) -> str:
    lines: list[str] = []
    lines.append("=== PROCEDURAL WORLD CONSTRAINTS ===")
    lines.append("")
    lines.append("The world below was generated procedurally. Use it as")
    lines.append("the factual foundation for your World Bible. You may name,")
    lines.append("describe, and enrich everything — but do NOT contradict")
    lines.append("the geography, civilizations, or history below.")
    lines.append("")

    # ── Regions ────────────────────────────────────────────────
    lines.append("## Geography")
    lines.append("")
    for r in regions:
        neighbors = ", ".join(r.neighbors[:4])
        lines.append(
            f"- {r.name} ({r.id}): {r.biome.replace('_', ' ')}, "
            f"{r.elevation} elevation, {r.climate.replace('_', ' ')} climate. "
            f"Prosperity: {r.prosperity:.2f}. "
            f"Neighbors: {neighbors}."
        )
    lines.append("")

    # ── Sites ──────────────────────────────────────────────────
    site_map: dict[str, Site] = {s.id: s for s in sites}
    civ_names: dict[str, str] = {c.id: c.name for c in civilizations}
    region_names: dict[str, str] = {r.id: r.name for r in regions}

    lines.append("## Settlements and Sites")
    lines.append("")
    for s in sites:
        rname = region_names.get(s.region_id, s.region_id)
        lines.append(
            f"- {s.name} ({s.id}): {s.site_type} in {rname}, "
            f"population {s.population}"
            + (f", capital of {civ_names.get(s.civilization_id, '?')}" if s.site_type == "capital" else "")
            + "."
        )
    lines.append("")

    # ── Civilizations ──────────────────────────────────────────
    lines.append("## Civilizations")
    lines.append("")
    for c in civilizations:
        rlist = ", ".join(region_names.get(rid, rid) for rid in c.controlled_regions)
        lines.append(
            f"- {c.name} ({c.id}): {c.race} {c.government.replace('_', ' ')}. "
            f"Culture: {c.culture.replace('_', ' ')}. "
            f"Population: {c.population}. "
            f"Territory: {rlist}."
        )
        if c.capital_site and c.capital_site in site_map:
            lines.append(f"  Capital: {site_map[c.capital_site].name}.")
    lines.append("")

    # ── Borders ────────────────────────────────────────────────
    lines.append("## Borders and Travel Routes")
    lines.append("")
    for c in civilizations:
        borders = _find_borders(c, regions, civilizations)
        if borders:
            lines.append(f"- {c.name} borders: {', '.join(borders)}.")
    lines.append("")

    # ── History ────────────────────────────────────────────────
    lines.append("## Historical Events")
    lines.append("")
    for h in history[:10]:
        lines.append(f"- Year {h.year}: {h.event}")
    lines.append("")

    # ── RULES ──────────────────────────────────────────────────
    lines.append("## RULES")
    lines.append("")
    lines.append("1. Every region listed above MUST appear as a location in the Bible.")
    lines.append("2. Every civilization MUST become a faction with its race and government.")
    lines.append("3. Borders and conflicts define valid travel paths — do not create shortcuts.")
    lines.append("4. The prosperity values should inform which regions are wealthy or poor.")
    lines.append("5. Historical events should be woven into the lore and character backgrounds.")
    lines.append("6. You may add additional characters, creatures, artifacts, and events.")
    lines.append("7. Do NOT invent new regions, civilizations, or continents — only enrich what exists.")
    lines.append("")

    return "\n".join(lines)


def _find_borders(
    civ: Civilization,
    regions: list[Region],
    all_civs: list[Civilization],
) -> list[str]:
    region_map = {r.id: r for r in regions}
    own_regions = set(civ.controlled_regions)
    neighbor_civs: set[str] = set()

    for rid in own_regions:
        if rid not in region_map:
            continue
        for nid in region_map[rid].neighbors:
            for other in all_civs:
                if other.id != civ.id and nid in other.controlled_regions:
                    neighbor_civs.add(other.name)

    return sorted(neighbor_civs)
