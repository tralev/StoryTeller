"""WG-LOCAL-003 cultural layout and smaller-entity persistence evidence."""
from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from src.world.views import WorldView
from src.worldgen.local_maps import generate_local_maps
from src.worldgen.local_reconciliation import validate_local_reconciliation
from src.worldgen.local_society import (
    cultural_layout_from_mapping,
    persistent_entity_from_mapping,
)


@pytest.fixture(scope="module")
def world_and_maps(phase4_world):
    world = WorldView(phase4_world)
    return world, generate_local_maps(world)


def test_every_site_has_cultural_layout_and_retained_smaller_entities(world_and_maps) -> None:
    world, maps = world_and_maps
    for local in maps:
        assert local.boundary is not None
        assert local.layout is not None
        assert local.layout.culture == local.boundary.culture
        assert local.layout.civilization_id == local.boundary.civilization_id
        assert 1 <= len(local.entities) <= 4
        assert len({entity.entity_id for entity in local.entities}) == len(local.entities)
        assert len(local.entities) <= max(1, local.boundary.settlement_population)
        validate_local_reconciliation(world, local)


def test_culture_and_status_tampering_is_rejected(world_and_maps) -> None:
    world, maps = world_and_maps
    local = maps[0]
    assert local.layout is not None
    forged = replace(local, layout=replace(local.layout, culture="forged-culture"))
    with pytest.raises(ValueError, match="WG-LOCAL"):
        validate_local_reconciliation(world, forged)
    forged_entity = replace(local.entities[0], status="invented")
    with pytest.raises(ValueError, match="WG-LOCAL"):
        validate_local_reconciliation(
            world, replace(local, entities=(forged_entity, *local.entities[1:]))
        )


def test_layout_and_entity_readers_are_strict(world_and_maps) -> None:
    _, maps = world_and_maps
    layout, entity = maps[0].layout, maps[0].entities[0]
    assert layout is not None
    layout_payload, entity_payload = asdict(layout), asdict(entity)
    assert cultural_layout_from_mapping(layout_payload) == layout
    assert persistent_entity_from_mapping(entity_payload) == entity
    with pytest.raises(ValueError, match="LAYOUT-READ"):
        cultural_layout_from_mapping({**layout_payload, "invented": True})
    with pytest.raises(ValueError, match="ENTITY-READ"):
        persistent_entity_from_mapping({**entity_payload, "cell": (False, 0, 0)})
