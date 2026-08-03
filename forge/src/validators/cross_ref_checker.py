"""Cross-Reference Checker — validates that all entity IDs, node targets,
and consequence flags are consistent across bible, story, and graph.

Runs after schema validation. Errors here indicate structural inconsistency
between artifacts, not just malformed JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


@dataclass
class RefError:
    """A cross-reference inconsistency."""

    category: str  # "entity", "node_target", "flag", "bible_node"
    path: str  # e.g. "graph.nodes[3].present_characters[0]"
    message: str


@dataclass
class RefResult:
    """Result of cross-reference validation."""

    is_valid: bool
    errors: List[RefError] = field(default_factory=list)

    def format_for_retry(self) -> str:
        """Format cross-reference errors for LLM retry feedback."""
        if self.is_valid:
            return "Cross-reference check: Valid. All references resolve."
        lines = [f"Cross-reference check: {len(self.errors)} issue(s):"]
        for e in self.errors:
            lines.append(f"  [{e.category}] {e.path}: {e.message}")
        return "\n".join(lines)


class CrossRefChecker:
    """Validates cross-references between bible, story, and graph artifacts.

    Checks:
    1. All entity IDs referenced in graph/story exist in the bible.
    2. All choice target_node values reference actual graph nodes.
    3. All consequence flags in choices/nodes are declared in flags_catalog.
    4. All bible entity node references exist in the graph (prefix-matching for branches).
    """

    ENTITY_CATEGORIES = ["characters", "locations", "factions", "creatures", "artifacts", "events"]

    def __init__(self) -> None:
        pass

    def check_all(
        self,
        bible: Dict[str, Any] | None = None,
        story: Dict[str, Any] | None = None,
        graph: Dict[str, Any] | None = None,
    ) -> RefResult:
        """Run all cross-reference checks across available artifacts."""
        all_errors: List[RefError] = []

        if bible and graph:
            all_errors.extend(self.check_entity_ids_exist(bible, graph))
            all_errors.extend(self.check_bible_node_refs(bible, graph))
        if graph:
            all_errors.extend(self.check_node_targets(graph))
            all_errors.extend(self.check_flag_consistency(graph))
        if bible and story:
            all_errors.extend(self.check_story_entities_exist(bible, story))

        return RefResult(is_valid=len(all_errors) == 0, errors=all_errors)

    # ── Entity ID checks ──────────────────────────────────────────────

    def check_entity_ids_exist(
        self, bible: Dict[str, Any], graph: Dict[str, Any]
    ) -> List[RefError]:
        """Verify all entity IDs in graph nodes exist in the bible."""
        errors: List[RefError] = []
        bible_ids = self._collect_bible_ids(bible)

        for i, node in enumerate(graph.get("nodes", [])):
            for j, char_id in enumerate(node.get("present_characters", [])):
                if char_id not in bible_ids:
                    errors.append(
                        RefError(
                            category="entity",
                            path=f"graph.nodes[{i}].present_characters[{j}]",
                            message=f"Character '{char_id}' not found in bible",
                        )
                    )

            loc_id = node.get("present_location")
            if loc_id and loc_id not in bible_ids:
                errors.append(
                    RefError(
                        category="entity",
                        path=f"graph.nodes[{i}].present_location",
                        message=f"Location '{loc_id}' not found in bible",
                    )
                )

            for j, cre_id in enumerate(node.get("present_creatures", [])):
                if cre_id not in bible_ids:
                    errors.append(
                        RefError(
                            category="entity",
                            path=f"graph.nodes[{i}].present_creatures[{j}]",
                            message=f"Creature '{cre_id}' not found in bible",
                        )
                    )

        return errors

    def check_story_entities_exist(
        self, bible: Dict[str, Any], story: Dict[str, Any]
    ) -> List[RefError]:
        """Verify all entity IDs referenced in story scenes exist in bible."""
        errors: List[RefError] = []
        bible_ids = self._collect_bible_ids(bible)

        for ci, chapter in enumerate(story.get("chapters", [])):
            for si, scene in enumerate(chapter.get("scenes", [])):
                for ji, char_id in enumerate(scene.get("characters_present", [])):
                    if char_id not in bible_ids:
                        errors.append(
                            RefError(
                                category="entity",
                                path=f"story.chapters[{ci}].scenes[{si}].characters_present[{ji}]",
                                message=f"Character '{char_id}' not found in bible",
                            )
                        )
                loc_id = scene.get("location")
                if loc_id and loc_id not in bible_ids:
                    errors.append(
                        RefError(
                            category="entity",
                            path=f"story.chapters[{ci}].scenes[{si}].location",
                            message=f"Location '{loc_id}' not found in bible",
                        )
                    )

        return errors

    # ── Node target checks ────────────────────────────────────────────

    def check_node_targets(self, graph: Dict[str, Any]) -> List[RefError]:
        """Verify all choice target_node values reference actual graph nodes."""
        errors: List[RefError] = []
        node_ids = {n["node_id"] for n in graph.get("nodes", [])}

        for i, node in enumerate(graph.get("nodes", [])):
            for j, choice in enumerate(node.get("choices", [])):
                target = choice.get("target_node")
                if target and target not in node_ids:
                    errors.append(
                        RefError(
                            category="node_target",
                            path=f"graph.nodes[{i}].choices[{j}].target_node",
                            message=f"Target node '{target}' does not exist in graph",
                        )
                    )

        # Also check starting_node
        start = graph.get("starting_node")
        if start and start not in node_ids:
            errors.append(
                RefError(
                    category="node_target",
                    path="graph.starting_node",
                    message=f"Starting node '{start}' does not exist in graph",
                )
            )

        return errors

    # ── Flag consistency ──────────────────────────────────────────────

    def check_flag_consistency(self, graph: Dict[str, Any]) -> List[RefError]:
        """Verify all flags used in choices/node conditions are in flags_catalog."""
        errors: List[RefError] = []
        declared_flags: Set[str] = set(graph.get("flags_catalog", {}).keys())

        for i, node in enumerate(graph.get("nodes", [])):
            for j, choice in enumerate(node.get("choices", [])):
                for k, flag in enumerate(choice.get("requires_flags", [])):
                    if flag not in declared_flags:
                        errors.append(
                            RefError(
                                category="flag",
                                path=f"graph.nodes[{i}].choices[{j}].requires_flags[{k}]",
                                message=f"Flag '{flag}' used but not declared in flags_catalog",
                            )
                        )
                for k, flag in enumerate(choice.get("forbids_flags", [])):
                    if flag not in declared_flags:
                        errors.append(
                            RefError(
                                category="flag",
                                path=f"graph.nodes[{i}].choices[{j}].forbids_flags[{k}]",
                                message=f"Flag '{flag}' used but not declared in flags_catalog",
                            )
                        )
                for k, flag in enumerate(choice.get("sets_flags", [])):
                    if flag not in declared_flags:
                        errors.append(
                            RefError(
                                category="flag",
                                path=f"graph.nodes[{i}].choices[{j}].sets_flags[{k}]",
                                message=f"Flag '{flag}' set but not declared in flags_catalog",
                            )
                        )

            for k, cond in enumerate(node.get("conditional_text", [])):
                flag = cond.get("if_flag")
                if flag and flag not in declared_flags:
                    errors.append(
                        RefError(
                            category="flag",
                            path=f"graph.nodes[{i}].conditional_text[{k}].if_flag",
                            message=f"Flag '{flag}' used but not declared in flags_catalog",
                        )
                    )

        return errors

    # ── Bible node references ─────────────────────────────────────────

    def check_bible_node_refs(
        self, bible: Dict[str, Any], graph: Dict[str, Any]
    ) -> List[RefError]:
        """Verify bible entity node references exist in graph.

        Uses prefix matching: bible node "node_02" matches graph nodes
        "node_02a", "node_02b", etc. (branch suffixes).
        """
        errors: List[RefError] = []
        graph_node_ids = {n["node_id"] for n in graph.get("nodes", [])}

        for category in self.ENTITY_CATEGORIES:
            for ei, entity in enumerate(bible.get("entities", {}).get(category, [])):
                for ni, node_ref in enumerate(entity.get("nodes", [])):
                    # Prefix match: "node_02" should match "node_02a" in graph
                    matches = [gn for gn in graph_node_ids if gn == node_ref or gn.startswith(node_ref)]
                    if not matches:
                        errors.append(
                            RefError(
                                category="bible_node",
                                path=f"bible.entities.{category}[{ei}].nodes[{ni}]",
                                message=(
                                    f"Node '{node_ref}' for '{entity['id']}' not found in graph "
                                    f"(no matching nodes)"
                                ),
                            )
                        )

        return errors

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _collect_bible_ids(bible: Dict[str, Any]) -> Set[str]:
        """Collect all entity IDs from a world bible."""
        ids: Set[str] = set()
        for category in CrossRefChecker.ENTITY_CATEGORIES:
            for entity in bible.get("entities", {}).get(category, []):
                ids.add(entity["id"])
        return ids
