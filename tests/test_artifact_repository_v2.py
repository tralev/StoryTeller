from __future__ import annotations

import pytest

from src.storage.artifact_repository import ArtifactRepository


def test_typed_atomic_round_trip(tmp_path) -> None:
    repository = ArtifactRepository(tmp_path)
    ref = repository.put_json(
        "bible",
        {"name": "world"},
        producer_fingerprint="producer-v1",
    )
    assert ref.artifact_id.startswith("bible_")
    assert repository.exists_verified(ref)
    assert repository.load_verified(ref) == b'{"name":"world"}'


def test_repository_confines_paths(tmp_path) -> None:
    repository = ArtifactRepository(tmp_path)
    with pytest.raises(ValueError, match="unsafe artifact path"):
        repository.put_bytes("images", "../escape.png", b"x")
