"""Tests for bible_helpers.py — shared Bible summarization helper.

Covers all parameter combinations used by the 4 callers:
  StoryWriter   (full, 3 categories, show_role/motivation/flaw)
  ArtDirector   (full, 6 categories, 80-char desc)
  GameDesigner skeleton (no world/magic, 3 categories, brief)
  GameDesigner node      (no world/magic, filtered, specific chars)
"""

from __future__ import annotations

from typing import Any

import pytest
from src.models.bible_helpers import summarize_bible


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_bible() -> dict[str, Any]:
    """A minimal but complete World Bible for testing."""
    return {
        "world_name": "The Ashen Marches",
        "narrative_rules": {
            "tone": "dark_fantasy",
            "mortality": "high",
            "forbidden": ["time travel", "resurrection"],
            "knowledge_level": "aware",
        },
        "entities": {
            "characters": [
                {
                    "id": "char_01",
                    "name": "Elena Brightblade",
                    "description": "A young knight sworn to unite the fractured kingdoms.",
                    "role": "protagonist",
                    "motivation": "Restore the Crystal Accord",
                    "flaw": "Naivety",
                },
                {
                    "id": "char_02",
                    "name": "Thorn Ironveil",
                    "description": "An aging dwarf warden guarding the High Pass.",
                    "role": "supporting",
                    "motivation": "Protect the mountain realm",
                    "flaw": "Stubbornness",
                },
            ],
            "locations": [
                {
                    "id": "loc_01",
                    "name": "High Pass",
                    "description": "A narrow mountain pass leading to the Crystal Spire.",
                },
            ],
            "factions": [
                {
                    "id": "fac_01",
                    "name": "The Shattered Council",
                    "description": "Remnants of the old ruling body.",
                },
            ],
            "creatures": [
                {
                    "id": "cre_01",
                    "name": "Ash Wraith",
                    "description": "A smoky apparition that feeds on fear.",
                },
            ],
            "artifacts": [
                {
                    "id": "art_01",
                    "name": "Crystal Shard",
                    "description": "A fragment of the original Accord.",
                },
            ],
            "events": [
                {
                    "id": "evt_01",
                    "name": "The Sundering",
                    "description": "The cataclysm that shattered the kingdoms.",
                },
            ],
        },
        "systems": {
            "magic": {
                "source": "Crystal resonance",
                "rules": ["Harmony amplifies", "Discord shatters"],
                "limitations": "Fades without unity",
            },
        },
    }


# ── StoryWriter-style (default: full, 3 cats, show extras) ───────────

def test_storywriter_defaults(sample_bible: dict) -> None:
    result = summarize_bible(sample_bible)
    assert "The Ashen Marches" in result
    assert "dark_fantasy" in result
    assert "Elena Brightblade" in result
    assert "Thorn Ironveil" in result
    assert "High Pass" in result
    assert "The Shattered Council" in result
    assert "Crystal resonance" in result
    assert "Harmony amplifies" in result
    # creatures/artifacts/events NOT in default categories
    assert "Ash Wraith" not in result
    assert "Crystal Shard" not in result


def test_storywriter_with_role(sample_bible: dict) -> None:
    result = summarize_bible(sample_bible, show_role=True)
    assert "protagonist" in result
    assert "supporting" in result


def test_storywriter_with_motivation(sample_bible: dict) -> None:
    result = summarize_bible(sample_bible, show_motivation=True)
    assert "Restore the Crystal Accord" in result
    assert "Protect the mountain realm" in result


def test_storywriter_with_flaw(sample_bible: dict) -> None:
    result = summarize_bible(sample_bible, show_flaw=True)
    assert "Naivety" in result
    assert "Stubbornness" in result


def test_storywriter_all_extras(sample_bible: dict) -> None:
    """StoryWriter uses role + motivation + flaw."""
    result = summarize_bible(
        sample_bible, show_role=True, show_motivation=True, show_flaw=True,
    )
    assert "protagonist" in result
    assert "Restore the Crystal Accord" in result
    assert "Naivety" in result


# ── ArtDirector-style (full, 6 categories, 80-char desc) ────────────

def test_artdirector_six_categories(sample_bible: dict) -> None:
    result = summarize_bible(
        sample_bible,
        categories=["characters", "locations", "factions", "creatures", "artifacts", "events"],
    )
    assert "Ash Wraith" in result
    assert "Crystal Shard" in result
    assert "The Sundering" in result
    # Category headers should appear for 6 categories
    assert "Characters" in result or "characters" in result


def test_artdirector_max_desc_len(sample_bible: dict) -> None:
    result = summarize_bible(sample_bible, max_desc_len=20)
    assert len(result) > 0
    # Description should be truncated
    for char in sample_bible["entities"]["characters"]:
        full_desc = char["description"]
        if len(full_desc) > 20:
            assert full_desc not in result
            assert full_desc[:20] in result


# ── GameDesigner skeleton style (no world/magic, 3 cats, brief) ─────

def test_skeleton_no_world_no_magic(sample_bible: dict) -> None:
    result = summarize_bible(sample_bible, include_world=False, include_magic=False)
    assert "The Ashen Marches" not in result
    assert "Crystal resonance" not in result
    assert "Elena Brightblade" in result  # entities still included


def test_skeleton_brief_desc(sample_bible: dict) -> None:
    result = summarize_bible(
        sample_bible, include_world=False, include_magic=False, max_desc_len=30,
    )
    # Descriptions should be truncated at 30 chars
    assert "A young knight sworn to unite" in result


# ── GameDesigner node style (no world/magic, filtered) ───────────────

def test_node_filtered_ids(sample_bible: dict) -> None:
    result = summarize_bible(
        sample_bible,
        include_world=False,
        include_magic=False,
        filter_ids={"characters": {"char_01"}},
    )
    assert "Elena Brightblade" in result
    assert "Thorn Ironveil" not in result


def test_node_filtered_multiple_categories(sample_bible: dict) -> None:
    result = summarize_bible(
        sample_bible,
        include_world=False,
        include_magic=False,
        filter_ids={"characters": {"char_01"}, "locations": {"loc_01"}},
    )
    assert "Elena Brightblade" in result
    assert "Thorn Ironveil" not in result
    assert "High Pass" in result
    # Faction not filtered → still included
    assert "The Shattered Council" in result


# ── Edge cases ────────────────────────────────────────────────────────

def test_empty_bible() -> None:
    result = summarize_bible({})
    assert "Unknown" in result  # world_name defaults
    assert "?" in result  # tone/mortality defaults


def test_no_entities(sample_bible: dict) -> None:
    bible = {"world_name": "Empty", "narrative_rules": {"tone": "?", "mortality": "low", "forbidden": []}}
    result = summarize_bible(bible, include_magic=False)
    assert "Empty" in result
    assert "low" in result


def test_no_magic_system(sample_bible: dict) -> None:
    bible = {**sample_bible}
    del bible["systems"]
    result = summarize_bible(bible, include_magic=True)
    # Should not crash — just no magic section
    assert "Crystal resonance" not in result
    assert "Elena Brightblade" in result


def test_forbidden_elements_appear(sample_bible: dict) -> None:
    result = summarize_bible(sample_bible)
    assert "time travel" in result.lower()
    assert "resurrection" in result.lower()


def test_knowledge_level_appears(sample_bible: dict) -> None:
    result = summarize_bible(sample_bible)
    assert "aware" in result


def test_single_category(sample_bible: dict) -> None:
    result = summarize_bible(
        sample_bible, categories=["characters"], include_world=False, include_magic=False,
    )
    assert "Elena Brightblade" in result
    assert "Thorn Ironveil" in result
    # Location dedicated entry should NOT appear (only character descriptions may reference)
    assert "[loc_01]" not in result
    assert "[fac_01]" not in result


def test_entity_without_description(sample_bible: dict) -> None:
    """Entity with no 'description' key should not crash and just emit empty desc."""
    bible = {**sample_bible}
    bible["entities"] = {
        "characters": [{"id": "char_x", "name": "NoDesc"}],
    }
    result = summarize_bible(bible, include_world=False, include_magic=False)
    assert "NoDesc" in result
    # Should not contain "None" or crash
    assert "None" not in result
