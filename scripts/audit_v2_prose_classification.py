"""Freeze ownership classification for every line in normative contract sections."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLASSIFICATION = ROOT / "docs" / "schema-contract-classification.json"
REPORT = ROOT / "docs" / "schema-contract-classification.generated.md"
OWNERS = {"schema", "validator", "mixed", "operational", "informational"}


def section_payloads(path: Path) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    in_code = False
    for raw in path.read_text().splitlines():
        if raw.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if raw.startswith("## ") and not raw.startswith("### "):
            current = raw[3:].strip()
            sections.setdefault(current, [])
            continue
        if raw.startswith("#"):
            continue
        if current is not None and raw.strip():
            sections[current].append(raw.strip())
    return {heading: "\n".join(lines) for heading, lines in sections.items()}


def payload_sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_classification(
    classification_path: Path = CLASSIFICATION,
    root: Path = ROOT,
) -> tuple[str, ...]:
    catalog = json.loads(classification_path.read_text())
    rules_path = root / "docs/schema-contract-rules.json"
    contract_inventory = json.loads(rules_path.read_text()) if rules_path.exists() else {}
    rule_owners = {
        rule["id"]: "schema" for rule in contract_inventory.get("rules", [])
    }
    rule_owners.update(
        {rule["id"]: "validator" for rule in contract_inventory.get("validator_rules", [])}
    )
    errors: list[str] = []
    require_all = set(catalog.get("require_all_sections", []))
    for relative, expected_sections in catalog.get("sources", {}).items():
        actual_sections = section_payloads(root / relative)
        if relative in require_all:
            unclassified = sorted(set(actual_sections) - set(expected_sections))
            missing = sorted(set(expected_sections) - set(actual_sections))
            errors.extend(
                f"{relative}#{heading}: section has no ownership classification"
                for heading in unclassified
            )
            errors.extend(
                f"{relative}#{heading}: classified section is missing"
                for heading in missing
            )
        for heading, record in expected_sections.items():
            owner = record.get("owner")
            if owner not in OWNERS:
                errors.append(f"{relative}#{heading}: invalid owner {owner!r}")
            if heading not in actual_sections:
                errors.append(f"{relative}#{heading}: section is missing")
                continue
            actual_hash = payload_sha256(actual_sections[heading])
            if record.get("sha256") != actual_hash:
                errors.append(
                    f"{relative}#{heading}: content changed; expected {record.get('sha256')!r}, "
                    f"found {actual_hash!r}"
                )
            clauses = record.get("clauses")
            if clauses is None:
                continue
            lines = actual_sections[heading].splitlines()
            covered: list[int] = []
            clause_ids: set[str] = set()
            for clause in clauses:
                clause_id = clause.get("id")
                owner = clause.get("owner")
                start = clause.get("start_line")
                end = clause.get("end_line")
                links = clause.get("rule_ids", [])
                if not isinstance(clause_id, str) or not clause_id or clause_id in clause_ids:
                    errors.append(f"{relative}#{heading}: invalid clause id {clause_id!r}")
                else:
                    clause_ids.add(clause_id)
                if owner not in OWNERS - {"mixed"}:
                    errors.append(f"{relative}#{heading}/{clause_id}: invalid owner {owner!r}")
                if not isinstance(start, int) or not isinstance(end, int) or start > end:
                    errors.append(f"{relative}#{heading}/{clause_id}: invalid line range")
                    continue
                covered.extend(range(start, end + 1))
                if owner in {"schema", "validator"} and not links:
                    errors.append(f"{relative}#{heading}/{clause_id}: missing executable rule")
                for rule_id in links:
                    if rule_owners.get(rule_id) != owner:
                        errors.append(
                            f"{relative}#{heading}/{clause_id}: {rule_id!r} is not a {owner} rule"
                        )
            expected_lines = list(range(1, len(lines) + 1))
            if sorted(covered) != expected_lines:
                errors.append(
                    f"{relative}#{heading}: clause ranges must cover each "
                    "non-code line exactly once"
                )
    return tuple(errors)


def build_report(classification_path: Path = CLASSIFICATION, root: Path = ROOT) -> str:
    catalog: dict[str, Any] = json.loads(classification_path.read_text())
    rows = [
        "# Schema Contract Classification",
        "",
        "Generated by `scripts/audit_v2_prose_classification.py`.",
        "",
        "| Source section | Owner | Non-code lines | SHA-256 |",
        "|---|---|---:|---|",
    ]
    for relative, expected_sections in catalog["sources"].items():
        actual_sections = section_payloads(root / relative)
        for heading, record in expected_sections.items():
            payload = actual_sections.get(heading, "")
            rows.append(
                f"| `{relative}#{heading}` | {record['owner']} | "
                f"{len(payload.splitlines())} | `{payload_sha256(payload)}` |"
            )
            for clause in record.get("clauses", []):
                links = ", ".join(clause.get("rule_ids", [])) or "—"
                rows.append(
                    f"| ↳ `{clause['id']}` (lines {clause['start_line']}–{clause['end_line']}; "
                    f"rules: {links}) | {clause['owner']} | — | — |"
                )
    rows.extend(["", "Every listed line is frozen to an explicit enforcement owner.", ""])
    return "\n".join(rows)


def main() -> int:
    if "--hashes" in sys.argv:
        catalog = json.loads(CLASSIFICATION.read_text())
        for relative, expected_sections in catalog["sources"].items():
            actual = section_payloads(ROOT / relative)
            for heading in expected_sections:
                print(f"{relative}\t{heading}\t{payload_sha256(actual.get(heading, ''))}")
        return 0
    errors = audit_classification()
    if errors:
        print(f"P8.C1 OPEN: {len(errors)} prose-classification mismatches")
        for error in errors:
            print(error)
        return 1
    REPORT.write_text(build_report())
    print("P8.C1 prose classification gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
