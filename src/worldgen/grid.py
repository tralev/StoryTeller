"""Immutable canonical world-grid primitives."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

from ..storage.fs import atomic_write_bytes
from .artifacts import MAX_GRID_CHUNK_AXIS, ChunkCoordinate, GridChunk
from .numeric import div_floor_exact

T = TypeVar("T", bound=int)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LAYER = re.compile(r"^[a-z][a-z0-9_]*$")


def _require_nonnegative_coordinate(*values: int) -> None:
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
        raise ValueError("WG-COORDINATE: coordinates must be nonnegative integers")


@dataclass(frozen=True, order=True)
class WorldCoordinate:
    x: int
    y: int

    def __post_init__(self) -> None:
        _require_nonnegative_coordinate(self.x, self.y)


@dataclass(frozen=True, order=True)
class LocalCoordinate:
    x: int
    y: int
    z: int

    def __post_init__(self) -> None:
        _require_nonnegative_coordinate(self.x, self.y, self.z)


# Compatibility name for existing surface-grid callers. New contracts should
# spell out WorldCoordinate or LocalCoordinate at their boundaries.
Coordinate = WorldCoordinate


@dataclass(frozen=True)
class GridSpec:
    width: int
    height: int
    metres_per_world_cell: int

    def __post_init__(self) -> None:
        if self.width < 1 or self.height < 1 or self.metres_per_world_cell < 1:
            raise ValueError("WG-GRID-SPEC: dimensions and scale must be positive")

    @property
    def cell_count(self) -> int:
        return self.width * self.height

    def index(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError((x, y))
        return y * self.width + x

    def coordinate(self, index: int) -> Coordinate:
        if not 0 <= index < self.cell_count:
            raise IndexError(index)
        return Coordinate(index % self.width, div_floor_exact(index, self.width))

    def neighbors4(self, index: int) -> tuple[int, ...]:
        point = self.coordinate(index)
        result: list[int] = []
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            x, y = point.x + dx, point.y + dy
            if 0 <= x < self.width and 0 <= y < self.height:
                result.append(self.index(x, y))
        return tuple(result)

    def indices(self) -> range:
        return range(self.cell_count)


@dataclass(frozen=True)
class IntGrid(Generic[T]):
    spec: GridSpec
    values: tuple[T, ...]

    def __post_init__(self) -> None:
        if len(self.values) != self.spec.cell_count:
            raise ValueError("WG-GRID-LENGTH: grid value count does not match dimensions")

    def at(self, x: int, y: int) -> T:
        return self.values[self.spec.index(x, y)]

    def items(self) -> Iterator[tuple[Coordinate, T]]:
        for index, value in enumerate(self.values):
            yield self.spec.coordinate(index), value

    def encode(self, layer: str) -> bytes:
        return GridChunk(layer, 0, 0, self.spec.width, self.spec.height, self.values).encode()


@dataclass(frozen=True, order=True)
class GridChunkDescriptor:
    chunk_y: int
    chunk_x: int
    width: int
    height: int
    sha256: str

    def __post_init__(self) -> None:
        ChunkCoordinate(self.chunk_x, self.chunk_y)
        if (
            isinstance(self.width, bool)
            or isinstance(self.height, bool)
            or not isinstance(self.width, int)
            or not isinstance(self.height, int)
            or not 1 <= self.width <= MAX_GRID_CHUNK_AXIS
            or not 1 <= self.height <= MAX_GRID_CHUNK_AXIS
        ):
            raise ValueError("WG-GRID-MANIFEST: invalid chunk dimensions")
        if not _SHA256.fullmatch(self.sha256):
            raise ValueError("WG-GRID-MANIFEST: invalid chunk hash")


@dataclass(frozen=True)
class DenseGridManifest:
    format: str
    layer: str
    grid: GridSpec
    chunk_width: int
    chunk_height: int
    chunks: tuple[GridChunkDescriptor, ...]

    def __post_init__(self) -> None:
        if self.format != "storyteller.dense-grid-manifest.v1":
            raise ValueError("WG-GRID-MANIFEST: unsupported format")
        if not _LAYER.fullmatch(self.layer):
            raise ValueError("WG-GRID-MANIFEST: invalid layer")
        if (
            isinstance(self.chunk_width, bool)
            or isinstance(self.chunk_height, bool)
            or not isinstance(self.chunk_width, int)
            or not isinstance(self.chunk_height, int)
            or not 1 <= self.chunk_width <= MAX_GRID_CHUNK_AXIS
            or not 1 <= self.chunk_height <= MAX_GRID_CHUNK_AXIS
        ):
            raise ValueError("WG-GRID-MANIFEST: invalid nominal chunk dimensions")
        expected: list[tuple[int, int, int, int]] = []
        for y in range(0, self.grid.height, self.chunk_height):
            for x in range(0, self.grid.width, self.chunk_width):
                expected.append(
                    (
                        div_floor_exact(y, self.chunk_height),
                        div_floor_exact(x, self.chunk_width),
                        min(self.chunk_width, self.grid.width - x),
                        min(self.chunk_height, self.grid.height - y),
                    )
                )
        actual = tuple(
            (item.chunk_y, item.chunk_x, item.width, item.height) for item in self.chunks
        )
        if actual != tuple(expected):
            raise ValueError("WG-GRID-MANIFEST: chunks must provide canonical exact coverage")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> DenseGridManifest:
        def integer(source: Mapping[str, object], key: str) -> int:
            item = source[key]
            if isinstance(item, bool) or not isinstance(item, int):
                raise ValueError(f"WG-GRID-MANIFEST: {key} must be an integer")
            return item

        grid_value = value["grid"]
        chunks_value = value["chunks"]
        if not isinstance(grid_value, Mapping) or not isinstance(chunks_value, Iterable):
            raise ValueError("WG-GRID-MANIFEST: invalid persisted shape")
        grid = GridSpec(
            integer(grid_value, "width"),
            integer(grid_value, "height"),
            integer(grid_value, "metres_per_world_cell"),
        )
        descriptors: list[GridChunkDescriptor] = []
        for raw in chunks_value:
            if not isinstance(raw, Mapping):
                raise ValueError("WG-GRID-MANIFEST: invalid descriptor shape")
            descriptors.append(
                GridChunkDescriptor(
                    integer(raw, "chunk_y"),
                    integer(raw, "chunk_x"),
                    integer(raw, "width"),
                    integer(raw, "height"),
                    str(raw["sha256"]),
                )
            )
        return cls(
            str(value["format"]),
            str(value["layer"]),
            grid,
            integer(value, "chunk_width"),
            integer(value, "chunk_height"),
            tuple(descriptors),
        )


@dataclass(frozen=True)
class DenseGridCatalog:
    format: str
    grid: GridSpec
    manifests: tuple[DenseGridManifest, ...]

    def __post_init__(self) -> None:
        if self.format != "storyteller.dense-grid-catalog.v1":
            raise ValueError("WG-GRID-CATALOG: unsupported format")
        layers = tuple(item.layer for item in self.manifests)
        if layers != tuple(sorted(layers)) or len(layers) != len(set(layers)):
            raise ValueError("WG-GRID-CATALOG: layers must be unique and sorted")
        if any(item.grid != self.grid for item in self.manifests):
            raise ValueError("WG-GRID-CATALOG: manifest grid mismatch")

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> DenseGridCatalog:
        grid_value = value["grid"]
        manifests_value = value["manifests"]
        if not isinstance(grid_value, Mapping) or not isinstance(manifests_value, Iterable):
            raise ValueError("WG-GRID-CATALOG: invalid persisted shape")

        def integer(key: str) -> int:
            item: object = grid_value[key]
            if isinstance(item, bool) or not isinstance(item, int):
                raise ValueError(f"WG-GRID-CATALOG: {key} must be an integer")
            return item

        grid = GridSpec(integer("width"), integer("height"), integer("metres_per_world_cell"))
        manifests: list[DenseGridManifest] = []
        for raw in manifests_value:
            if not isinstance(raw, Mapping):
                raise ValueError("WG-GRID-CATALOG: invalid manifest shape")
            manifests.append(DenseGridManifest.from_mapping(raw))
        return cls(str(value["format"]), grid, tuple(manifests))

    def manifest(self, layer: str) -> DenseGridManifest:
        for item in self.manifests:
            if item.layer == layer:
                return item
        raise KeyError(layer)


def iter_grid_chunks(
    layer: str,
    grid: IntGrid[int],
    *,
    chunk_width: int = MAX_GRID_CHUNK_AXIS,
    chunk_height: int = MAX_GRID_CHUNK_AXIS,
) -> Iterator[GridChunk]:
    """Yield canonical row-major chunks while retaining at most one new chunk."""
    if not 1 <= chunk_width <= MAX_GRID_CHUNK_AXIS or not 1 <= chunk_height <= MAX_GRID_CHUNK_AXIS:
        raise ValueError("WG-GRID: invalid chunk dimensions")
    for y in range(0, grid.spec.height, chunk_height):
        for x in range(0, grid.spec.width, chunk_width):
            width = min(chunk_width, grid.spec.width - x)
            height = min(chunk_height, grid.spec.height - y)
            values = tuple(
                grid.values[grid.spec.index(x + dx, y + dy)]
                for dy in range(height)
                for dx in range(width)
            )
            yield GridChunk(
                layer,
                div_floor_exact(x, chunk_width),
                div_floor_exact(y, chunk_height),
                width,
                height,
                values,
            )


def build_grid_manifest(
    layer: str,
    grid: IntGrid[int],
    *,
    chunk_width: int = MAX_GRID_CHUNK_AXIS,
    chunk_height: int = MAX_GRID_CHUNK_AXIS,
) -> DenseGridManifest:
    descriptors = tuple(
        GridChunkDescriptor(
            chunk.chunk_y,
            chunk.chunk_x,
            chunk.width,
            chunk.height,
            hashlib.sha256(chunk.encode()).hexdigest(),
        )
        for chunk in iter_grid_chunks(
            layer,
            grid,
            chunk_width=chunk_width,
            chunk_height=chunk_height,
        )
    )
    return DenseGridManifest(
        "storyteller.dense-grid-manifest.v1",
        layer,
        grid.spec,
        chunk_width,
        chunk_height,
        descriptors,
    )


def reconstruct_grid(
    manifest: DenseGridManifest,
    chunks: Iterable[GridChunk],
) -> IntGrid[int]:
    """Verify and rebuild a dense grid independent of chunk arrival order."""
    expected = {(item.chunk_x, item.chunk_y): item for item in manifest.chunks}
    seen: set[tuple[int, int]] = set()
    values = [0] * manifest.grid.cell_count
    for chunk in chunks:
        key = (chunk.chunk_x, chunk.chunk_y)
        descriptor = expected.get(key)
        if descriptor is None or key in seen:
            raise ValueError("WG-GRID-MANIFEST: unknown or duplicate chunk")
        if (
            chunk.layer != manifest.layer
            or chunk.width != descriptor.width
            or chunk.height != descriptor.height
            or hashlib.sha256(chunk.encode()).hexdigest() != descriptor.sha256
        ):
            raise ValueError("WG-GRID-MANIFEST: corrupt or mismatched chunk")
        origin_x = chunk.chunk_x * manifest.chunk_width
        origin_y = chunk.chunk_y * manifest.chunk_height
        for dy in range(chunk.height):
            for dx in range(chunk.width):
                source = dy * chunk.width + dx
                target = manifest.grid.index(origin_x + dx, origin_y + dy)
                values[target] = chunk.values[source]
        seen.add(key)
    if seen != set(expected):
        raise ValueError("WG-GRID-MANIFEST: incomplete chunk coverage")
    return IntGrid(manifest.grid, tuple(values))


class DenseGridRepository:
    """Confined atomic storage for canonical uncompressed grid chunks."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, layer: str, coordinate: ChunkCoordinate) -> Path:
        if not _LAYER.fullmatch(layer):
            raise ValueError("WG-GRID-PATH: invalid layer")
        return self.root / layer / f"{coordinate.y:06d}_{coordinate.x:06d}.grid"

    def put(self, manifest: DenseGridManifest, chunks: Iterable[GridChunk]) -> tuple[Path, ...]:
        expected = {(item.chunk_x, item.chunk_y): item for item in manifest.chunks}
        written: list[Path] = []
        seen: set[tuple[int, int]] = set()
        for chunk in chunks:
            key = (chunk.chunk_x, chunk.chunk_y)
            descriptor = expected.get(key)
            encoded = chunk.encode()
            if (
                descriptor is None
                or key in seen
                or chunk.layer != manifest.layer
                or chunk.width != descriptor.width
                or chunk.height != descriptor.height
                or hashlib.sha256(encoded).hexdigest() != descriptor.sha256
            ):
                raise ValueError("WG-GRID-PUBLISH: chunk does not match manifest")
            path = self._path(manifest.layer, chunk.coordinate)
            atomic_write_bytes(path, encoded)
            written.append(path)
            seen.add(key)
        if seen != set(expected):
            raise ValueError("WG-GRID-PUBLISH: incomplete chunk coverage")
        return tuple(written)

    def iter_verified(self, manifest: DenseGridManifest) -> Iterator[GridChunk]:
        for descriptor in manifest.chunks:
            coordinate = ChunkCoordinate(descriptor.chunk_x, descriptor.chunk_y)
            path = self._path(manifest.layer, coordinate)
            try:
                encoded = path.read_bytes()
            except FileNotFoundError as error:
                raise ValueError("WG-GRID-READ: missing chunk") from error
            if hashlib.sha256(encoded).hexdigest() != descriptor.sha256:
                raise ValueError("WG-GRID-READ: corrupt chunk hash")
            chunk = GridChunk.decode(encoded)
            if (
                chunk.layer != manifest.layer
                or chunk.coordinate != coordinate
                or chunk.width != descriptor.width
                or chunk.height != descriptor.height
            ):
                raise ValueError("WG-GRID-READ: chunk metadata mismatch")
            yield chunk

    def load(self, manifest: DenseGridManifest) -> IntGrid[int]:
        return reconstruct_grid(manifest, self.iter_verified(manifest))
