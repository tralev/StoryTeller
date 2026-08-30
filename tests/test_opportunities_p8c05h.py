"""WG-INTEGRATION-001 authoritative opportunity evidence."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.narrative.opportunities import validate_opportunities
from src.narrative.pipeline import _graph_from_dict, _opportunities_from_dict
from src.world.views import WorldView
from src.worldgen.local_index import local_world_index_from_mapping
from src.worldgen.simulation.projections import (
    ALL_OPPORTUNITY_KINDS,
    OPPORTUNITY_KINDS,
    OPPORTUNITY_ROLES,
)


def _authority(phase5_project):
    world_root, _, narrative_root = phase5_project
    world = WorldView(world_root)
    index = local_world_index_from_mapping(
        json.loads((narrative_root / "local_index.json").read_text())
    )
    opportunities = _opportunities_from_dict(
        json.loads((narrative_root / "opportunities.json").read_text())
    )
    return world, index, opportunities


def test_opportunities_bind_every_authoritative_evidence_dimension(phase5_project) -> None:
    world, index, opportunities = _authority(phase5_project)
    validate_opportunities(world, index, opportunities)
    assert all(
        item.participant_ids
        and item.location_ids
        and item.person_ids
        and item.belief_ids
        and item.site_ids
        and len(item.local_containment_ids) == 2
        for item in opportunities
    )
    kinds = {item.opportunity_kind for item in opportunities}
    assert set(OPPORTUNITY_KINDS) <= kinds <= set(ALL_OPPORTUNITY_KINDS)
    assert all(
        tuple(role for role, _ in item.role_assignments) == OPPORTUNITY_ROLES
        and item.constraint_ids
        for item in opportunities
    )
    mystery = next(item for item in opportunities if item.opportunity_kind == "factual_mystery")
    assert mystery.answer_fact_ids


def test_opportunity_sources_cover_every_projected_authority(phase5_project) -> None:
    world, _, opportunities = _authority(phase5_project)
    required = {
        world.artifact_ids[kind]
        for kind in (
            "civilizations",
            "regions",
            "routes",
            "sites",
            "history",
            "identities",
            "geology",
            "ecology",
        )
    }
    projected = {source for item in opportunities for source in item.source_ids}
    factual_answers = {answer for item in opportunities for answer in item.answer_fact_ids}
    assert required - {world.artifact_ids["geology"]} <= projected
    assert world.artifact_ids["geology"] in factual_answers


def test_every_revealable_fact_and_answer_is_indexed_by_story_nodes(phase5_project) -> None:
    _, _, narrative_root = phase5_project
    opportunities = _opportunities_from_dict(
        json.loads((narrative_root / "opportunities.json").read_text())
    )
    graph = _graph_from_dict(json.loads((narrative_root / "graph.json").read_text()))
    references = {node.opportunity_id: set(node.authoritative_refs) for node in graph.nodes}
    for item in opportunities:
        assert (
            set(item.revealable_fact_ids + item.answer_fact_ids) <= references[item.opportunity_id]
        )


def test_opportunity_validator_rejects_invented_local_containment(phase5_project) -> None:
    world, index, opportunities = _authority(phase5_project)
    forged = (
        replace(opportunities[0], local_containment_ids=("invented", "summary")),
        *opportunities[1:],
    )
    with pytest.raises(ValueError, match="OPPORTUNITY-AUTHORITY"):
        validate_opportunities(world, index, forged)


def test_opportunity_validator_rejects_invented_answer_fact(phase5_project) -> None:
    world, index, opportunities = _authority(phase5_project)
    mystery = next(item for item in opportunities if item.opportunity_kind == "factual_mystery")
    others = tuple(item for item in opportunities if item is not mystery)
    forged = (replace(mystery, answer_fact_ids=("invented_answer",)), *others)
    with pytest.raises(ValueError, match="OPPORTUNITY-AUTHORITY"):
        validate_opportunities(world, index, forged)
