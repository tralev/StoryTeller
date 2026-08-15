# Generated Production Pipeline Plan

> `PipelinePlan.production_v2()` is the sole product generation and resume plan.
> This file is generated implementation evidence; see `arch.md` for authority.

| Order | Step | Output | Requires | Model | Failure | Checkpoint |
|---:|---|---|---|---|---|---|
| 1 | `physical_world` | `world_physical` | — | none | abort | yes |
| 2 | `simulate_world` | `world` | `world_physical` | none | abort | yes |
| 3 | `world_builder_v2` | `bible` | `world` | text | abort | yes |
| 4 | `reconcile_world` | `reconciliation` | `world`, `bible` | text | abort | yes |
| 5 | `art_direction_v2` | `style_bible` | `world`, `bible`, `reconciliation` | text | abort | yes |
| 6 | `story_v2` | `story` | `world`, `bible`, `reconciliation` | text | abort | yes |
| 7 | `graph_v2` | `narrative_project` | `world`, `bible`, `reconciliation`, `story` | text | abort | yes |
| 8 | `media_intents_v2` | `media_intents` | `narrative_project` | text | abort | yes |
| 9 | `image_media_v2` | `images` | `narrative_project`, `media_intents`, `style_bible` | image | abort | yes |
| 10 | `local_maps_v2` | `local_maps` | `world`, `narrative_project` | none | abort | yes |
| 11 | `music_media_v2` | `midi` | `narrative_project`, `media_intents` | none | abort | yes |
| 12 | `accept_media_v2` | `media` | `narrative_project`, `images`, `midi` | none | abort | yes |
| 13 | `gm_index_v2` | `gm_index` | `world`, `bible`, `narrative_project`, `local_maps`, `media` | none | abort | yes |
| 14 | `package_v2` | `package_candidate` | `world`, `bible`, `reconciliation`, `style_bible`, `narrative_project`, `media_intents`, `images`, `local_maps`, `midi`, `media`, `gm_index` | none | abort | yes |
| 15 | `accept_package_v2` | `package_acceptance` | `package_candidate` | none | abort | yes |
| 16 | `packager` | `packager` | `package_candidate`, `package_acceptance` | none | abort | yes |
