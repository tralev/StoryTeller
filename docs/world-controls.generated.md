# Generated World Controls

> Generated from `WorldSpec` and the checked CLI classification. All constraints are enforced by `WorldSpec.validate()`.

| Field | Type | Default | CLI mapping | Policy | Resume behavior |
|---|---|---:|---|---|---|
| `width` | integer | `1024` | `--width` | configurable | locked by run fingerprint |
| `height` | integer | `1024` | `--height` | configurable | locked by run fingerprint |
| `continent_count` | integer | `1` | `--continents` | configurable | locked by run fingerprint |
| `metres_per_world_cell` | integer | `8000` | `--metres-per-world-cell` | configurable | locked by run fingerprint |
| `plate_count` | integer | `24` | `--plate-count` | configurable | locked by run fingerprint |
| `minimum_continent_cells` | integer | `4096` | `--minimum-continent-cells` | configurable | locked by run fingerprint |
| `history_years` | integer | `500` | `--history-years` | configurable | locked by run fingerprint |
| `history_ticks_per_year` | integer | `12` | — | fixed worldgen-1 invariant (`12`) | locked by run fingerprint |
| `civilization_count` | integer | `8` | `--civilizations` | configurable | locked by run fingerprint |
| `sea_level_ppm` | integer | `380000` | `--sea-level-ppm` | configurable | locked by run fingerprint |
| `axial_tilt_millidegrees` | integer | `23500` | `--axial-tilt-millidegrees` | configurable | locked by run fingerprint |
| `erosion_passes` | integer | `32` | `--erosion-passes` | configurable | locked by run fingerprint |
| `climate_relaxation_passes` | integer | `64` | `--climate-relaxation-passes` | configurable | locked by run fingerprint |
| `snapshot_interval_years` | integer | `10` | — | fixed worldgen-1 invariant (`10`) | locked by run fingerprint |
| `local_site_width` | integer | `128` | `--local-site-width` | configurable | locked by run fingerprint |
| `local_site_height` | integer | `128` | `--local-site-height` | configurable | locked by run fingerprint |
| `local_z_levels` | integer | `32` | `--local-z-levels` | configurable | locked by run fingerprint |
| `local_cell_millimetres` | integer | `2000` | `--local-cell-millimetres` | configurable | locked by run fingerprint |
