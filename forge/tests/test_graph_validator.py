"""Tests for GraphValidator."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, cast

import pytest

from src.validators.graph_validator import GraphResult, GraphValidator


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_json(filename: str) -> Dict[str, Any]:
    with open(os.path.join(FIXTURES_DIR, filename)) as f:
        return cast(Dict[str, Any], json.load(f))


@pytest.fixture
def validator() -> GraphValidator:
    return GraphValidator()


@pytest.fixture
def valid_graph() -> Dict[str, Any]:
    return _load_json("graph_valid.json")


class TestValidGraph:
    """A well-formed graph should pass all checks."""

    def test_valid_graph_passes(self, validator: GraphValidator, valid_graph: Dict[str, Any]) -> None:
        result = validator.check(valid_graph)
        assert result.is_valid, result.format_for_retry()
        assert len(result.issues) == 0
        assert len(result.reachable_nodes) == 11  # 11 nodes total
        assert len(result.unreachable_nodes) == 0
        assert len(result.orphan_nodes) == 0
        assert len(result.dead_end_nodes) == 0
        assert len(result.cycles) == 0

    def test_all_nodes_reachable(self, validator: GraphValidator, valid_graph: Dict[str, Any]) -> None:
        result = validator.check(valid_graph)
        node_ids = {n["node_id"] for n in valid_graph["nodes"]}
        assert set(result.reachable_nodes) == node_ids

    def test_format_for_retry_valid(self, validator: GraphValidator, valid_graph: Dict[str, Any]) -> None:
        result = validator.check(valid_graph)
        text = result.format_for_retry()
        assert "Valid" in text
        assert "reachable" in text


class TestUnreachableNodes:
    """Nodes not reachable from the starting node."""

    def test_unreachable_detected(self, validator: GraphValidator) -> None:
        graph = _load_json("graph_with_orphan.json")
        result = validator.check(graph)
        # node_99 should be unreachable (orphan)
        assert "node_99" in result.unreachable_nodes
        issues = [i for i in result.issues if i.category == "reachability"]
        assert len(issues) >= 1


class TestOrphans:
    """Nodes with no incoming edges (excluding starting node)."""

    def test_orphan_detected(self, validator: GraphValidator) -> None:
        graph = _load_json("graph_with_orphan.json")
        result = validator.check(graph)
        assert "node_99" in result.orphan_nodes
        issues = [i for i in result.issues if i.category == "orphan"]
        assert len(issues) >= 1
        assert any("node_99" in i.node_id for i in issues)

    def test_starting_node_not_orphan(self, validator: GraphValidator, valid_graph: Dict[str, Any]) -> None:
        result = validator.check(valid_graph)
        assert "node_01" not in result.orphan_nodes


class TestDeadEnds:
    """Non-ending nodes with no choices (but reachable)."""

    def test_dead_end_detected(self, validator: GraphValidator) -> None:
        """A reachable node with no choices and not marked as ending."""
        graph = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": "2026-08-03T00:00:00Z",
            "model_versions": {"text_generator": "test", "validator": "test"},
            "seed": 42,
            "starting_node": "node_01",
            "flags_catalog": {},
            "endings_summary": [{"node_id": "node_02", "type": "dark", "title": "End"}],
            "nodes": [
                {
                    "node_id": "node_01",
                    "chapter": 1,
                    "scene_type": "exploration",
                    "text": "Start node.",
                    "present_characters": [],
                    "present_location": "loc_01",
                    "mood": "desolate",
                    "choices": [],  # no choices, but reachable
                    "endings": {"is_ending": False},  # not an ending
                },
                {
                    "node_id": "node_02",
                    "chapter": 1,
                    "scene_type": "ending",
                    "text": "End node.",
                    "present_characters": [],
                    "present_location": "loc_01",
                    "mood": "dark",
                    "choices": [],
                    "endings": {"is_ending": True, "ending_type": "dark", "ending_title": "End"},
                },
            ],
        }
        result = validator.check(graph)
        assert "node_01" in result.dead_end_nodes
        assert "node_02" not in result.dead_end_nodes  # it's a valid ending

    def test_dead_end_not_an_ending(self, validator: GraphValidator) -> None:
        """An unreachable dead end is not reported as dead_end."""
        graph = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": "2026-08-03T00:00:00Z",
            "model_versions": {"text_generator": "test", "validator": "test"},
            "seed": 42,
            "starting_node": "node_01",
            "flags_catalog": {},
            "endings_summary": [],
            "nodes": [
                {
                    "node_id": "node_01",
                    "chapter": 1,
                    "scene_type": "exploration",
                    "text": "Start node.",
                    "present_characters": [],
                    "present_location": "loc_01",
                    "mood": "desolate",
                    "choices": [],
                    "endings": {"is_ending": False},
                },
                {
                    "node_id": "node_02",
                    "chapter": 1,
                    "scene_type": "exploration",
                    "text": "Unreachable node with no choices.",
                    "present_characters": [],
                    "present_location": "loc_01",
                    "mood": "desolate",
                    "choices": [],
                    "endings": {"is_ending": False},
                },
            ],
        }
        result = validator.check(graph)
        # node_02 is unreachable → not reported as dead_end (dead_end only for reachable)
        assert "node_02" not in result.dead_end_nodes
        assert "node_02" in result.unreachable_nodes


class TestCycleDetection:
    """Cycles in the graph should be detected."""

    def test_cycle_detected(self, validator: GraphValidator) -> None:
        graph = _load_json("graph_with_cycle.json")
        result = validator.check(graph)
        assert len(result.cycles) >= 1
        issues = [i for i in result.issues if i.category == "cycle"]
        assert len(issues) >= 1

    def test_cycle_contains_expected_nodes(self, validator: GraphValidator) -> None:
        graph = _load_json("graph_with_cycle.json")
        result = validator.check(graph)
        # node_01 → node_02 → node_01 should be detected
        cycle_nodes = set()
        for cycle in result.cycles:
            cycle_nodes.update(cycle)
        assert "node_01" in cycle_nodes
        assert "node_02" in cycle_nodes

    def test_no_cycles_in_valid_graph(self, validator: GraphValidator, valid_graph: Dict[str, Any]) -> None:
        result = validator.check(valid_graph)
        assert len(result.cycles) == 0

    def test_simple_self_loop(self, validator: GraphValidator) -> None:
        """A node pointing to itself."""
        graph = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": "2026-08-03T00:00:00Z",
            "model_versions": {"text_generator": "test", "validator": "test"},
            "seed": 42,
            "starting_node": "node_01",
            "flags_catalog": {},
            "endings_summary": [],
            "nodes": [
                {
                    "node_id": "node_01",
                    "chapter": 1,
                    "scene_type": "exploration",
                    "text": "A node that points to itself.",
                    "present_characters": [],
                    "present_location": "loc_01",
                    "mood": "desolate",
                    "choices": [{"choice_id": "ch_01_a", "choice_text": "Stay", "target_node": "node_01"}],
                    "endings": {"is_ending": False},
                },
            ],
        }
        result = validator.check(graph)
        assert len(result.cycles) >= 1


class TestEdgeCases:
    """Boundary conditions."""

    def test_empty_nodes(self, validator: GraphValidator) -> None:
        graph = {
            "starting_node": "node_01",
            "nodes": [],
            "flags_catalog": {},
        }
        result = validator.check(graph)
        # Starting node doesn't exist → no reachable nodes
        assert len(result.reachable_nodes) == 0

    def test_missing_starting_node(self, validator: GraphValidator) -> None:
        graph = {
            "starting_node": "nonexistent",
            "nodes": [
                {
                    "node_id": "node_01",
                    "chapter": 1,
                    "scene_type": "exploration",
                    "text": "Some text here for the scene.",
                    "present_characters": [],
                    "present_location": "loc_01",
                    "mood": "desolate",
                    "choices": [],
                    "endings": {"is_ending": False},
                },
            ],
            "flags_catalog": {},
        }
        result = validator.check(graph)
        assert "node_01" in result.unreachable_nodes

    def test_result_attributes_all_populated(self, validator: GraphValidator, valid_graph: Dict[str, Any]) -> None:
        result = validator.check(valid_graph)
        assert isinstance(result.reachable_nodes, list)
        assert isinstance(result.unreachable_nodes, list)
        assert isinstance(result.orphan_nodes, list)
        assert isinstance(result.dead_end_nodes, list)
        assert isinstance(result.cycles, list)
