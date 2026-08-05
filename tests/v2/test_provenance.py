import json
import zipfile

from src.storage.package_v2 import ID_RE, content_hash, validate_v2_package


def test_complete_fixture_has_full_provenance() -> None:
    package = "tests/fixtures/v2/complete.story"
    assert validate_v2_package(package).accepted
    with zipfile.ZipFile(package) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert manifest["content_hash"] == content_hash(manifest["artifacts"])
    assert all(ID_RE.fullmatch(item["artifact_id"]) for item in manifest["artifacts"])
    assert all(len(item["sha256"]) == 64 for item in manifest["artifacts"])
