from pathlib import Path

from scripts.audit_v2_validator_parity import build_report, load_matrix


def test_every_validator_rule_has_three_platform_statuses() -> None:
    rows, errors = load_matrix()
    assert errors == ()
    assert len(rows) == 70
    assert all(set(row["platforms"]) == {"python", "kotlin", "swift"} for row in rows)


def test_initial_archive_contracts_have_reviewed_three_platform_evidence() -> None:
    rows, _ = load_matrix()
    by_id = {row["id"]: row for row in rows}
    for rule_id in ("VAL-ZIP-CONTAINER", "VAL-ROOT-MANIFEST"):
        assert all(
            record["status"] == "complete" and record["evidence"]
            for record in by_id[rule_id]["platforms"].values()
        )


def test_generated_validator_parity_report_is_current() -> None:
    assert Path("docs/validator-parity.generated.md").read_text() == build_report()
