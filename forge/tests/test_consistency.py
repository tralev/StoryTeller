"""Tests for ConsistencyChecker."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from src.validators.consistency import ConsistencyChecker, ConsistencyResult


def _make_bible(
    mortality: str = "moderate",
    dead_ids: list[str] | None = None,
) -> Dict[str, Any]:
    """Build a minimal bible for consistency tests."""
    characters = [
        {"id": "char_01", "name": "Hero", "aliases": [], "description": "A hero.", "role": "protagonist", "archetype": "hero", "motivation": "Good", "flaw": "Pride", "strength": "Courage", "relationships": [], "status": "alive"},
        {"id": "char_02", "name": "Mentor", "aliases": [], "description": "A mentor.", "role": "supporting", "archetype": "mentor", "motivation": "Teach", "flaw": "Old", "strength": "Wisdom", "relationships": [], "status": "alive"},
    ]
    if dead_ids:
        for c in characters:
            if c["id"] in dead_ids:
                c["status"] = "dead"

    return {
        "world_name": "Test World",
        "narrative_rules": {
            "tone": "dark_fantasy",
            "forbidden": [],
            "required_themes": [],
            "mortality": mortality,
            "knowledge_level": "aware",
        },
        "entities": {
            "characters": characters,
            "locations": [
                {"id": "loc_01", "name": "Village", "aliases": [], "description": "Small village.", "type": "village", "mood": "peaceful"},
            ],
            "factions": [],
            "creatures": [],
            "artifacts": [],
            "events": [],
        },
        "systems": {
            "magic": {"source": "Void", "rules": ["Fades at dawn"], "costs": [], "limitations": "None"},
            "politics": {"power_structure": "Monarchy", "conflicts": []},
            "religion": {"gods": [], "afterlife": "Void"},
        },
    }


def _make_story(
    characters: list[str] | None = None,
    location: str = "loc_01",
    text: str = "The hero walked through the village.",
) -> Dict[str, Any]:
    """Build a minimal story for consistency tests."""
    return {
        "chapters": [
            {
                "number": 1,
                "title": "The Beginning",
                "summary": "A chapter.",
                "scenes": [
                    {
                        "scene_id": "scene_01_01",
                        "text": text,
                        "characters_present": characters or ["char_01"],
                        "location": location,
                        "entities_referenced": [],
                        "word_count": 100,
                    }
                ],
            }
        ],
    }


class TestConsistencyChecker:
    """Consistency checks between bible and story."""

    def test_valid_bible_and_story_pass(self) -> None:
        checker = ConsistencyChecker()
        result = checker.check_all(_make_bible(), _make_story())
        assert result.is_consistent
        assert len(result.violations) == 0

    def test_format_for_retry_valid(self) -> None:
        checker = ConsistencyChecker()
        result = checker.check_all(_make_bible(), _make_story())
        text = result.format_for_retry()
        assert "Valid" in text

    def test_unknown_character_detected(self) -> None:
        checker = ConsistencyChecker()
        story = _make_story(characters=["nonexistent_char"])
        result = checker.check_all(_make_bible(), story)

        assert not result.is_consistent
        violations = [v for v in result.violations if v.category == "character"]
        assert len(violations) == 1
        assert "nonexistent_char" in violations[0].entity_id
        assert violations[0].severity == "critical"

    def test_unknown_location_detected(self) -> None:
        checker = ConsistencyChecker()
        story = _make_story(location="nonexistent_loc")
        result = checker.check_all(_make_bible(), story)

        assert not result.is_consistent
        violations = [v for v in result.violations if v.category == "location"]
        assert len(violations) == 1
        assert "nonexistent_loc" in violations[0].entity_id

    def test_dead_character_detected(self) -> None:
        checker = ConsistencyChecker()
        bible = _make_bible(dead_ids=["char_02"])
        story = _make_story(characters=["char_01", "char_02"])
        result = checker.check_all(bible, story)

        assert not result.is_consistent
        violations = [v for v in result.violations if v.category == "character"]
        assert len(violations) == 1
        assert "char_02" in violations[0].entity_id
        assert "Dead character" in violations[0].description

    def test_mortality_low_flags_death_keywords(self) -> None:
        checker = ConsistencyChecker()
        bible = _make_bible(mortality="low")
        story = _make_story(
            characters=["char_01"],
            text="The Hero was killed by the dragon.",
        )
        result = checker.check_all(bible, story)

        violations = [v for v in result.violations if v.category == "mortality"]
        assert len(violations) >= 1
        assert violations[0].severity == "critical"

    def test_mortality_high_allows_death(self) -> None:
        checker = ConsistencyChecker()
        bible = _make_bible(mortality="high")
        story = _make_story(
            characters=["char_01"],
            text="The Hero was killed by the dragon.",
        )
        result = checker.check_all(bible, story)

        # Mortality high → no mortality violations
        violations = [v for v in result.violations if v.category == "mortality"]
        assert len(violations) == 0

    def test_format_for_retry_with_violations(self) -> None:
        checker = ConsistencyChecker()
        story = _make_story(characters=["nonexistent_char"])
        result = checker.check_all(_make_bible(), story)

        text = result.format_for_retry()
        assert "violation" in text
        assert "nonexistent_char" in text or "nonexistent" in text.lower()

    def test_multiple_violations_reported(self) -> None:
        checker = ConsistencyChecker()
        story = _make_story(
            characters=["nonexistent_char"],
            location="nonexistent_loc",
        )
        result = checker.check_all(_make_bible(), story)

        assert not result.is_consistent
        assert len(result.violations) >= 2

    def test_empty_story_no_chapters(self) -> None:
        checker = ConsistencyChecker()
        result = checker.check_all(_make_bible(), {"chapters": []})
        assert result.is_consistent

    def test_mortality_low_no_protagonists(self) -> None:
        """Mortality=low with no protagonist characters — no false positives."""
        checker = ConsistencyChecker()
        bible = _make_bible(mortality="low")
        # Remove the protagonist role from all characters
        for c in bible["entities"]["characters"]:
            c["role"] = "background"
        story = _make_story(text="The background character was killed.")
        result = checker.check_all(bible, story)
        # No protagonists → no mortality violations (background deaths OK even on low)
        violations = [v for v in result.violations if v.category == "mortality"]
        assert len(violations) == 0

    def test_find_entity_name_nonexistent(self) -> None:
        """_find_entity_name returns None for unknown ID."""
        result = ConsistencyChecker._find_entity_name(_make_bible(), "nonexistent_id")
        assert result is None

    def test_collect_bible_ids_all_categories(self) -> None:
        """_collect_bible_ids returns IDs from all entity categories."""
        ids = ConsistencyChecker._collect_bible_ids(_make_bible())
        assert "char_01" in ids
        assert "char_02" in ids
        assert "loc_01" in ids
        # No factions/creatures/artifacts/events in minimal bible

    def test_character_without_name_field(self) -> None:
        """Characters missing the 'name' field should not crash mortality checks."""
        checker = ConsistencyChecker()
        bible = _make_bible(mortality="low")
        # Remove 'name' from one character
        del bible["entities"]["characters"][0]["name"]
        story = _make_story(
            characters=["char_01"],
            text="The hero was killed in battle.",
        )
        # Should not crash — _find_entity_name returns None, then .lower() is skipped
        result = checker.check_all(bible, story)
        # Mortality check skips characters without names
        assert isinstance(result, ConsistencyResult)
