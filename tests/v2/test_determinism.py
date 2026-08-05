from scripts.generate_v2_fixtures import build_complete, generate_schemas
from src.storage.content_hash import compute_zip_content_hash


def test_archive_and_content_are_deterministic_across_directories(tmp_path) -> None:
    generate_schemas()
    first, second = tmp_path / "a.story", tmp_path / "other/b.story"
    build_complete(first); second.parent.mkdir(); build_complete(second)
    assert first.read_bytes() == second.read_bytes()
    assert compute_zip_content_hash(first) == compute_zip_content_hash(second)
