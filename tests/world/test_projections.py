from src.world.projections import build_projections
from src.world.views import WorldView


def test_projection_determinism_budget_and_sources(phase4_world):
    view = WorldView(phase4_world)
    first = build_projections(view, token_budget=256)
    second = build_projections(view, token_budget=256)
    assert first == second
    assert all(chunk.estimated_tokens <= 256 for chunk in first.chunks)
    assert all(record.source_ids for chunk in first.chunks for record in chunk.records)
    assert all(included == total for included, total in first.source_coverage.values())
