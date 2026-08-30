"""Deterministic art direction derived from maps, climate, cultures, and Bible refs."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .models import BibleV2
from .views import WorldView


@dataclass(frozen=True)
class ArtDirectionV2:
    map_artifact_id: str
    climate_artifact_id: str
    accepted_bible_refs: tuple[str, ...]
    climate_palettes: dict[str, str]
    culture_motifs: dict[str, str]
    world_map: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def derive_art_direction(world: WorldView, bible: BibleV2) -> ArtDirectionV2:
    if set(bible.authoritative_refs) != set(world.artifact_ids.values()):
        raise ValueError("art direction requires a Bible accepted for this exact world")
    regimes = sorted({claim.climate_regime for claim in bible.regions})
    palettes = {
        str(regime): (
            "iron grey, cold blue"
            if regime <= 1
            else "ochre, moss green"
            if regime <= 3
            else "deep green, storm violet"
        )
        for regime in regimes
    }
    motifs = {
        claim.civilization_id: f"{claim.government}; {claim.name} heraldic geometry"
        for claim in bible.civilizations
    }
    maps = world.payload("maps")
    rasters = maps["rasters"]
    return ArtDirectionV2(
        world.artifact_ids["maps"],
        world.artifact_ids["climate"],
        bible.authoritative_refs,
        palettes,
        motifs,
        rasters["world"]["path"],
    )
