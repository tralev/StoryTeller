"""Attributed cosmology and place-bound supernatural culture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from ..numeric import identity, stable_id
from .magic import EpistemicStatus, MagicLaw, MagicSource, Religion
from .registries import simulation_registry_entries


@dataclass(frozen=True)
class CosmologicalLayer:
    layer_id: str
    order: int
    name: str
    claim: str
    attributed_to: str
    epistemic_status: EpistemicStatus


@dataclass(frozen=True)
class CelestialCycle:
    cycle_id: str
    name: str
    period_months: int
    phase_offset_months: int
    interpreted_claim: str
    attributed_to: str
    epistemic_status: EpistemicStatus


@dataclass(frozen=True)
class AttributedEntity:
    entity_id: str
    entity_kind: str
    name: str
    layer_id: str
    claim: str
    attributed_to: str
    epistemic_status: EpistemicStatus


@dataclass(frozen=True)
class AfterlifeClaim:
    claim_id: str
    destination_layer_id: str
    claim: str
    attributed_to: str
    epistemic_status: EpistemicStatus


@dataclass(frozen=True)
class SupernaturalPlace:
    place_id: str
    site_id: str
    phenomenon_kind: str
    description: str
    law_id: str
    source_id: str


@dataclass(frozen=True)
class Cult:
    cult_id: str
    religion_id: str
    entity_id: str
    site_id: str
    rite: str


@dataclass(frozen=True)
class SacredRelic:
    relic_id: str
    religion_id: str
    site_id: str
    name: str
    attributed_power: str
    attributed_to: str
    epistemic_status: EpistemicStatus


class CosmologyBundle(NamedTuple):
    layers: tuple[CosmologicalLayer, ...]
    cycles: tuple[CelestialCycle, ...]
    entities: tuple[AttributedEntity, ...]
    afterlife_claims: tuple[AfterlifeClaim, ...]
    places: tuple[SupernaturalPlace, ...]
    cults: tuple[Cult, ...]
    relics: tuple[SacredRelic, ...]


def validate_cosmology(
    bundle: CosmologyBundle,
    laws: tuple[MagicLaw, ...],
    sources: tuple[MagicSource, ...],
    religions: tuple[Religion, ...],
    site_ids: tuple[str, ...],
) -> None:
    layer_ids = {layer.layer_id for layer in bundle.layers}
    if (
        not bundle.layers
        or len(layer_ids) != len(bundle.layers)
        or tuple(layer.order for layer in bundle.layers) != tuple(range(len(bundle.layers)))
    ):
        raise ValueError("WG-COSMOLOGY-LAYERS: layers must have unique IDs and contiguous order")
    attributions = (
        *((item.attributed_to, item.epistemic_status) for item in bundle.layers),
        *((item.attributed_to, item.epistemic_status) for item in bundle.cycles),
        *((item.attributed_to, item.epistemic_status) for item in bundle.entities),
        *((item.attributed_to, item.epistemic_status) for item in bundle.afterlife_claims),
        *((item.attributed_to, item.epistemic_status) for item in bundle.relics),
    )
    if any(
        not attributed_to or not isinstance(status, EpistemicStatus)
        for attributed_to, status in attributions
    ):
        raise ValueError("WG-COSMOLOGY-ATTRIBUTION: claim lacks attribution or epistemic status")
    if any(
        cycle.period_months <= 0 or not 0 <= cycle.phase_offset_months < cycle.period_months
        for cycle in bundle.cycles
    ):
        raise ValueError("WG-COSMOLOGY-CYCLE: invalid celestial period or phase")
    allowed_entities = {"deity", "spirit", "demon", "saint", "false_entity"}
    entity_ids = {entity.entity_id for entity in bundle.entities}
    if len(entity_ids) != len(bundle.entities) or any(
        entity.entity_kind not in allowed_entities or entity.layer_id not in layer_ids
        for entity in bundle.entities
    ):
        raise ValueError("WG-COSMOLOGY-ENTITY: invalid attributed entity")
    if any(claim.destination_layer_id not in layer_ids for claim in bundle.afterlife_claims):
        raise ValueError("WG-COSMOLOGY-AFTERLIFE: destination layer is unknown")
    law_ids = {law.law_id for law in laws}
    source_by_id = {source.source_id: source for source in sources}
    known_sites = set(site_ids)
    place_ids = {place.place_id for place in bundle.places}
    if len(place_ids) != len(bundle.places) or any(
        place.site_id not in known_sites
        or place.phenomenon_kind not in {"hazard", "resource"}
        or place.law_id not in law_ids
        or place.source_id not in source_by_id
        or source_by_id[place.source_id].location_id != place.site_id
        or source_by_id[place.source_id].law_id != place.law_id
        for place in bundle.places
    ):
        raise ValueError("WG-COSMOLOGY-PLACE: invalid place-bound supernatural phenomenon")
    religion_ids = {religion.religion_id for religion in religions}
    if any(
        cult.religion_id not in religion_ids
        or cult.entity_id not in entity_ids
        or cult.site_id not in known_sites
        or not cult.rite
        for cult in bundle.cults
    ):
        raise ValueError("WG-COSMOLOGY-CULT: invalid cult, rite, or site")
    if any(
        relic.religion_id not in religion_ids
        or relic.site_id not in known_sites
        or not relic.attributed_power
        for relic in bundle.relics
    ):
        raise ValueError("WG-COSMOLOGY-RELIC: invalid attributed relic")


def generate_cosmology(
    seed: int,
    laws: tuple[MagicLaw, ...],
    sources: tuple[MagicSource, ...],
    religions: tuple[Religion, ...],
    site_ids: tuple[str, ...],
) -> CosmologyBundle:
    entries = simulation_registry_entries("beliefs")
    raw = next(entry for entry in entries if entry["id"] == "cosmology_v1")
    layer_names = raw["layers"]
    cycles_raw = raw["cycles"]
    entity_kinds = raw["entity_kinds"]
    if (
        not isinstance(layer_names, tuple)
        or not isinstance(cycles_raw, tuple)
        or not isinstance(entity_kinds, tuple)
    ):
        raise ValueError("WG-COSMOLOGY-REGISTRY: cosmology collections must be tuples")
    attribution = "keeper_circle"
    layers = tuple(
        CosmologicalLayer(
            stable_id("cosmological_layer", seed, identity("layer_index", index)),
            index,
            str(name),
            f"{name} surrounds the mortal world",
            attribution,
            EpistemicStatus.UNCERTAIN,
        )
        for index, name in enumerate(layer_names)
    )
    cycles: list[CelestialCycle] = []
    for cycle_raw in cycles_raw:
        if not isinstance(cycle_raw, dict):
            raise ValueError("WG-COSMOLOGY-REGISTRY: cycle must be a mapping")
        period = cycle_raw["period_months"]
        if isinstance(period, bool) or not isinstance(period, int):
            raise ValueError("WG-COSMOLOGY-REGISTRY: cycle period must be an integer")
        name = str(cycle_raw["name"])
        cycles.append(
            CelestialCycle(
                stable_id("celestial_cycle", seed, identity("cycle_index", len(cycles))),
                name,
                period,
                seed % period,
                f"the {name} marks passages between layers",
                attribution,
                EpistemicStatus.METAPHORICAL,
            )
        )
    entities = tuple(
        AttributedEntity(
            stable_id("cosmological_entity", seed, identity("kind", str(kind))),
            str(kind),
            f"The {str(kind).replace('_', ' ').title()}",
            layers[index % len(layers)].layer_id,
            f"a {str(kind).replace('_', ' ')} watches the {layers[index % len(layers)].name}",
            attribution,
            EpistemicStatus.FALSE if kind == "false_entity" else EpistemicStatus.UNCERTAIN,
        )
        for index, kind in enumerate(entity_kinds)
    )
    afterlife = (
        AfterlifeClaim(
            stable_id("afterlife_claim", seed, identity("layer_id", layers[-1].layer_id)),
            layers[-1].layer_id,
            f"the remembered dead travel to {layers[-1].name}",
            attribution,
            EpistemicStatus.UNCERTAIN,
        ),
    )
    source_by_site = {source.location_id: source for source in sources}
    places = tuple(
        SupernaturalPlace(
            stable_id("supernatural_place", seed, identity("site_id", site_id)),
            site_id,
            "hazard" if index % 2 == 0 else "resource",
            "light-draining resonance" if index % 2 == 0 else "light-bearing resonance",
            source.law_id,
            source.source_id,
        )
        for index, site_id in enumerate(site_ids)
        if (source := source_by_site.get(site_id))
    )
    cults = tuple(
        Cult(
            stable_id("cult", seed, identity("religion_id", religion.religion_id)),
            religion.religion_id,
            entities[index % len(entities)].entity_id,
            religion.holy_site_id,
            str(raw["rite"]),
        )
        for index, religion in enumerate(religions)
    )
    relics = tuple(
        SacredRelic(
            stable_id("sacred_relic", seed, identity("religion_id", religion.religion_id)),
            religion.religion_id,
            religion.holy_site_id,
            f"Waystone of {index + 1}",
            "said to remember every pilgrim",
            cult.cult_id,
            EpistemicStatus.UNCERTAIN,
        )
        for index, (religion, cult) in enumerate(zip(religions, cults))
    )
    result = CosmologyBundle(layers, tuple(cycles), entities, afterlife, places, cults, relics)
    validate_cosmology(result, laws, sources, religions, site_ids)
    return result
