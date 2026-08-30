import json
from pathlib import Path

from scripts.audit_v2_schema_contract import _integer_bound_errors, audit_contract_rules


def test_independent_frozen_prose_rules_match_schemas() -> None:
    assert audit_contract_rules() == ()


def test_contract_audit_detects_schema_drift(tmp_path: Path) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()
    schema = json.loads(Path("schemas/v2/manifest.schema.json").read_text())
    schema["properties"]["package_version"]["const"] = 3
    (schema_root / "manifest.schema.json").write_text(json.dumps(schema))
    rules = {"rules": [{
        "id": "PKG-VERSION",
        "source": "package-v2.md#media-type-and-container",
        "schema": "manifest.schema.json",
        "pointer": "/properties/package_version/const",
        "expected": 2,
    }]}
    rules_path = tmp_path / "rules.json"
    rules_path.write_text(json.dumps(rules))

    errors = audit_contract_rules(rules_path, schema_root)

    assert len(errors) == 1
    assert "PKG-VERSION" in errors[0]
    assert "found 3" in errors[0]


def test_integer_contract_rejects_missing_or_loose_bounds() -> None:
    assert _integer_bound_errors(
        {"type": "integer", "minimum": -9007199254740992},
        "/value",
        -9007199254740991,
        9007199254740991,
    ) == [
        "/value: integer minimum is not bounded at -9007199254740991",
        "/value: integer maximum is not bounded at 9007199254740991",
    ]


def test_non_schema_rules_are_explicitly_owned_by_validators() -> None:
    inventory = json.loads(Path("docs/schema-contract-rules.json").read_text())
    rules = inventory["validator_rules"]
    assert {rule["id"] for rule in rules} == {
        "VAL-ARTIFACT-DEPENDENCY-DAG",
        "VAL-ARTIFACT-FILE-BIJECTION",
        "VAL-ARTIFACT-JCS-DERIVATION",
        "VAL-ACCEPTANCE-ORDER",
        "VAL-CANONICAL-ARRAY-ORDER",
        "VAL-CANONICAL-JSON-PROFILE",
        "VAL-CHUNK-BOUNDARY-SHAPE",
        "VAL-CLIMATE-SEASON-LAYERS",
        "VAL-CONTENT-HASH-DERIVATION",
        "VAL-EARLIER-CAUSES",
        "VAL-EVENT-ORDER",
        "VAL-FEATURE-ORDER",
        "VAL-INTERNAL-FILE-HASHES",
        "VAL-MEDIA-COVERAGE",
        "VAL-MEDIA-MANDATORY",
        "VAL-MIDI-PROFILE",
        "VAL-HISTORY-REPLAY-HASH",
        "VAL-HYDROLOGY-CATALOG",
        "VAL-OPTIONAL-FEATURE-SEMANTICS",
        "VAL-PNG-PROFILE",
        "VAL-SCORE-REFERENCES",
        "VAL-SNAPSHOT-CADENCE",
        "VAL-SITE-REFERENCES",
        "VAL-SOURCE-COVERAGE-BIJECTION",
        "VAL-SCORE-BEAT-ARITHMETIC",
        "VAL-SCORE-EVENT-ORDER",
        "VAL-SCORE-EVENT-SHAPE",
        "VAL-SCORE-MARKER-ORDER",
        "VAL-SCORE-MIDI-HASH",
        "VAL-SCORE-TRACK-PROGRAM",
        "VAL-CIVILIZATION-REFERENCES",
        "VAL-DEPOSIT-GEOLOGY",
        "VAL-REGION-PARTITION",
        "VAL-RESOURCE-CATALOG",
        "VAL-REFERENCE-RESOLUTION",
        "VAL-ROUTE-TOPOLOGY",
        "VAL-BINARY-LAYER-ENCODING",
        "VAL-BIBLE-AUTHORITY-REFERENCES",
        "VAL-GM-COVERAGE",
        "VAL-GM-BASE-SCORING",
        "VAL-GM-CONTEXT-BUDGET",
        "VAL-GM-CONTEXT-SCORING",
        "VAL-GM-DEFAULTS",
        "VAL-GM-IDENTITY-INPUTS",
        "VAL-GM-NATIVE-PARITY",
        "VAL-GM-NORMALIZATION",
        "VAL-GM-RANK-ORDER",
        "VAL-GM-RECENCY-SCORING",
        "VAL-GM-REVEAL-GATE",
        "VAL-GM-SPOILER-ISOLATION",
        "VAL-GRAPH-SEMANTICS",
        "VAL-RECONCILIATION-INPUTS",
        "VAL-STORY-GRAPH-REFERENCES",
        "VAL-PROHIBITED-PACKAGE-CONTENT",
        "VAL-UNKNOWN-REQUIRED-FEATURE",
        "VAL-UNSUPPORTED-VERSION-GUIDANCE",
        "VAL-NO-SILENT-COERCION",
        "VAL-TRUSTED-SCHEMA-PARITY",
        "VAL-JSON-DEPTH-LIMIT",
        "VAL-ZIP-ENTRY-LIMIT",
        "VAL-ZIP-MEMBER-SIZE-LIMIT",
        "VAL-ZIP-TOTAL-SIZE-LIMIT",
        "VAL-ZIP-COMPRESSION-RATIO",
        "VAL-EXTRACTION-FREE-SPACE",
        "VAL-ZIP-LINK-PROHIBITION",
        "VAL-ZIP-METADATA-PROFILE",
        "VAL-ZIP-PATH-PROFILE",
        "VAL-ZIP-CONTAINER",
        "VAL-ROOT-MANIFEST",
        "VAL-ZIP-ONLY-COMPRESSION",
    }
    assert all("#" in rule["source"] and rule["reason"] for rule in rules)
