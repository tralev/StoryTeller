"""P8.C1 closure gate for shallow or open-ended v2 JSON schemas."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def schema_depth_errors(schema: dict[str, Any], name: str) -> tuple[str, ...]:
    errors: list[str] = []
    if schema.get("type") != "object":
        errors.append(f"{name}: root must be an object")
    if schema.get("additionalProperties") is not False:
        errors.append(f"{name}: root must set additionalProperties=false")
    properties = schema.get("properties")
    if not isinstance(properties, dict) or not properties:
        errors.append(f"{name}: root properties are missing")
        properties = {}
    required = schema.get("required")
    if not isinstance(required, list) or not required:
        errors.append(f"{name}: required fields are missing")
        required = []
    for field in required:
        definition = properties.get(field)
        if not isinstance(definition, dict) or not definition:
            errors.append(f"{name}: required field {field!r} has no schema")
        elif not any(key in definition for key in
                     ("type", "$ref", "const", "enum", "oneOf", "anyOf", "allOf")):
            errors.append(f"{name}: required field {field!r} has no type or reference")
    for field, definition in properties.items():
        if not isinstance(definition, dict) or "$ref" in definition:
            continue
        value_type = definition.get("type")
        if value_type == "array" and not isinstance(definition.get("items"), dict):
            errors.append(f"{name}: array field {field!r} has no item schema")
        if value_type == "object":
            child_properties = definition.get("properties")
            keyed_values = definition.get("additionalProperties")
            if keyed_values is not False and not isinstance(keyed_values, dict):
                errors.append(f"{name}: object field {field!r} is open-ended")
            if not isinstance(child_properties, dict) and not isinstance(keyed_values, dict):
                errors.append(f"{name}: object field {field!r} has no value schema")
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
        print(
            f"P8.C1 OPEN: {len(failures)} of {schema_count} schemas fail depth gate"
        )
        for errors in failures.values():
            for error in errors:
                print(error)
        return 1
    print("P8.C1 schema depth gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
