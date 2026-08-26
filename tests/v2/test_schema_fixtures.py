"""Validate every generated schema fixture against its schema.

Run after: python scripts/generate_schema_fixtures.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.storage.v2_schemas import draft202012_validator

FIXTURES_DIR = Path("tests/fixtures/v2/schema_fixtures")
SCHEMAS_DIR = Path("schemas/v2")
CATALOG_PATH = Path("tests/fixtures/v2/schema_fixtures.json")


def _load_schemas() -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for f in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        name = f.stem.replace(".schema", "")
        schemas[name] = json.loads(f.read_text())
    return schemas


def _load_catalog() -> list[dict[str, Any]]:
    if not CATALOG_PATH.exists():
        return []
    data: list[dict[str, Any]] = json.loads(CATALOG_PATH.read_text()).get("scenarios", [])
    return data


class TestSchemaFixtures:
    """Validate every fixture in the generated catalog."""

    @pytest.fixture(scope="class")
    def schemas(self) -> dict[str, dict[str, Any]]:
        return _load_schemas()

    @pytest.fixture(scope="class")
    def catalog(self) -> list[dict[str, Any]]:
        return _load_catalog()

    def test_catalog_exists_and_has_entries(self, catalog: list[dict[str, Any]]) -> None:
        assert len(catalog) > 0, (
            "No schema fixtures found. Run: python scripts/generate_schema_fixtures.py"
        )
        valid_count = sum(1 for s in catalog if s.get("valid"))
        invalid_count = len(catalog) - valid_count
        assert valid_count >= 20, f"Expected at least 20 valid fixtures, got {valid_count}"
        assert invalid_count >= 20, f"Expected at least 20 invalid fixtures, got {invalid_count}"

    def test_every_schema_has_valid_fixture(self, schemas: dict[str, dict[str, Any]],
                                             catalog: list[dict[str, Any]]) -> None:
        for name in schemas:
            has_valid = any(
                s["schema"] == name and s.get("valid")
                for s in catalog
            )
            assert has_valid, f"Schema '{name}' has no valid fixture"

    def test_valid_fixtures_pass_validation(self, schemas: dict[str, dict[str, Any]],
                                              catalog: list[dict[str, Any]]) -> None:
        for scenario in catalog:
            if not scenario.get("valid"):
                continue
            schema_name = scenario["schema"]
            fixture_path = Path("tests/fixtures/v2") / scenario["path"]
            if not fixture_path.exists():
                pytest.fail(
                    f"Fixture {fixture_path} not found — "
                    "run scripts/generate_schema_fixtures.py"
                )

            schema = schemas.get(schema_name)
            if schema is None:
                pytest.fail(f"Schema {schema_name} not found")

            doc = json.loads(fixture_path.read_text())
            validator = draft202012_validator(schema)
            errors = list(validator.iter_errors(doc))
            assert len(errors) == 0, (
                f"{scenario['id']}: valid fixture failed validation: "
                f"{errors[0].message if errors else '?'}"
            )

    def test_invalid_fixtures_fail_validation(self, schemas: dict[str, dict[str, Any]],
                                                catalog: list[dict[str, Any]]) -> None:
        for scenario in catalog:
            if scenario.get("valid"):
                continue
            schema_name = scenario["schema"]
            fixture_path = Path("tests/fixtures/v2") / scenario["path"]
            if not fixture_path.exists():
                pytest.fail(
                    f"Fixture {fixture_path} not found — "
                    "run scripts/generate_schema_fixtures.py"
                )

            schema = schemas.get(schema_name)
            if schema is None:
                pytest.fail(f"Schema {schema_name} not found")

            doc = json.loads(fixture_path.read_text())
            validator = draft202012_validator(schema)
            errors = list(validator.iter_errors(doc))
            assert len(errors) > 0, (
                f"{scenario['id']}: invalid fixture unexpectedly passed validation "
                f"(rule: {scenario.get('rule')}, desc: {scenario.get('description')})"
            )

    def test_catalog_scenario_ids_are_unique(self, catalog: list[dict[str, Any]]) -> None:
        ids = [s["id"] for s in catalog]
        duplicates = [item for item in ids if ids.count(item) > 1]
        assert len(ids) == len(set(ids)), f"Duplicate scenario IDs: {duplicates}"

    def test_fixture_directory_matches_catalog(self, catalog: list[dict[str, Any]]) -> None:
        catalogued = {Path(item["path"]).name for item in catalog}
        on_disk = {path.name for path in FIXTURES_DIR.glob("*.json")}
        assert on_disk == catalogued, (
            f"Regenerate schema fixtures; stale={sorted(on_disk - catalogued)}, "
            f"missing={sorted(catalogued - on_disk)}"
        )
