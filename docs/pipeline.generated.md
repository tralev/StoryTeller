# Generated Pipeline Plan

> Current compatibility `PipelinePlan.standard()` snapshot. This is
> implementation evidence, not the target pipeline authority; see `arch.md`
> and remaining migration/cleanup in `roadmap.md`.

| Order | Step | Output | Requires | Model | Failure | Checkpoint |
|---:|---|---|---|---|---|---|
| 1 | `world_builder` | `bible` | — | text | abort | yes |
| 2 | `art_director` | `style_bible` | `bible` | text | abort | yes |
| 3 | `story_writer` | `story` | `bible` | text | abort | yes |
| 4 | `game_designer` | `graph` | `bible`, `story` | text | abort | yes |
| 5 | `music_generator` | `midi` | `graph` | text | quarantine | yes |
| 6 | `image_generator` | `images` | `graph`, `style_bible` | image | quarantine | yes |
| 7 | `indexer` | `gm_index` | `bible`, `graph` | none | abort | yes |
| 8 | `packager` | `packager` | `bible`, `story`, `graph`, `images`, `midi`, `gm_index`, `style_bible` | none | abort | yes |
