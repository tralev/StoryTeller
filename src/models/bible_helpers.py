"""Shared Bible summarization helper — one implementation, all callers.

Replaces four duplicate _summarize_bible methods across:
  - StoryWriter   (full world+magic, 3 categories, 100-char desc, char detail)
  - ArtDirector   (full world+magic, 6 categories, 80-char desc)
  - GameDesigner skeleton (no world/magic, 3 categories, 60-char desc, brief)
  - GameDesigner node      (no world/magic, filtered by node, 80-char desc)

Each caller passes its needs via keyword arguments.
"""

from __future__ import annotations

from typing import Any


def summarize_bible(
    bible: dict[str, Any],
    *,
    include_world: bool = True,
    include_magic: bool = True,
    categories: list[str] | None = None,
    max_desc_len: int = 80,
    show_role: bool = False,
    show_motivation: bool = False,
    show_flaw: bool = False,
    filter_ids: dict[str, set[str]] | None = None,
) -> str:
    """Build a concise text summary of the World Bible for prompt injection.

    Args:
        bible: The World Bible dict (entities, narrative_rules, systems, world_name).
        include_world: If True, prepend world name + tone + mortality + forbidden.
        include_magic: If True, append magic system rules + limitations.
        categories: Entity categories to include. Defaults to
            ["characters", "locations", "factions"].
        max_desc_len: Truncate entity descriptions to this many characters.
        show_role: If True, append the character's role in parens.
        show_motivation: If True, append the character's motivation.
        show_flaw: If True, append the character's flaw.
        filter_ids: Per-category set of entity IDs to include.
            Entities not in the set are skipped.
            Example: {"characters": {"char_01", "char_03"}, "locations": {"loc_02"}}.

    Returns:
        A multi-line string ready for Jinja2 template injection.
    """
    if categories is None:
        categories = ["characters", "locations", "factions"]

    lines: list[str] = []

    # ── world / narrative rules ──────────────────────────────────────
    if include_world:
        world = bible.get("world_name", "Unknown")
        rules = bible.get("narrative_rules", {})
        tone = rules.get("tone", "?")
        mortality = rules.get("mortality", "?")
        forbidden = ", ".join(rules.get("forbidden", []))
        knowledge = rules.get("knowledge_level", "")

        header_parts = [f"World: {world} | Tone: {tone} | Mortality: {mortality}"]
        if knowledge:
            header_parts.append(f"Knowledge: {knowledge}")
        lines.append(" | ".join(header_parts))
        if forbidden:
            lines.append(f"Forbidden elements: {forbidden}")

    # ── entities ─────────────────────────────────────────────────────
    entities = bible.get("entities", {})
    for cat in categories:
        items = entities.get(cat, [])
        if not items:
            continue

        # Optional category header for ArtDirector's multi-category output
        if len(categories) > 3:
            lines.append(f"\n{cat.title()} ({len(items)}):")

        for e in items:
            entity_id = e.get("id", "?")
            # Filtering
            if filter_ids and cat in filter_ids and entity_id not in filter_ids[cat]:
                continue

            name = e.get("name", "?")
            desc = e.get("description", "")[:max_desc_len]
            prefix = f"  " if len(categories) > 3 else ""

            if cat == "characters":
                extra: list[str] = []
                if show_role:
                    extra.append(e.get("role", "?"))
                if show_motivation:
                    extra.append(f"Motivation: {e.get('motivation', '?')}")
                if show_flaw:
                    extra.append(f"Flaw: {e.get('flaw', '?')}")
                suffix = " | ".join(extra)
                if suffix:
                    lines.append(
                        f"{prefix}[{entity_id}] {name} ({suffix}): {desc}"
                    )
                else:
                    lines.append(f"{prefix}[{entity_id}] {name}: {desc}")
            else:
                lines.append(f"{prefix}[{entity_id}] {name}: {desc}")

    # ── magic ────────────────────────────────────────────────────────
    if include_magic:
        magic = bible.get("systems", {}).get("magic", {})
        if magic:
            rules_list = "; ".join(magic.get("rules", []))
            limits = magic.get("limitations", "?")
            source = magic.get("source", "")
            if source:
                lines.append(f"\nMagic source: {source}")
            if rules_list:
                lines.append(f"Magic rules: {rules_list}")
            lines.append(f"Magic limitations: {limits}")

    return "\n".join(lines)
