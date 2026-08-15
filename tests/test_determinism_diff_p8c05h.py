"""P8.C05H determinism diff reporter tests — WG-INTEGRATION-014."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.worldgen.determinism_diff import (
    compare_artifact_repositories,
    compare_canonical_bytes,
    _json_pointer,
    _walk_and_compare,
)


class TestDeterminismDiff:
    def test_identical_bytes_return_empty(self) -> None:
        data = b'{"a":1,"b":2}'
        result = compare_canonical_bytes(data, data)
        assert result == ""

    def test_different_values_report_pointer(self) -> None:
        a = json.dumps({"x": 1, "y": 2}, sort_keys=True).encode()
        b = json.dumps({"x": 1, "y": 3}, sort_keys=True).encode()
        result = compare_canonical_bytes(a, b)
        assert "/y" in result
        assert "2" in result or "3" in result

    def test_missing_key_detected(self) -> None:
        a = json.dumps({"a": 1, "b": 2}, sort_keys=True).encode()
        b = json.dumps({"a": 1}, sort_keys=True).encode()
        result = compare_canonical_bytes(a, b)
        assert "b" in result

    def test_different_types_detected(self) -> None:
        a = json.dumps({"x": [1, 2, 3]}, sort_keys=True).encode()
        b = json.dumps({"x": [1, "two", 3]}, sort_keys=True).encode()
        result = compare_canonical_bytes(a, b)
        assert result != ""

    def test_label_prefixed_to_report(self) -> None:
        a = json.dumps({"x": 1}, sort_keys=True).encode()
        b = json.dumps({"x": 2}, sort_keys=True).encode()
        result = compare_canonical_bytes(a, b, label="artifact_42.json")
        assert result.startswith("[artifact_42.json]")

    def test_non_json_falls_back_to_byte_offset(self) -> None:
        a = b"abcdef"
        b = b"abcxyz"
        result = compare_canonical_bytes(a, b)
        assert "byte 3" in result

    def test_artifact_repo_with_same_contents_is_empty(self, tmp_path: Path) -> None:
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        (a_dir / "terrain.json").write_text('{"elevation": 100}')
        (b_dir / "terrain.json").write_text('{"elevation": 100}')
        result = compare_artifact_repositories(a_dir, b_dir)
        assert result == ""

    def test_artifact_repo_different_file_detected(self, tmp_path: Path) -> None:
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        (a_dir / "terrain.json").write_text('{"elevation": 100}')
        (b_dir / "terrain.json").write_text('{"elevation": 200}')
        result = compare_artifact_repositories(a_dir, b_dir)
        assert result != ""
        assert "elevation" in result

    def test_missing_files_detected(self, tmp_path: Path) -> None:
        a_dir = tmp_path / "a"
        b_dir = tmp_path / "b"
        a_dir.mkdir()
        b_dir.mkdir()
        (a_dir / "extra.json").write_text("{}")
        result = compare_artifact_repositories(a_dir, b_dir)
        assert "extra.json" in result
