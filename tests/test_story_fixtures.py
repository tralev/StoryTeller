"""Frozen v2 package fixtures and migrated legacy-acceptance guarantees."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

from src.storage.package_v2 import validate_v2_package

FIXTURES = Path(__file__).parent / "fixtures" / "v2"


def _catalog() -> dict[str, dict[str, object]]:
    raw = json.loads((FIXTURES / "catalog.json").read_text())
    return {scenario["id"]: scenario for scenario in raw["scenarios"]}


def test_complete_v2_fixture_is_accepted_and_immutable() -> None:
    package = FIXTURES / "complete.story"
    result = validate_v2_package(package)
    assert result.accepted, result.issues

    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert "manifest.json" in names
        assert "narrative/bible.json" in names
        assert "narrative/story.json" in names
        assert "narrative/graph.json" in names
        assert "narrative/gm_index.json" in names
        assert not any(name == "save" or name.startswith("save/") for name in names)
        assert not any(name.startswith("content/") for name in names)
        for name in names:
            if name.endswith(".json"):
                assert json.loads(archive.read(name)) is not None


def test_legacy_acceptance_guarantees_have_v2_scenarios() -> None:
    scenarios = _catalog()
    expected = {
        "unsupported-v1": "PACKAGE_UNSUPPORTED_VERSION",
        "manifest-type-coercion": "PACKAGE_TYPE_COERCION",
        "corrupt": "PACKAGE_HASH_MISMATCH",
        "dependency-broken": "PACKAGE_PROVENANCE_BROKEN",
        "incomplete-world": "PACKAGE_MISSING_ARTIFACT",
        "graph-semantics": "PACKAGE_GRAPH_SEMANTICS",
        "story-graph-references": "PACKAGE_STORY_GRAPH_REFERENCES",
        "media-coverage": "PACKAGE_MEDIA_COVERAGE",
        "png-profile": "PACKAGE_PNG_PROFILE",
        "midi-profile": "PACKAGE_MIDI_PROFILE",
    }
    for scenario_id, issue_code in expected.items():
        scenario = scenarios[scenario_id]
        assert scenario["accepted"] is False
        assert scenario["issue_code"] == issue_code
        result = validate_v2_package(FIXTURES / str(scenario["path"]))
        assert not result.accepted
        assert result.issues[0].code == issue_code


def test_valid_v2_fixtures_share_cross_platform_contract() -> None:
    for scenario_id in ("complete", "small"):
        scenario = _catalog()[scenario_id]
        package = FIXTURES / str(scenario["path"])
        assert zipfile.is_zipfile(package)
        assert validate_v2_package(package).accepted
