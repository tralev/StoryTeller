import zipfile

from src.storage.package_v2 import validate_v2_package


def test_path_traversal_is_rejected(tmp_path) -> None:
    package = tmp_path / "unsafe.story"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("../manifest.json", b"{}")
    result = validate_v2_package(package)
    assert not result.accepted
    assert result.issues[0].code == "PACKAGE_UNSAFE_PATH"


def test_duplicate_path_is_rejected(tmp_path) -> None:
    package = tmp_path / "duplicate.story"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("manifest.json", b"{}")
        archive.writestr("manifest.json", b"{}")
    assert validate_v2_package(package).issues[0].code == "PACKAGE_DUPLICATE_PATH"
