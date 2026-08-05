"""Strict pre-freeze Bible v2 enrichment models."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

LOCAL_KINDS = frozenset({"building", "street", "cave", "ruin", "item", "minor_character"})


@dataclass(frozen=True)
class RegionClaim:
    region_id: str
    center: int
    biome_id: int
    climate_regime: int
    resources: tuple[str, ...]
    neighbors: tuple[str, ...]


@dataclass(frozen=True)
class RouteClaim:
    route_id: str
    start_region: str
    end_region: str


@dataclass(frozen=True)
class CivilizationClaim:
    civilization_id: str
    name: str
    government: str
    territory: tuple[str, ...]


@dataclass(frozen=True)
class EventClaim:
    event_id: str
    year: int
    causes: tuple[str, ...]


@dataclass(frozen=True)
class LocalEntity:
    entity_id: str
    kind: str
    name: str
    contained_by: str
    authoritative_refs: tuple[str, ...]


@dataclass(frozen=True)
class MagicClaim:
    claim_id: str
    statement: str
    epistemic_status: str
    authoritative_ref: str


@dataclass(frozen=True)
class BibleV2:
    schema_version: str
    title: str
    present_year: int
    authoritative_refs: tuple[str, ...]
    regions: tuple[RegionClaim, ...]
    routes: tuple[RouteClaim, ...]
    civilizations: tuple[CivilizationClaim, ...]
    history: tuple[EventClaim, ...]
    local_entities: tuple[LocalEntity, ...]
    magic_claims: tuple[MagicClaim, ...]
    interpretations: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != "2-pre1":
            raise ValueError("unsupported pre-freeze Bible schema")
        if not self.title.strip():
            raise ValueError("Bible title is required")
        if any(entity.kind not in LOCAL_KINDS for entity in self.local_entities):
            raise ValueError("unsupported local entity kind")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "BibleV2":
        required = {"schema_version", "title", "present_year", "authoritative_refs", "regions",
                    "routes", "civilizations", "history", "local_entities", "magic_claims", "interpretations"}
        if set(value) != required:
            raise ValueError("Bible fields do not match strict pre-freeze schema")
        return cls(str(value["schema_version"]), str(value["title"]), int(value["present_year"]),
                   tuple(value["authoritative_refs"]),
                   tuple(RegionClaim(item["region_id"], item["center"], item["biome_id"],
                                     item["climate_regime"], tuple(item["resources"]), tuple(item["neighbors"]))
                         for item in value["regions"]),
                   tuple(RouteClaim(**item) for item in value["routes"]),
                   tuple(CivilizationClaim(item["civilization_id"], item["name"], item["government"],
                                           tuple(item["territory"])) for item in value["civilizations"]),
                   tuple(EventClaim(item["event_id"], item["year"], tuple(item["causes"]))
                         for item in value["history"]),
                   tuple(LocalEntity(item["entity_id"], item["kind"], item["name"], item["contained_by"],
                                     tuple(item["authoritative_refs"])) for item in value["local_entities"]),
                   tuple(MagicClaim(**item) for item in value["magic_claims"]),
                   tuple(value["interpretations"]))
