"""Canonical world-stage envelopes, encoding and dependency invalidation."""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path, PurePosixPath
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Generic, TypeVar

from ..storage.fs import atomic_write_bytes

T = TypeVar("T")


def canonical_json(value: object) -> bytes:
    def convert(item: object) -> object:
        if is_dataclass(item) and not isinstance(item, type):
            return convert(asdict(item))
        if isinstance(item, dict):
            return {str(key): convert(item[key]) for key in sorted(item)}
        if isinstance(item, (tuple, list)):
            return [convert(part) for part in item]
        if item is None or isinstance(item, (bool, int, str)):
            return item
        raise TypeError(f"non-canonical world value: {type(item).__name__}")
    return json.dumps(
        convert(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")


@dataclass(frozen=True)
class WorldArtifact(Generic[T]):
    artifact_id: str
    kind: str
    payload: T
    sha256: str
    depends_on: tuple[str, ...]
    producer_fingerprint: str

    @classmethod
    def build(
        cls, kind: str, payload: T, *, depends_on: tuple[str, ...] = (),
        producer_fingerprint: str,
    ) -> "WorldArtifact[T]":
        digest = hashlib.sha256(canonical_json(payload)).hexdigest()
        return cls(
            artifact_id=f"{kind}_{digest[:32]}", kind=kind, payload=payload,
            sha256=digest, depends_on=tuple(sorted(depends_on)),
            producer_fingerprint=producer_fingerprint,
        )


class DependencyGraph:
    def __init__(self, dependencies: dict[str, tuple[str, ...]]) -> None:
        self.dependencies = dict(dependencies)
        self._validate()

    def _validate(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError(f"world artifact dependency cycle at {node}")
            if node in visited:
                return
            visiting.add(node)
            for dependency in self.dependencies.get(node, ()):
                if dependency not in self.dependencies:
                    raise ValueError(f"unknown world artifact dependency: {dependency}")
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in sorted(self.dependencies):
            visit(node)

    def invalidation_closure(self, changed: set[str]) -> set[str]:
        invalid = set(changed)
        while True:
            expanded = invalid | {
                node for node, dependencies in self.dependencies.items()
                if any(dependency in invalid for dependency in dependencies)
            }
            if expanded == invalid:
                return invalid
            invalid = expanded


class WorldArtifactRepository:
    """Atomic confined repository for complete world artifact envelopes."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, artifact: WorldArtifact[Any]) -> Path:
        name = PurePosixPath(artifact.kind)
        if len(name.parts) != 1 or name.name in ("", ".", ".."):
            raise ValueError(f"WG-PATH: unsafe world artifact kind {artifact.kind!r}")
        path = self.root / f"{name.name}.json"
        envelope = {
            "artifact_id": artifact.artifact_id, "kind": artifact.kind,
            "sha256": artifact.sha256, "depends_on": list(artifact.depends_on),
            "producer_fingerprint": artifact.producer_fingerprint,
            "payload": artifact.payload,
        }
        atomic_write_bytes(path, canonical_json(envelope))
        return path

    def load_verified(self, kind: str) -> WorldArtifact[Any]:
        path = self.root / f"{kind}.json"
        envelope = json.loads(path.read_bytes())
        artifact = WorldArtifact(
            artifact_id=envelope["artifact_id"], kind=envelope["kind"],
            payload=envelope["payload"], sha256=envelope["sha256"],
            depends_on=tuple(envelope["depends_on"]),
            producer_fingerprint=envelope["producer_fingerprint"],
        )
        actual = hashlib.sha256(canonical_json(artifact.payload)).hexdigest()
        if actual != artifact.sha256 or artifact.artifact_id != f"{kind}_{actual[:32]}":
            raise ValueError(f"WG-HASH: corrupt world artifact {kind}")
        return artifact


@dataclass(frozen=True)
class GridChunk:
    """Canonical uncompressed signed-int32 rectangular grid chunk."""

    layer: str
    chunk_x: int
    chunk_y: int
    width: int
    height: int
    values: tuple[int, ...]

    def encode(self) -> bytes:
        if self.width < 1 or self.height < 1 or len(self.values) != self.width * self.height:
            raise ValueError("WG-GRID: dimensions do not match value count")
        header = canonical_json({
            "format": "storyteller.grid.i32be.v1", "layer": self.layer,
            "chunk_x": self.chunk_x, "chunk_y": self.chunk_y,
            "width": self.width, "height": self.height,
        })
        body = b"".join(struct.pack(">i", value) for value in self.values)
        return struct.pack(">I", len(header)) + header + body

    @classmethod
    def decode(cls, encoded: bytes) -> "GridChunk":
        if len(encoded) < 4:
            raise ValueError("WG-GRID: truncated header")
        header_size = struct.unpack(">I", encoded[:4])[0]
        header_end = 4 + header_size
        header = json.loads(encoded[4:header_end])
        if header.get("format") != "storyteller.grid.i32be.v1":
            raise ValueError("WG-GRID: unsupported format")
        width, height = int(header["width"]), int(header["height"])
        body = encoded[header_end:]
        if len(body) != width * height * 4:
            raise ValueError("WG-GRID: invalid payload length")
        values = tuple(item[0] for item in struct.iter_unpack(">i", body))
        return cls(
            layer=header["layer"], chunk_x=int(header["chunk_x"]),
            chunk_y=int(header["chunk_y"]), width=width, height=height,
            values=values,
        )
