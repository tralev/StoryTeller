"""WG-INTEGRATION-001 authoritative opportunity evidence."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from src.narrative.opportunities import validate_opportunities
from src.narrative.pipeline import _opportunities_from_dict
from src.world.views import WorldView
from src.worldgen.local_index import local_world_index_from_mapping


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
        item.participant_ids and item.location_ids and item.person_ids and item.belief_ids
        and item.site_ids and len(item.local_containment_ids) == 2
        for item in opportunities
    )


def test_opportunity_validator_rejects_invented_local_containment(phase5_project) -> None:
    world, index, opportunities = _authority(phase5_project)
    forged = (replace(opportunities[0], local_containment_ids=("invented", "summary")),
              *opportunities[1:])
    with pytest.raises(ValueError, match="OPPORTUNITY-AUTHORITY"):
        validate_opportunities(world, index, forged)
