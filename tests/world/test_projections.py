from dataclasses import replace

import pytest

from src.world.projections import PROJECTION_CATEGORIES, build_projections, validate_projections
from src.world.views import WorldView


def test_projection_determinism_budget_and_sources(phase4_world):
    view = WorldView(phase4_world)
    first = build_projections(view, token_budget=256)
    second = build_projections(view, token_budget=256)
    assert first == second
    assert all(chunk.estimated_tokens <= 256 for chunk in first.chunks)
    assert all(record.source_ids for chunk in first.chunks for record in chunk.records)
    assert all(item.included == item.available for item in first.source_coverage)
    assert {item.category for item in first.source_coverage} == set(PROJECTION_CATEGORIES)
    assert all(
        len(chunk.records) <= 128 and chunk.estimated_tokens <= 256 for chunk in first.chunks
    )
    assert all(
        {record.category for record in chunk.records} == {chunk.category} for chunk in first.chunks
    )
    validate_projections(first, view.authoritative_inventory())
    assert first.authoritative_world == view.authoritative_inventory()
    assert len(first.authoritative_world) > len(
        {source for coverage in first.source_coverage for source in coverage.source_ids}
    )


def test_projection_validator_rejects_forged_source_and_incomplete_coverage(phase4_world):
    view = WorldView(phase4_world)
    projection = build_projections(view, token_budget=256)
    first_chunk = projection.chunks[0]
    forged_record = replace(first_chunk.records[0], source_ids=("artifact_unknown",))
    forged_chunk = replace(first_chunk, records=(forged_record,) + first_chunk.records[1:])
    with pytest.raises(ValueError, match="WG-BIBLE-PROJECTION-SOURCE"):
        validate_projections(
            replace(projection, chunks=(forged_chunk,) + projection.chunks[1:]),
            view.authoritative_inventory(),
        )

    coverage = projection.source_coverage[0]
    with pytest.raises(ValueError, match="WG-BIBLE-PROJECTION-COVERAGE"):
        validate_projections(
            replace(
                projection,
                source_coverage=(replace(coverage, included=0),) + projection.source_coverage[1:],
            ),
            view.authoritative_inventory(),
        )


def test_projection_rejects_pruned_authoritative_world_identity(phase4_world):
    view = WorldView(phase4_world)
    projection = build_projections(view, token_budget=256)
    with pytest.raises(ValueError, match="WG-BIBLE-PROJECTION-WORLD"):
        validate_projections(
            replace(projection, authoritative_world=projection.authoritative_world[:-1]),
            view.authoritative_inventory(),
        )
