import json
import zipfile

from scripts.generate_v2_fixtures import build_complete, generate_schemas
from src.storage.content_hash import compute_zip_content_hash


def test_archive_and_content_are_deterministic_across_directories(tmp_path) -> None:
    generate_schemas()
    first, second = tmp_path / "a.story", tmp_path / "other/b.story"
    build_complete(first)
    second.parent.mkdir()
    build_complete(second)
    assert first.read_bytes() == second.read_bytes()
    assert compute_zip_content_hash(first) == compute_zip_content_hash(second)
    with zipfile.ZipFile(first) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert compute_zip_content_hash(first) == manifest["content_hash"]


def test_v2_hash_recomputes_member_bytes_instead_of_trusting_manifest(tmp_path) -> None:
    generate_schemas()
    package = tmp_path / "original.story"
    build_complete(package)
    with zipfile.ZipFile(package) as source:
        members = {info.filename: source.read(info) for info in source.infolist()}
    target = next(name for name in members if name != "manifest.json")
    members[target] += b"tampered"
    tampered = tmp_path / "tampered.story"
    with zipfile.ZipFile(tampered, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    assert compute_zip_content_hash(tampered) != compute_zip_content_hash(package)
