import json
from dataclasses import replace

import pytest

from src.domain.run_spec import WorldSpec
from src.worldgen.artifacts import WorldArtifactRepository, canonical_json
from src.worldgen.grid import DenseGridCatalog, DenseGridRepository, GridSpec
from src.worldgen.hydrology import generate_hydrology
from src.worldgen.maps import MapLayerCatalog
from src.worldgen.index_reader import VerifiedReferenceIndexReader, VerifiedSpatialIndexReader
from src.worldgen.indexes import BoundingBox
from src.worldgen.index_rebuild import rebuild_physical_indexes
from src.worldgen.hydrology_reader import VerifiedHydrologyReader
from src.worldgen.climate_reader import VerifiedClimateReader
from src.worldgen.biome_reader import VerifiedBiomeReader
from src.worldgen.resource_reader import VerifiedResourceReader
from src.worldgen.region_reader import VerifiedRegionReader
from src.worldgen.route_reader import VerifiedRouteReader
from src.worldgen.geology_reader import VerifiedGeologyReader
from src.worldgen.geology import generate_geology
from src.worldgen.artifact_shape_audit import audit_physical_artifacts, embedded_dense_grid_paths
from src.worldgen.grid_catalog_audit import verify_catalog_chunk_bytes
from src.worldgen.physical_dag import PHYSICAL_STAGE_DAG, validate_physical_stage_dag
from src.worldgen.physical_biomes import classify_physical_biomes
from src.worldgen.resources import generate_resources
from src.worldgen.physical_regions import generate_regions
from src.worldgen.routes import generate_routes
from src.worldgen.physical_pipeline import generate_physical_world
from src.worldgen.physical_validation_report import measure_physical_invariants
from src.worldgen.physical_models import ErosionPassLedger
from src.worldgen.physical_terrain import generate_physical_terrain
from src.worldgen.terrain_reader import VerifiedTerrainReader
from src.worldgen.weather import generate_weather
from src.worldgen.soil import generate_soil
from src.worldgen.soil_reader import VerifiedSoilReader


def test_all_domains_are_independent_verified_artifacts(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2, climate_relaxation_passes=8)
    first = generate_physical_world(spec, 42, tmp_path / "a")
    second = generate_physical_world(spec, 42, tmp_path / "b")
    assert first["world_index"] == second["world_index"]
    expected = {"plates", "terrain", "terrain_grid_catalog", "geology", "geology_grid_catalog", "hydrology",
                "hydrology_grid_catalog", "climate", "climate_grid_catalog", "soil", "soil_grid_catalog", "biomes",
                "biome_grid_catalog",
                "resources", "resource_grid_catalog", "species", "ecology", "regions",
                "region_grid_catalog", "routes", "spatial_index", "reference_index",
                "map_layers", "maps", "validation_report", "world_index"}
    assert {path.stem for path in (tmp_path / "a" / "artifacts").glob("*.json")} == expected
    index = json.loads((tmp_path / "a" / "artifacts" / "world_index.json").read_text())
    assert set(index["payload"]["artifacts"]) == expected - {"world_index"}
    assert all(len(value["sha256"]) == 64 for value in index["payload"]["artifacts"].values())
    repository = WorldArtifactRepository(tmp_path / "a" / "artifacts")
    layer_artifact = repository.load_verified("map_layers")
    layers = MapLayerCatalog.from_mapping(layer_artifact.payload)
    assert tuple(layer.layer_id for layer in layers.scalar_layers) == (
        "biome", "climate", "hazard", "hydrology", "political", "resource", "soil", "terrain",
    )
    assert tuple(layer.layer_id for layer in layers.vector_layers) == ("regions", "routes")
    assert {layer.source_artifact_id for layer in layers.scalar_layers + layers.vector_layers} <= {
        dependency for dependency in layer_artifact.depends_on
    }
    maps = repository.load_verified("maps")
    assert maps.payload["format"] == "storyteller.map-raster-catalog.v1"
    assert {f"layer_{layer.layer_id}" for layer in layers.scalar_layers} <= set(maps.payload["rasters"])


def test_terrain_catalog_reconstructs_complete_model_and_links_dependencies(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    artifacts = WorldArtifactRepository(root / "artifacts")
    terrain = artifacts.load_verified("terrain")
    catalog_artifact = artifacts.load_verified("terrain_grid_catalog")
    geology = artifacts.load_verified("geology")
    catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
    verified = VerifiedTerrainReader(root).load().terrain
    expected = generate_physical_terrain(
        GridSpec(32, 32, spec.metres_per_world_cell), 42, continent_count=1,
        plate_count=4, erosion_passes=2, minimum_continent_cells=1,
    )
    assert verified == expected
    assert all(DenseGridRepository(root / "chunks").load(manifest).spec == verified.grid
               for manifest in catalog.manifests)
    for field in ("elevation_mm", "plate_id", "plate_boundary", "slope_ppm", "land", "continent_id"):
        assert field not in terrain.payload
    assert "elevation_mm" not in geology.payload and "plate_id" not in geology.payload
    assert catalog_artifact.depends_on == (terrain.artifact_id,)
    assert catalog_artifact.artifact_id in geology.depends_on


def test_terrain_elevation_chunk_bytes_are_deterministic_and_corruption_is_rejected(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    first, second = tmp_path / "first", tmp_path / "second"
    generate_physical_world(spec, 42, first)
    generate_physical_world(spec, 42, second)
    first_files = sorted((first / "chunks").rglob("*.grid"))
    second_files = sorted((second / "chunks").rglob("*.grid"))
    assert [path.relative_to(first / "chunks") for path in first_files] == [
        path.relative_to(second / "chunks") for path in second_files
    ]
    assert [path.read_bytes() for path in first_files] == [path.read_bytes() for path in second_files]

    catalog_payload = WorldArtifactRepository(first / "artifacts").load_verified(
        "terrain_grid_catalog"
    ).payload
    catalog = DenseGridCatalog.from_mapping(catalog_payload)
    damaged = sorted((first / "chunks" / catalog.manifests[0].layer).glob("*.grid"))[0]
    encoded = bytearray(damaged.read_bytes())
    encoded[-1] ^= 1
    damaged.write_bytes(encoded)
    with pytest.raises(ValueError, match="corrupt chunk hash"):
        DenseGridRepository(first / "chunks").load(catalog.manifests[0])


def test_geology_catalog_reconstructs_typed_tectonic_model(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    repository = WorldArtifactRepository(root / "artifacts")
    metadata = repository.load_verified("geology")
    catalog_artifact = repository.load_verified("geology_grid_catalog")
    terrain = VerifiedTerrainReader(root).load().terrain
    assert VerifiedGeologyReader(root).load().geology == generate_geology(terrain)
    assert set(metadata.payload) == {"algorithm_version", "terrain_grid_catalog"}
    catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
    assert len(catalog.manifests) == 6
    assert catalog_artifact.depends_on == (metadata.artifact_id,)
    for downstream in ("soil", "resources"):
        assert catalog_artifact.artifact_id in repository.load_verified(downstream).depends_on


def test_verified_terrain_reader_rejects_catalog_dependency_mismatch(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    repository = WorldArtifactRepository(root / "artifacts")
    wrong_dependency = repository.load_verified("geology").artifact_id
    path = root / "artifacts" / "terrain_grid_catalog.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["depends_on"] = [wrong_dependency]
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError, match="WG-HASH"):
        VerifiedTerrainReader(root).load()


def test_hydrology_catalog_reconstructs_complete_model_without_embedded_grids(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    repository = WorldArtifactRepository(root / "artifacts")
    metadata = repository.load_verified("hydrology")
    catalog_artifact = repository.load_verified("hydrology_grid_catalog")
    catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
    terrain = VerifiedTerrainReader(root).load().terrain
    expected = generate_hydrology(terrain)
    verified = VerifiedHydrologyReader(root).load().hydrology
    assert verified == expected
    dense_fields = (
        "filled_elevation_mm", "flow_to", "accumulation", "watershed_id", "coastline",
        "aquifer_capacity_mm", "salinity_ppm", "snowpack_mm", "glacier",
        "delta",
    )
    assert all(field not in metadata.payload for field in dense_fields)
    assert len(catalog.manifests) == len(dense_fields)
    assert catalog_artifact.depends_on == (metadata.artifact_id,)
    assert catalog_artifact.artifact_id in repository.load_verified("climate").depends_on
    assert catalog_artifact.artifact_id in repository.load_verified("regions").depends_on


def test_hydrology_reader_rejects_chunk_corruption_and_dependency_tampering(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    corrupt_root = tmp_path / "corrupt"
    generate_physical_world(spec, 42, corrupt_root)
    chunk = sorted((corrupt_root / "chunks" / "hydrology_accumulation").glob("*.grid"))[0]
    encoded = bytearray(chunk.read_bytes()); encoded[-1] ^= 1; chunk.write_bytes(encoded)
    with pytest.raises(ValueError, match="corrupt chunk hash"):
        VerifiedHydrologyReader(corrupt_root).load()

    dependency_root = tmp_path / "dependency"
    generate_physical_world(spec, 42, dependency_root)
    repository = WorldArtifactRepository(dependency_root / "artifacts")
    wrong = repository.load_verified("terrain").artifact_id
    path = dependency_root / "artifacts" / "hydrology_grid_catalog.json"
    envelope = json.loads(path.read_text(encoding="utf-8")); envelope["depends_on"] = [wrong]
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError, match="WG-HASH"):
        VerifiedHydrologyReader(dependency_root).load()


def test_climate_catalog_reconstructs_all_annual_and_seasonal_grids(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    repository = WorldArtifactRepository(root / "artifacts")
    metadata = repository.load_verified("climate")
    catalog_artifact = repository.load_verified("climate_grid_catalog")
    catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
    terrain = VerifiedTerrainReader(root).load().terrain
    hydrology = VerifiedHydrologyReader(root).load().hydrology
    expected = generate_weather(
        terrain, hydrology, axial_tilt_millidegrees=spec.axial_tilt_millidegrees,
        relaxation_passes=spec.climate_relaxation_passes,
    )
    assert VerifiedClimateReader(root).load().climate == expected
    assert set(metadata.payload) == {"algorithm_version", "season_count", "water_ledger"}
    assert len(catalog.manifests) == 3 + 9 * len(expected.seasons)
    assert catalog_artifact.depends_on == (metadata.artifact_id,)
    for downstream in ("soil", "biomes", "routes"):
        assert catalog_artifact.artifact_id in repository.load_verified(downstream).depends_on


def test_climate_reader_rejects_chunk_corruption_and_dependency_tampering(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    corrupt_root = tmp_path / "corrupt"
    generate_physical_world(spec, 42, corrupt_root)
    chunk = sorted((corrupt_root / "chunks" / "climate_weather_regime").glob("*.grid"))[0]
    encoded = bytearray(chunk.read_bytes()); encoded[-1] ^= 1; chunk.write_bytes(encoded)
    with pytest.raises(ValueError, match="corrupt chunk hash"):
        VerifiedClimateReader(corrupt_root).load()

    dependency_root = tmp_path / "dependency"
    generate_physical_world(spec, 42, dependency_root)
    repository = WorldArtifactRepository(dependency_root / "artifacts")
    wrong = repository.load_verified("terrain").artifact_id
    path = dependency_root / "artifacts" / "climate_grid_catalog.json"
    envelope = json.loads(path.read_text(encoding="utf-8")); envelope["depends_on"] = [wrong]
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError, match="WG-HASH"):
        VerifiedClimateReader(dependency_root).load()


def test_biome_catalog_reconstructs_biome_and_soil_grids_for_all_consumers(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    repository = WorldArtifactRepository(root / "artifacts")
    metadata = repository.load_verified("biomes")
    soil = repository.load_verified("soil")
    catalog_artifact = repository.load_verified("biome_grid_catalog")
    catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
    terrain = VerifiedTerrainReader(root).load().terrain
    hydrology = VerifiedHydrologyReader(root).load().hydrology
    climate = VerifiedClimateReader(root).load().climate
    geology = VerifiedGeologyReader(root).load().geology
    expected_soil = generate_soil(terrain, geology, hydrology, climate)
    expected = classify_physical_biomes(terrain, hydrology, climate, expected_soil)
    verified = VerifiedBiomeReader(root).load()
    persisted_soil = VerifiedSoilReader(root).load()
    assert persisted_soil.soil == expected_soil
    assert verified.biomes == expected
    assert set(metadata.payload) == {"algorithm_version"}
    assert set(soil.payload) == {"algorithm_version"}
    assert len(catalog.manifests) == 3
    assert catalog_artifact.depends_on == (metadata.artifact_id,)
    assert persisted_soil.grid_catalog_id in metadata.depends_on
    for downstream in ("resources", "species", "ecology", "regions", "maps"):
        assert catalog_artifact.artifact_id in repository.load_verified(downstream).depends_on


def test_biome_reader_rejects_chunk_corruption_and_dependency_tampering(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    corrupt_root = tmp_path / "corrupt"
    generate_physical_world(spec, 42, corrupt_root)
    chunk = sorted((corrupt_root / "chunks" / "biome_carrying_capacity").glob("*.grid"))[0]
    encoded = bytearray(chunk.read_bytes()); encoded[-1] ^= 1; chunk.write_bytes(encoded)
    with pytest.raises(ValueError, match="corrupt chunk hash"):
        VerifiedBiomeReader(corrupt_root).load()

    dependency_root = tmp_path / "dependency"
    generate_physical_world(spec, 42, dependency_root)
    repository = WorldArtifactRepository(dependency_root / "artifacts")
    wrong = repository.load_verified("terrain").artifact_id
    path = dependency_root / "artifacts" / "biome_grid_catalog.json"
    envelope = json.loads(path.read_text(encoding="utf-8")); envelope["depends_on"] = [wrong]
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError, match="WG-HASH"):
        VerifiedBiomeReader(dependency_root).load()


def test_resource_catalog_reconstructs_all_geology_and_renewable_grids(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    repository = WorldArtifactRepository(root / "artifacts")
    metadata = repository.load_verified("resources")
    catalog_artifact = repository.load_verified("resource_grid_catalog")
    catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
    terrain = VerifiedTerrainReader(root).load().terrain
    biomes = VerifiedBiomeReader(root).load().biomes
    expected = generate_resources(terrain, biomes, 42)
    assert VerifiedResourceReader(root).load().resources == expected
    dense_fields = ("geology_id", "strata_id", "parent_material_id", "fault",
                    "volcano", "renewable_yield")
    assert all(field not in metadata.payload for field in dense_fields)
    assert set(metadata.payload) == {"algorithm_version", "deposits"}
    assert len(catalog.manifests) == 1
    assert catalog_artifact.depends_on == (metadata.artifact_id,)
    assert catalog_artifact.artifact_id in repository.load_verified("routes").depends_on


def test_resource_reader_rejects_chunk_corruption_and_dependency_tampering(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    corrupt_root = tmp_path / "corrupt"
    generate_physical_world(spec, 42, corrupt_root)
    chunk = sorted((corrupt_root / "chunks" / "resource_renewable_yield").glob("*.grid"))[0]
    encoded = bytearray(chunk.read_bytes()); encoded[-1] ^= 1; chunk.write_bytes(encoded)
    with pytest.raises(ValueError, match="corrupt chunk hash"):
        VerifiedResourceReader(corrupt_root).load()

    dependency_root = tmp_path / "dependency"
    generate_physical_world(spec, 42, dependency_root)
    repository = WorldArtifactRepository(dependency_root / "artifacts")
    wrong = repository.load_verified("terrain").artifact_id
    path = dependency_root / "artifacts" / "resource_grid_catalog.json"
    envelope = json.loads(path.read_text(encoding="utf-8")); envelope["depends_on"] = [wrong]
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError, match="WG-HASH"):
        VerifiedResourceReader(dependency_root).load()


def test_region_catalog_reconstructs_ownership_and_sparse_region_records(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    repository = WorldArtifactRepository(root / "artifacts")
    metadata = repository.load_verified("regions")
    catalog_artifact = repository.load_verified("region_grid_catalog")
    terrain = VerifiedTerrainReader(root).load().terrain
    hydrology = VerifiedHydrologyReader(root).load().hydrology
    climate = VerifiedClimateReader(root).load().climate
    biomes = VerifiedBiomeReader(root).load().biomes
    expected = generate_regions(terrain, hydrology, climate, biomes)
    assert VerifiedRegionReader(root).load().regions == expected
    assert set(metadata.payload) == {"algorithm_version", "cost_model", "regions"}
    assert "cell_region" not in metadata.payload
    catalog = DenseGridCatalog.from_mapping(catalog_artifact.payload)
    assert tuple(item.layer for item in catalog.manifests) == ("region_cell_region",)
    assert catalog_artifact.depends_on == (metadata.artifact_id,)
    for downstream in ("routes", "maps"):
        assert catalog_artifact.artifact_id in repository.load_verified(downstream).depends_on


def test_region_reader_rejects_chunk_corruption_and_dependency_tampering(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    corrupt_root = tmp_path / "corrupt"
    generate_physical_world(spec, 42, corrupt_root)
    chunk = sorted((corrupt_root / "chunks" / "region_cell_region").glob("*.grid"))[0]
    encoded = bytearray(chunk.read_bytes()); encoded[-1] ^= 1; chunk.write_bytes(encoded)
    with pytest.raises(ValueError, match="corrupt chunk hash"):
        VerifiedRegionReader(corrupt_root).load()

    dependency_root = tmp_path / "dependency"
    generate_physical_world(spec, 42, dependency_root)
    repository = WorldArtifactRepository(dependency_root / "artifacts")
    wrong = repository.load_verified("terrain").artifact_id
    path = dependency_root / "artifacts" / "region_grid_catalog.json"
    envelope = json.loads(path.read_text(encoding="utf-8")); envelope["depends_on"] = [wrong]
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError, match="WG-HASH"):
        VerifiedRegionReader(dependency_root).load()


def test_verified_route_reader_reconstructs_sparse_route_graph(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    terrain = VerifiedTerrainReader(root).load().terrain
    hydrology = VerifiedHydrologyReader(root).load().hydrology
    climate = VerifiedClimateReader(root).load().climate
    resources = VerifiedResourceReader(root).load().resources
    regions = VerifiedRegionReader(root).load().regions
    expected = generate_routes(terrain, hydrology, climate, resources, regions)
    assert VerifiedRouteReader(root).load().routes == expected


def test_verified_route_reader_rejects_region_dependency_tampering(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    repository = WorldArtifactRepository(root / "artifacts")
    region = repository.load_verified("regions").artifact_id
    path = root / "artifacts" / "routes.json"
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["depends_on"] = [item for item in envelope["depends_on"] if item != region]
    path.write_bytes(canonical_json(envelope))
    with pytest.raises(ValueError, match="WG-HASH"):
        VerifiedRouteReader(root).load()


def test_physical_artifact_shape_audit_proves_dense_grids_are_not_in_json(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    audit_physical_artifacts(root)
    assert embedded_dense_grid_paths({"safe": {"algorithm_version": 1}}) == ()
    assert embedded_dense_grid_paths({
        "biome_id": {"spec": {"width": 2}, "values": [1, 2]},
    }) == ("payload.biome_id",)


def test_all_physical_catalog_chunks_have_deterministic_canonical_bytes(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    first, second = tmp_path / "first", tmp_path / "second"
    generate_physical_world(spec, 42, first)
    generate_physical_world(spec, 42, second)
    audit = verify_catalog_chunk_bytes(first, second)
    assert audit.catalogs == 8
    assert audit.layers == 70
    assert audit.chunks == audit.layers

    damaged = sorted((second / "chunks" / "geology_fault").glob("*.grid"))[0]
    encoded = bytearray(damaged.read_bytes()); encoded[-1] ^= 1; damaged.write_bytes(encoded)
    with pytest.raises(ValueError, match="byte mismatch"):
        verify_catalog_chunk_bytes(first, second)


def test_physical_stage_dag_and_worker_counts_produce_identical_bytes(tmp_path):
    validate_physical_stage_dag()
    assert tuple(node.kind for node in PHYSICAL_STAGE_DAG) == (
        "plates", "terrain", "terrain_grid_catalog", "geology", "geology_grid_catalog", "hydrology",
        "hydrology_grid_catalog", "climate", "climate_grid_catalog", "soil",
        "soil_grid_catalog", "biomes", "biome_grid_catalog", "resources", "resource_grid_catalog",
        "species", "ecology", "regions", "region_grid_catalog", "routes", "spatial_index",
        "reference_index", "map_layers", "maps",
        "validation_report",
        "world_index",
    )
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=2,
                     climate_relaxation_passes=8)
    one, many = tmp_path / "one", tmp_path / "many"
    first = generate_physical_world(spec, 42, one, worker_count=1)
    second = generate_physical_world(spec, 42, many, worker_count=4)
    assert first == second
    assert verify_catalog_chunk_bytes(one, many).layers == 70
    assert {
        path.name: path.read_bytes() for path in (one / "artifacts").glob("*.json")
    } == {
        path.name: path.read_bytes() for path in (many / "artifacts").glob("*.json")
    }


def test_validation_report_binds_the_complete_physical_contract(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    repository = WorldArtifactRepository(root / "artifacts")
    report = repository.load_verified("validation_report")
    records = report.payload["artifacts"]
    assert len(records) == 24
    assert report.payload["catalog_count"] == 8
    assert report.payload["dense_layer_count"] == 70
    invariants = report.payload["invariants"]
    assert invariants["erosion"]["pass_count"] == spec.erosion_passes
    assert invariants["erosion"]["initial_mass_mm"] == invariants["erosion"]["final_mass_mm"]
    assert (invariants["hydrology"]["river_edge_count"]
            == invariants["hydrology"]["monotonic_river_edge_count"])
    assert invariants["climate"]["season_count"] == 4
    assert set(report.payload["checks"]) == {
        "WG-ARTIFACT-SET", "WG-DEPENDENCY-DAG", "WG-DENSE-JSON",
        "WG-GRID-CATALOG", "WG-TERRAIN-SPEC", "WG-PHYSICAL-INVARIANTS", "WG-ECOLOGY",
    }
    assert report.depends_on == tuple(sorted(record["artifact_id"] for record in records))
    world_index = repository.load_verified("world_index")
    assert report.artifact_id in world_index.depends_on
    assert world_index.payload["artifacts"]["validation_report"]["sha256"] == report.sha256


def test_indexes_delete_and_rebuild_to_exact_bytes_without_touching_sources(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    index_paths = tuple(root / "artifacts" / f"{kind}.json"
                        for kind in ("spatial_index", "reference_index"))
    expected = tuple(path.read_bytes() for path in index_paths)
    source_paths = tuple(sorted(
        path for path in (root / "artifacts").glob("*.json") if path not in index_paths
    ))
    source_hashes = {path.name: path.read_bytes() for path in source_paths}
    for path in index_paths:
        path.unlink()
    rebuilt_ids = rebuild_physical_indexes(root)
    assert tuple(path.read_bytes() for path in index_paths) == expected
    assert rebuilt_ids == tuple(WorldArtifactRepository(root / "artifacts").load_verified(kind).artifact_id
                                for kind in ("spatial_index", "reference_index"))
    assert {path.name: path.read_bytes() for path in source_paths} == source_hashes


def test_corrupt_index_is_isolated_and_repairable_from_authoritative_domains(tmp_path):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    root = tmp_path / "world"
    generate_physical_world(spec, 42, root)
    damaged = root / "artifacts" / "spatial_index.json"
    damaged.write_bytes(damaged.read_bytes() + b" ")
    with pytest.raises(ValueError, match="noncanonical"):
        VerifiedSpatialIndexReader(root)
    assert VerifiedTerrainReader(root).load().terrain.grid == GridSpec(32, 32, spec.metres_per_world_cell)
    assert VerifiedRegionReader(root).load().regions.regions
    assert VerifiedRouteReader(root).load().routes.routes
    rebuild_physical_indexes(root)
    assert VerifiedSpatialIndexReader(root).regions_in_bbox(BoundingBox(0, 0, 31, 31))


def test_invariant_evidence_rejects_adversarial_ledger_and_river_mutations(physical_world):
    terrain, hydrology, climate, *_ = physical_world
    first = terrain.erosion_ledger[0]
    bad_erosion = replace(terrain, erosion_ledger=(
        ErosionPassLedger(first.pass_index, first.mass_before_mm,
                          first.thermal_moved_mm, first.hydraulic_moved_mm,
                          first.mass_after_mm + 1),
        *terrain.erosion_ledger[1:],
    ))
    with pytest.raises(ValueError, match="WG-EROSION"):
        measure_physical_invariants(bad_erosion, hydrology, climate)

    edge = hydrology.rivers[0]
    bad_flow = list(hydrology.flow_to.values)
    bad_flow[edge.upstream] = -1
    with pytest.raises(ValueError, match="WG-RIVER"):
        measure_physical_invariants(
            terrain, replace(hydrology, flow_to=type(hydrology.flow_to)(
                terrain.grid, tuple(bad_flow),
            )), climate,
        )

    first_ledger = climate.water_ledger[0]
    bad_climate = replace(climate, water_ledger=(
        replace(first_ledger, precipitation_total_mm=first_ledger.precipitation_total_mm + 1),
        *climate.water_ledger[1:],
    ))
    with pytest.raises(ValueError, match="WG-CLIMATE-WATER"):
        measure_physical_invariants(terrain, hydrology, bad_climate)


@pytest.mark.parametrize("worker_count", [0, -1, True])
def test_physical_pipeline_rejects_invalid_worker_counts(tmp_path, worker_count):
    spec = WorldSpec(width=32, height=32, continent_count=1, plate_count=4,
                     minimum_continent_cells=1, erosion_passes=1,
                     climate_relaxation_passes=8)
    with pytest.raises(ValueError, match="WG-WORKERS"):
        generate_physical_world(spec, 42, tmp_path / str(worker_count),
                                worker_count=worker_count)
