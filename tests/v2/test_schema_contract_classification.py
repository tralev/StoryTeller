import json
from pathlib import Path

from scripts.audit_v2_prose_classification import audit_classification, build_report


def test_all_normative_sections_have_frozen_ownership() -> None:
    assert audit_classification() == ()


def test_generated_classification_report_is_current() -> None:
    assert Path("docs/schema-contract-classification.generated.md").read_text() == build_report()


def test_classification_gate_detects_prose_drift(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/contract.md").write_text("# Contract\n\n## Frozen\n\nRule changed.\n")
    catalog = {
        "sources": {
            "docs/contract.md": {
                "Frozen": {"owner": "schema", "sha256": "0" * 64}
            }
        }
    }
    path = tmp_path / "classification.json"
    path.write_text(json.dumps(catalog))

    errors = audit_classification(path, tmp_path)

    assert len(errors) == 1
    assert "content changed" in errors[0]


def test_classification_gate_detects_unclassified_normative_section(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/contract.md").write_text(
        "# Contract\n\n## Frozen\n\nKnown rule.\n\n## New rule\n\nUnowned rule.\n"
    )
    catalog = {
        "require_all_sections": ["docs/contract.md"],
        "sources": {
            "docs/contract.md": {
                "Frozen": {
                    "owner": "schema",
                    "sha256": "0fa924fb6ba56f47193f3f6e70d32093b53bdc20b81f0e283d20bb2792076d82",
                }
            }
        },
    }
    path = tmp_path / "classification.json"
    path.write_text(json.dumps(catalog))

    errors = audit_classification(path, tmp_path)

    assert errors == (
        "docs/contract.md#New rule: section has no ownership classification",
    )


def test_classification_gate_requires_complete_clause_ownership(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/contract.md").write_text("# Contract\n\n## Mixed\n\nFirst.\nSecond.\n")
    (tmp_path / "docs/schema-contract-rules.json").write_text(
        json.dumps({"rules": [], "validator_rules": []})
    )
    catalog = {
        "sources": {
            "docs/contract.md": {
                "Mixed": {
                    "owner": "mixed",
                    "sha256": "a43c1356320ad2f92aba1eb1457227f0012f712dbd7c56c3706f673d30072a79",
                    "clauses": [
                        {
                            "id": "first",
                            "owner": "schema",
                            "start_line": 1,
                            "end_line": 1,
                            "rule_ids": [],
                        }
                    ],
                }
            }
        }
    }
    path = tmp_path / "classification.json"
    path.write_text(json.dumps(catalog))

    errors = audit_classification(path, tmp_path)

    assert any("missing executable rule" in error for error in errors)
    assert any("cover each non-code line exactly once" in error for error in errors)
