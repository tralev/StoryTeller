"""P8.C05H step 6 — Determinism diff reporter.

Given two artifact repositories (or two runs that should be byte-identical),
find the *first* difference and report: artifact ID, JSON pointer path,
and byte offset.

This is a diagnostic tool, not a validator. It is used by hardening
suites to produce actionable failure messages instead of a generic
"hashes differ" assertion.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


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
        all_keys = sorted(set(a_dict.keys()) | set(b_dict.keys()))
        for key in all_keys:
            av = a_dict.get(key)
            bv = b_dict.get(key)
            if av != bv:
                child_path = path + (key,)
                if isinstance(av, (dict, list)) and isinstance(bv, (dict, list)):
                    diffs = _walk_and_compare(av, bv, child_path)
                    if diffs:
                        return diffs
                return [(child_path, av, bv)]
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


def compare_canonical_bytes(
    a_bytes: bytes, b_bytes: bytes, label: str = ""
) -> str:
    """Compare two canonical JSON byte strings and return a diff report.

    The report includes the first differing JSON pointer and a byte-level
    offset hint.
    """
    if a_bytes == b_bytes:
        return ""

    # Try decoding as JSON for structured diff
    try:
        a_tree = json.loads(a_bytes)
        b_tree = json.loads(b_bytes)
    except (json.JSONDecodeError, TypeError):
        # Not valid JSON — report byte-level difference
        if len(a_bytes) != len(b_bytes):
            prefix = f"[{label}] " if label else ""
            return (
                f"{prefix}length mismatch: "
                f"{len(a_bytes)} bytes vs {len(b_bytes)} bytes"
            )
        offset = 0
        for offset, (ca, cb) in enumerate(zip(a_bytes, b_bytes)):
            if ca != cb:
                break
        prefix = f"[{label}] " if label else ""
        return (
            f"{prefix}byte {offset}: 0x{ca:02x} vs 0x{cb:02x}"
        )

    diffs = _walk_and_compare(a_tree, b_tree)
    if not diffs:
        # Trees compare equal but bytes differ — likely encoding difference
        offset = 0
        for offset, (ca, cb) in enumerate(zip(a_bytes, b_bytes)):
            if ca != cb:
                break
        prefix = f"[{label}] " if label else ""
        return (
            f"{prefix}byte {offset}: 0x{ca:02x} vs 0x{cb:02x} "
            f"(json trees equal but bytes differ; check encoding)"
        )

    path, a_val, b_val = diffs[0]
    pointer = _json_pointer(path)
    prefix = f"[{label}] " if label else ""
    return (
        f"{prefix}{pointer}: {json.dumps(a_val, default=str)} "
        f"vs {json.dumps(b_val, default=str)}"
    )


def compare_artifact_repositories(
    repo_a_path: str | Path, repo_b_path: str | Path,
) -> str:
    """Compare two artifact repositories and report the first difference.

    Each repository is a directory of canonical JSON artifact files.
    Returns empty string if identical, or a diff report.
    """
    a_dir = Path(repo_a_path)
    b_dir = Path(repo_b_path)

    if not a_dir.is_dir():
        return f"path {repo_a_path} is not a directory"
    if not b_dir.is_dir():
        return f"path {repo_b_path} is not a directory"

    # Currently only compares *.json artifacts. Binary artifacts (images,
    # MIDI, compressed grids) would need byte-level comparison extension.
    a_files = sorted(f.name for f in a_dir.glob("*.json"))
    b_files = sorted(f.name for f in b_dir.glob("*.json"))

    if a_files != b_files:
        only_a = set(a_files) - set(b_files)
        only_b = set(b_files) - set(a_files)
        parts: list[str] = []
        if only_a:
            parts.append(f"only in a: {sorted(only_a)}")
        if only_b:
            parts.append(f"only in b: {sorted(only_b)}")
        return "; ".join(parts)

    for filename in a_files:
        a_bytes = (a_dir / filename).read_bytes()
        b_bytes = (b_dir / filename).read_bytes()
        if a_bytes != b_bytes:
            return compare_canonical_bytes(a_bytes, b_bytes, label=filename)

    return ""
