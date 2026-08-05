"""Typed read-only query facade over Phase 2 and Phase 3 artifacts."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..worldgen.artifacts import WorldArtifactRepository

REQUIRED_KINDS = ("world_index", "plates", "terrain", "geology", "hydrology", "climate",
                  "soil", "biomes", "resources", "species", "ecology", "regions", "routes", "maps",
                  "sites", "settlements", "civilizations",
                  "history", "snapshots", "registries", "identities", "simulation_index")


@dataclass(frozen=True)
class WorldFact:
    fact_id: str
    kind: str
    value: dict[str, Any]
    source_ids: tuple[str, ...]


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

    @property
    def present_year(self) -> int:
        return int(self._payloads["simulation_index"]["present_year"])

    def payload(self, kind: str) -> Any:
        if kind not in self._payloads:
            raise KeyError(kind)
        return self._payloads[kind]

    def regions(self) -> tuple[WorldFact, ...]:
        source = self._artifact_ids["regions"]
        biomes = self._payloads["biomes"]["biome_id"]["values"]
        climate = self._payloads["climate"]["weather_regime"]["values"]
        resources = self._payloads["resources"]
        deposits = resources["deposits"]
        result = []
        for region in self._payloads["regions"]["regions"]:
            center = int(region["center"])
            resource_names = sorted({deposit["resource"] for deposit in deposits
                                     if any(cell in set(region["cells"]) for cell in deposit["cells"])})
            value = dict(region)
            value.update({"biome_id": int(biomes[center]), "climate_regime": int(climate[center]),
                          "resources": resource_names})
            result.append(WorldFact(str(region["region_id"]), "region", value,
                                    (source, self._artifact_ids["biomes"], self._artifact_ids["climate"],
                                     self._artifact_ids["resources"])))
        return tuple(result)

    def routes(self) -> tuple[WorldFact, ...]:
        source = self._artifact_ids["routes"]
        return tuple(WorldFact(str(item["route_id"]), "route", dict(item), (source,))
                     for item in self._payloads["routes"]["routes"])

    def sites(self) -> tuple[WorldFact, ...]:
        source = self._artifact_ids["sites"]
        return tuple(WorldFact(str(item["site_id"]), "site", dict(item), (source,))
                     for item in self._payloads["sites"])

    def civilizations(self) -> tuple[WorldFact, ...]:
        source = self._artifact_ids["civilizations"]
        return tuple(WorldFact(str(item["civilization_id"]), "civilization", dict(item), (source,))
                     for item in self._payloads["civilizations"])

    def settlements(self) -> tuple[WorldFact, ...]:
        source = self._artifact_ids["settlements"]
        return tuple(WorldFact(str(item["settlement_id"]), "settlement", dict(item), (source,))
                     for item in self._payloads["settlements"])

    def cohorts(self) -> tuple[WorldFact, ...]:
        snapshot = self._payloads["snapshots"][-1]["state"]
        source = self._artifact_ids["snapshots"]
        return tuple(WorldFact(str(item["cohort_id"]), "cohort", dict(item), (source,))
                     for item in snapshot["cohorts"])

    def ecology(self) -> WorldFact:
        return WorldFact("world_ecology", "ecology", dict(self._payloads["ecology"]),
                         (self._artifact_ids["ecology"], self._artifact_ids["species"]))

    def registries(self) -> WorldFact:
        return WorldFact("world_registries", "registries", dict(self._payloads["registries"]),
                         (self._artifact_ids["registries"],))

    def events(self, kinds: Iterable[str] | None = None) -> tuple[WorldFact, ...]:
        selected = set(kinds) if kinds is not None else None
        source = self._artifact_ids["history"]
        return tuple(WorldFact(str(item["event_id"]), "event", dict(item), (source,))
                     for item in self._payloads["history"]
                     if selected is None or item["kind"] in selected)

    def identities(self) -> WorldFact:
        return WorldFact("world_identities", "identities", dict(self._payloads["identities"]),
                         (self._artifact_ids["identities"], self._artifact_ids["registries"]))

    def assert_unchanged(self, expected_hashes: dict[str, str]) -> None:
        for kind, expected in expected_hashes.items():
            actual = hashlib.sha256((self.root / "artifacts" / f"{kind}.json").read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f"WORLD-MUTATED: {kind}")
