"""Generate valid + invalid fixture pairs for every v2 schema.

Produces:
  tests/fixtures/v2/schema_fixtures/{name}.valid.json
  tests/fixtures/v2/schema_fixtures/{name}.invalid.{rule}.json
  tests/fixtures/v2/schema_fixtures.json (catalog)

Re-run whenever schemas change: python scripts/generate_schema_fixtures.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "schemas" / "v2"
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "v2" / "schema_fixtures"
CATALOG_PATH = ROOT / "tests" / "fixtures" / "v2" / "schema_fixtures.json"


def load_schemas() -> dict[str, dict[str, Any]]:
    schemas = {}
    for f in sorted(SCHEMAS_DIR.glob("*.schema.json")):
        name = f.stem.replace(".schema", "")
        schemas[name] = json.loads(f.read_text())
    return schemas


def generate_valid(schema: dict[str, Any]) -> dict[str, Any]:
    """Generate a minimal valid document for the schema.

    Recursively fills required fields from properties, following nested
    object structures. Handles top-level $id/$schema as metadata only.
    """
    return _fill_required(schema, {})


def _fill_required(schema: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Recursively fill required fields from properties into result."""
    props = schema.get("properties", {})
    required = schema.get("required", [])

    for key in required:
        if key in result:
            continue
        prop_schema = props.get(key, {})
        val = _example_value(key, prop_schema)
        # If the value is an object and the property schema has nested required
        # fields, fill those recursively
        if isinstance(val, dict) and prop_schema.get("type") == "object":
            val = _fill_required(prop_schema, val)
        result[key] = val

    return result


def _example_value(key: str, prop: dict[str, Any]) -> object:
    """Generate an example value matching the property schema.

    The key hint helps generate pattern-conforming values.
    """
    # Handle const/enum first (most specific)
    if "const" in prop:
        return prop["const"]
    if "enum" in prop:
        return prop["enum"][0]

    t = prop.get("type", "string")

    if t == "string":
        pat = prop.get("pattern", "")
        # SHA-256 hex hash: ^[0-9a-f]{64}$
        if pat and pat.endswith("{64}$") and "0-9a-f" in pat:
            return "a" * 64
        # Story / node / artifact IDs: ^(story_|node_|[a-z][a-z0-9]*_)[0-9a-f]{32}$
        if pat and "{32}$" in pat and "0-9a-f" in pat:
            if pat.startswith("^story_"):
                return "story_" + "a" * 32
            if pat.startswith("^node_"):
                return "node_" + "a" * 32
            # Catch-all for artifact_id style: ^[a-z][a-z0-9]*_[0-9a-f]{32}$
            return "example_" + "a" * 32
        # Generic lowercase underscore ID: ^[a-z][a-z0-9_]*$
        if pat and pat.startswith("^[a-z]") and pat.endswith("*$"):
            return "example_id"
        # path pattern: safe relative path (e.g. ^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))[^\\]+$)
        if pat and pat.startswith("^(?!") and "\\.\\." in pat:
            return "artifacts/example.json"
        # Any other hex pattern: just fill with matching chars
        if pat and "0-9a-f" in pat:
            length_hint = 32  # default
            for c in ["64", "32", "16", "8"]:
                if "{" + c + "}$" in pat:
                    length_hint = int(c)
                    break
            return "a" * length_hint
        # Default string with key hint
        return f"example_{key}" if not key.startswith("_") else "example"

    if t == "integer":
        mn = prop.get("minimum", 0)
        return max(mn, 1)
    if t == "number":
        mn = prop.get("minimum", 0)
        return max(float(mn), 1.0)
    if t == "boolean":
        return True
    if t == "array":
        items = prop.get("items", {})
        if items:
            return [_example_value("item", items)]
        # Empty array but with a plausible single item for minimumItems
        min_items = prop.get("minItems", 0)
        if min_items > 0:
            return [_example_value("item", {}) for _ in range(min_items)]
        return []
    if t == "object":
        # Build minimal object from nested required fields
        nested: dict[str, Any] = {}
        for nk in prop.get("required", []):
            nested[nk] = _example_value(nk, prop.get("properties", {}).get(nk, {}))
        return nested

    return "example"


def generate_invalids(name: str, schema: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    """Generate targeted invalid documents, one per constraint."""
    invalids: dict[str, tuple[str, dict[str, Any]]] = {}
    valid = generate_valid(schema)
    props = schema.get("properties", {})
    required = schema.get("required", [])

    # Collect ALL required fields recursively (top-level only for now)
    all_required: list[str] = list(required)

    # 1. Missing each required field (up to 5)
    for field in all_required[:5]:
        invalid = dict(valid)
        invalid.pop(field, None)
        invalids[f"missing-{field}"] = (
            f"Required field '{field}' is missing", invalid
        )

    # 2. Wrong type for each required field (up to 5)
    for field in all_required[:5]:
        if field in props and "const" not in props[field]:
            t = props[field].get("type", "string")
            wrong = dict(valid)
            if t == "string":
                wrong[field] = 999
            elif t in ("integer", "number"):
                wrong[field] = "not-a-number"
            elif t == "array":
                wrong[field] = "not-an-array"
            elif t == "object":
                wrong[field] = "not-an-object"
            elif t == "boolean":
                wrong[field] = "not-a-bool"
            else:
                continue
            invalids[f"wrong-type-{field}"] = (
                f"'{field}' expects {t}", wrong
            )

    # 3. Below minimum for integer fields (up to 5)
    for field in all_required[:5]:
        if field in props and props[field].get("type") == "integer":
            mn = props[field].get("minimum", 0)
            if mn > 0:
                wrong = dict(valid)
                wrong[field] = mn - 1
                invalids[f"below-min-{field}"] = (
                    f"'{field}' must be >= {mn}", wrong
                )

    # 4. Pattern violation for string fields with patterns (up to 5)
    for field in all_required[:5]:
        if field in props and props[field].get("type") == "string":
            pat = props[field].get("pattern", "")
            if pat:
                wrong = dict(valid)
                if "0-9a-f" in pat or "a-f" in pat:
                    wrong[field] = "DEADBEEF_ZZZZZZZZ_!!!"
                elif pat.startswith("^(?!") or "/" in pat:
                    wrong[field] = "/absolute/path"
                elif pat.startswith("^[a-z]"):
                    wrong[field] = "INVALID_UPPERCASE"
                else:
                    wrong[field] = ""
                invalids[f"pattern-{field}"] = (
                    f"'{field}' violates pattern", wrong
                )

    # 5. Extra property when additionalProperties is False
    if schema.get("additionalProperties") is False:
        wrong = dict(valid)
        wrong["_extra_unknown_field_"] = "unexpected"
        invalids["extra-property"] = (
            "Unknown additional property rejected", wrong
        )

    return invalids


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    schemas = load_schemas()
    catalog: dict[str, Any] = {"format": "storyteller.schema-fixtures.v1", "scenarios": []}

    # This directory is generated output. Remove prior generated documents so
    # files that are no longer described by the current schemas cannot masquerade
    # as uncatalogued conformance evidence.
    for old_fixture in FIXTURES_DIR.glob("*.json"):
        old_fixture.unlink()

    for name in sorted(schemas):
        schema = schemas[name]

        # Generate valid fixture
        valid_doc = generate_valid(schema)
        valid_path = FIXTURES_DIR / f"{name}.valid.json"
        valid_path.write_text(json.dumps(valid_doc, indent=2) + "\n")
        catalog["scenarios"].append({
            "id": f"{name}-valid",
            "schema": name,
            "path": f"schema_fixtures/{name}.valid.json",
            "valid": True,
            "description": f"Minimal valid {name} document",
        })

        # Generate invalid fixtures
        invalids = generate_invalids(name, schema)
        for rule_id, (desc, invalid_doc) in invalids.items():
            inv_path = FIXTURES_DIR / f"{name}.invalid.{rule_id}.json"
            inv_path.write_text(json.dumps(invalid_doc, indent=2) + "\n")
            catalog["scenarios"].append({
                "id": f"{name}-invalid-{rule_id}",
                "schema": name,
                "path": f"schema_fixtures/{name}.invalid.{rule_id}.json",
                "valid": False,
                "rule": rule_id,
                "description": desc,
            })

    # Write catalog
    CATALOG_PATH.write_text(json.dumps(catalog, indent=2) + "\n")

    total = len(catalog["scenarios"])
    valid_count = sum(1 for s in catalog["scenarios"] if s["valid"])
    invalid_count = total - valid_count
    print(
        f"Generated {total} fixtures ({valid_count} valid, {invalid_count} invalid) "
        f"for {len(schemas)} schemas"
    )
    print(f"Catalog: {CATALOG_PATH}")


if __name__ == "__main__":
    main()
