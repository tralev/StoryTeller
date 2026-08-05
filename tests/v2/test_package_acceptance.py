import json
import zipfile

from src.storage.package_v2 import validate_v2_package


def test_complete_is_accepted() -> None:
    assert validate_v2_package("tests/fixtures/v2/complete.story").accepted


def test_v1_is_rejected_with_stable_code(tmp_path) -> None:
    package = tmp_path / "v1.story"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"package_version": 1}))
    result = validate_v2_package(package)
    assert not result.accepted
    assert result.issues[0].code == "PACKAGE_UNSUPPORTED_VERSION"


def test_scenario_catalog_matches_reference_validator() -> None:
    catalog = json.loads(open("tests/fixtures/v2/catalog.json").read())
    for scenario in catalog["scenarios"]:
        result = validate_v2_package("tests/fixtures/v2/" + scenario["path"])
        assert result.accepted is scenario["accepted"]
        if not scenario["accepted"]:
            assert result.issues[0].code == scenario["issue_code"]
