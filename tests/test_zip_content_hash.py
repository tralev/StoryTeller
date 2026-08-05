"""Canonical package identity hashes files inside ZIPs, not archive bytes."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from src.storage.content_hash import compute_zip_content_hash


def _write(path: Path, compression: int, comment: bytes) -> None:
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        archive.comment = comment
        archive.writestr("content/story.json", b'{"title":"same"}')
        archive.writestr("content/image.png", b"same-image")
        archive.writestr("manifest.json", b'{"operational":"different"}')
        archive.writestr("save/state.json", b'{"visited":["node_1"]}')


def test_recompression_and_zip_metadata_do_not_change_content_hash(tmp_path: Path) -> None:
    stored = tmp_path / "stored.story"
    deflated = tmp_path / "deflated.story"
    _write(stored, zipfile.ZIP_STORED, b"first transport")
    _write(deflated, zipfile.ZIP_DEFLATED, b"second transport")

    assert stored.read_bytes() != deflated.read_bytes()
    assert compute_zip_content_hash(stored) == compute_zip_content_hash(deflated)


def test_duplicate_internal_paths_are_not_hashable(tmp_path: Path) -> None:
    package = tmp_path / "duplicate.story"
    with pytest.warns(UserWarning):
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("content/story.json", b"first")
            archive.writestr("content/story.json", b"second")

    with pytest.raises(ValueError, match="duplicate ZIP entry"):
        compute_zip_content_hash(package)
