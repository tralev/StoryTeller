"""Region segmentation — groups contiguous cells into named regions.

Uses flood-fill to group cells sharing the same biome, then
computes prosperity and neighbor relationships.
"""

from __future__ import annotations

from .models import Climate, Elevation, GridCell, Region, WorldRNG

# Biome → prosperity base value
_PROSPERITY_BASE: dict[str, float] = {
    "temperate_forest": 0.80,
    "temperate_grassland": 0.75,
    "river_valley": 0.90,
    "coastal": 0.70,
    "tropical_forest": 0.65,
    "savanna": 0.55,
    "wetland": 0.45,
    "taiga": 0.40,
    "tundra": 0.20,
    "highland": 0.50,
    "mountain": 0.30,
    "desert": 0.15,
}

# Elevation band labels
_ELEVATION_LABELS: dict[tuple[float, float], str] = {
    (-1.0, -0.05): "deep",
    (-0.05, 0.15): "lowland",
    (0.15, 0.35): "hills",
    (0.35, 0.55): "highland",
    (0.55, 0.75): "mountain",
    (0.75, 1.0): "peak",
}

# Name components for procedural naming
_NAME_TERRAIN: list[str] = [
    "Iron", "Crimson", "Verdant", "Ashen", "Frozen", "Golden",
    "Shadow", "Thunder", "Silent", "Blighted", "Emerald", "Obsidian",
]
_NAME_FEATURE: list[str] = [
    "Reach", "Vale", "Expanse", "Wilds", "March", "Foothills",
    "Basin", "Coast", "Plateau", "Ridge", "Depths", "Hinterlands",
]


def segment_regions(
    grid: list[list[GridCell]],
    seed: int,
) -> list[Region]:
    """Segment the grid into contiguous biomes and build Region objects.

    Uses flood-fill to cluster cells of the same biome, then characterizes
    each region with prosperity, neighbors, and a procedural name.
    """
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    if height == 0 or width == 0:
        return []

    rng = WorldRNG(seed + 500009)

    visited: set[tuple[int, int]] = set()
    regions: list[Region] = []
    rid = 0

    for y in range(height):
        for x in range(width):
            if (x, y) in visited:
                continue
            cell = grid[y][x]
            if not cell.biome or cell.elevation <= 0:
                visited.add((x, y))
                continue

            # Flood-fill this biome
            cluster, center = _flood_fill(grid, x, y, width, height, cell.biome, visited)

            rid += 1
            region_id = f"region_{rid:02d}"

            # Mark cells with region ID
            for cx, cy in cluster:
                grid[cy][cx].region_id = region_id

            # Compute attributes
            elevation_band = _elevation_label(
                sum(grid[cy][cx].elevation for cx, cy in cluster) / len(cluster),
            )
            climate_band = _climate_label(
                sum(grid[cy][cx].temperature for cx, cy in cluster) / len(cluster),
            )
            prosperity = _prosperity_base(cell.biome)
            prosperity += rng.uniform(-0.1, 0.1)
            prosperity = max(0.0, min(1.0, prosperity))

            name = _generate_name(rng, cell.biome)

            regions.append(Region(
                id=region_id,
                name=name,
                biome=cell.biome,
                elevation=elevation_band,
                climate=climate_band,
                prosperity=prosperity,
                center_x=center[0],
                center_y=center[1],
            ))

    # Compute neighbors (regions that share a border)
    _compute_neighbors(grid, width, height, regions)

    return regions


def _flood_fill(
    grid: list[list[GridCell]],
    sx: int, sy: int,
    w: int, h: int,
    biome: str,
    visited: set[tuple[int, int]],
) -> tuple[list[tuple[int, int]], tuple[int, int]]:
    """Flood-fill from (sx,sy), return cluster cells + center."""
    stack = [(sx, sy)]
    cluster: list[tuple[int, int]] = []

    while stack:
        x, y = stack.pop()
        if (x, y) in visited:
            continue
        if not (0 <= x < w and 0 <= y < h):
            continue
        cell = grid[y][x]
        if cell.biome != biome or cell.elevation <= 0:
            continue

        visited.add((x, y))
        cluster.append((x, y))

        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            stack.append((x + dx, y + dy))

    # Center = centroid of cluster
    cx = sum(p[0] for p in cluster) // max(1, len(cluster))
    cy = sum(p[1] for p in cluster) // max(1, len(cluster))
    return cluster, (cx, cy)


def _compute_neighbors(
    grid: list[list[GridCell]],
    w: int, h: int,
    regions: list[Region],
) -> None:
    """Compute neighbor relations between regions."""
    region_index: dict[str, int] = {r.id: i for i, r in enumerate(regions)}
    neighbors: dict[str, set[str]] = {r.id: set() for r in regions}

    for y in range(h):
        for x in range(w):
            rid = grid[y][x].region_id
            if not rid:
                continue
            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h:
                    nid = grid[ny][nx].region_id
                    if nid and nid != rid:
                        neighbors[rid].add(nid)

    for rid, nids in neighbors.items():
        if rid in region_index:
            regions[region_index[rid]].neighbors = sorted(nids)


def _elevation_label(avg_elevation: float) -> str:
    for (lo, hi), label in _ELEVATION_LABELS.items():
        if lo <= avg_elevation < hi:
            return label
    return "lowland"


def _climate_label(avg_temp: float) -> str:
    if avg_temp < -0.5:
        return Climate.ARCTIC.value
    if avg_temp < -0.15:
        return Climate.COLD_DRY.value if avg_temp < -0.35 else Climate.COLD_WET.value
    if avg_temp < 0.15:
        return Climate.TEMPERATE_DRY.value if avg_temp < 0.0 else Climate.TEMPERATE_WET.value
    if avg_temp < 0.5:
        return Climate.WARM_DRY.value if avg_temp < 0.35 else Climate.WARM_WET.value
    return Climate.HOT_DRY.value if avg_temp < 0.7 else Climate.HOT_WET.value


def _prosperity_base(biome: str) -> float:
    return _PROSPERITY_BASE.get(biome, 0.5)


def _generate_name(rng: WorldRNG, biome: str) -> str:
    """Generate a procedural region name."""
    terrain = rng.choice(_NAME_TERRAIN)
    feature = rng.choice(_NAME_FEATURE)
    return f"{terrain} {feature}"
