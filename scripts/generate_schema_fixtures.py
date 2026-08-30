"""Generate valid + invalid fixture pairs for every v2 schema.

Produces:
  tests/fixtures/v2/schema_fixtures/{name}.valid.json
  tests/fixtures/v2/schema_fixtures/{name}.invalid.{rule}.json
  tests/fixtures/v2/schema_fixtures.json (catalog)

Re-run whenever schemas change: python scripts/generate_schema_fixtures.py
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCHEMAS_DIR = ROOT / "schemas" / "v2"
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "v2" / "schema_fixtures"
CATALOG_PATH = ROOT / "tests" / "fixtures" / "v2" / "schema_fixtures.json"

_BUNDLE: dict[str, dict[str, Any]] = {}


def load_schemas() -> dict[str, dict[str, Any]]:
    from src.storage.v2_schemas import load_v2_schemas

    loaded = load_v2_schemas(SCHEMAS_DIR)
    return {name.removesuffix(".schema.json"): schema for name, schema in loaded.items()}


def _ensure_bundle() -> dict[str, dict[str, Any]]:
    global _BUNDLE
    if not _BUNDLE:
        from src.storage.v2_schemas import load_v2_schemas
        _BUNDLE = load_v2_schemas(SCHEMAS_DIR)
    return _BUNDLE


def generate_valid(schema: dict[str, Any]) -> dict[str, Any]:
    """Generate a minimal valid document for the schema.

    Recursively fills required fields from properties, following nested
    object structures. Handles top-level $id/$schema as metadata only.
    """
    _ensure_bundle()
    return _fill_required(schema, schema, {})


def _document_for_ref(ref: str, current: dict[str, Any]) -> dict[str, Any]:
    if ref.startswith("#/"):
        return current
    uri = ref.split("#", 1)[0]
    filename = uri.rsplit("/", 1)[-1]
    bundle = _ensure_bundle()
    if filename in bundle:
        return bundle[filename]
    for schema in bundle.values():
        if schema.get("$id") == uri:
            return schema
    return current


def _unwrap(
    prop: dict[str, Any], current: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    from src.storage.v2_schemas import resolve_ref

    while "$ref" in prop:
        ref = str(prop["$ref"])
        siblings = {key: value for key, value in prop.items() if key != "$ref"}
        current = _document_for_ref(ref, current)
        resolved = resolve_ref(ref, current, _ensure_bundle())
        prop = {**resolved, **siblings}
    if "oneOf" in prop and isinstance(prop["oneOf"], list) and prop["oneOf"]:
        first = prop["oneOf"][0]
        if isinstance(first, dict):
            return _unwrap(first, current)
    return prop, current


def _fill_required(
    schema: dict[str, Any], current: dict[str, Any], result: dict[str, Any],
) -> dict[str, Any]:
    """Recursively fill required fields from properties into result."""
    resolved, current = _unwrap(schema, current)
    props = resolved.get("properties", {})
    required = resolved.get("required", [])

    for key in required:
        if key in result:
            continue
        prop_schema = props.get(key, resolved.get("additionalProperties", {}))
        if not isinstance(prop_schema, dict):
            continue
        unwrapped, owner = _unwrap(prop_schema, current)
        val = _example_value(key, unwrapped, owner)
        if isinstance(val, dict) and unwrapped.get("type") == "object":
            val = _fill_required(unwrapped, owner, val)
        result[key] = val

    return result


def _example_value(
    key: str, prop: dict[str, Any], current: dict[str, Any] | None = None,
) -> object:
    """Generate an example value matching the property schema.

    The key hint helps generate pattern-conforming values.
    """
    current = current or prop
    prop, current = _unwrap(prop, current)
    # Handle const/enum first (most specific)
    if "const" in prop:
        return prop["const"]
    if "enum" in prop:
        return prop["enum"][0]

    t = prop.get("type", "string")
    if isinstance(t, list):
        if t == ["null"] or t == [None]:
            return None
        if "null" in t and len(t) > 1:
            t = next(item for item in t if item != "null")
        else:
            t = t[0]
    if t == "null":
        return None

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
        prefix = prop.get("prefixItems")
        if isinstance(prefix, list) and prefix:
            return [
                _example_value(f"{key}_{index}", item, current)
                if isinstance(item, dict) else item
                for index, item in enumerate(prefix)
            ]
        items = prop.get("items", {})
        if isinstance(items, dict) and items:
            count = max(int(prop.get("minItems") or 1), 1)
            if prop.get("maxItems") is not None:
                count = min(count, int(prop["maxItems"]))
            item_enum = items.get("enum")
            if isinstance(item_enum, list) and prop.get("uniqueItems"):
                return item_enum[:count]
            values = [_example_value(f"item_{index}", items, current) for index in range(count)]
            if prop.get("uniqueItems") and count > 1:
                uniqued: list[object] = []
                for index, value in enumerate(values):
                    if (
                        isinstance(value, str)
                        and "_" in value
                        and len(value.rsplit("_", 1)[-1]) == 32
                    ):
                        prefix, _digest = value.rsplit("_", 1)
                        uniqued.append(f"{prefix}_{index:032x}")
                    elif isinstance(value, str):
                        uniqued.append(f"{value}_{index}")
                    elif isinstance(value, int) and not isinstance(value, bool):
                        candidate = value + index
                        maximum = items.get("maximum")
                        if isinstance(maximum, int) and candidate > maximum:
                            candidate = value - index
                        uniqued.append(candidate)
                    else:
                        uniqued.append(value)
                values = uniqued
            return values
        min_items = prop.get("minItems", 0)
        if min_items > 0:
            return [_example_value("item", {}, current) for _ in range(min_items)]
        return []
    if t == "object":
        nested: dict[str, Any] = {}
        nested = _fill_required(prop, current, nested)
        extra = prop.get("additionalProperties")
        min_props = int(prop.get("minProperties") or 0)
        if isinstance(extra, dict) and min_props > len(nested):
            names = prop.get("propertyNames", {})
            map_key = (
                _example_value("property_name", names, current)
                if isinstance(names, dict)
                else "example_item"
            )
            nested[str(map_key)] = _example_value("entry", extra, current)
        return nested

    return "example"


def generate_invalids(name: str, schema: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    """Generate targeted invalid documents, one per constraint."""
    invalids: dict[str, tuple[str, dict[str, Any]]] = {}
    valid = generate_valid(schema)
    resolved, owner = _unwrap(schema, schema)
    props = {}
    prop_owners: dict[str, dict[str, Any]] = {}
    for key, value in resolved.get("properties", {}).items():
        if isinstance(value, dict):
            props[key], prop_owners[key] = _unwrap(value, owner)
        else:
            props[key] = value
    required = resolved.get("required", [])

    # Cover every top-level required field. Nested constraint mutation is a
    # separate P8.C1 slice, but no field may disappear merely because it occurs
    # after an arbitrary catalog limit.
    all_required: list[str] = list(required)

    # 1. Missing each required field
    for field in all_required:
        invalid = dict(valid)
        invalid.pop(field, None)
        invalids[f"missing-{field}"] = (
            f"Required field '{field}' is missing", invalid
        )

    # 2. Wrong type for each required field
    for field in all_required:
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

    # 3. Below minimum for integer fields
    for field in all_required:
        if field in props and props[field].get("type") == "integer":
            mn = props[field].get("minimum", 0)
            if mn > 0:
                wrong = dict(valid)
                wrong[field] = mn - 1
                invalids[f"below-min-{field}"] = (
                    f"'{field}' must be >= {mn}", wrong
                )

    # 4. Pattern violation for string fields with patterns
    for field in all_required:
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

    # 5. Remaining top-level constraint classes.
    for field in all_required:
        prop = props.get(field)
        if field in valid and isinstance(prop, dict):
            _constraint_invalids(
                valid, prop, prop_owners.get(field, owner), (field,), invalids, nested=False
            )

    # 6. Extra property when additionalProperties is False
    if schema.get("additionalProperties") is False:
        wrong = dict(valid)
        wrong["_extra_unknown_field_"] = "unexpected"
        invalids["extra-property"] = (
            "Unknown additional property rejected", wrong
        )

    _generate_nested_invalids(valid, schema, schema, (), invalids)

    return invalids


def definition_wrapper(definition: str) -> dict[str, Any]:
    """Return a closed document wrapper that activates one shared definition."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["value"],
        "properties": {
            "value": {
                "$ref": (
                    "https://storyteller.local/schemas/v2/defs.schema.json"
                    f"#/$defs/{definition}"
                )
            }
        },
    }


def _rule_path(path: tuple[str, ...]) -> str:
    return "-".join(path).replace("_", "-")


def _replace_at(document: dict[str, Any], path: tuple[str, ...], value: object) -> None:
    target: Any = document
    for part in path[:-1]:
        target = target[0] if part == "item" else target[part]
    final = path[-1]
    if final == "item":
        target[0] = value
    else:
        target[final] = value


def _delete_at(document: dict[str, Any], path: tuple[str, ...]) -> None:
    target: Any = document
    for part in path[:-1]:
        target = target[0] if part == "item" else target[part]
    del target[path[-1]]


def _wrong_type(schema: dict[str, Any]) -> object | None:
    value_type = schema.get("type")
    types = value_type if isinstance(value_type, list) else [value_type]
    if "object" in types:
        return "not-an-object"
    if "array" in types:
        return "not-an-array"
    if "string" in types:
        return 999
    if "integer" in types or "number" in types:
        return "not-a-number"
    if "boolean" in types:
        return "not-a-bool"
    return None


def _different_value(value: object) -> object:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, str):
        return value + "_invalid"
    return "__invalid__"


def _constraint_invalids(
    valid: dict[str, Any],
    resolved: dict[str, Any],
    owner: dict[str, Any],
    path: tuple[str, ...],
    invalids: dict[str, tuple[str, dict[str, Any]]],
    *,
    nested: bool,
) -> None:
    value: Any = valid
    for part in path:
        value = value[0] if part == "item" else value[part]
    label = _rule_path(path)
    prefix = "nested-" if nested else ""

    mutations: list[tuple[str, str, object]] = []
    if "const" in resolved:
        mutations.append(("const", "enforces its constant value", _different_value(value)))
    if isinstance(resolved.get("enum"), list):
        mutations.append(("enum", "enforces its enumeration", "__invalid_enum__"))
    if isinstance(value, str) and int(resolved.get("minLength") or 0) > 0:
        mutations.append(("below-min-length", "enforces its minimum length", ""))
    if isinstance(value, str) and resolved.get("maxLength") is not None:
        mutations.append(
            (
                "above-max-length",
                "enforces its maximum length",
                "x" * (int(resolved["maxLength"]) + 1),
            )
        )
    if isinstance(value, list):
        minimum = int(resolved.get("minItems") or 0)
        if minimum > 0:
            mutations.append(("below-min-items", "enforces its minimum item count", []))
        if resolved.get("maxItems") is not None:
            maximum = int(resolved["maxItems"])
            item_schema = resolved.get("items")
            sample = (
                _example_value("item", item_schema, owner)
                if isinstance(item_schema, dict)
                else 0
            )
            mutations.append(
                ("above-max-items", "enforces its maximum item count", [sample] * (maximum + 1))
            )
        if resolved.get("uniqueItems") is True:
            item_schema = resolved.get("items")
            sample = (
                _example_value("item", item_schema, owner)
                if isinstance(item_schema, dict)
                else "duplicate"
            )
            mutations.append(("duplicate-items", "enforces unique items", [sample, sample]))
    if isinstance(value, dict):
        minimum = int(resolved.get("minProperties") or 0)
        if minimum > 0:
            mutations.append(("below-min-properties", "enforces its minimum property count", {}))
        names = resolved.get("propertyNames")
        if value and isinstance(names, dict) and names.get("pattern"):
            renamed = dict(value)
            first = sorted(renamed)[0]
            renamed["INVALID KEY"] = renamed.pop(first)
            mutations.append(("property-name-pattern", "enforces property-name grammar", renamed))

    for rule, description, replacement in mutations:
        wrong = copy.deepcopy(valid)
        _replace_at(wrong, path, replacement)
        invalids.setdefault(
            f"{prefix}{rule}-{label}",
            (f"Field '{'.'.join(path)}' {description}", wrong),
        )


def _generate_nested_invalids(
    valid: dict[str, Any],
    node: dict[str, Any],
    owner: dict[str, Any],
    path: tuple[str, ...],
    invalids: dict[str, tuple[str, dict[str, Any]]],
) -> None:
    """Generate one mutation for each reachable nested structural constraint."""
    resolved, owner = _unwrap(node, owner)
    value: Any = valid
    for part in path:
        value = value[0] if part == "item" else value[part]

    # Top-level field constraints already use the stable legacy rule IDs above.
    # Recursive IDs begin below the root property to avoid duplicate fixtures.
    if len(path) > 1:
        label = _rule_path(path)
        wrong_value = _wrong_type(resolved)
        if wrong_value is not None:
            wrong = copy.deepcopy(valid)
            _replace_at(wrong, path, wrong_value)
            invalids.setdefault(
                f"nested-wrong-type-{label}",
                (f"Nested field '{'.'.join(path)}' enforces its type", wrong),
            )
        if isinstance(value, str) and resolved.get("pattern"):
            wrong = copy.deepcopy(valid)
            _replace_at(wrong, path, "INVALID/../UPPERCASE")
            invalids.setdefault(
                f"nested-pattern-{label}",
                (f"Nested field '{'.'.join(path)}' enforces its pattern", wrong),
            )
        if isinstance(value, int) and not isinstance(value, bool) and "minimum" in resolved:
            wrong = copy.deepcopy(valid)
            _replace_at(wrong, path, int(resolved["minimum"]) - 1)
            invalids.setdefault(
                f"nested-below-min-{label}",
                (f"Nested field '{'.'.join(path)}' enforces its minimum", wrong),
            )
        if isinstance(value, int) and not isinstance(value, bool) and "maximum" in resolved:
            wrong = copy.deepcopy(valid)
            _replace_at(wrong, path, int(resolved["maximum"]) + 1)
            invalids.setdefault(
                f"nested-above-max-{label}",
                (f"Nested field '{'.'.join(path)}' enforces its maximum", wrong),
            )
        _constraint_invalids(valid, resolved, owner, path, invalids, nested=True)

    if resolved.get("type") == "object" and isinstance(value, dict):
        properties = resolved.get("properties", {})
        for field in resolved.get("required", []):
            if path and field in value:
                wrong = copy.deepcopy(valid)
                _delete_at(wrong, path + (field,))
                label = _rule_path(path + (field,))
                invalids.setdefault(
                    f"nested-missing-{label}",
                    (f"Nested required field '{'.'.join(path + (field,))}' is missing", wrong),
                )
        if path and resolved.get("additionalProperties") is False:
            wrong = copy.deepcopy(valid)
            target: Any = wrong
            for part in path:
                target = target[0] if part == "item" else target[part]
            target["_extra_unknown_field_"] = "unexpected"
            invalids.setdefault(
                f"nested-extra-property-{_rule_path(path)}",
                (f"Nested record '{'.'.join(path)}' rejects unknown fields", wrong),
            )
        for field, child in properties.items():
            if field in value and isinstance(child, dict):
                _generate_nested_invalids(valid, child, owner, path + (field,), invalids)
        additional = resolved.get("additionalProperties")
        if isinstance(additional, dict) and value:
            first_key = sorted(value)[0]
            _generate_nested_invalids(valid, additional, owner, path + (first_key,), invalids)

    if resolved.get("type") == "array" and isinstance(value, list) and value:
        items = resolved.get("items")
        if isinstance(items, dict):
            _generate_nested_invalids(valid, items, owner, path + ("item",), invalids)


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    schemas = load_schemas()
    catalog: dict[str, Any] = {"format": "storyteller.schema-fixtures.v1", "scenarios": []}

    # This directory is generated output. Remove prior generated documents so
    # files that are no longer described by the current schemas cannot masquerade
    # as uncatalogued conformance evidence.
    for old_fixture in FIXTURES_DIR.glob("*.json"):
        old_fixture.unlink()

    _ensure_bundle()
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

    # `$defs` is a library document, so definitions not reached by one of the
    # persisted root schemas would otherwise validate only as inert metadata.
    # Wrap every definition under a required `value` field and exercise it as
    # an independently addressable schema contract.
    definitions = schemas["defs"].get("$defs")
    if not isinstance(definitions, dict):
        raise SystemExit("defs schema has no definition catalog")
    for definition in sorted(definitions):
        wrapper = definition_wrapper(definition)
        fixture_name = f"defs--{definition}"
        valid_doc = generate_valid(wrapper)
        valid_path = FIXTURES_DIR / f"{fixture_name}.valid.json"
        valid_path.write_text(json.dumps(valid_doc, indent=2) + "\n")
        catalog["scenarios"].append({
            "id": f"{fixture_name}-valid",
            "schema": "defs",
            "definition": definition,
            "path": f"schema_fixtures/{fixture_name}.valid.json",
            "valid": True,
            "description": f"Minimal valid shared definition {definition}",
        })
        for rule_id, (desc, invalid_doc) in generate_invalids(fixture_name, wrapper).items():
            inv_path = FIXTURES_DIR / f"{fixture_name}.invalid.{rule_id}.json"
            inv_path.write_text(json.dumps(invalid_doc, indent=2) + "\n")
            catalog["scenarios"].append({
                "id": f"{fixture_name}-invalid-{rule_id}",
                "schema": "defs",
                "definition": definition,
                "path": f"schema_fixtures/{fixture_name}.invalid.{rule_id}.json",
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
