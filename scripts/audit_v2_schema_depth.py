"""P8.C1 closure gate for shallow or open-ended v2 JSON schemas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _typed(definition: dict[str, Any]) -> bool:
    return any(
        key in definition
        for key in ("type", "$ref", "const", "enum", "oneOf", "anyOf", "allOf", "prefixItems")
    )


def _record_errors(schema: dict[str, Any], name: str, path: str) -> list[str]:
    errors: list[str] = []
    if "$ref" in schema:
        return errors
    value_type = schema.get("type")
    types = value_type if isinstance(value_type, list) else [value_type]
    if "array" in types:
        items = schema.get("items")
        prefix = schema.get("prefixItems")
        if items is False and isinstance(prefix, list) and prefix:
            for index, item in enumerate(prefix):
                if not isinstance(item, dict) or not _typed(item):
                    errors.append(f"{name}: {path} prefixItems[{index}] has no type")
        elif not isinstance(items, dict):
            errors.append(f"{name}: {path} array has no item schema")
        elif "$ref" not in items and items.get("type") == "object":
            errors.extend(_object_errors(items, name, f"{path}[]"))
        elif not _typed(items):
            errors.append(f"{name}: {path} array items have no type")
    if "object" in types:
        errors.extend(_object_errors(schema, name, path))
    for key in ("oneOf", "anyOf", "allOf"):
        options = schema.get(key)
        if not isinstance(options, list):
            continue
        for index, item in enumerate(options):
            if isinstance(item, dict):
                errors.extend(_record_errors(item, name, f"{path}{key}[{index}]"))
    return errors


def _object_errors(schema: dict[str, Any], name: str, path: str) -> list[str]:
    errors: list[str] = []
    if schema.get("additionalProperties") is not False:
        keyed = schema.get("additionalProperties")
        if not isinstance(keyed, dict):
            errors.append(f"{name}: {path} is open-ended")
        elif not _typed(keyed):
            errors.append(f"{name}: {path} additionalProperties has no type")
    keyed_values = schema.get("additionalProperties")
    is_typed_map = isinstance(keyed_values, dict) and _typed(keyed_values)
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        if not schema.get("$defs") and not is_typed_map:
            errors.append(f"{name}: {path} properties are missing")
        properties = {}
    required = schema.get("required")
    if path == "/" and isinstance(schema.get("$defs"), dict) and schema["$defs"] and not properties:
        required = required or []
    elif is_typed_map and not properties:
        required = required or []
    elif not isinstance(required, list) or not required:
        errors.append(f"{name}: {path} required fields are missing")
        required = []
    for field in required:
        definition = properties.get(field)
        if not isinstance(definition, dict) or not definition:
            errors.append(f"{name}: {path} required field {field!r} has no schema")
        elif not _typed(definition):
            errors.append(f"{name}: {path} required field {field!r} has no type or reference")
    for field, definition in properties.items():
        if not isinstance(definition, dict):
            continue
        errors.extend(_record_errors(definition, name, f"{path}{field}"))
    defs = schema.get("$defs")
    if isinstance(defs, dict):
        for field, definition in defs.items():
            if not isinstance(definition, dict):
                errors.append(f"{name}: $defs.{field} is not a schema")
                continue
            errors.extend(_record_errors(definition, name, f"$defs.{field}"))
    return errors


def schema_depth_errors(schema: dict[str, Any], name: str) -> tuple[str, ...]:
    if "$ref" in schema:
        return ()
    errors: list[str] = []
    if schema.get("type") != "object":
        errors.append(f"{name}: root must be an object")
    errors.extend(_object_errors(schema, name, "/"))
    return tuple(errors)


def audit_schema_directory(root: Path) -> dict[str, tuple[str, ...]]:
    failures: dict[str, tuple[str, ...]] = {}
    for path in sorted(root.glob("*.schema.json")):
        errors = schema_depth_errors(json.loads(path.read_text()), path.name)
        if errors:
            failures[path.name] = errors
    return failures


def main() -> int:
    root = Path(__file__).resolve().parents[1] / "schemas" / "v2"
    failures = audit_schema_directory(root)
    if failures:
        schema_count = len(tuple(root.glob("*.schema.json")))
        print(f"P8.C1 OPEN: {len(failures)} of {schema_count} schemas fail depth gate")
        for errors in failures.values():
            for error in errors:
                print(error)
        return 1
    print("P8.C1 schema depth gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
