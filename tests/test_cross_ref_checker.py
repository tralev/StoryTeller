"""Tests for CrossRefChecker."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from src.validators.cross_ref_checker import CrossRefChecker, RefResult

from .conftest import load_fixture


@pytest.fixture
def checker() -> CrossRefChecker:
    return CrossRefChecker()


@pytest.fixture
def bible() -> Dict[str, Any]:
    return load_fixture("bible_valid.json")


@pytest.fixture
def graph() -> Dict[str, Any]:
    return load_fixture("graph_valid.json")


@pytest.fixture
def story() -> Dict[str, Any]:
    return load_fixture("story_valid.json")


class TestEntityIdChecks:
    """Verify entity IDs in graph/story exist in bible."""

    def test_all_graph_entities_resolve(
        self, checker: CrossRefChecker, bible: Dict[str, Any], graph: Dict[str, Any]
    ) -> None:
        result = checker.check_all(bible=bible, graph=graph)
        entity_errors = [e for e in result.errors if e.category == "entity"]
        assert len(entity_errors) == 0, f"Unexpected entity errors: {entity_errors}"

    def test_missing_character_detected(
        self, checker: CrossRefChecker, bible: Dict[str, Any], graph: Dict[str, Any]
    ) -> None:
        graph["nodes"][0]["present_characters"] = ["nonexistent_char"]
        result = checker.check_all(bible=bible, graph=graph)
        entity_errors = [e for e in result.errors if e.category == "entity"]
        assert len(entity_errors) >= 1
        assert "nonexistent_char" in entity_errors[0].message

    def test_missing_location_detected(
        self, checker: CrossRefChecker, bible: Dict[str, Any], graph: Dict[str, Any]
    ) -> None:
        graph["nodes"][0]["present_location"] = "nonexistent_loc"
        result = checker.check_all(bible=bible, graph=graph)
        loc_errors = [e for e in result.errors if e.category == "entity" and "loc" in e.message.lower()]
        assert len(loc_errors) >= 1

    def test_story_entities_resolve(
        self, checker: CrossRefChecker, bible: Dict[str, Any], story: Dict[str, Any]
    ) -> None:
        result = checker.check_all(bible=bible, story=story)
        entity_errors = [e for e in result.errors if e.category == "entity"]
        assert len(entity_errors) == 0, f"Unexpected entity errors: {entity_errors}"


class TestNodeTargetChecks:
    """Verify choice target_nodes reference real graph nodes."""

    def test_valid_targets_pass(
        self, checker: CrossRefChecker, graph: Dict[str, Any]
    ) -> None:
        result = checker.check_all(graph=graph)
        target_errors = [e for e in result.errors if e.category == "node_target"]
        assert len(target_errors) == 0, f"Unexpected target errors: {target_errors}"

    def test_invalid_target_detected(
        self, checker: CrossRefChecker, graph: Dict[str, Any]
    ) -> None:
        graph["nodes"][0]["choices"][0]["target_node"] = "node_99"  # doesn't exist
        result = checker.check_all(graph=graph)
        target_errors = [e for e in result.errors if e.category == "node_target"]
        assert len(target_errors) >= 1
        assert "node_99" in target_errors[0].message

    def test_invalid_starting_node_detected(
        self, checker: CrossRefChecker, graph: Dict[str, Any]
    ) -> None:
        graph["starting_node"] = "node_nonexistent"
        result = checker.check_all(graph=graph)
        target_errors = [e for e in result.errors if e.category == "node_target"]
        assert len(target_errors) >= 1
        assert any("starting_node" in e.path for e in target_errors)


class TestFlagConsistencyChecks:
    """Verify all used flags are declared in flags_catalog."""

    def test_valid_flags_pass(
        self, checker: CrossRefChecker, graph: Dict[str, Any]
    ) -> None:
        result = checker.check_all(graph=graph)
        flag_errors = [e for e in result.errors if e.category == "flag"]
        assert len(flag_errors) == 0, f"Unexpected flag errors: {flag_errors}"

    def test_undeclared_flag_detected(
        self, checker: CrossRefChecker, graph: Dict[str, Any]
    ) -> None:
        graph["nodes"][0]["choices"][0]["sets_flags"] = ["undeclared_flag"]
        result = checker.check_all(graph=graph)
        flag_errors = [e for e in result.errors if e.category == "flag"]
        assert len(flag_errors) >= 1
        assert "undeclared_flag" in flag_errors[0].message

    def test_undeclared_forbids_flag_detected(
        self, checker: CrossRefChecker, graph: Dict[str, Any]
    ) -> None:
        graph["nodes"][0]["choices"][0]["forbids_flags"] = ["missing_flag"]
        result = checker.check_all(graph=graph)
        flag_errors = [e for e in result.errors if e.category == "flag"]
        assert len(flag_errors) >= 1

    def test_undeclared_conditional_flag_detected(
        self, checker: CrossRefChecker, graph: Dict[str, Any]
    ) -> None:
        graph["nodes"][3]["conditional_text"] = [
            {"if_flag": "undeclared_conditional", "append": "test"}
        ]
        result = checker.check_all(graph=graph)
        flag_errors = [e for e in result.errors if e.category == "flag"]
        assert len(flag_errors) >= 1


class TestBibleNodeReferences:
    """Verify bible entity node references exist in graph (prefix matching)."""

    def test_all_bible_nodes_resolve(
        self, checker: CrossRefChecker, bible: Dict[str, Any], graph: Dict[str, Any]
    ) -> None:
        result = checker.check_all(bible=bible, graph=graph)
        bible_errors = [e for e in result.errors if e.category == "bible_node"]
        assert len(bible_errors) == 0, f"Unexpected bible node errors: {bible_errors}"

    def test_prefix_match_for_branched_nodes(
        self, checker: CrossRefChecker, bible: Dict[str, Any], graph: Dict[str, Any]
    ) -> None:
        """Bible ref 'node_02' should match graph nodes 'node_02a', 'node_02b'."""
        # char_01 has nodes: ["node_01"] — should match exactly
        # The fixture bible now uses node_01, node_03, node_05, node_06, node_07, node_08
        # None of these require prefix matching currently, but the logic is tested below
        result = checker.check_all(bible=bible, graph=graph)
        assert result.is_valid, result.format_for_retry()

    def test_missing_bible_node_detected(
        self, checker: CrossRefChecker, bible: Dict[str, Any], graph: Dict[str, Any]
    ) -> None:
        """A bible entity referencing a node that doesn't exist in graph."""
        bible["entities"]["characters"][0]["nodes"] = ["node_nonexistent"]
        result = checker.check_all(bible=bible, graph=graph)
        bible_errors = [e for e in result.errors if e.category == "bible_node"]
        assert len(bible_errors) >= 1
        assert "node_nonexistent" in bible_errors[0].message


class TestFormatForRetry:
    """CrossRefChecker result formatting."""

    def test_valid_format(self, checker: CrossRefChecker, bible: Dict[str, Any], graph: Dict[str, Any]) -> None:
        result = checker.check_all(bible=bible, graph=graph)
        text = result.format_for_retry()
        assert "Valid" in text

    def test_invalid_format(self, checker: CrossRefChecker, graph: Dict[str, Any]) -> None:
        graph["nodes"][0]["choices"][0]["target_node"] = "node_99"
        result = checker.check_all(graph=graph)
        text = result.format_for_retry()
        assert "issue(s)" in text


class TestCheckAllIntegration:
    """check_all with all three artifacts at once."""

    def test_all_three_artifacts(
        self, checker: CrossRefChecker,
        bible: Dict[str, Any], story: Dict[str, Any], graph: Dict[str, Any],
    ) -> None:
        """check_all with bible + story + graph runs all checks."""
        result = checker.check_all(bible=bible, story=story, graph=graph)
        assert result.is_valid, result.format_for_retry()

    def test_all_three_with_graph_error(
        self, checker: CrossRefChecker,
        bible: Dict[str, Any], story: Dict[str, Any], graph: Dict[str, Any],
    ) -> None:
        """An error in graph is caught even when story is also provided."""
        graph["nodes"][0]["choices"][0]["target_node"] = "node_99"
        result = checker.check_all(bible=bible, story=story, graph=graph)
        assert not result.is_valid
        assert any(e.category == "node_target" for e in result.errors)

    def test_all_three_with_story_error(
        self, checker: CrossRefChecker,
        bible: Dict[str, Any], story: Dict[str, Any], graph: Dict[str, Any],
    ) -> None:
        """An error in story is caught even when graph is also provided."""
        story["chapters"][0]["scenes"][0]["characters_present"] = ["nonexistent_character"]
        result = checker.check_all(bible=bible, story=story, graph=graph)
        assert not result.is_valid
        assert any(e.category == "entity" for e in result.errors)


class TestEmptyBible:
    """CrossRefChecker with an empty bible."""

    def test_empty_entities(self, checker: CrossRefChecker, graph: Dict[str, Any]) -> None:
        """Bible with no entities — all graph refs are invalid."""
        empty_bible = {"entities": {}}
        result = checker.check_all(bible=empty_bible, graph=graph)
        entity_errors = [e for e in result.errors if e.category == "entity"]
        # Every graph node references at least one character, so errors expected
        assert len(entity_errors) >= 1

    def test_missing_entities_key(self, checker: CrossRefChecker, graph: Dict[str, Any]) -> None:
        """Bible without 'entities' key at all."""
        empty_bible: Dict[str, Any] = {}
        result = checker.check_all(bible=empty_bible, graph=graph)
        entity_errors = [e for e in result.errors if e.category == "entity"]
        assert len(entity_errors) >= 1


class TestPrefixMatchingEdgeCases:
    """Bible node prefix matching should not over-match."""

    def test_partial_prefix_does_not_match(
        self, checker: CrossRefChecker, bible: Dict[str, Any], graph: Dict[str, Any]
    ) -> None:
        """'node_0' should NOT match 'node_01' via prefix."""
        bible["entities"]["characters"][0]["nodes"] = ["node_0"]
        result = checker.check_all(bible=bible, graph=graph)
        bible_errors = [e for e in result.errors if e.category == "bible_node"]
        assert len(bible_errors) >= 1, f"Expected bible_node error, got none"
        assert "node_0" in bible_errors[0].message

    def test_exact_match_works(self, checker: CrossRefChecker, bible: Dict[str, Any], graph: Dict[str, Any]) -> None:
        """Exact bible node refs always resolve."""
        bible["entities"]["characters"][0]["nodes"] = ["node_01"]
        result = checker.check_all(bible=bible, graph=graph)
        bible_errors = [e for e in result.errors if e.category == "bible_node"]
        assert len(bible_errors) == 0

    def test_prefix_matches_branched(self, checker: CrossRefChecker, bible: Dict[str, Any], graph: Dict[str, Any]) -> None:
        """'node_02' prefix-matches 'node_02a' and 'node_02b'."""
        bible["entities"]["characters"][0]["nodes"] = ["node_02"]
        result = checker.check_all(bible=bible, graph=graph)
        bible_errors = [e for e in result.errors if e.category == "bible_node"]
        assert len(bible_errors) == 0  # node_02a and node_02b both exist


class TestCheckAllEdgeCases:
    """Edge cases for check_all with various combinations."""

    def test_all_none_returns_valid(self, checker: CrossRefChecker) -> None:
        """check_all with no artifacts returns valid empty result."""
        result = checker.check_all(bible=None, story=None, graph=None)
        assert result.is_valid
        assert len(result.errors) == 0


class TestKeyErrorResilience:
    """CrossRefChecker tolerates malformed data (missing keys)."""

    def test_node_without_node_id_in_graph(self, checker: CrossRefChecker, graph: dict[str, Any]) -> None:
        """A node without 'node_id' in graph should be skipped, not crash."""
        graph["nodes"].append({"chapter": 1, "scene_type": "exploration", "text": "bad node"})
        # Should not crash — set comprehension filters empty strings
        result = checker.check_all(graph=graph)
        assert isinstance(result, RefResult)

    def test_entity_without_id_in_bible(self, checker: CrossRefChecker, graph: dict[str, Any]) -> None:
        """An entity without 'id' in bible is skipped, not crashed."""
        bible: dict[str, Any] = {"entities": {"characters": [{"name": "Ghost"}]}}
        result = checker.check_all(bible=bible, graph=graph)
        assert isinstance(result, RefResult)

    def test_node_without_choices(self, checker: CrossRefChecker, graph: dict[str, Any]) -> None:
        """Node without 'choices' key should not crash."""
        graph["nodes"][0].pop("choices", None)
        result = checker.check_all(graph=graph)
        assert isinstance(result, RefResult)
