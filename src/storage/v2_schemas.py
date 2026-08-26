"""Load the frozen v2 schema bundle and resolve ``$ref`` targets."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "v2"
DEFS_NAME = "defs.schema.json"


def load_v2_schemas(root: Path | None = None) -> dict[str, dict[str, Any]]:
    base = root or SCHEMA_ROOT
    schemas: dict[str, dict[str, Any]] = {}
    for path in sorted(base.glob("*.schema.json")):
        schemas[path.name] = json.loads(path.read_bytes())
    return schemas


def v2_schema_registry(root: Path | None = None) -> Registry[Any]:
    resources: list[tuple[str, Resource[Any]]] = []
    for name, schema in load_v2_schemas(root).items():
        identifier = str(schema.get("$id") or name)
        resources.append((identifier, Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def draft202012_validator(
    schema: dict[str, Any], *, root: Path | None = None,
) -> Draft202012Validator:
    return Draft202012Validator(schema, registry=v2_schema_registry(root))


def resolve_ref(
    ref: str,
    current: dict[str, Any],
    schemas: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Resolve a local or bundle ``$ref`` to a schema object."""
    if ref.startswith("#/$defs/"):
        name = ref.rsplit("/", 1)[-1]
        defs = current.get("$defs")
        if not isinstance(defs, dict) or name not in defs:
            raise KeyError(f"unresolved local $ref: {ref}")
        target = defs[name]
        if not isinstance(target, dict):
            raise KeyError(f"invalid local $ref: {ref}")
        return target
    uri, _, fragment = ref.partition("#")
    filename = uri.rsplit("/", 1)[-1] if uri else ""
    bundle = schemas.get(filename)
    if bundle is None:
        for schema in schemas.values():
            if schema.get("$id") == uri:
                bundle = schema
                break
    if bundle is None:
        raise KeyError(f"unresolved $ref: {ref}")
    if not fragment:
        return bundle
    if not fragment.startswith("/$defs/"):
        raise KeyError(f"unsupported $ref fragment: {ref}")
    name = fragment.rsplit("/", 1)[-1]
    defs = bundle.get("$defs")
    if not isinstance(defs, dict) or name not in defs:
        raise KeyError(f"unresolved $ref: {ref}")
    target = defs[name]
    if not isinstance(target, dict):
        raise KeyError(f"invalid $ref: {ref}")
    return target
