"""Climate generation — precipitation and drainage.

Precipitation is influenced by prevailing wind patterns (west-to-east
in mid-latitudes), orographic lift (mountains catch rain), and
temperature. Drainage simulates water flowing downhill.
"""

from __future__ import annotations

from .models import GridCell, WorldRNG


def generate_climate(
    grid: list[list[GridCell]],
    seed: int,
) -> None:
    """Set precipitation and drainage on each cell (mutates grid).

    Precipitation:
      - Wind blows from west to east (simplified mid-latitude pattern).
      - Mountains on the windward side catch moisture (orographic lift).
      - Rain shadow on leeward side.
      - Coastal cells get more moisture.
      - Temperature modulates — warm air holds more moisture.

    Drainage:
      - Water flows to the lowest neighbor.
      - Accumulates downstream.
    """
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    if height == 0 or width == 0:
        return

    rng = WorldRNG(seed + 999983)  # Offset from terrain seed

    # ── precipitation ──────────────────────────────────────────────
    # Base moisture decreases as wind crosses land (rainout effect)
    BASE_MOISTURE = 1.0  # Moisture content of incoming wind

    for y in range(height):
        moisture = BASE_MOISTURE
        for x in range(width):
            cell = grid[y][x]
            e = cell.elevation

            # Determine if coastal (near a water cell at any edge)
            is_coastal = _is_coastal(grid, x, y, width, height)
            cell.is_coastal = is_coastal

            if is_coastal:
                moisture = BASE_MOISTURE  # Reset moisture at coast

            # Orographic lift: rising air cools, releases moisture
            if x > 0:
                prev_e = grid[y][x - 1].elevation
                if e > prev_e:
                    # Uphill: rainout
                    drop = (e - prev_e) * 0.4
                    moisture = max(0.0, moisture - drop)
                elif e < prev_e:
                    # Downhill: no additional rainout, but also no rain shadow recovery
                    pass

            # Arid climate: every cell loses a bit of moisture
            moisture = max(0.0, moisture - 0.015)

            # Temperature modifier: warmer = more potential precipitation
            temp_mod = 0.5 + cell.temperature * 0.3  # 0.2 to 0.8

            # Noise for local variation
            noise = rng.noise_2d_smooth(x, y, scale=6.0) * 0.15

            cell.precipitation = max(0.0, min(1.0, moisture * temp_mod + noise))

    # ── drainage ──────────────────────────────────────────────────
    # Water flows to the lowest neighbor, accumulates downstream
    drainage_order = sorted(
        [(x, y) for y in range(height) for x in range(width)],
        key=lambda p: -grid[p[1]][p[0]].elevation,  # High to low
    )

    for x, y in drainage_order:
        cell = grid[y][x]
        nx, ny = _lowest_neighbor(grid, x, y, width, height)
        if nx != x or ny != y:
            grid[ny][nx].drainage += cell.precipitation * 0.5 + cell.drainage

    # Mark river cells (high drainage)
    for y in range(height):
        for x in range(width):
            if grid[y][x].drainage > 2.5:
                grid[y][x].is_river = True


def _is_coastal(
    grid: list[list[GridCell]], x: int, y: int, w: int, h: int,
) -> bool:
    """A cell is coastal if it's land next to water."""
    cell = grid[y][x]
    if cell.elevation <= 0:
        return False  # It's water itself
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1),
                   (-1, -1), (-1, 1), (1, -1), (1, 1)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h:
            if grid[ny][nx].elevation <= 0:
                return True
    return False


def _lowest_neighbor(
    grid: list[list[GridCell]], x: int, y: int, w: int, h: int,
) -> tuple[int, int]:
    """Return the lowest neighbor (including self)."""
    best_x, best_y = x, y
    best_e = grid[y][x].elevation
    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h:
            if grid[ny][nx].elevation < best_e:
                best_e = grid[ny][nx].elevation
                best_x, best_y = nx, ny
    return best_x, best_y
