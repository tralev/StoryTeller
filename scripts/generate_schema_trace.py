"""Generate the schema-trace matrix: docs/schema-trace.generated.md

Maps every normative rule in each v2 schema to validator functions,
valid fixture, and invalid fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "schemas" / "v2"
FIXTURES_DIR = ROOT / "tests" / "fixtures" / "v2" / "schema_fixtures"
TRACE_PATH = ROOT / "docs" / "schema-trace.generated.md"


def build_trace() -> str:
    lines: list[str] = []
    lines.append("# Schema Trace Matrix")
    lines.append("")
    lines.append("> Generated from `scripts/generate_schema_trace.py`.")
    lines.append("> Fixture counts prove generator coverage only; they are not P8.C1 closure evidence.")
    lines.append("> Re-run after schema changes: `python scripts/generate_schema_trace.py`")
    lines.append("")

    # Load fixture catalog
    catalog_path = ROOT / "tests" / "fixtures" / "v2" / "schema_fixtures.json"
    catalog: dict = {"scenarios": []}
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text())
    scenarios_by_schema: dict[str, list[dict]] = {}
    for s in catalog.get("scenarios", []):
        scenarios_by_schema.setdefault(s["schema"], []).append(s)

    schemas = sorted(SCHEMAS_DIR.glob("*.schema.json"))

    for schema_path in schemas:
        name = schema_path.stem.replace(".schema", "")
        schema = json.loads(schema_path.read_text())
        props = schema.get("properties", {})
        required = schema.get("required", [])

        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"| Rule | Type | Validator | Valid Fixture | Invalid Fixture |")
        lines.append(f"|---|---|---|---|---|")

        scenarios = scenarios_by_schema.get(name, [])
        valid_scenario = next((s for s in scenarios if s.get("valid")), None)
        invalid_by_rule: dict[str, dict] = {}
        for s in scenarios:
            if not s.get("valid") and s.get("rule"):
                invalid_by_rule[s["rule"]] = s

        row_count = 0

        # Type constraint
        if "type" in schema:
            lines.append(
                f"| Root type: `{schema['type']}` | type | metaschema |"
                f" {_fixture_link(name, valid_scenario)} | — |"
            )
            row_count += 1

        # additionalProperties
        if schema.get("additionalProperties") is False:
            inv = invalid_by_rule.get("extra-property")
            lines.append(
                f"| `additionalProperties: false` | constraint | jsonschema |"
                f" {_fixture_link(name, valid_scenario)} |"
                f" {_fixture_link(name, inv)} |"
            )
            row_count += 1

        # Required fields
        for field in required:
            prop = props.get(field, {})
            ptype = prop.get("type", "?")
            pat = prop.get("pattern", "")
            mn = prop.get("minimum", "")
            constraints = f"type={ptype}"
            if pat:
                constraints += f", pattern"
            if mn != "":
                constraints += f", min={mn}"

            inv_missing = invalid_by_rule.get(f"missing-{field}")
            inv_wrong = invalid_by_rule.get(f"wrong-type-{field}")
            inv_pattern = invalid_by_rule.get(f"pattern-{field}")
            inv_below = invalid_by_rule.get(f"below-min-{field}")

            # Required row
            lines.append(
                f"| `{field}` ({constraints}) | required | jsonschema |"
                f" {_fixture_link(name, valid_scenario)} |"
                f" {_fixture_link(name, inv_missing)} |"
            )
            row_count += 1

            # Type row if we have a wrong-type fixture
            if inv_wrong:
                lines.append(
                    f"| `{field}` type enforcement | type | jsonschema |"
                    f" — |"
                    f" {_fixture_link(name, inv_wrong)} |"
                )
                row_count += 1

            # Pattern row
            if inv_pattern:
                lines.append(
                    f"| `{field}` pattern `{pat[:30]}...` | pattern | jsonschema |"
                    f" — |"
                    f" {_fixture_link(name, inv_pattern)} |"
                )
                row_count += 1

            # Range row
            if inv_below:
                lines.append(
                    f"| `{field}` minimum={mn} | range | jsonschema |"
                    f" — |"
                    f" {_fixture_link(name, inv_below)} |"
                )
                row_count += 1

        lines.append("")
        lines.append(f"_{row_count} traceable rules_")
        lines.append("")

    # Add summary
    lines.insert(3, f"**Schemas:** {len(schemas)} | **Total scenarios:** {len(catalog.get('scenarios',[]))}")
    lines.insert(4, "")

    return "\n".join(lines)


def _fixture_link(schema_name: str, scenario: dict | None) -> str:
    if scenario is None:
        return "—"
    path = scenario.get("path", "")
    return f"[{scenario['id']}]({path})"


def main() -> None:
    trace = build_trace()
    TRACE_PATH.write_text(trace)
    print(f"Trace matrix written to {TRACE_PATH}")


if __name__ == "__main__":
    main()
