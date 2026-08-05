import pytest

from src.world.views import REQUIRED_KINDS, WorldView


def test_complete_typed_world_queries(phase4_world):
    view = WorldView(phase4_world)
    assert set(view.artifact_ids) == set(REQUIRED_KINDS)
    assert view.present_year == 20
    assert view.regions() and view.routes() and view.sites() and view.civilizations() and view.events()
    assert view.settlements() and view.cohorts() and view.ecology().source_ids and view.registries().source_ids
    assert all(fact.source_ids for fact in view.regions())


def test_incomplete_world_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="WORLD-INCOMPLETE"):
        WorldView(tmp_path)
