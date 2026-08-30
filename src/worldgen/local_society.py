"""Deterministic cultural layouts and persistent smaller local entities."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .local_boundaries import LocalBoundaryConditions
from .numeric import div_floor_exact, identity, rng_for_decision, stable_id

LAYOUT_STYLES = ("courtyard", "linear", "ring", "terraced")
WALL_MATERIALS = ("earth", "stone", "timber")
ROOF_FORMS = ("flat", "gabled", "vaulted")


@dataclass(frozen=True)
class CulturalLocalLayout:
    style_id: str
    street_axis: str
    wall_material: str
    roof_form: str
    parcel_radius: int
    civilization_id: str
    culture: str
    settlement_status: str
    source_ids: tuple[str, ...]


@dataclass(frozen=True, order=True)
class PersistentLocalEntity:
    entity_id: str
    kind: str
    cell: tuple[int, int, int]
    civilization_id: str
    settlement_id: str
    status: str
    source_ids: tuple[str, ...]


def derive_cultural_layout(
    seed: int,
    boundary: LocalBoundaryConditions,
) -> CulturalLocalLayout:
    """Derive bounded layout vocabulary from culture without race rules."""
    key = f"{boundary.civilization_id}:{boundary.culture}:{boundary.settlement_status}"
    rng = rng_for_decision(seed, "local_layout", key, "cultural_form")
    return CulturalLocalLayout(
        LAYOUT_STYLES[rng.below(len(LAYOUT_STYLES))],
        ("east_west", "north_south")[rng.below(2)],
        WALL_MATERIALS[rng.below(len(WALL_MATERIALS))],
        ROOF_FORMS[rng.below(len(ROOF_FORMS))],
        2 + rng.below(2),
        boundary.civilization_id,
        boundary.culture,
        boundary.settlement_status,
        boundary.source_artifact_ids,
    )


def generate_persistent_local_entities(
    seed: int,
    boundary: LocalBoundaryConditions,
    building_cells: tuple[tuple[int, int, int], ...],
) -> tuple[PersistentLocalEntity, ...]:
    """Create a small retained identity layer without duplicating population."""
    if not building_cells:
        raise ValueError("WG-LOCAL-ENTITY: entity containment requires a building")
    count = min(4, max(1, div_floor_exact(boundary.settlement_population, 1_000)))
    kind = "resident" if boundary.settlement_status == "inhabited" else "site_caretaker"
    status = "active" if boundary.settlement_status == "inhabited" else "dormant"
    return tuple(
        PersistentLocalEntity(
            stable_id(
                "local_entity",
                seed,
                identity("site_id", boundary.site_id),
                identity("ordinal", ordinal),
                identity("kind", kind),
            ),
            kind,
            building_cells[ordinal % len(building_cells)],
            boundary.civilization_id,
            boundary.settlement_id,
            status,
            boundary.source_artifact_ids,
        )
        for ordinal in range(count)
    )


def validate_local_society(
    boundary: LocalBoundaryConditions,
    layout: CulturalLocalLayout,
    entities: tuple[PersistentLocalEntity, ...],
    building_cells: tuple[tuple[int, int, int], ...],
) -> None:
    if (
        layout.civilization_id != boundary.civilization_id
        or layout.culture != boundary.culture
        or layout.settlement_status != boundary.settlement_status
        or layout.source_ids != boundary.source_artifact_ids
        or layout.style_id not in LAYOUT_STYLES
        or layout.street_axis not in {"east_west", "north_south"}
        or layout.wall_material not in WALL_MATERIALS
        or layout.roof_form not in ROOF_FORMS
        or layout.parcel_radius not in {2, 3}
    ):
        raise ValueError("WG-LOCAL-LAYOUT: cultural layout contradicts boundary")
    if len({item.entity_id for item in entities}) != len(entities):
        raise ValueError("WG-LOCAL-ENTITY: duplicate persistent identity")
    building = set(building_cells)
    expected_status = "active" if boundary.settlement_status == "inhabited" else "dormant"
    if any(
        item.cell not in building
        or item.civilization_id != boundary.civilization_id
        or item.settlement_id != boundary.settlement_id
        or item.status != expected_status
        or item.source_ids != boundary.source_artifact_ids
        for item in entities
    ):
        raise ValueError("WG-LOCAL-ENTITY: identity contradicts containment or present state")


def cultural_layout_from_mapping(value: Mapping[str, object]) -> CulturalLocalLayout:
    expected = {
        "style_id",
        "street_axis",
        "wall_material",
        "roof_form",
        "parcel_radius",
        "civilization_id",
        "culture",
        "settlement_status",
        "source_ids",
    }
    if set(value) != expected:
        raise ValueError("WG-LOCAL-LAYOUT-READ: field set mismatch")
    texts = tuple(
        value[name]
        for name in (
            "style_id",
            "street_axis",
            "wall_material",
            "roof_form",
            "civilization_id",
            "culture",
            "settlement_status",
        )
    )
    radius, sources = value["parcel_radius"], value["source_ids"]
    if (
        any(not isinstance(item, str) for item in texts)
        or isinstance(radius, bool)
        or not isinstance(radius, int)
        or not isinstance(sources, Sequence)
        or isinstance(sources, (str, bytes))
        or any(not isinstance(item, str) for item in sources)
    ):
        raise ValueError("WG-LOCAL-LAYOUT-READ: invalid field type")
    return CulturalLocalLayout(
        str(texts[0]),
        str(texts[1]),
        str(texts[2]),
        str(texts[3]),
        radius,
        str(texts[4]),
        str(texts[5]),
        str(texts[6]),
        tuple(str(item) for item in sources),
    )


def persistent_entity_from_mapping(value: Mapping[str, object]) -> PersistentLocalEntity:
    expected = {
        "entity_id",
        "kind",
        "cell",
        "civilization_id",
        "settlement_id",
        "status",
        "source_ids",
    }
    if set(value) != expected:
        raise ValueError("WG-LOCAL-ENTITY-READ: field set mismatch")
    cell, sources = value["cell"], value["source_ids"]
    names = tuple(
        value[name]
        for name in (
            "entity_id",
            "kind",
            "civilization_id",
            "settlement_id",
            "status",
        )
    )
    if (
        any(not isinstance(item, str) for item in names)
        or not isinstance(cell, Sequence)
        or isinstance(cell, (str, bytes))
        or len(cell) != 3
        or any(isinstance(item, bool) or not isinstance(item, int) for item in cell)
        or not isinstance(sources, Sequence)
        or isinstance(sources, (str, bytes))
        or any(not isinstance(item, str) for item in sources)
    ):
        raise ValueError("WG-LOCAL-ENTITY-READ: invalid field type")
    return PersistentLocalEntity(
        str(names[0]),
        str(names[1]),
        (int(cell[0]), int(cell[1]), int(cell[2])),
        str(names[2]),
        str(names[3]),
        str(names[4]),
        tuple(str(item) for item in sources),
    )
