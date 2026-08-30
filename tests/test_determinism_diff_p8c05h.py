"""P8.C05H determinism diff reporter tests — WG-INTEGRATION-014."""

from __future__ import annotations

import json
from pathlib import Path

from src.worldgen.determinism_diff import (
    DeterminismDifference,
    compare_artifact_repositories,
    compare_canonical_bytes,
    first_artifact_repository_difference,
    first_canonical_difference,
)


def test_typed_first_difference_contains_complete_diagnostics() -> None:
    expected = b'{"producer":{"fingerprint":"expected"},"value":1}'
    actual = b'{"producer":{"fingerprint":"actual"},"value":1}'
    result = first_canonical_difference(expected, actual, "world/value.json")
    assert result is not None
    assert result.artifact_path == "world/value.json"
    assert result.json_pointer == "/producer/fingerprint"
    assert result.byte_offset >= 0
    assert len(result.expected_sha256) == len(result.actual_sha256) == 64
    assert result.expected_producer_fingerprint == "expected"
    assert result.actual_producer_fingerprint == "actual"


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
        assert "sha256=" in result

    def test_typed_json_report_has_pointer_offset_digests_and_producers(self) -> None:
        expected = json.dumps(
            {
                "producer": {"fingerprint": "a" * 64},
                "value": {"x": 1},
            },
            sort_keys=True,
        ).encode()
        actual = json.dumps(
            {
                "producer": {"fingerprint": "b" * 64},
                "value": {"x": 2},
            },
            sort_keys=True,
        ).encode()
        result = first_canonical_difference(expected, actual, "world/value.json")
        assert isinstance(result, DeterminismDifference)
        assert result.artifact_path == "world/value.json"
        assert result.json_pointer == "/producer/fingerprint"
        assert result.byte_offset >= 0
        assert len(result.expected_sha256) == len(result.actual_sha256) == 64
        assert result.expected_producer_fingerprint == "a" * 64
        assert result.actual_producer_fingerprint == "b" * 64

    def test_missing_key_is_distinct_from_explicit_null(self) -> None:
        result = first_canonical_difference(b'{"value":null}', b"{}")
        assert result is not None
        assert result.json_pointer == "/value"
        assert result.expected_value is None
        assert result.actual_value == "<missing>"

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

    def test_nested_binary_first_difference_is_typed(self, tmp_path: Path) -> None:
        a_dir, b_dir = tmp_path / "a", tmp_path / "b"
        (a_dir / "chunks").mkdir(parents=True)
        (b_dir / "chunks").mkdir(parents=True)
        (a_dir / "chunks/first.bin").write_bytes(b"abc123")
        (b_dir / "chunks/first.bin").write_bytes(b"abc923")
        result = first_artifact_repository_difference(a_dir, b_dir)
        assert result is not None
        assert result.artifact_path == "chunks/first.bin"
        assert result.json_pointer is None
        assert result.byte_offset == 3
