"""WG-LOCAL-007 micro-to-macro accounting and non-duplication evidence."""
from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from src.world.views import WorldView
from src.worldgen.local_maps import generate_local_maps, validate_local_map
from src.worldgen.local_summary import (
    SUMMARY_RULES,
    derive_local_macro_summary,
    local_macro_summary_from_mapping,
    validate_local_macro_summary,
)


@pytest.fixture(scope="module")
def summarized_world(phase4_world):
    world = WorldView(phase4_world)
    return world, generate_local_maps(world)


def test_every_site_summary_references_exact_macro_accounts(summarized_world) -> None:
    world, local_maps = summarized_world
    settlements = {item.value["site_id"]: item for item in world.settlements()}
    for local in local_maps:
        summary = local.macro_summary
        assert summary is not None
        settlement = settlements[local.site_id].value
        assert summary.population == settlement["population"]
        assert summary.storage == tuple(sorted(
            (item["material_id"], item["quantity"])
            for item in settlement["inventory"]
        ))
        assert summary.civilization_id == settlement["civilization_id"]
        assert summary.aggregation_rules == SUMMARY_RULES
        assert summary == derive_local_macro_summary(local)
        validate_local_macro_summary(local, summary)
        validate_local_map(local)


def test_local_refinements_are_explicitly_nonadditive(summarized_world) -> None:
    world, local_maps = summarized_world
    macro_population = sum(item.value["population"] for item in world.settlements())
    assert sum(local.macro_summary.population for local in local_maps
               if local.macro_summary is not None) == macro_population
    assert all(
        local.macro_summary is not None
        and local.macro_summary.local_entity_anchor_count == len(local.entities)
        and local.macro_summary.local_entity_anchor_count <= 4
        for local in local_maps
    )
    assert dict(SUMMARY_RULES)["population"] == "macro_reference;local_entities_zero_weight"


def test_summary_rejects_double_counting_and_macro_tampering(summarized_world) -> None:
    _, local_maps = summarized_world
    local = local_maps[0]
    summary = local.macro_summary
    assert summary is not None
    with pytest.raises(ValueError, match="SUMMARY-RECONCILE"):
        validate_local_macro_summary(local, replace(
            summary, population=summary.population + summary.local_entity_anchor_count,
        ))
    with pytest.raises(ValueError, match="SUMMARY-RECONCILE"):
        validate_local_macro_summary(local, replace(
            summary, local_debris_mass=summary.local_debris_mass + 1,
        ))


def test_persisted_summary_reader_is_strict(summarized_world) -> None:
    _, local_maps = summarized_world
    summary = local_maps[0].macro_summary
    assert summary is not None
    payload = asdict(summary)
    assert local_macro_summary_from_mapping(payload) == summary
    with pytest.raises(ValueError, match="SUMMARY-READ"):
        local_macro_summary_from_mapping({**payload, "invented": True})
    with pytest.raises(ValueError, match="SUMMARY-READ"):
        local_macro_summary_from_mapping({
            **payload,
            "aggregation_rules": tuple(reversed(payload["aggregation_rules"])),
        })
