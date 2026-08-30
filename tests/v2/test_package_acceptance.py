import json
import stat
import zipfile

from src.storage.package_v2 import has_extraction_space, validate_v2_package


def test_complete_is_accepted() -> None:
    assert validate_v2_package("tests/fixtures/v2/complete.story").accepted


def test_v1_is_rejected_with_stable_code(tmp_path) -> None:
    package = tmp_path / "v1.story"
    with zipfile.ZipFile(package, "w") as archive:
        info = zipfile.ZipInfo("manifest.json", (1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, json.dumps({"package_version": 1}))
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


def test_extraction_space_exact_boundary() -> None:
    result = validate_v2_package("tests/fixtures/v2/complete.story")
    assert result.required_bytes > 0
    assert has_extraction_space(result.required_bytes, result.required_bytes)
    assert not has_extraction_space(result.required_bytes, result.required_bytes - 1)
