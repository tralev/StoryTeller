"""Immutable canonical world-grid primitives."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Iterator, TypeVar

from .artifacts import GridChunk

T = TypeVar("T", bound=int)


@dataclass(frozen=True, order=True)
class Coordinate:
    x: int
    y: int


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
        return Coordinate(index % self.width, index // self.width)

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
