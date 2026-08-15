# Schema Trace Matrix

> Generated from `scripts/generate_schema_trace.py`.
**Schemas:** 22 | **Total scenarios:** 71

> Fixture counts prove generator coverage only; they are not P8.C1 closure evidence.
> Re-run after schema changes: `python scripts/generate_schema_trace.py`

## artifact-provenance

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | [artifact-provenance-invalid-extra-property](schema_fixtures/artifact-provenance.invalid.extra-property.json) |
| `artifact_id` (type=string, pattern) | required | jsonschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | [artifact-provenance-invalid-missing-artifact_id](schema_fixtures/artifact-provenance.invalid.missing-artifact_id.json) |
| `artifact_id` type enforcement | type | jsonschema | — | [artifact-provenance-invalid-wrong-type-artifact_id](schema_fixtures/artifact-provenance.invalid.wrong-type-artifact_id.json) |
| `artifact_id` pattern `^[a-z][a-z0-9]*_[0-9a-f]{32}$...` | pattern | jsonschema | — | [artifact-provenance-invalid-pattern-artifact_id](schema_fixtures/artifact-provenance.invalid.pattern-artifact_id.json) |
| `kind` (type=string, pattern) | required | jsonschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | [artifact-provenance-invalid-missing-kind](schema_fixtures/artifact-provenance.invalid.missing-kind.json) |
| `kind` type enforcement | type | jsonschema | — | [artifact-provenance-invalid-wrong-type-kind](schema_fixtures/artifact-provenance.invalid.wrong-type-kind.json) |
| `kind` pattern `^[a-z][a-z0-9_]*$...` | pattern | jsonschema | — | [artifact-provenance-invalid-pattern-kind](schema_fixtures/artifact-provenance.invalid.pattern-kind.json) |
| `path` (type=string, pattern) | required | jsonschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | [artifact-provenance-invalid-missing-path](schema_fixtures/artifact-provenance.invalid.missing-path.json) |
| `path` type enforcement | type | jsonschema | — | [artifact-provenance-invalid-wrong-type-path](schema_fixtures/artifact-provenance.invalid.wrong-type-path.json) |
| `path` pattern `^(?!/)(?!.*(?:^|/)\.\.(?:/|$))...` | pattern | jsonschema | — | [artifact-provenance-invalid-pattern-path](schema_fixtures/artifact-provenance.invalid.pattern-path.json) |
| `sha256` (type=string, pattern) | required | jsonschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | [artifact-provenance-invalid-missing-sha256](schema_fixtures/artifact-provenance.invalid.missing-sha256.json) |
| `sha256` type enforcement | type | jsonschema | — | [artifact-provenance-invalid-wrong-type-sha256](schema_fixtures/artifact-provenance.invalid.wrong-type-sha256.json) |
| `sha256` pattern `^[0-9a-f]{64}$...` | pattern | jsonschema | — | [artifact-provenance-invalid-pattern-sha256](schema_fixtures/artifact-provenance.invalid.pattern-sha256.json) |
| `size_bytes` (type=integer, min=0) | required | jsonschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | [artifact-provenance-invalid-missing-size_bytes](schema_fixtures/artifact-provenance.invalid.missing-size_bytes.json) |
| `size_bytes` type enforcement | type | jsonschema | — | [artifact-provenance-invalid-wrong-type-size_bytes](schema_fixtures/artifact-provenance.invalid.wrong-type-size_bytes.json) |
| `depends_on` (type=array) | required | jsonschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | — |
| `producer` (type=object) | required | jsonschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | — |

_18 traceable rules_

## bible

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [bible-valid](schema_fixtures/bible.valid.json) | — |
| `schema_version` (type=?) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-schema_version](schema_fixtures/bible.invalid.missing-schema_version.json) |

_2 traceable rules_

## biomes

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [biomes-valid](schema_fixtures/biomes.valid.json) | — |
| `chunk_shape` (type=?) | required | jsonschema | [biomes-valid](schema_fixtures/biomes.valid.json) | [biomes-invalid-missing-chunk_shape](schema_fixtures/biomes.invalid.missing-chunk_shape.json) |

_2 traceable rules_

## civilizations

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [civilizations-valid](schema_fixtures/civilizations.valid.json) | — |
| `civilizations` (type=?) | required | jsonschema | [civilizations-valid](schema_fixtures/civilizations.valid.json) | [civilizations-invalid-missing-civilizations](schema_fixtures/civilizations.invalid.missing-civilizations.json) |

_2 traceable rules_

## climate

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [climate-valid](schema_fixtures/climate.valid.json) | — |
| `chunk_shape` (type=?) | required | jsonschema | [climate-valid](schema_fixtures/climate.valid.json) | [climate-invalid-missing-chunk_shape](schema_fixtures/climate.invalid.missing-chunk_shape.json) |

_2 traceable rules_

## gm-index

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [gm-index-valid](schema_fixtures/gm-index.valid.json) | — |

_1 traceable rules_

## graph

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [graph-valid](schema_fixtures/graph.valid.json) | — |
| `schema_version` (type=?) | required | jsonschema | [graph-valid](schema_fixtures/graph.valid.json) | [graph-invalid-missing-schema_version](schema_fixtures/graph.invalid.missing-schema_version.json) |
| `starting_node` (type=?) | required | jsonschema | [graph-valid](schema_fixtures/graph.valid.json) | [graph-invalid-missing-starting_node](schema_fixtures/graph.invalid.missing-starting_node.json) |
| `nodes` (type=?) | required | jsonschema | [graph-valid](schema_fixtures/graph.valid.json) | [graph-invalid-missing-nodes](schema_fixtures/graph.invalid.missing-nodes.json) |

_4 traceable rules_

## history

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [history-valid](schema_fixtures/history.valid.json) | — |
| `events` (type=?) | required | jsonschema | [history-valid](schema_fixtures/history.valid.json) | [history-invalid-missing-events](schema_fixtures/history.invalid.missing-events.json) |

_2 traceable rules_

## hydrology

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [hydrology-valid](schema_fixtures/hydrology.valid.json) | — |

_1 traceable rules_

## local-map

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [local-map-valid](schema_fixtures/local-map.valid.json) | — |
| `site_id` (type=?) | required | jsonschema | [local-map-valid](schema_fixtures/local-map.valid.json) | [local-map-invalid-missing-site_id](schema_fixtures/local-map.invalid.missing-site_id.json) |
| `chunk_shape` (type=?) | required | jsonschema | [local-map-valid](schema_fixtures/local-map.valid.json) | [local-map-invalid-missing-chunk_shape](schema_fixtures/local-map.invalid.missing-chunk_shape.json) |

_3 traceable rules_

## manifest

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-extra-property](schema_fixtures/manifest.invalid.extra-property.json) |
| `package_format` (type=?) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-package_format](schema_fixtures/manifest.invalid.missing-package_format.json) |
| `package_version` (type=?) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-package_version](schema_fixtures/manifest.invalid.missing-package_version.json) |
| `story_id` (type=string, pattern) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-story_id](schema_fixtures/manifest.invalid.missing-story_id.json) |
| `story_id` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-story_id](schema_fixtures/manifest.invalid.wrong-type-story_id.json) |
| `story_id` pattern `^story_[0-9a-f]{32}$...` | pattern | jsonschema | — | [manifest-invalid-pattern-story_id](schema_fixtures/manifest.invalid.pattern-story_id.json) |
| `title` (type=string) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-title](schema_fixtures/manifest.invalid.missing-title.json) |
| `title` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-title](schema_fixtures/manifest.invalid.wrong-type-title.json) |
| `content_profile` (type=?) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-content_profile](schema_fixtures/manifest.invalid.missing-content_profile.json) |
| `master_seed` (type=integer) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |
| `required_features` (type=array) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |
| `optional_features` (type=array) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |
| `entry_node` (type=string, pattern) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |
| `world` (type=object) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |
| `artifacts` (type=array) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |
| `node_assets` (type=object) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |
| `region_maps` (type=object) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |
| `content_hash` (type=string, pattern) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |

_19 traceable rules_

## reconciliation

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [reconciliation-valid](schema_fixtures/reconciliation.valid.json) | — |
| `accepted` (type=?) | required | jsonschema | [reconciliation-valid](schema_fixtures/reconciliation.valid.json) | [reconciliation-invalid-missing-accepted](schema_fixtures/reconciliation.invalid.missing-accepted.json) |

_2 traceable rules_

## regions

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [regions-valid](schema_fixtures/regions.valid.json) | — |
| `regions` (type=?) | required | jsonschema | [regions-valid](schema_fixtures/regions.valid.json) | [regions-invalid-missing-regions](schema_fixtures/regions.invalid.missing-regions.json) |

_2 traceable rules_

## resources

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [resources-valid](schema_fixtures/resources.valid.json) | — |

_1 traceable rules_

## routes

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [routes-valid](schema_fixtures/routes.valid.json) | — |
| `routes` (type=?) | required | jsonschema | [routes-valid](schema_fixtures/routes.valid.json) | [routes-invalid-missing-routes](schema_fixtures/routes.invalid.missing-routes.json) |

_2 traceable rules_

## sites

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [sites-valid](schema_fixtures/sites.valid.json) | — |
| `sites` (type=?) | required | jsonschema | [sites-valid](schema_fixtures/sites.valid.json) | [sites-invalid-missing-sites](schema_fixtures/sites.invalid.missing-sites.json) |

_2 traceable rules_

## snapshots

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [snapshots-valid](schema_fixtures/snapshots.valid.json) | — |
| `snapshots` (type=?) | required | jsonschema | [snapshots-valid](schema_fixtures/snapshots.valid.json) | [snapshots-invalid-missing-snapshots](schema_fixtures/snapshots.invalid.missing-snapshots.json) |

_2 traceable rules_

## story

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [story-valid](schema_fixtures/story.valid.json) | — |
| `schema_version` (type=?) | required | jsonschema | [story-valid](schema_fixtures/story.valid.json) | [story-invalid-missing-schema_version](schema_fixtures/story.invalid.missing-schema_version.json) |
| `scenes` (type=?) | required | jsonschema | [story-valid](schema_fixtures/story.valid.json) | [story-invalid-missing-scenes](schema_fixtures/story.invalid.missing-scenes.json) |

_3 traceable rules_

## structured-score

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | — |
| `format_version` (type=?) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-format_version](schema_fixtures/structured-score.invalid.missing-format_version.json) |
| `ppq` (type=?) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-ppq](schema_fixtures/structured-score.invalid.missing-ppq.json) |
| `notes` (type=?) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-notes](schema_fixtures/structured-score.invalid.missing-notes.json) |

_4 traceable rules_

## style

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [style-valid](schema_fixtures/style.valid.json) | — |

_1 traceable rules_

## terrain

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [terrain-valid](schema_fixtures/terrain.valid.json) | — |
| `chunk_shape` (type=?) | required | jsonschema | [terrain-valid](schema_fixtures/terrain.valid.json) | [terrain-invalid-missing-chunk_shape](schema_fixtures/terrain.invalid.missing-chunk_shape.json) |

_2 traceable rules_

## world-index

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [world-index-valid](schema_fixtures/world-index.valid.json) | — |
| `width` (type=?) | required | jsonschema | [world-index-valid](schema_fixtures/world-index.valid.json) | [world-index-invalid-missing-width](schema_fixtures/world-index.invalid.missing-width.json) |
| `height` (type=?) | required | jsonschema | [world-index-valid](schema_fixtures/world-index.valid.json) | [world-index-invalid-missing-height](schema_fixtures/world-index.invalid.missing-height.json) |
| `present_year` (type=?) | required | jsonschema | [world-index-valid](schema_fixtures/world-index.valid.json) | [world-index-invalid-missing-present_year](schema_fixtures/world-index.invalid.missing-present_year.json) |
| `domains` (type=?) | required | jsonschema | [world-index-valid](schema_fixtures/world-index.valid.json) | [world-index-invalid-missing-domains](schema_fixtures/world-index.invalid.missing-domains.json) |

_5 traceable rules_
