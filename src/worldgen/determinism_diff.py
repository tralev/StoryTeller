"""P8.C05H step 6 — Determinism diff reporter.

Given two artifact repositories (or two runs that should be byte-identical),
find the *first* difference and report: artifact ID, JSON pointer path,
and byte offset.

This is a diagnostic tool, not a validator. It is used by hardening
suites to produce actionable failure messages instead of a generic
"hashes differ" assertion.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_MISSING = object()


@dataclass(frozen=True)
class DeterminismDifference:
    """Canonical first difference between two expected-identical outputs."""

    artifact_path: str
    expected_sha256: str
    actual_sha256: str
    byte_offset: int
    json_pointer: str | None = None
    expected_value: Any = None
    actual_value: Any = None
    expected_producer_fingerprint: str | None = None
    actual_producer_fingerprint: str | None = None

    def format(self) -> str:
        location = (
            f"json {self.json_pointer}"
            if self.json_pointer is not None
            else (f"byte {self.byte_offset}")
        )
        values = ""
        if self.json_pointer is not None:
            values = (
                f"; expected={json.dumps(self.expected_value, ensure_ascii=False, default=str)}"
                f" actual={json.dumps(self.actual_value, ensure_ascii=False, default=str)}"
            )
        producers = ""
        if self.expected_producer_fingerprint or self.actual_producer_fingerprint:
            producers = (
                f"; producer={self.expected_producer_fingerprint or '-'}"
                f"/{self.actual_producer_fingerprint or '-'}"
            )
        label = f"[{self.artifact_path}] " if self.artifact_path else ""
        return (
            f"{label}{location}; sha256={self.expected_sha256}/{self.actual_sha256}"
            f"{values}{producers}"
        )


def _json_pointer(path_segments: tuple[str | int, ...]) -> str:
    """RFC 6901 JSON pointer from path segments."""
    parts: list[str] = []
    for seg in path_segments:
        if isinstance(seg, int):
            parts.append(str(seg))
        else:
            parts.append(seg.replace("~", "~0").replace("/", "~1"))
    return "/" + "/".join(parts)


def _walk_and_compare(
    a: Any, b: Any, path: tuple[str | int, ...] = ()
) -> list[tuple[tuple[str | int, ...], Any, Any]]:
    """Recursively compare two JSON-serializable trees.

    Returns a list of (path, a_value, b_value) for each difference found.
    Stops after finding the first difference to keep the report minimal.
    """
    if type(a) is not type(b):
        return [(path, a, b)]

    if isinstance(a, Mapping):
        a_dict: dict[str, Any] = dict(a)
        b_dict: dict[str, Any] = dict(b)
        all_keys = sorted(set(a_dict) | set(b_dict), key=lambda value: value.encode("utf-16-be"))
        for key in all_keys:
            av = a_dict.get(key, _MISSING)
            bv = b_dict.get(key, _MISSING)
            if av != bv:
                child_path = path + (key,)
                if isinstance(av, (dict, list)) and isinstance(bv, (dict, list)):
                    diffs = _walk_and_compare(av, bv, child_path)
                    if diffs:
                        return diffs
                return [
                    (
                        child_path,
                        "<missing>" if av is _MISSING else av,
                        "<missing>" if bv is _MISSING else bv,
                    )
                ]
        return []
    elif isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return [(path, f"len={len(a)}", f"len={len(b)}")]
        for i, (av, bv) in enumerate(zip(a, b)):
            if av != bv:
                child_path = path + (i,)
                if isinstance(av, (dict, list)) and isinstance(bv, (dict, list)):
                    diffs = _walk_and_compare(av, bv, child_path)
                    if diffs:
                        return diffs
                return [(child_path, av, bv)]
        return []
    else:
        return [(path, a, b)]


def _first_byte_offset(expected: bytes, actual: bytes) -> int:
    for offset, (left, right) in enumerate(zip(expected, actual)):
        if left != right:
            return offset
    return min(len(expected), len(actual))


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _producer_fingerprint(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    producer = value.get("producer")
    fingerprint = producer.get("fingerprint") if isinstance(producer, dict) else None
    return fingerprint if isinstance(fingerprint, str) else None


def first_canonical_difference(
    expected: bytes,
    actual: bytes,
    artifact_path: str = "",
) -> DeterminismDifference | None:
    """Return a typed JSON-aware or binary first difference with both digests."""
    if expected == actual:
        return None
    offset = _first_byte_offset(expected, actual)

    try:
        expected_tree = json.loads(expected)
        actual_tree = json.loads(actual)
    except (json.JSONDecodeError, TypeError):
        return DeterminismDifference(
            artifact_path,
            _sha256(expected),
            _sha256(actual),
            offset,
        )

    diffs = _walk_and_compare(expected_tree, actual_tree)
    if not diffs:
        return DeterminismDifference(
            artifact_path,
            _sha256(expected),
            _sha256(actual),
            offset,
            expected_producer_fingerprint=_producer_fingerprint(expected_tree),
            actual_producer_fingerprint=_producer_fingerprint(actual_tree),
        )
    path, expected_value, actual_value = diffs[0]
    return DeterminismDifference(
        artifact_path,
        _sha256(expected),
        _sha256(actual),
        offset,
        _json_pointer(path),
        expected_value,
        actual_value,
        _producer_fingerprint(expected_tree),
        _producer_fingerprint(actual_tree),
    )


def compare_canonical_bytes(a_bytes: bytes, b_bytes: bytes, label: str = "") -> str:
    """Backward-compatible formatted canonical first-difference report."""
    difference = first_canonical_difference(a_bytes, b_bytes, label)
    return "" if difference is None else difference.format()


def first_artifact_repository_difference(
    expected_root: str | Path,
    actual_root: str | Path,
) -> DeterminismDifference | None:
    """Compare every nested JSON/binary member in canonical UTF-8 path order."""
    a_dir = Path(expected_root)
    b_dir = Path(actual_root)

    if not a_dir.is_dir():
        raise ValueError(f"DETERMINISM-PATH: {expected_root} is not a directory")
    if not b_dir.is_dir():
        raise ValueError(f"DETERMINISM-PATH: {actual_root} is not a directory")

    a_files = sorted(
        (path.relative_to(a_dir).as_posix() for path in a_dir.rglob("*") if path.is_file()),
        key=lambda value: value.encode("utf-8"),
    )
    b_files = sorted(
        (path.relative_to(b_dir).as_posix() for path in b_dir.rglob("*") if path.is_file()),
        key=lambda value: value.encode("utf-8"),
    )

    for filename in sorted(set(a_files) | set(b_files), key=lambda value: value.encode("utf-8")):
        expected_path, actual_path = a_dir / filename, b_dir / filename
        expected = expected_path.read_bytes() if expected_path.is_file() else b""
        actual = actual_path.read_bytes() if actual_path.is_file() else b""
        if expected_path.is_file() != actual_path.is_file():
            return DeterminismDifference(
                filename,
                _sha256(expected),
                _sha256(actual),
                0,
                expected_value="present" if expected_path.is_file() else "<missing artifact>",
                actual_value="present" if actual_path.is_file() else "<missing artifact>",
            )
        difference = first_canonical_difference(expected, actual, filename)
        if difference is not None:
            return difference
    return None


def compare_artifact_repositories(
    repo_a_path: str | Path,
    repo_b_path: str | Path,
) -> str:
    """Backward-compatible formatted repository first-difference report."""
    difference = first_artifact_repository_difference(repo_a_path, repo_b_path)
    return "" if difference is None else difference.format()
