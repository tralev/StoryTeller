"""Audit hand-transcribed frozen prose rules against v2 schemas.

Unlike generated fixtures, this inventory is authored from package-v2.md and
api.md. It therefore provides P8.C1 an independent schema-drift oracle.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "docs" / "schema-contract-rules.json"
SCHEMA_ROOT = ROOT / "schemas" / "v2"


def _integer_bound_errors(value: Any, path: str, minimum: int, maximum: int) -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        value_type = value.get("type")
        types = value_type if isinstance(value_type, list) else [value_type]
        if "integer" in types:
            lower = value.get("minimum")
            upper = value.get("maximum")
            if not isinstance(lower, int) or lower < minimum:
                errors.append(f"{path}: integer minimum is not bounded at {minimum}")
            if not isinstance(upper, int) or upper > maximum:
                errors.append(f"{path}: integer maximum is not bounded at {maximum}")
        for key, child in value.items():
            errors.extend(_integer_bound_errors(child, f"{path}/{key}", minimum, maximum))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_integer_bound_errors(child, f"{path}/{index}", minimum, maximum))
    return errors


def resolve_pointer(document: Any, pointer: str) -> Any:
    value = document
    if not pointer.startswith("/"):
        raise ValueError(f"JSON pointer must start with '/': {pointer!r}")
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            value = value[int(token)]
        elif isinstance(value, dict):
            value = value[token]
        else:
            raise KeyError(token)
    return value


def audit_contract_rules(
    rules_path: Path = RULES_PATH, schema_root: Path = SCHEMA_ROOT
) -> tuple[str, ...]:
    inventory = json.loads(rules_path.read_text())
    errors: list[str] = []
    seen: set[str] = set()
    for rule in inventory.get("rules", []):
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id or rule_id in seen:
            errors.append(f"invalid or duplicate rule id: {rule_id!r}")
            continue
        seen.add(rule_id)
        source = rule.get("source")
        if not isinstance(source, str) or "#" not in source:
            errors.append(f"{rule_id}: missing prose source anchor")
        if rule.get("check") == "bounded-integers":
            minimum = rule.get("minimum")
            maximum = rule.get("maximum")
            if not isinstance(minimum, int) or not isinstance(maximum, int):
                errors.append(f"{rule_id}: invalid integer bounds")
                continue
            for schema_path in sorted(schema_root.glob("*.schema.json")):
                schema = json.loads(schema_path.read_text())
                for error in _integer_bound_errors(schema, "", minimum, maximum):
                    errors.append(f"{rule_id}:{schema_path.name}{error}")
            continue
        schema_path = schema_root / str(rule.get("schema", ""))
        try:
            schema = json.loads(schema_path.read_text())
            actual = resolve_pointer(schema, str(rule.get("pointer", "")))
        except (FileNotFoundError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append(f"{rule_id}: unresolved schema rule: {exc}")
            continue
        if actual != rule.get("expected"):
            errors.append(f"{rule_id}: expected {rule.get('expected')!r}, found {actual!r}")
    if not seen:
        errors.append("contract inventory contains no rules")
    return tuple(errors)


def main() -> int:
    errors = audit_contract_rules()
    if errors:
        print(f"P8.C1 OPEN: {len(errors)} frozen prose/schema mismatches")
        for error in errors:
            print(error)
        return 1
    count = len(json.loads(RULES_PATH.read_text())["rules"])
    print(f"P8.C1 prose/schema contract audit passed ({count} independent rules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
