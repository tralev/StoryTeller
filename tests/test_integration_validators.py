"""Integration tests: chaining SchemaValidator → CrossRefChecker → GraphValidator.

Tests the full validation pipeline as it would run in production.
"""

from __future__ import annotations

import os

import pytest

from src.validators.schema_validator import SchemaValidator
from src.validators.cross_ref_checker import CrossRefChecker
from src.validators.graph_validator import GraphValidator

from .conftest import load_fixture


SCHEMAS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "schemas"))


@pytest.fixture(scope="module")
def schema_validator() -> SchemaValidator:
    return SchemaValidator(SCHEMAS_DIR)


@pytest.fixture
def cross_ref_checker() -> CrossRefChecker:
    return CrossRefChecker()


@pytest.fixture
def graph_validator() -> GraphValidator:
    return GraphValidator()


class TestFullValidationPipeline:
    """Chain all 3 validators in the order they run in production."""

    def test_bible_pipeline(
        self, schema_validator: SchemaValidator, cross_ref_checker: CrossRefChecker
    ) -> None:
        """Bible: schema → cross_ref (bible-only has no graph yet)."""
        bible = load_fixture("bible_valid.json")

        # 1. Schema validation
        schema_result = schema_validator.validate_bible(bible)
        assert schema_result.is_valid, schema_result.format_for_retry()

    def test_graph_pipeline(
        self,
        schema_validator: SchemaValidator,
        cross_ref_checker: CrossRefChecker,
        graph_validator: GraphValidator,
    ) -> None:
        """Graph: schema → cross_ref → graph structure."""
        bible = load_fixture("bible_valid.json")
        graph = load_fixture("graph_valid.json")

        # 1. Schema validation
        schema_result = schema_validator.validate_graph(graph)
        assert schema_result.is_valid, schema_result.format_for_retry()

        # 2. Cross-reference check (graph ↔ bible)
        ref_result = cross_ref_checker.check_all(bible=bible, graph=graph)
        assert ref_result.is_valid, ref_result.format_for_retry()

        # 3. Graph structure validation
        graph_result = graph_validator.check(graph)
        assert graph_result.is_valid, graph_result.format_for_retry()

    def test_full_pipeline_bible_story_graph(
        self,
        schema_validator: SchemaValidator,
        cross_ref_checker: CrossRefChecker,
        graph_validator: GraphValidator,
    ) -> None:
        """All three artifacts: schema → cross_ref → graph."""
        bible = load_fixture("bible_valid.json")
        story = load_fixture("story_valid.json")
        graph = load_fixture("graph_valid.json")

        # 1. Schema validation for all 3
        for name, data, validator_fn in [
            ("bible", bible, schema_validator.validate_bible),
            ("story", story, schema_validator.validate_story),
            ("graph", graph, schema_validator.validate_graph),
        ]:
            result = validator_fn(data)
            assert result.is_valid, f"[{name}] {result.format_for_retry()}"

        # 2. Cross-reference check for all 3 together
        ref_result = cross_ref_checker.check_all(bible=bible, story=story, graph=graph)
        assert ref_result.is_valid, ref_result.format_for_retry()

        # 3. Graph structure validation
        graph_result = graph_validator.check(graph)
        assert graph_result.is_valid, graph_result.format_for_retry()

    def test_invalid_graph_fails_integration(
        self,
        schema_validator: SchemaValidator,
        graph_validator: GraphValidator,
    ) -> None:
        """An invalid graph fails at the graph structure check."""
        graph = load_fixture("graph_with_cycle.json")

        # Schema may pass (the fixture is structurally valid JSON)
        schema_result = schema_validator.validate_graph(graph)
        assert schema_result.is_valid  # Cycle is not a schema violation

        # But graph structure check catches the cycle
        graph_result = graph_validator.check(graph)
        assert not graph_result.is_valid
        assert len(graph_result.cycles) >= 1

    def test_format_all_errors_for_retry(
        self,
        schema_validator: SchemaValidator,
        cross_ref_checker: CrossRefChecker,
        graph_validator: GraphValidator,
    ) -> None:
        """All three validators produce format_for_retry() output."""
        bible = load_fixture("bible_valid.json")
        graph = load_fixture("graph_valid.json")

        schema_text = schema_validator.validate_bible(bible).format_for_retry()
        ref_text = cross_ref_checker.check_all(bible=bible, graph=graph).format_for_retry()
        graph_text = graph_validator.check(graph).format_for_retry()

        assert "Valid" in schema_text
        assert "Valid" in ref_text
        assert "Valid" in graph_text
