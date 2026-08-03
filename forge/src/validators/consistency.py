"""Consistency Validator — detects Bible violations in generated story content.

Performs both programmatic checks (entity presence, mortality rules)
and supports LLM-based checking via consistency_check_v1.j2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast


@dataclass
class ConsistencyViolation:
    """A single lore or consistency violation."""

    category: str  # "character", "location", "magic", "factual", "mortality"
    severity: str  # "critical", "major", "minor"
    entity_id: str
    location: str  # Where in the content (e.g., "chapter 2, scene 3")
    description: str
    suggestion: str = ""


@dataclass
class ConsistencyResult:
    """Result of consistency checking."""

    is_consistent: bool
    violations: list[ConsistencyViolation] = field(default_factory=list)

    def format_for_retry(self) -> str:
        """Format violations as human-readable feedback for retry prompts."""
        if self.is_consistent:
            return "Consistency check: Valid. No Bible violations found."
        lines = [f"Consistency check: {len(self.violations)} violation(s):"]
        for v in self.violations:
            lines.append(
                f"  [{v.severity}] [{v.category}] {v.entity_id} @ {v.location}: "
                f"{v.description}"
            )
        return "\n".join(lines)


class ConsistencyChecker:
    """Validates story content against the World Bible.

    Runs programmatic checks (no LLM needed for basic validation).
    LLM-based deep checking uses consistency_check_v1.j2 via a Validator.

    Checks performed:
    1. All referenced entities exist in the bible
    2. Dead characters are not present in scenes
    3. Character motivations and flaws are respected (LLM)
    4. Magic rules are not violated (LLM)
    5. Location descriptions match their bible moods (LLM)
    6. Mortality setting is respected (no casual deaths if mortality=low)
    """

    def check_all(
        self,
        bible: dict[str, Any],
        story: dict[str, Any],
    ) -> ConsistencyResult:
        """Run all consistency checks.

        Args:
            bible: The World Bible dict.
            story: The generated story dict with chapters.

        Returns:
            ConsistencyResult with list of violations.
        """
        violations: list[ConsistencyViolation] = []

        violations.extend(self._check_entity_presence(bible, story))
        violations.extend(self._check_dead_characters(bible, story))
        violations.extend(self._check_mortality_rules(bible, story))

        return ConsistencyResult(
            is_consistent=len(violations) == 0,
            violations=violations,
        )

    def _check_entity_presence(
        self, bible: dict[str, Any], story: dict[str, Any]
    ) -> list[ConsistencyViolation]:
        """Verify all entities referenced in story exist in the bible."""
        violations: list[ConsistencyViolation] = []
        bible_ids = self._collect_bible_ids(bible)

        for chapter in story.get("chapters", []):
            ch_num = chapter.get("number", "?")
            for scene in chapter.get("scenes", []):
                scene_id = scene.get("scene_id", "?")
                for char_id in scene.get("characters_present", []):
                    if char_id not in bible_ids:
                        violations.append(
                            ConsistencyViolation(
                                category="character",
                                severity="critical",
                                entity_id=char_id,
                                location=f"chapter {ch_num}, {scene_id}",
                                description=f"Character '{char_id}' not found in bible",
                            )
                        )
                loc_id = scene.get("location", "")
                if loc_id and loc_id not in bible_ids:
                    violations.append(
                        ConsistencyViolation(
                            category="location",
                            severity="critical",
                            entity_id=loc_id,
                            location=f"chapter {ch_num}, {scene_id}",
                            description=f"Location '{loc_id}' not found in bible",
                        )
                    )

        return violations

    def _check_dead_characters(
        self, bible: dict[str, Any], story: dict[str, Any]
    ) -> list[ConsistencyViolation]:
        """Verify dead characters don't appear alive in scenes."""
        violations: list[ConsistencyViolation] = []
        dead_ids = {
            c["id"]
            for c in bible.get("entities", {}).get("characters", [])
            if c.get("status") == "dead"
        }

        if not dead_ids:
            return violations

        for chapter in story.get("chapters", []):
            ch_num = chapter.get("number", "?")
            for scene in chapter.get("scenes", []):
                scene_id = scene.get("scene_id", "?")
                for char_id in scene.get("characters_present", []):
                    if char_id in dead_ids:
                        violations.append(
                            ConsistencyViolation(
                                category="character",
                                severity="critical",
                                entity_id=char_id,
                                location=f"chapter {ch_num}, {scene_id}",
                                description=f"Dead character '{char_id}' appears in scene",
                                suggestion="Remove from characters_present or change status in bible",
                            )
                        )

        return violations

    def _check_mortality_rules(
        self, bible: dict[str, Any], story: dict[str, Any]
    ) -> list[ConsistencyViolation]:
        """Check mortality setting is respected.

        If mortality=low, flag any scene that mentions character death.
        This is a heuristic check — not exhaustive (LLM handles deep analysis).
        """
        violations: list[ConsistencyViolation] = []
        mortality = (
            bible.get("narrative_rules", {}).get("mortality", "moderate")
        )

        if mortality != "low":
            return violations

        death_keywords = ["died", "dead", "killed", "slain", "corpse", "death"]
        protagonist_ids = {
            c["id"]
            for c in bible.get("entities", {}).get("characters", [])
            if c.get("role") == "protagonist"
        }

        for chapter in story.get("chapters", []):
            ch_num = chapter.get("number", "?")
            for scene in chapter.get("scenes", []):
                scene_id = scene.get("scene_id", "?")
                text = scene.get("text", "").lower()

                # Check if a protagonist is mentioned with death keywords
                for pid in protagonist_ids:
                    # Look for the character name near death keywords
                    char_name = self._find_entity_name(bible, pid)
                    if char_name and char_name.lower() in text:
                        for kw in death_keywords:
                            if kw in text:
                                violations.append(
                                    ConsistencyViolation(
                                        category="mortality",
                                        severity="critical",
                                        entity_id=pid,
                                        location=f"chapter {ch_num}, {scene_id}",
                                        description=(
                                            f"Mortality is '{mortality}' but protagonist "
                                            f"'{pid}' appears near '{kw}'"
                                        ),
                                        suggestion=(
                                            "Remove death reference or change mortality setting"
                                        ),
                                    )
                                )
                                break  # One violation per scene is enough

        return violations

    @staticmethod
    def _collect_bible_ids(bible: dict[str, Any]) -> set[str]:
        """Collect all entity IDs from the bible."""
        ids: set[str] = set()
        for cat in ["characters", "locations", "factions", "creatures", "artifacts", "events"]:
            for e in bible.get("entities", {}).get(cat, []):
                ids.add(e["id"])
        return ids

    @staticmethod
    def _find_entity_name(bible: dict[str, Any], entity_id: str) -> str | None:
        """Find an entity's name by ID."""
        for cat in ["characters", "locations", "factions", "creatures", "artifacts", "events"]:
            for e in bible.get("entities", {}).get(cat, []):
                if e["id"] == entity_id:
                    return cast(str, e.get("name"))
        return None
