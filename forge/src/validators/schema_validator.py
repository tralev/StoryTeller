"""Schema Validator — validates generated JSON against JSON Schema contracts.

Used at each pipeline stage: after generation and after normalizer.
Schema violations become structured feedback for LLM retry.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft7Validator


@dataclass
class SchemaError:
    """A single validation error with path and message."""

    path: str
    message: str
    schema_path: str = ""


@dataclass
class SchemaResult:
    """Result of validating a JSON document against its schema."""

    schema_name: str
    is_valid: bool
    errors: list[SchemaError] = field(default_factory=list)

    def format_for_retry(self) -> str:
        """Format errors as human-readable feedback for LLM retry prompts."""
        if self.is_valid:
            return f"[{self.schema_name}] Valid. No issues."
        lines = [f"[{self.schema_name}] {len(self.errors)} issue(s) found:"]
        for e in self.errors:
            loc = f" at {e.path}" if e.path else ""
            lines.append(f"  -{loc}: {e.message}")
        return "\n".join(lines)


class SchemaValidator:
    """Loads JSON Schema files and validates generated artifacts against them.

    Usage:
        validator = SchemaValidator("docs/schemas")
        result = validator.validate(data, "bible")
        if not result.is_valid:
            feedback = result.format_for_retry()  # inject into LLM prompt
    """

    def __init__(self, schemas_dir: str):
        self._schemas: dict[str, dict[str, Any]] = {}
        self._validators: dict[str, Draft7Validator] = {}
        self._load_schemas(schemas_dir)

    def _load_schemas(self, schemas_dir: str) -> None:
        """Load all .schema.json files from the schemas directory."""
        for fname in sorted(os.listdir(schemas_dir)):
            if not fname.endswith(".schema.json"):
                continue
            name = fname.replace(".schema.json", "")
            path = os.path.join(schemas_dir, fname)
            with open(path) as f:
                schema = json.load(f)
            self._schemas[name] = schema
            self._validators[name] = Draft7Validator(schema)

    @property
    def available_schemas(self) -> list[str]:
        return sorted(self._schemas.keys())

    def validate(self, data: dict[str, Any], schema_name: str) -> SchemaResult:
        """Validate data against the named JSON Schema.

        Args:
            data: The JSON dict to validate.
            schema_name: e.g. "bible", "story", "graph", "gm_index", "style_bible", "manifest"

        Returns:
            SchemaResult with .is_valid and .errors.
        """
        if schema_name not in self._validators:
            return SchemaResult(
                schema_name=schema_name,
                is_valid=False,
                errors=[SchemaError(path="", message=f"Unknown schema: {schema_name}")],
            )

        validator = self._validators[schema_name]
        raw_errors = list(validator.iter_errors(data))

        errors = [
            SchemaError(
                path=_format_path(e.absolute_path),
                message=e.message,
                schema_path=" → ".join(str(p) for p in e.absolute_schema_path) if e.absolute_schema_path else "",
            )
            for e in raw_errors
        ]

        return SchemaResult(
            schema_name=schema_name,
            is_valid=len(errors) == 0,
            errors=errors,
        )

    # Convenience methods
    def validate_bible(self, data: dict[str, Any]) -> SchemaResult:
        return self.validate(data, "bible")

    def validate_story(self, data: dict[str, Any]) -> SchemaResult:
        return self.validate(data, "story")

    def validate_graph(self, data: dict[str, Any]) -> SchemaResult:
        return self.validate(data, "graph")

    def validate_gm_index(self, data: dict[str, Any]) -> SchemaResult:
        return self.validate(data, "gm_index")

    def validate_style_bible(self, data: dict[str, Any]) -> SchemaResult:
        return self.validate(data, "style_bible")

    def validate_manifest(self, data: dict[str, Any]) -> SchemaResult:
        return self.validate(data, "manifest")


def _format_path(absolute_path: list[Any]) -> str:
    """Convert jsonschema absolute_path list to a readable dot-path."""
    parts: list[str] = []
    for p in absolute_path:
        if isinstance(p, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{p}]"
            else:
                parts.append(f"[{p}]")
        else:
            parts.append(str(p))
    return " → ".join(parts) if parts else ""
