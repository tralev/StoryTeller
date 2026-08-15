"""P8.C05D — Entity, temporal, and reverse-reference indexes.

Built from authoritative physical-world and history artifacts.
Index corruption invalidates only derived indexes; rebuild produces
canonical equality.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from .physical_models import (
    Deposit, EcologyLayer, Hydrology, Lake, PhysicalRegion, RegionLayer,
    ResourceLayer, RiverEdge, Route, RouteLayer, Species, Terrain,
)
from .artifacts import canonical_json


@dataclass(frozen=True)
class ReferenceIndex:
    """Lazy-lookup index over entities, temporal ranges, and reverse references."""

    algorithm_version: int
    # Entity → metadata lookups
    region_by_id: dict[str, PhysicalRegion]
    route_by_id: dict[str, Route]
    lake_by_id: dict[str, Lake]
    species_by_id: dict[str, Species]
    deposit_by_id: dict[str, Deposit]
    # Reverse references
    routes_through_region: dict[str, tuple[str, ...]]
    deposits_in_region: dict[str, tuple[str, ...]]
    species_in_biome: dict[int, tuple[str, ...]]
    # Cell → features
    rivers_by_cell: dict[int, tuple[str, ...]]  # cell index → river edge IDs
    lakes_by_cell: dict[int, tuple[str, ...]]   # cell index → lake IDs
    temporal_ranges: dict[str, tuple[int, int | None]]
    MAX_QUERY_RESULTS = 256

    @classmethod
    def build(
        cls, terrain: Terrain, hydrology: Hydrology,
        regions: RegionLayer, routes: RouteLayer,
        resources: ResourceLayer,
        ecology: EcologyLayer | None = None,
    ) -> "ReferenceIndex":
        # Region lookups
        region_by_id = {r.region_id: r for r in regions.regions}
        route_by_id = {r.route_id: r for r in routes.routes}
        lake_by_id = {l.lake_id: l for l in hydrology.lakes}

        # Species lookup
        species_by_id: dict[str, Species] = {}
        if ecology:
            species_by_id = {s.species_id: s for s in ecology.species}

        # Deposit lookup
        deposit_by_id = {d.deposit_id: d for d in resources.deposits}

        # Routes through region
        routes_through: dict[str, list[str]] = {r.region_id: [] for r in regions.regions}
        for route in routes.routes:
            if route.start_region in routes_through:
                routes_through[route.start_region].append(route.route_id)
            if route.end_region in routes_through:
                routes_through[route.end_region].append(route.route_id)

        # Deposits in region
        cell_to_region = {cell: num for cell, num in enumerate(regions.cell_region.values)
                          if num > 0}
        deposits_in: dict[str, list[str]] = {r.region_id: [] for r in regions.regions}
        for deposit in resources.deposits:
            for cell in deposit.cells:
                region_num = cell_to_region.get(cell, 0)
                if region_num > 0:
                    rid = f"region_{region_num:05d}"
                    if deposit.deposit_id not in deposits_in[rid]:
                        deposits_in[rid].append(deposit.deposit_id)

        # Species in biome
        species_in_biome: dict[int, list[str]] = {}
        if ecology:
            for species in ecology.species:
                for biome in species.habitat_biomes:
                    species_in_biome.setdefault(biome, []).append(species.species_id)

        # Rivers at cell
        rivers_at_cell: dict[int, list[str]] = {}
        for i, edge in enumerate(hydrology.rivers):
            rid = f"river_{i:05d}"
            rivers_at_cell.setdefault(edge.upstream, []).append(rid)
            rivers_at_cell.setdefault(edge.downstream, []).append(rid)

        # Lakes at cell
        lakes_at_cell: dict[int, list[str]] = {}
        for lake in hydrology.lakes:
            for cell in lake.cells:
                lakes_at_cell.setdefault(cell, []).append(lake.lake_id)

        return cls(
            1,
            region_by_id, route_by_id, lake_by_id, species_by_id, deposit_by_id,
            {k: tuple(sorted(v)) for k, v in routes_through.items()},
            {k: tuple(sorted(v)) for k, v in deposits_in.items()},
            {k: tuple(sorted(v)) for k, v in species_in_biome.items()},
            {k: tuple(sorted(v)) for k, v in rivers_at_cell.items()},
            {k: tuple(sorted(v)) for k, v in lakes_at_cell.items()},
            {entity_id: (0, None) for entity_id in sorted(
                (*region_by_id, *route_by_id, *lake_by_id, *species_by_id, *deposit_by_id))},
        )

    def region(self, region_id: str) -> PhysicalRegion | None:
        return self.region_by_id.get(region_id)

    def route(self, route_id: str) -> Route | None:
        return self.route_by_id.get(route_id)

    def lake(self, lake_id: str) -> Lake | None:
        return self.lake_by_id.get(lake_id)

    def species(self, species_id: str) -> Species | None:
        return self.species_by_id.get(species_id)

    def deposit(self, deposit_id: str) -> Deposit | None:
        return self.deposit_by_id.get(deposit_id)

    def routes_for_region(self, region_id: str) -> tuple[str, ...]:
        return self.routes_through_region.get(region_id, ())

    def deposits_for_region(self, region_id: str) -> tuple[str, ...]:
        return self.deposits_in_region.get(region_id, ())

    def species_for_biome(self, biome_id: int) -> tuple[str, ...]:
        return self.species_in_biome.get(biome_id, ())

    def rivers_crossing_cell(self, cell_index: int) -> tuple[str, ...]:
        return self.rivers_by_cell.get(cell_index, ())

    def lake_at_cell(self, cell_index: int) -> tuple[str, ...]:
        return self.lakes_by_cell.get(cell_index, ())

    def active_between(self, start: int, end: int, *, limit: int = MAX_QUERY_RESULTS) -> tuple[str, ...]:
        if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int)
                or not isinstance(end, int) or start > end):
            raise ValueError("WG-INDEX-QUERY: invalid temporal range")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_QUERY_RESULTS:
            raise ValueError("WG-INDEX-QUERY: invalid result limit")
        return tuple(entity_id for entity_id, (first, last) in sorted(self.temporal_ranges.items())
                     if first <= end and (last is None or start <= last))[:limit]


def reference_index_payload(index: ReferenceIndex, sources: Mapping[str, str]) -> dict[str, object]:
    return {
        "format": "storyteller.reference-index.v1", "sources": dict(sources),
        "entities": {
            "regions": tuple(sorted(index.region_by_id)), "routes": tuple(sorted(index.route_by_id)),
            "lakes": tuple(sorted(index.lake_by_id)), "species": tuple(sorted(index.species_by_id)),
            "deposits": tuple(sorted(index.deposit_by_id)),
        },
        "routes_through_region": index.routes_through_region,
        "deposits_in_region": index.deposits_in_region,
        "species_in_biome": {str(key): value for key, value in index.species_in_biome.items()},
        "rivers_by_cell": {str(key): value for key, value in index.rivers_by_cell.items()},
        "lakes_by_cell": {str(key): value for key, value in index.lakes_by_cell.items()},
        "temporal_ranges": index.temporal_ranges,
        "max_query_results": ReferenceIndex.MAX_QUERY_RESULTS,
    }


def validate_reference_index_payload(payload: Mapping[str, object], expected: Mapping[str, object],
                                     dependencies: tuple[str, ...]) -> None:
    if canonical_json(payload) != canonical_json(expected):
        raise ValueError("WG-INDEX: reference index does not match authoritative rebuild")
    sources = payload.get("sources")
    if not isinstance(sources, Mapping) or not set(sources.values()) <= set(dependencies):
        raise ValueError("WG-INDEX: reference index provenance mismatch")
