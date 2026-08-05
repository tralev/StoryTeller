"""Atomic typed repository for JSON and binary artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from ..domain.artifacts import ArtifactKey, ArtifactRef
from ..domain.json_value import JsonValue
from .fs import atomic_write_bytes


class ArtifactRepository:
    """Confined content-addressed artifact storage.

    Paths are package-style relative paths. Every successful write returns the
    complete reference needed for checkpoint and provenance verification.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put_json(
        self, kind: ArtifactKey, value: JsonValue, *, path: str | None = None,
        depends_on: tuple[str, ...] = (), producer_fingerprint: str = "",
    ) -> ArtifactRef:
        canonical = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        return self.put_bytes(
            kind, path or f"content/{kind}.json", canonical,
            depends_on=depends_on, producer_fingerprint=producer_fingerprint,
        )

    def put_bytes(
        self, kind: ArtifactKey, path: str, value: bytes, *,
        depends_on: tuple[str, ...] = (), producer_fingerprint: str = "",
    ) -> ArtifactRef:
        relative, target = self._target(path)
        digest = hashlib.sha256(value).hexdigest()
        atomic_write_bytes(target, value)
        return ArtifactRef(
            artifact_id=f"{kind}_{digest[:32]}", kind=kind,
            canonical_path=relative, sha256=digest, size_bytes=len(value),
            depends_on=tuple(sorted(depends_on)),
            producer_fingerprint=producer_fingerprint,
        )

    def load_verified(self, ref: ArtifactRef) -> bytes:
        _, target = self._target(ref.canonical_path)
        data = target.read_bytes()
        if len(data) != ref.size_bytes or hashlib.sha256(data).hexdigest() != ref.sha256:
            raise ValueError(f"artifact verification failed: {ref.canonical_path}")
        return data

    def exists_verified(self, ref: ArtifactRef) -> bool:
        try:
            self.load_verified(ref)
        except (OSError, ValueError):
            return False
        return True

    def _target(self, path: str) -> tuple[str, Path]:
        pure = PurePosixPath(path)
        if pure.is_absolute() or not pure.parts or any(p in ("", ".", "..") for p in pure.parts):
            raise ValueError(f"unsafe artifact path: {path}")
        relative = pure.as_posix()
        target = (self.root / Path(*pure.parts)).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError(f"artifact path escapes repository: {path}")
        return relative, target
