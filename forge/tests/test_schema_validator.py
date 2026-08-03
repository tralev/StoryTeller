"""Tests for SchemaValidator."""

from __future__ import annotations

import os

import pytest

from src.validators.schema_validator import SchemaResult, SchemaValidator

from .conftest import load_fixture


SCHEMAS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docs", "schemas"))


@pytest.fixture(scope="module")
def validator() -> SchemaValidator:
    return SchemaValidator(SCHEMAS_DIR)


class TestSchemaValidator:
    """Core schema validator tests."""

    def test_loads_all_six_schemas(self, validator: SchemaValidator) -> None:
        names = validator.available_schemas
        assert "bible" in names
        assert "story" in names
        assert "graph" in names
        assert "gm_index" in names
        assert "style_bible" in names
        assert "manifest" in names
        assert len(names) == 6

    def test_validate_bible_valid(self, validator: SchemaValidator) -> None:
        data = load_fixture("bible_valid.json")
        result = validator.validate_bible(data)
        assert result.is_valid, result.format_for_retry()
        assert len(result.errors) == 0

    def test_validate_bible_invalid(self, validator: SchemaValidator) -> None:
        data = load_fixture("bible_invalid.json")
        result = validator.validate_bible(data)
        assert not result.is_valid
        assert len(result.errors) > 0

    def test_validate_story_valid(self, validator: SchemaValidator) -> None:
        data = load_fixture("story_valid.json")
        result = validator.validate_story(data)
        assert result.is_valid, result.format_for_retry()

    def test_validate_graph_valid(self, validator: SchemaValidator) -> None:
        data = load_fixture("graph_valid.json")
        result = validator.validate_graph(data)
        assert result.is_valid, result.format_for_retry()

    def test_validate_gm_index_valid(self, validator: SchemaValidator) -> None:
        data = load_fixture("gm_index_valid.json")
        result = validator.validate_gm_index(data)
        assert result.is_valid, result.format_for_retry()

    def test_validate_style_bible_valid(self, validator: SchemaValidator) -> None:
        data = load_fixture("style_bible_valid.json")
        result = validator.validate_style_bible(data)
        assert result.is_valid, result.format_for_retry()

    def test_unknown_schema(self, validator: SchemaValidator) -> None:
        result = validator.validate({}, "nonexistent")
        assert not result.is_valid
        assert "Unknown schema" in result.errors[0].message

    def test_format_for_retry_valid(self, validator: SchemaValidator) -> None:
        data = load_fixture("bible_valid.json")
        result = validator.validate_bible(data)
        text = result.format_for_retry()
        assert "Valid" in text

    def test_format_for_retry_invalid(self, validator: SchemaValidator) -> None:
        data = load_fixture("bible_invalid.json")
        result = validator.validate_bible(data)
        text = result.format_for_retry()
        assert "issue(s) found" in text
        assert "schema_version" in text.lower() or "required" in text.lower()

    def test_invalid_json_structure(self, validator: SchemaValidator) -> None:
        """Schema errors include meaningful path information."""
        result = validator.validate_bible({})
        assert not result.is_valid
        # Should report missing required fields
        error_texts = [e.message.lower() for e in result.errors]
        assert any("required" in t for t in error_texts)

    def test_validate_manifest_valid(self, validator: SchemaValidator) -> None:
        """Manifest fixture passes schema validation."""
        data = load_fixture("manifest_valid.json")
        result = validator.validate_manifest(data)
        assert result.is_valid, result.format_for_retry()
        assert len(result.errors) == 0


class TestSchemaErrorPathFormatting:
    """Path formatting from absolute_path."""

    def test_empty_path(self, validator: SchemaValidator) -> None:
        result = validator.validate({}, "bible")
        for e in result.errors:
            if e.path == "":
                # Some errors have no path (e.g. missing top-level required)
                assert "required" in e.message.lower()
                return
        pytest.fail("Expected at least one root-level error")

    def test_nested_path(self, validator: SchemaValidator) -> None:
        """Errors in nested structures show readable paths."""
        data = load_fixture("bible_valid.json")
        # Corrupt one field to produce a nested error
        data["entities"]["characters"][0]["role"] = "invalid_role"
        result = validator.validate_bible(data)
        assert not result.is_valid
        paths = [e.path for e in result.errors]
        assert any("role" in p for p in paths) or any("enum" in e.message.lower() for e in result.errors)
