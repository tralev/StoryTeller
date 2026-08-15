"""Canonical world-stage envelopes, encoding and dependency invalidation."""

from __future__ import annotations

import hashlib
import json
import re
import struct
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path, PurePosixPath
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Generic, TypeVar, overload

from ..storage.fs import atomic_write_bytes

T = TypeVar("T")
GRID_CHUNK_FORMAT = "storyteller.grid.i32be.v1"
MAX_GRID_CHUNK_AXIS = 256
MAX_GRID_HEADER_BYTES = 1024
MAX_GRID_CHUNK_BYTES = 4 + MAX_GRID_HEADER_BYTES + MAX_GRID_CHUNK_AXIS ** 2 * 4
_GRID_LAYER = re.compile(r"^[a-z][a-z0-9_]*$")
_ARTIFACT_KIND = re.compile(r"^[a-z][a-z0-9_]*$")
_ARTIFACT_ID = re.compile(r"^[a-z][a-z0-9_]*_[0-9a-f]{32}$")
_PRODUCER_FINGERPRINT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ArtifactId(str):
    """Validated, string-compatible canonical artifact identity."""

    def __new__(cls, value: str) -> "ArtifactId":
        if not isinstance(value, str) or not _ARTIFACT_ID.fullmatch(value):
            raise ValueError("WG-ARTIFACT-ID: invalid artifact identity")
        return str.__new__(cls, value)


class ArtifactDependency(ArtifactId):
    """Typed reference to an immutable upstream artifact."""


class ProducerFingerprint(str):
    """Validated, string-compatible producer implementation identity."""

    def __new__(cls, value: str) -> "ProducerFingerprint":
        if not isinstance(value, str) or not _PRODUCER_FINGERPRINT.fullmatch(value):
            raise ValueError("WG-PRODUCER-FINGERPRINT: invalid producer fingerprint")
        return str.__new__(cls, value)


@dataclass(frozen=True)
class FrozenMap(Mapping[str, object]):
    """Canonical immutable mapping used inside persisted artifact payloads."""

    entries: tuple[tuple[str, object], ...]

    def __post_init__(self) -> None:
        keys = tuple(key for key, _ in self.entries)
        if keys != tuple(sorted(keys, key=_utf16_key)) or len(keys) != len(set(keys)):
            raise ValueError("frozen map keys must be unique and canonically sorted")

    def __getitem__(self, key: str) -> object:
        for candidate, value in self.entries:
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (key for key, _ in self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return False
        return dict(self.items()) == dict(other.items())


@dataclass(frozen=True)
class FrozenSequence(Sequence[object]):
    """Immutable JSON-array-compatible sequence with structural equality."""

    values: tuple[object, ...]

    @overload
    def __getitem__(self, index: int) -> object: ...

    @overload
    def __getitem__(self, index: slice) -> Sequence[object]: ...

    def __getitem__(self, index: int | slice) -> object | Sequence[object]:
        if isinstance(index, slice):
            return FrozenSequence(self.values[index])
        return self.values[index]

    def __len__(self) -> int:
        return len(self.values)

    def __iter__(self) -> Iterator[object]:
        return iter(self.values)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Sequence) or isinstance(other, (str, bytes, bytearray)):
            return False
        return tuple(self) == tuple(other)


def freeze_canonical(value: T) -> T:
    """Recursively freeze JSON-shaped containers while preserving value objects."""
    if isinstance(value, (FrozenMap, FrozenSequence)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return freeze_canonical(asdict(value))  # type: ignore[return-value]
    if isinstance(value, Mapping):
        normalized: list[tuple[str, object]] = []
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise TypeError("canonical artifact map keys must be strings")
            key = unicodedata.normalize("NFC", raw_key)
            normalized.append((key, freeze_canonical(item)))
        keys = [key for key, _ in normalized]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate object key after NFC normalization")
        normalized.sort(key=lambda item: _utf16_key(item[0]))
        return FrozenMap(tuple(normalized))  # type: ignore[return-value]
    if isinstance(value, list):
        return FrozenSequence(tuple(freeze_canonical(item) for item in value))  # type: ignore[return-value]
    if isinstance(value, tuple):
        return tuple(freeze_canonical(item) for item in value)  # type: ignore[return-value]
    return value


def _utf16_key(value: str) -> bytes:
    """Canonical sort key: UTF-16-BE code-unit ordering (generation.md)."""
    return value.encode("utf-16-be", "surrogatepass")


def canonical_json(value: object) -> bytes:
    """RFC 8785 JCS with NFC normalization and UTF-16-BE key ordering.

    Rejects NaN/Infinity, uses scaled integers not floats, sorts object
    keys by their UTF-16-BE code-unit representation with NFC normalization
    per the worldgen-1 specification.
    """
    def convert(item: object) -> object:
        if isinstance(item, Mapping):
            # Normalize keys to NFC and sort by UTF-16-BE code units
            items: list[tuple[str, object]] = []
            for k, v in item.items():
                if not isinstance(k, str):
                    raise TypeError("canonical JSON object keys must be strings")
                if any(0xD800 <= ord(character) <= 0xDFFF for character in k):
                    raise ValueError("canonical JSON rejects lone Unicode surrogates")
                key = unicodedata.normalize("NFC", k)
                items.append((key, convert(v)))
            # Detect duplicate keys after NFC normalization
            keys = [k for k, _ in items]
            if len(keys) != len(set(keys)):
                raise ValueError("duplicate object key after NFC normalization")
            items.sort(key=lambda p: _utf16_key(p[0]))
            return {k: v for k, v in items}
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            return [convert(part) for part in item]
        if is_dataclass(item) and not isinstance(item, type):
            return convert(asdict(item))
        if isinstance(item, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in item):
                raise ValueError("canonical JSON rejects lone Unicode surrogates")
            return unicodedata.normalize("NFC", item)
        if isinstance(item, float):
            raise ValueError("canonical data uses scaled integers, not floats")
        if item is None or isinstance(item, (bool, int)):
            return item
        raise TypeError(f"non-canonical world value: {type(item).__name__}")
    return json.dumps(
        convert(value),
        ensure_ascii=False,
        sort_keys=False,  # keys already sorted by _utf16_key order
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def artifact_identity_digest(
    kind: str, sha256: str, depends_on: Sequence[str], producer_fingerprint: str,
) -> str:
    """Return the full provenance-sensitive SHA-256 identity derivation digest."""
    if not isinstance(kind, str) or not _ARTIFACT_KIND.fullmatch(kind):
        raise ValueError("WG-ARTIFACT-KIND: invalid artifact kind")
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("WG-ARTIFACT-HASH: sha256 must be 64 lowercase hex characters")
    dependencies = tuple(sorted(ArtifactDependency(value) for value in depends_on))
    if len(dependencies) != len(set(dependencies)):
        raise ValueError("WG-DEPENDENCY: duplicate artifact dependency")
    fingerprint = ProducerFingerprint(producer_fingerprint)
    identity = {
        "depends_on": dependencies, "kind": kind,
        "producer_fingerprint": fingerprint, "sha256": sha256,
    }
    return hashlib.sha256(canonical_json(identity)).hexdigest()


@dataclass(frozen=True)
class WorldArtifact(Generic[T]):
    artifact_id: ArtifactId
    kind: str
    payload: T
    sha256: str
    depends_on: tuple[ArtifactDependency, ...]
    producer_fingerprint: ProducerFingerprint

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not _ARTIFACT_KIND.fullmatch(self.kind):
            raise ValueError("WG-ARTIFACT-KIND: invalid artifact kind")
        if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
            raise ValueError("WG-ARTIFACT-HASH: sha256 must be 64 lowercase hex characters")
        object.__setattr__(self, "artifact_id", ArtifactId(self.artifact_id))
        object.__setattr__(self, "payload", freeze_canonical(self.payload))
        dependencies = tuple(sorted(ArtifactDependency(value) for value in self.depends_on))
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("WG-DEPENDENCY: duplicate artifact dependency")
        object.__setattr__(self, "depends_on", dependencies)
        object.__setattr__(self, "producer_fingerprint",
                           ProducerFingerprint(self.producer_fingerprint))

    @classmethod
    def build(
        cls, kind: str, payload: T, *, depends_on: tuple[str, ...] = (),
        producer_fingerprint: str | ProducerFingerprint,
    ) -> "WorldArtifact[T]":
        frozen_payload = freeze_canonical(payload)
        digest = hashlib.sha256(canonical_json(frozen_payload)).hexdigest()
        identity_digest = artifact_identity_digest(
            kind, digest, depends_on, str(producer_fingerprint),
        )
        return cls(
            artifact_id=ArtifactId(f"{kind}_{identity_digest[:32]}"), kind=kind,
            payload=frozen_payload,
            sha256=digest,
            depends_on=tuple(sorted(ArtifactDependency(value) for value in depends_on)),
            producer_fingerprint=ProducerFingerprint(producer_fingerprint),
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

    @staticmethod
    def _kind_name(kind: str) -> str:
        if not isinstance(kind, str) or not _ARTIFACT_KIND.fullmatch(kind):
            raise ValueError(f"WG-PATH: unsafe world artifact kind {kind!r}")
        name = PurePosixPath(kind)
        if len(name.parts) != 1 or name.name in ("", ".", ".."):
            raise ValueError(f"WG-PATH: unsafe world artifact kind {kind!r}")
        return name.name

    def put(self, artifact: WorldArtifact[Any]) -> Path:
        name = self._kind_name(artifact.kind)
        path = self.root / f"{name}.json"
        if path.exists():
            existing = self.load_verified(artifact.kind)
            if existing != artifact:
                raise ValueError(f"WG-REUSE: conflicting world artifact {artifact.kind}")
            return path
        envelope = {
            "artifact_id": artifact.artifact_id, "kind": artifact.kind,
            "sha256": artifact.sha256, "depends_on": list(artifact.depends_on),
            "producer_fingerprint": artifact.producer_fingerprint,
            "payload": artifact.payload,
        }
        atomic_write_bytes(path, canonical_json(envelope))
        return path

    def load_verified(self, kind: str) -> WorldArtifact[Any]:
        name = self._kind_name(kind)
        path = self.root / f"{name}.json"
        encoded = path.read_bytes()
        envelope = json.loads(encoded)
        required = {
            "artifact_id", "kind", "sha256", "depends_on",
            "producer_fingerprint", "payload",
        }
        if not isinstance(envelope, dict) or set(envelope) != required:
            raise ValueError(f"WG-ENVELOPE: invalid world artifact {kind}")
        if canonical_json(envelope) != encoded:
            raise ValueError(f"WG-ENVELOPE: noncanonical world artifact {kind}")
        if envelope["kind"] != kind:
            raise ValueError(f"WG-ENVELOPE: kind mismatch for {kind}")
        artifact = WorldArtifact(
            artifact_id=envelope["artifact_id"], kind=envelope["kind"],
            payload=envelope["payload"], sha256=envelope["sha256"],
            depends_on=tuple(envelope["depends_on"]),
            producer_fingerprint=envelope["producer_fingerprint"],
        )
        actual = hashlib.sha256(canonical_json(artifact.payload)).hexdigest()
        identity_digest = artifact_identity_digest(
            artifact.kind, artifact.sha256, artifact.depends_on,
            artifact.producer_fingerprint,
        )
        if (actual != artifact.sha256
                or artifact.artifact_id != f"{kind}_{identity_digest[:32]}"):
            raise ValueError(f"WG-HASH: corrupt world artifact {kind}")
        return artifact


@dataclass(frozen=True)
class ChunkCoordinate:
    x: int
    y: int

    def __post_init__(self) -> None:
        if (isinstance(self.x, bool) or isinstance(self.y, bool)
                or not isinstance(self.x, int) or not isinstance(self.y, int)
                or self.x < 0 or self.y < 0):
            raise ValueError("WG-GRID: chunk coordinates must be nonnegative integers")


@dataclass(frozen=True)
class GridChunk:
    """Canonical uncompressed signed-int32 rectangular grid chunk."""

    layer: str
    chunk_x: int
    chunk_y: int
    width: int
    height: int
    values: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.layer, str) or not _GRID_LAYER.fullmatch(self.layer):
            raise ValueError("WG-GRID: layer must use lowercase snake_case")
        if unicodedata.normalize("NFC", self.layer) != self.layer:
            raise ValueError("WG-GRID: layer must use NFC normalization")
        ChunkCoordinate(self.chunk_x, self.chunk_y)
        if (isinstance(self.width, bool) or isinstance(self.height, bool)
                or not isinstance(self.width, int) or not isinstance(self.height, int)
                or not 1 <= self.width <= MAX_GRID_CHUNK_AXIS
                or not 1 <= self.height <= MAX_GRID_CHUNK_AXIS):
            raise ValueError("WG-GRID: chunk dimensions must be within 1..256")
        if len(self.values) != self.width * self.height:
            raise ValueError("WG-GRID: dimensions do not match value count")
        if any(isinstance(value, bool) or not isinstance(value, int)
               or not -(1 << 31) <= value < (1 << 31) for value in self.values):
            raise ValueError("WG-GRID: values must be signed 32-bit integers")

    @property
    def coordinate(self) -> ChunkCoordinate:
        return ChunkCoordinate(self.chunk_x, self.chunk_y)

    def encode(self) -> bytes:
        header = canonical_json({
            "format": GRID_CHUNK_FORMAT, "layer": self.layer,
            "chunk_x": self.chunk_x, "chunk_y": self.chunk_y,
            "width": self.width, "height": self.height,
        })
        body = b"".join(struct.pack(">i", value) for value in self.values)
        return struct.pack(">I", len(header)) + header + body

    @classmethod
    def decode(cls, encoded: bytes) -> "GridChunk":
        if len(encoded) < 4:
            raise ValueError("WG-GRID: truncated header")
        if len(encoded) > MAX_GRID_CHUNK_BYTES:
            raise ValueError("WG-GRID: encoded chunk exceeds byte limit")
        header_size = struct.unpack(">I", encoded[:4])[0]
        if not 1 <= header_size <= MAX_GRID_HEADER_BYTES:
            raise ValueError("WG-GRID: header exceeds byte limit")
        header_end = 4 + header_size
        if header_end > len(encoded):
            raise ValueError("WG-GRID: truncated header")
        try:
            header = json.loads(encoded[4:header_end])
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("WG-GRID: invalid header JSON") from error
        if not isinstance(header, dict) or header.get("format") != GRID_CHUNK_FORMAT:
            raise ValueError("WG-GRID: unsupported format")
        required = {"format", "layer", "chunk_x", "chunk_y", "width", "height"}
        if set(header) != required:
            raise ValueError("WG-GRID: invalid header fields")
        width, height = header["width"], header["height"]
        if (isinstance(width, bool) or isinstance(height, bool)
                or not isinstance(width, int) or not isinstance(height, int)
                or not 1 <= width <= MAX_GRID_CHUNK_AXIS
                or not 1 <= height <= MAX_GRID_CHUNK_AXIS):
            raise ValueError("WG-GRID: chunk dimensions must be within 1..256")
        body = encoded[header_end:]
        if len(body) != width * height * 4:
            raise ValueError("WG-GRID: invalid payload length")
        values = tuple(item[0] for item in struct.iter_unpack(">i", body))
        chunk = cls(
            layer=header["layer"], chunk_x=header["chunk_x"],
            chunk_y=header["chunk_y"], width=width, height=height,
            values=values,
        )
        if chunk.encode() != encoded:
            raise ValueError("WG-GRID: noncanonical encoding")
        return chunk
