"""Typed read-only query facade over Phase 2 and Phase 3 artifacts."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..worldgen.artifacts import WorldArtifactRepository
from ..worldgen.biome_reader import PersistedBiomes, VerifiedBiomeReader
from ..worldgen.climate_reader import PersistedClimate, VerifiedClimateReader
from ..worldgen.geology_reader import PersistedGeology, VerifiedGeologyReader
from ..worldgen.grid import IntGrid
from ..worldgen.hydrology_reader import PersistedHydrology, VerifiedHydrologyReader
from ..worldgen.index_reader import (
    VerifiedReferenceIndexReader,
    VerifiedSpatialIndexReader,
    VerifiedWorldIndex,
)
from ..worldgen.region_reader import PersistedRegions, VerifiedRegionReader
from ..worldgen.resource_reader import PersistedResources, VerifiedResourceReader
from ..worldgen.route_reader import PersistedRoutes, VerifiedRouteReader
from ..worldgen.terrain_reader import VerifiedTerrainReader

REQUIRED_KINDS = (
    "world_index",
    "plates",
    "terrain",
    "terrain_grid_catalog",
    "geology",
    "geology_grid_catalog",
    "hydrology",
    "hydrology_grid_catalog",
    "climate",
    "climate_grid_catalog",
    "soil",
    "soil_grid_catalog",
    "biomes",
    "biome_grid_catalog",
    "resources",
    "resource_grid_catalog",
    "species",
    "ecology",
    "regions",
    "region_grid_catalog",
    "routes",
    "spatial_index",
    "reference_index",
    "map_layers",
    "maps",
    "validation_report",
    "sites",
    "settlements",
    "civilizations",
    "economy",
    "history",
    "snapshots",
    "registries",
    "identities",
    "genealogy",
    "simulation_index",
    "megabeasts",
    "legendary_artifacts",
    "legendary_artifact_histories",
)


@dataclass(frozen=True)
class WorldFact:
    fact_id: str
    kind: str
    value: dict[str, Any]
    source_ids: tuple[str, ...]


@dataclass(frozen=True, order=True)
class AuthoritativeArtifactIdentity:
    """Verified identity of one retained authoritative artifact file."""

    kind: str
    artifact_id: str
    sha256: str


class WorldView:
    """Loads verified envelopes once and exposes typed, non-mutating queries."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.repository = WorldArtifactRepository(self.root / "artifacts")
        self._payloads: dict[str, Any] = {}
        self._artifact_ids: dict[str, str] = {}
        self._file_hashes: dict[str, str] = {}
        for kind in REQUIRED_KINDS:
            path = self.root / "artifacts" / f"{kind}.json"
            if not path.is_file():
                raise ValueError(f"WORLD-INCOMPLETE: missing required artifact {kind}")
            artifact = self.repository.load_verified(kind)
            self._payloads[kind] = artifact.payload
            self._artifact_ids[kind] = artifact.artifact_id
            self._file_hashes[kind] = hashlib.sha256(path.read_bytes()).hexdigest()

    @property
    def artifact_ids(self) -> dict[str, str]:
        return dict(self._artifact_ids)

    @property
    def file_hashes(self) -> dict[str, str]:
        return dict(self._file_hashes)

    def authoritative_inventory(self) -> tuple[AuthoritativeArtifactIdentity, ...]:
        """Return the complete verified artifact inventory, not only query prerequisites."""
        inventory = []
        for path in sorted((self.root / "artifacts").glob("*.json"), key=lambda item: item.name):
            artifact = self.repository.load_verified(path.stem)
            inventory.append(
                AuthoritativeArtifactIdentity(
                    path.stem,
                    artifact.artifact_id,
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )
        return tuple(inventory)

    @property
    def present_year(self) -> int:
        return int(self._payloads["simulation_index"]["present_year"])

    def payload(self, kind: str) -> Any:
        if kind not in self._payloads:
            raise KeyError(kind)
        return self._payloads[kind]

    def terrain_elevation(self) -> IntGrid[int]:
        """Load authoritative elevation through its verified chunk manifest."""
        return VerifiedTerrainReader(self.root).load().elevation_mm

    def hydrology(self) -> PersistedHydrology:
        """Load the complete authoritative hydrology through verified chunks."""
        return VerifiedHydrologyReader(self.root).load()

    def geology(self) -> PersistedGeology:
        """Load authoritative geology through verified chunks."""
        return VerifiedGeologyReader(self.root).load()

    def climate(self) -> PersistedClimate:
        """Load the complete authoritative climate through verified chunks."""
        return VerifiedClimateReader(self.root).load()

    def biomes(self) -> PersistedBiomes:
        """Load authoritative biome and soil fields through verified chunks."""
        return VerifiedBiomeReader(self.root).load()

    def resources(self) -> PersistedResources:
        """Load authoritative resource fields through verified chunks."""
        return VerifiedResourceReader(self.root).load()

    def region_layer(self) -> PersistedRegions:
        """Load region ownership and records through the verified region reader."""
        return VerifiedRegionReader(self.root).load()

    def route_layer(self) -> PersistedRoutes:
        """Load the sparse route graph through its verified typed reader."""
        return VerifiedRouteReader(self.root).load()

    def spatial_index(self) -> VerifiedSpatialIndexReader:
        return VerifiedSpatialIndexReader(self.root)

    def reference_index(self) -> VerifiedReferenceIndexReader:
        return VerifiedReferenceIndexReader(self.root)

    def indexes(self) -> VerifiedWorldIndex:
        return VerifiedWorldIndex(self.root)

    def regions(self) -> tuple[WorldFact, ...]:
        source = self._artifact_ids["regions"]
        biomes = self.biomes().biomes.biome_id.values
        climate = self.climate().climate.weather_regime.values
        deposits = self.resources().resources.deposits
        result = []
        for typed_region in self.region_layer().regions.regions:
            region_cells = set(typed_region.cells)
            region = {
                "region_id": typed_region.region_id,
                "cells": typed_region.cells,
                "center": typed_region.center,
                "area_m2": typed_region.area_m2,
                "boundary_cells": typed_region.boundary_cells,
                "neighbors": typed_region.neighbors,
            }
            center = typed_region.center
            resource_names = sorted(
                {
                    deposit.resource
                    for deposit in deposits
                    if any(cell in region_cells for cell in deposit.cells)
                }
            )
            value = dict(region)
            value.update(
                {
                    "biome_id": int(biomes[center]),
                    "climate_regime": int(climate[center]),
                    "resources": resource_names,
                }
            )
            result.append(
                WorldFact(
                    str(region["region_id"]),
                    "region",
                    value,
                    (
                        source,
                        self._artifact_ids["biomes"],
                        self._artifact_ids["climate"],
                        self._artifact_ids["resources"],
                    ),
                )
            )
        return tuple(result)

    def routes(self) -> tuple[WorldFact, ...]:
        source = self._artifact_ids["routes"]
        return tuple(
            WorldFact(
                item.route_id,
                "route",
                {
                    "route_id": item.route_id,
                    "start_region": item.start_region,
                    "end_region": item.end_region,
                    "cells": item.cells,
                    "distance_m": item.distance_m,
                    "terrain_cost": item.terrain_cost,
                    "river_crossings": item.river_crossings,
                    "seasonal_risk_ppm": item.seasonal_risk_ppm,
                    "seasonal_capacity": item.seasonal_capacity,
                    "route_kind": item.route_kind,
                    "seasonal_cells": item.seasonal_cells,
                    "traversable_seasons": item.traversable_seasons,
                    "cost_unit": item.cost_unit,
                    "annual_maintenance": item.annual_maintenance,
                    "source_ids": item.source_ids,
                },
                (source,),
            )
            for item in self.route_layer().routes.routes
        )

    def sites(self) -> tuple[WorldFact, ...]:
        source = self._artifact_ids["sites"]
        return tuple(
            WorldFact(str(item["site_id"]), "site", dict(item), (source,))
            for item in self._payloads["sites"]
        )

    def civilizations(self) -> tuple[WorldFact, ...]:
        source = self._artifact_ids["civilizations"]
        return tuple(
            WorldFact(str(item["civilization_id"]), "civilization", dict(item), (source,))
            for item in self._payloads["civilizations"]
        )

    def people(self) -> tuple[WorldFact, ...]:
        """Return consequential people with their final event-sourced status."""
        source = self._artifact_ids["genealogy"]
        payload = self._payloads["genealogy"]
        statuses = {str(item["person_id"]): item for item in payload["person_statuses"]}
        result = []
        for person in payload["people"]:
            value = dict(person)
            transition = statuses.get(str(person["person_id"]))
            value["status"] = str(transition["new_status"]) if transition else "living"
            value["status_year"] = int(transition["year"]) if transition else None
            result.append(WorldFact(str(person["person_id"]), "person", value, (source,)))
        return tuple(result)

    def settlements(self) -> tuple[WorldFact, ...]:
        source = self._artifact_ids["settlements"]
        return tuple(
            WorldFact(str(item["settlement_id"]), "settlement", dict(item), (source,))
            for item in self._payloads["settlements"]
        )

    def cohorts(self) -> tuple[WorldFact, ...]:
        snapshot = self._payloads["snapshots"][-1]["state"]
        source = self._artifact_ids["snapshots"]
        return tuple(
            WorldFact(str(item["cohort_id"]), "cohort", dict(item), (source,))
            for item in snapshot["cohorts"]
        )

    def ecology(self) -> WorldFact:
        return WorldFact(
            "world_ecology",
            "ecology",
            dict(self._payloads["ecology"]),
            (self._artifact_ids["ecology"], self._artifact_ids["species"]),
        )

    def registries(self) -> WorldFact:
        return WorldFact(
            "world_registries",
            "registries",
            dict(self._payloads["registries"]),
            (self._artifact_ids["registries"],),
        )

    def events(self, kinds: Iterable[str] | None = None) -> tuple[WorldFact, ...]:
        selected = set(kinds) if kinds is not None else None
        source = self._artifact_ids["history"]
        return tuple(
            WorldFact(str(item["event_id"]), "event", dict(item), (source,))
            for item in self._payloads["history"]
            if selected is None or item["kind"] in selected
        )

    def megabeasts(self) -> tuple[WorldFact, ...]:
        """Return each megabeast merged with its final event-sourced region/condition."""
        source = self._artifact_ids["megabeasts"]
        payload = self._payloads["megabeasts"]
        finals: dict[str, dict[str, Any]] = {}
        for entry in payload["history"]:
            beast_id = str(entry["megabeast_id"])
            current = finals.get(beast_id)
            if current is None or int(entry["year"]) >= int(current["year"]):
                finals[beast_id] = entry
        result = []
        for beast in payload["entities"]:
            beast_id = str(beast["megabeast_id"])
            value = dict(beast)
            final = finals.get(beast_id)
            value["region_id"] = (
                str(final["new_region_id"]) if final else str(beast["origin_region_id"])
            )
            value["condition"] = (
                str(final["new_condition"]) if final else str(beast["initial_condition"])
            )
            result.append(WorldFact(beast_id, "megabeast", value, (source,)))
        return tuple(result)

    def legendary_artifacts(self) -> tuple[WorldFact, ...]:
        """Return each legendary artifact merged with its final event-sourced status."""
        source = self._artifact_ids["legendary_artifacts"]
        history_source = self._artifact_ids["legendary_artifact_histories"]
        finals: dict[str, dict[str, Any]] = {}
        for entry in self._payloads["legendary_artifact_histories"]:
            artifact_id = str(entry["artifact_id"])
            current = finals.get(artifact_id)
            if current is None or int(entry["year"]) >= int(current["year"]):
                finals[artifact_id] = entry
        result = []
        for artifact in self._payloads["legendary_artifacts"]:
            artifact_id = str(artifact["artifact_id"])
            value = dict(artifact)
            final = finals.get(artifact_id)
            value["owner_id"] = (
                str(final["new_owner_id"]) if final else str(artifact["creator_id"])
            )
            value["current_site_id"] = (
                str(final["new_site_id"]) if final else str(artifact["site_id"])
            )
            value["status"] = str(final["new_status"]) if final else "intact"
            result.append(
                WorldFact(artifact_id, "legendary_artifact", value, (source, history_source)),
            )
        return tuple(result)

    def identities(self) -> WorldFact:
        return WorldFact(
            "world_identities",
            "identities",
            dict(self._payloads["identities"]),
            (self._artifact_ids["identities"], self._artifact_ids["registries"]),
        )

    def assert_unchanged(self, expected_hashes: dict[str, str]) -> None:
        for kind, expected in expected_hashes.items():
            actual = hashlib.sha256(
                (self.root / "artifacts" / f"{kind}.json").read_bytes()
            ).hexdigest()
            if actual != expected:
                raise ValueError(f"WORLD-MUTATED: {kind}")

    def assert_inventory_unchanged(
        self,
        expected: tuple[AuthoritativeArtifactIdentity, ...],
    ) -> None:
        """Detect changed, deleted, or newly injected authoritative artifacts."""
        actual_names = tuple(sorted(path.stem for path in (self.root / "artifacts").glob("*.json")))
        expected_names = tuple(item.kind for item in expected)
        if actual_names != expected_names:
            raise ValueError("WORLD-MUTATED: authoritative artifact inventory changed")
        for item in expected:
            path = self.root / "artifacts" / f"{item.kind}.json"
            if hashlib.sha256(path.read_bytes()).hexdigest() != item.sha256:
                raise ValueError(f"WORLD-MUTATED: {item.kind}")
            if self.repository.load_verified(item.kind).artifact_id != item.artifact_id:
                raise ValueError(f"WORLD-MUTATED: {item.kind} identity")
