import pytest

from src.world.views import REQUIRED_KINDS, WorldView
from src.worldgen.indexes import BoundingBox


def test_complete_typed_world_queries(phase4_world):
    view = WorldView(phase4_world)
    assert set(view.artifact_ids) == set(REQUIRED_KINDS)
    assert view.present_year == 20
    assert (
        view.regions() and view.routes() and view.sites() and view.civilizations() and view.events()
    )
    assert (
        view.settlements()
        and view.cohorts()
        and view.ecology().source_ids
        and view.registries().source_ids
    )
    assert all(fact.source_ids for fact in view.regions())
    elevation = view.terrain_elevation()
    assert len(elevation.values) == elevation.spec.cell_count
    assert view.hydrology().hydrology.flow_to.spec == elevation.spec
    assert view.geology().geology.strata_id.spec == elevation.spec
    assert view.climate().climate.weather_regime.spec == elevation.spec
    assert view.biomes().biomes.carrying_capacity.spec == elevation.spec
    assert view.resources().resources.renewable_yield.spec == elevation.spec
    assert view.region_layer().regions.cell_region.spec == elevation.spec
    assert view.route_layer().routes.routes


def test_incomplete_world_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="WORLD-INCOMPLETE"):
        WorldView(tmp_path)


def test_world_index_facade_covers_all_bounded_query_forms(phase4_world):
    view = WorldView(phase4_world)
    index = view.indexes()
    assert index.load_budget.artifact_envelopes == 2
    assert index.load_budget.dense_chunks == 0
    region = view.regions()[0]
    route = view.routes()[0]
    assert index.fact(region.fact_id).source_artifact_id == view.artifact_ids["regions"]
    assert index.route(route.fact_id).entity_id == route.fact_id
    assert region.fact_id in {
        item.entity_id
        for item in index.source(
            view.artifact_ids["regions"],
            limit=2,
        )
    }
    references = index.region(region.fact_id)
    assert set(references.route_ids) == set(index.spatial.routes_for_region(region.fact_id))
    assert region.fact_id in index.bounding_box(BoundingBox(0, 0, 31, 31))
    assert index.time_range(0, view.present_year, limit=3)
    index.cell(0)
    center = int(region.value["center"])
    grid = view.region_layer().regions.cell_region.spec
    coordinate = grid.coordinate(center)
    assert index.point(coordinate.x, coordinate.y) == region.fact_id
    assert index.load_budget.artifact_envelopes == 3
    assert index.load_budget.dense_chunks <= 1


def test_world_index_facade_rejects_hostile_unbounded_queries(phase4_world):
    index = WorldView(phase4_world).indexes()
    for operation in (
        lambda: index.source("x" * 129),
        lambda: index.source(index.references.sources["regions"], limit=257),
        lambda: index.bounding_box(BoundingBox(0, 0, 31, 31), limit=0),
        lambda: index.time_range(5, 4),
        lambda: index.cell(-1),
    ):
        with pytest.raises(ValueError, match="WG-INDEX-QUERY"):
            operation()
