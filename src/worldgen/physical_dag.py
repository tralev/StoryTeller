"""Declarative artifact DAG for the physical world pipeline."""
from __future__ import annotations

from dataclasses import dataclass

from .artifacts import DependencyGraph


@dataclass(frozen=True)
class PhysicalStageNode:
    kind: str
    requires: tuple[str, ...] = ()


PHYSICAL_STAGE_DAG = (
    PhysicalStageNode("plates"),
    PhysicalStageNode("terrain", ("plates",)),
    PhysicalStageNode("terrain_grid_catalog", ("terrain",)),
    PhysicalStageNode("geology", ("terrain", "terrain_grid_catalog")),
    PhysicalStageNode("geology_grid_catalog", ("geology",)),
    PhysicalStageNode("hydrology", ("geology", "terrain")),
    PhysicalStageNode("hydrology_grid_catalog", ("hydrology",)),
    PhysicalStageNode("climate", ("hydrology", "hydrology_grid_catalog", "terrain")),
    PhysicalStageNode("climate_grid_catalog", ("climate",)),
    PhysicalStageNode("soil", ("climate", "climate_grid_catalog", "geology",
                               "geology_grid_catalog", "hydrology",
                               "hydrology_grid_catalog", "terrain")),
    PhysicalStageNode("soil_grid_catalog", ("soil",)),
    PhysicalStageNode("biomes", ("climate", "climate_grid_catalog", "soil",
                                 "soil_grid_catalog")),
    PhysicalStageNode("biome_grid_catalog", ("biomes",)),
    PhysicalStageNode("resources", ("biome_grid_catalog", "biomes", "geology",
                                    "geology_grid_catalog", "soil", "soil_grid_catalog")),
    PhysicalStageNode("resource_grid_catalog", ("resources",)),
    PhysicalStageNode("species", ("biome_grid_catalog", "biomes")),
    PhysicalStageNode("ecology", ("biome_grid_catalog", "biomes", "species")),
    PhysicalStageNode("regions", ("biome_grid_catalog", "biomes", "climate",
                                  "climate_grid_catalog", "hydrology", "hydrology_grid_catalog")),
    PhysicalStageNode("region_grid_catalog", ("regions",)),
    PhysicalStageNode("routes", ("climate", "climate_grid_catalog", "region_grid_catalog",
                                 "regions", "resource_grid_catalog", "resources")),
    PhysicalStageNode("spatial_index", ("region_grid_catalog", "regions", "routes")),
    PhysicalStageNode("reference_index", ("ecology", "hydrology", "regions", "resources",
                                          "routes", "species")),
    PhysicalStageNode("map_layers", ("biome_grid_catalog", "climate_grid_catalog",
                                     "hydrology_grid_catalog", "region_grid_catalog",
                                     "regions", "resource_grid_catalog", "routes",
                                     "soil_grid_catalog", "terrain_grid_catalog")),
    PhysicalStageNode("maps", ("biome_grid_catalog", "biomes", "climate_grid_catalog",
                               "hydrology_grid_catalog", "map_layers", "region_grid_catalog",
                               "regions", "resource_grid_catalog", "routes", "soil_grid_catalog",
                               "terrain_grid_catalog")),
    PhysicalStageNode("validation_report", (
        "biome_grid_catalog", "biomes", "climate", "climate_grid_catalog", "ecology",
        "geology", "geology_grid_catalog", "hydrology", "hydrology_grid_catalog", "map_layers", "maps", "plates",
        "reference_index", "region_grid_catalog", "regions", "resource_grid_catalog", "resources", "routes",
        "soil", "soil_grid_catalog", "spatial_index", "species", "terrain", "terrain_grid_catalog",
    )),
    PhysicalStageNode("world_index", (
        "biome_grid_catalog", "biomes", "climate", "climate_grid_catalog", "ecology",
        "geology", "geology_grid_catalog", "hydrology", "hydrology_grid_catalog", "map_layers", "maps", "plates",
        "reference_index", "region_grid_catalog", "regions", "resource_grid_catalog", "resources", "routes",
        "soil", "soil_grid_catalog", "spatial_index", "species", "terrain", "terrain_grid_catalog",
        "validation_report",
    )),
)

PHYSICAL_STAGE_DEPENDENCIES = {node.kind: node.requires for node in PHYSICAL_STAGE_DAG}


def validate_physical_stage_dag() -> None:
    """Validate acyclicity, declared dependencies, and topological declaration order."""
    DependencyGraph(PHYSICAL_STAGE_DEPENDENCIES)
    available: set[str] = set()
    for node in PHYSICAL_STAGE_DAG:
        missing = set(node.requires) - available
        if missing:
            raise ValueError(f"WG-PHYSICAL-DAG: {node.kind} declared before {sorted(missing)}")
        available.add(node.kind)
