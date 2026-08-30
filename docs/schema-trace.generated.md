# Schema Trace Matrix

> Generated from `scripts/generate_schema_trace.py`.
**Schemas:** 25 | **Total scenarios:** 2878

> Depth-gate closure is `scripts/audit_v2_schema_depth.py`. Native field
> parity remains P8.C2.
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
| `depends_on` (type=array) | required | jsonschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | [artifact-provenance-invalid-missing-depends_on](schema_fixtures/artifact-provenance.invalid.missing-depends_on.json) |
| `depends_on` type enforcement | type | jsonschema | — | [artifact-provenance-invalid-wrong-type-depends_on](schema_fixtures/artifact-provenance.invalid.wrong-type-depends_on.json) |
| `producer` (type=object) | required | jsonschema | [artifact-provenance-valid](schema_fixtures/artifact-provenance.valid.json) | [artifact-provenance-invalid-missing-producer](schema_fixtures/artifact-provenance.invalid.missing-producer.json) |
| `producer` type enforcement | type | jsonschema | — | [artifact-provenance-invalid-wrong-type-producer](schema_fixtures/artifact-provenance.invalid.wrong-type-producer.json) |

_20 traceable rules_

## bible

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [bible-valid](schema_fixtures/bible.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-extra-property](schema_fixtures/bible.invalid.extra-property.json) |
| `schema_version` (type=const) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-schema_version](schema_fixtures/bible.invalid.missing-schema_version.json) |
| `title` (type=string) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-title](schema_fixtures/bible.invalid.missing-title.json) |
| `title` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-title](schema_fixtures/bible.invalid.wrong-type-title.json) |
| `present_year` (type=integer, min=0) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-present_year](schema_fixtures/bible.invalid.missing-present_year.json) |
| `present_year` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-present_year](schema_fixtures/bible.invalid.wrong-type-present_year.json) |
| `authoritative_refs` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-authoritative_refs](schema_fixtures/bible.invalid.missing-authoritative_refs.json) |
| `authoritative_refs` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-authoritative_refs](schema_fixtures/bible.invalid.wrong-type-authoritative_refs.json) |
| `regions` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-regions](schema_fixtures/bible.invalid.missing-regions.json) |
| `regions` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-regions](schema_fixtures/bible.invalid.wrong-type-regions.json) |
| `routes` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-routes](schema_fixtures/bible.invalid.missing-routes.json) |
| `routes` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-routes](schema_fixtures/bible.invalid.wrong-type-routes.json) |
| `sites` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-sites](schema_fixtures/bible.invalid.missing-sites.json) |
| `sites` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-sites](schema_fixtures/bible.invalid.wrong-type-sites.json) |
| `civilizations` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-civilizations](schema_fixtures/bible.invalid.missing-civilizations.json) |
| `civilizations` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-civilizations](schema_fixtures/bible.invalid.wrong-type-civilizations.json) |
| `people` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-people](schema_fixtures/bible.invalid.missing-people.json) |
| `people` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-people](schema_fixtures/bible.invalid.wrong-type-people.json) |
| `history` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-history](schema_fixtures/bible.invalid.missing-history.json) |
| `history` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-history](schema_fixtures/bible.invalid.wrong-type-history.json) |
| `local_entities` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-local_entities](schema_fixtures/bible.invalid.missing-local_entities.json) |
| `local_entities` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-local_entities](schema_fixtures/bible.invalid.wrong-type-local_entities.json) |
| `magic_claims` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-magic_claims](schema_fixtures/bible.invalid.missing-magic_claims.json) |
| `magic_claims` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-magic_claims](schema_fixtures/bible.invalid.wrong-type-magic_claims.json) |
| `interpretations` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-interpretations](schema_fixtures/bible.invalid.missing-interpretations.json) |
| `interpretations` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-interpretations](schema_fixtures/bible.invalid.wrong-type-interpretations.json) |
| `megabeasts` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-megabeasts](schema_fixtures/bible.invalid.missing-megabeasts.json) |
| `megabeasts` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-megabeasts](schema_fixtures/bible.invalid.wrong-type-megabeasts.json) |
| `legendary_artifacts` (type=array) | required | jsonschema | [bible-valid](schema_fixtures/bible.valid.json) | [bible-invalid-missing-legendary_artifacts](schema_fixtures/bible.invalid.missing-legendary_artifacts.json) |
| `legendary_artifacts` type enforcement | type | jsonschema | — | [bible-invalid-wrong-type-legendary_artifacts](schema_fixtures/bible.invalid.wrong-type-legendary_artifacts.json) |

_31 traceable rules_

## biomes

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [biomes-valid](schema_fixtures/biomes.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [biomes-valid](schema_fixtures/biomes.valid.json) | [biomes-invalid-extra-property](schema_fixtures/biomes.invalid.extra-property.json) |
| `format` (type=const) | required | jsonschema | [biomes-valid](schema_fixtures/biomes.valid.json) | [biomes-invalid-missing-format](schema_fixtures/biomes.invalid.missing-format.json) |
| `width` (type=integer, min=1) | required | jsonschema | [biomes-valid](schema_fixtures/biomes.valid.json) | [biomes-invalid-missing-width](schema_fixtures/biomes.invalid.missing-width.json) |
| `width` type enforcement | type | jsonschema | — | [biomes-invalid-wrong-type-width](schema_fixtures/biomes.invalid.wrong-type-width.json) |
| `width` minimum=1 | range | jsonschema | — | [biomes-invalid-below-min-width](schema_fixtures/biomes.invalid.below-min-width.json) |
| `height` (type=integer, min=1) | required | jsonschema | [biomes-valid](schema_fixtures/biomes.valid.json) | [biomes-invalid-missing-height](schema_fixtures/biomes.invalid.missing-height.json) |
| `height` type enforcement | type | jsonschema | — | [biomes-invalid-wrong-type-height](schema_fixtures/biomes.invalid.wrong-type-height.json) |
| `height` minimum=1 | range | jsonschema | — | [biomes-invalid-below-min-height](schema_fixtures/biomes.invalid.below-min-height.json) |
| `layers` (type=object) | required | jsonschema | [biomes-valid](schema_fixtures/biomes.valid.json) | [biomes-invalid-missing-layers](schema_fixtures/biomes.invalid.missing-layers.json) |
| `layers` type enforcement | type | jsonschema | — | [biomes-invalid-wrong-type-layers](schema_fixtures/biomes.invalid.wrong-type-layers.json) |

_11 traceable rules_

## civilizations

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [civilizations-valid](schema_fixtures/civilizations.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [civilizations-valid](schema_fixtures/civilizations.valid.json) | [civilizations-invalid-extra-property](schema_fixtures/civilizations.invalid.extra-property.json) |
| `civilizations` (type=array) | required | jsonschema | [civilizations-valid](schema_fixtures/civilizations.valid.json) | [civilizations-invalid-missing-civilizations](schema_fixtures/civilizations.invalid.missing-civilizations.json) |
| `civilizations` type enforcement | type | jsonschema | — | [civilizations-invalid-wrong-type-civilizations](schema_fixtures/civilizations.invalid.wrong-type-civilizations.json) |

_4 traceable rules_

## climate

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [climate-valid](schema_fixtures/climate.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [climate-valid](schema_fixtures/climate.valid.json) | [climate-invalid-extra-property](schema_fixtures/climate.invalid.extra-property.json) |
| `format` (type=const) | required | jsonschema | [climate-valid](schema_fixtures/climate.valid.json) | [climate-invalid-missing-format](schema_fixtures/climate.invalid.missing-format.json) |
| `width` (type=integer, min=1) | required | jsonschema | [climate-valid](schema_fixtures/climate.valid.json) | [climate-invalid-missing-width](schema_fixtures/climate.invalid.missing-width.json) |
| `width` type enforcement | type | jsonschema | — | [climate-invalid-wrong-type-width](schema_fixtures/climate.invalid.wrong-type-width.json) |
| `width` minimum=1 | range | jsonschema | — | [climate-invalid-below-min-width](schema_fixtures/climate.invalid.below-min-width.json) |
| `height` (type=integer, min=1) | required | jsonschema | [climate-valid](schema_fixtures/climate.valid.json) | [climate-invalid-missing-height](schema_fixtures/climate.invalid.missing-height.json) |
| `height` type enforcement | type | jsonschema | — | [climate-invalid-wrong-type-height](schema_fixtures/climate.invalid.wrong-type-height.json) |
| `height` minimum=1 | range | jsonschema | — | [climate-invalid-below-min-height](schema_fixtures/climate.invalid.below-min-height.json) |
| `layers` (type=object) | required | jsonschema | [climate-valid](schema_fixtures/climate.valid.json) | [climate-invalid-missing-layers](schema_fixtures/climate.invalid.missing-layers.json) |
| `layers` type enforcement | type | jsonschema | — | [climate-invalid-wrong-type-layers](schema_fixtures/climate.invalid.wrong-type-layers.json) |

_11 traceable rules_

## defs

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [defs-valid](schema_fixtures/defs.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [defs-valid](schema_fixtures/defs.valid.json) | [defs--worldCoordinate-invalid-extra-property](schema_fixtures/defs--worldCoordinate.invalid.extra-property.json) |

_2 traceable rules_

## gm-index

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [gm-index-valid](schema_fixtures/gm-index.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [gm-index-valid](schema_fixtures/gm-index.valid.json) | [gm-index-invalid-extra-property](schema_fixtures/gm-index.invalid.extra-property.json) |
| `entries` (type=array) | required | jsonschema | [gm-index-valid](schema_fixtures/gm-index.valid.json) | [gm-index-invalid-missing-entries](schema_fixtures/gm-index.invalid.missing-entries.json) |
| `entries` type enforcement | type | jsonschema | — | [gm-index-invalid-wrong-type-entries](schema_fixtures/gm-index.invalid.wrong-type-entries.json) |

_4 traceable rules_

## graph

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [graph-valid](schema_fixtures/graph.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [graph-valid](schema_fixtures/graph.valid.json) | [graph-invalid-extra-property](schema_fixtures/graph.invalid.extra-property.json) |
| `schema_version` (type=const) | required | jsonschema | [graph-valid](schema_fixtures/graph.valid.json) | [graph-invalid-missing-schema_version](schema_fixtures/graph.invalid.missing-schema_version.json) |
| `starting_node` (type=string, pattern) | required | jsonschema | [graph-valid](schema_fixtures/graph.valid.json) | [graph-invalid-missing-starting_node](schema_fixtures/graph.invalid.missing-starting_node.json) |
| `starting_node` type enforcement | type | jsonschema | — | [graph-invalid-wrong-type-starting_node](schema_fixtures/graph.invalid.wrong-type-starting_node.json) |
| `starting_node` pattern `^node_[0-9a-f]{32}$...` | pattern | jsonschema | — | [graph-invalid-pattern-starting_node](schema_fixtures/graph.invalid.pattern-starting_node.json) |
| `flags` (type=array) | required | jsonschema | [graph-valid](schema_fixtures/graph.valid.json) | [graph-invalid-missing-flags](schema_fixtures/graph.invalid.missing-flags.json) |
| `flags` type enforcement | type | jsonschema | — | [graph-invalid-wrong-type-flags](schema_fixtures/graph.invalid.wrong-type-flags.json) |
| `nodes` (type=array) | required | jsonschema | [graph-valid](schema_fixtures/graph.valid.json) | [graph-invalid-missing-nodes](schema_fixtures/graph.invalid.missing-nodes.json) |
| `nodes` type enforcement | type | jsonschema | — | [graph-invalid-wrong-type-nodes](schema_fixtures/graph.invalid.wrong-type-nodes.json) |

_10 traceable rules_

## history-event

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|

_0 traceable rules_

## history

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [history-valid](schema_fixtures/history.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [history-valid](schema_fixtures/history.valid.json) | [history-invalid-extra-property](schema_fixtures/history.invalid.extra-property.json) |
| `events` (type=array) | required | jsonschema | [history-valid](schema_fixtures/history.valid.json) | [history-invalid-missing-events](schema_fixtures/history.invalid.missing-events.json) |
| `events` type enforcement | type | jsonschema | — | [history-invalid-wrong-type-events](schema_fixtures/history.invalid.wrong-type-events.json) |
| `snapshots` (type=array) | required | jsonschema | [history-valid](schema_fixtures/history.valid.json) | [history-invalid-missing-snapshots](schema_fixtures/history.invalid.missing-snapshots.json) |
| `snapshots` type enforcement | type | jsonschema | — | [history-invalid-wrong-type-snapshots](schema_fixtures/history.invalid.wrong-type-snapshots.json) |

_6 traceable rules_

## hydrology

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [hydrology-valid](schema_fixtures/hydrology.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [hydrology-valid](schema_fixtures/hydrology.valid.json) | [hydrology-invalid-extra-property](schema_fixtures/hydrology.invalid.extra-property.json) |
| `algorithm_version` (type=integer, min=1) | required | jsonschema | [hydrology-valid](schema_fixtures/hydrology.valid.json) | [hydrology-invalid-missing-algorithm_version](schema_fixtures/hydrology.invalid.missing-algorithm_version.json) |
| `algorithm_version` type enforcement | type | jsonschema | — | [hydrology-invalid-wrong-type-algorithm_version](schema_fixtures/hydrology.invalid.wrong-type-algorithm_version.json) |
| `algorithm_version` minimum=1 | range | jsonschema | — | [hydrology-invalid-below-min-algorithm_version](schema_fixtures/hydrology.invalid.below-min-algorithm_version.json) |
| `lakes` (type=array) | required | jsonschema | [hydrology-valid](schema_fixtures/hydrology.valid.json) | [hydrology-invalid-missing-lakes](schema_fixtures/hydrology.invalid.missing-lakes.json) |
| `lakes` type enforcement | type | jsonschema | — | [hydrology-invalid-wrong-type-lakes](schema_fixtures/hydrology.invalid.wrong-type-lakes.json) |
| `rivers` (type=array) | required | jsonschema | [hydrology-valid](schema_fixtures/hydrology.valid.json) | [hydrology-invalid-missing-rivers](schema_fixtures/hydrology.invalid.missing-rivers.json) |
| `rivers` type enforcement | type | jsonschema | — | [hydrology-invalid-wrong-type-rivers](schema_fixtures/hydrology.invalid.wrong-type-rivers.json) |
| `terminals` (type=array) | required | jsonschema | [hydrology-valid](schema_fixtures/hydrology.valid.json) | [hydrology-invalid-missing-terminals](schema_fixtures/hydrology.invalid.missing-terminals.json) |
| `terminals` type enforcement | type | jsonschema | — | [hydrology-invalid-wrong-type-terminals](schema_fixtures/hydrology.invalid.wrong-type-terminals.json) |

_11 traceable rules_

## local-map

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [local-map-valid](schema_fixtures/local-map.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [local-map-valid](schema_fixtures/local-map.valid.json) | [local-map-invalid-extra-property](schema_fixtures/local-map.invalid.extra-property.json) |
| `site_id` (type=string, pattern) | required | jsonschema | [local-map-valid](schema_fixtures/local-map.valid.json) | [local-map-invalid-missing-site_id](schema_fixtures/local-map.invalid.missing-site_id.json) |
| `site_id` type enforcement | type | jsonschema | — | [local-map-invalid-wrong-type-site_id](schema_fixtures/local-map.invalid.wrong-type-site_id.json) |
| `site_id` pattern `^[a-z][a-z0-9]*_[0-9a-f]{32}$...` | pattern | jsonschema | — | [local-map-invalid-pattern-site_id](schema_fixtures/local-map.invalid.pattern-site_id.json) |
| `chunk_shape` (type=array) | required | jsonschema | [local-map-valid](schema_fixtures/local-map.valid.json) | [local-map-invalid-missing-chunk_shape](schema_fixtures/local-map.invalid.missing-chunk_shape.json) |
| `chunk_shape` type enforcement | type | jsonschema | — | [local-map-invalid-wrong-type-chunk_shape](schema_fixtures/local-map.invalid.wrong-type-chunk_shape.json) |
| `boundary` (type=object) | required | jsonschema | [local-map-valid](schema_fixtures/local-map.valid.json) | [local-map-invalid-missing-boundary](schema_fixtures/local-map.invalid.missing-boundary.json) |
| `boundary` type enforcement | type | jsonschema | — | [local-map-invalid-wrong-type-boundary](schema_fixtures/local-map.invalid.wrong-type-boundary.json) |
| `macro_summary` (type=object) | required | jsonschema | [local-map-valid](schema_fixtures/local-map.valid.json) | [local-map-invalid-missing-macro_summary](schema_fixtures/local-map.invalid.missing-macro_summary.json) |
| `macro_summary` type enforcement | type | jsonschema | — | [local-map-invalid-wrong-type-macro_summary](schema_fixtures/local-map.invalid.wrong-type-macro_summary.json) |
| `chunks` (type=array) | required | jsonschema | [local-map-valid](schema_fixtures/local-map.valid.json) | [local-map-invalid-missing-chunks](schema_fixtures/local-map.invalid.missing-chunks.json) |
| `chunks` type enforcement | type | jsonschema | — | [local-map-invalid-wrong-type-chunks](schema_fixtures/local-map.invalid.wrong-type-chunks.json) |
| `occupancy_chunks` (type=array) | required | jsonschema | [local-map-valid](schema_fixtures/local-map.valid.json) | [local-map-invalid-missing-occupancy_chunks](schema_fixtures/local-map.invalid.missing-occupancy_chunks.json) |
| `occupancy_chunks` type enforcement | type | jsonschema | — | [local-map-invalid-wrong-type-occupancy_chunks](schema_fixtures/local-map.invalid.wrong-type-occupancy_chunks.json) |
| `construction_chunks` (type=array) | required | jsonschema | [local-map-valid](schema_fixtures/local-map.valid.json) | [local-map-invalid-missing-construction_chunks](schema_fixtures/local-map.invalid.missing-construction_chunks.json) |
| `construction_chunks` type enforcement | type | jsonschema | — | [local-map-invalid-wrong-type-construction_chunks](schema_fixtures/local-map.invalid.wrong-type-construction_chunks.json) |

_17 traceable rules_

## manifest

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [manifest-valid](schema_fixtures/manifest.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-extra-property](schema_fixtures/manifest.invalid.extra-property.json) |
| `package_format` (type=const) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-package_format](schema_fixtures/manifest.invalid.missing-package_format.json) |
| `package_version` (type=const) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-package_version](schema_fixtures/manifest.invalid.missing-package_version.json) |
| `story_id` (type=string, pattern) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-story_id](schema_fixtures/manifest.invalid.missing-story_id.json) |
| `story_id` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-story_id](schema_fixtures/manifest.invalid.wrong-type-story_id.json) |
| `story_id` pattern `^story_[0-9a-f]{32}$...` | pattern | jsonschema | — | [manifest-invalid-pattern-story_id](schema_fixtures/manifest.invalid.pattern-story_id.json) |
| `title` (type=string) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-title](schema_fixtures/manifest.invalid.missing-title.json) |
| `title` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-title](schema_fixtures/manifest.invalid.wrong-type-title.json) |
| `content_profile` (type=const) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-content_profile](schema_fixtures/manifest.invalid.missing-content_profile.json) |
| `master_seed` (type=integer, min=-9007199254740991) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-master_seed](schema_fixtures/manifest.invalid.missing-master_seed.json) |
| `master_seed` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-master_seed](schema_fixtures/manifest.invalid.wrong-type-master_seed.json) |
| `required_features` (type=array) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-required_features](schema_fixtures/manifest.invalid.missing-required_features.json) |
| `required_features` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-required_features](schema_fixtures/manifest.invalid.wrong-type-required_features.json) |
| `optional_features` (type=array) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-optional_features](schema_fixtures/manifest.invalid.missing-optional_features.json) |
| `optional_features` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-optional_features](schema_fixtures/manifest.invalid.wrong-type-optional_features.json) |
| `entry_node` (type=string, pattern) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-entry_node](schema_fixtures/manifest.invalid.missing-entry_node.json) |
| `entry_node` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-entry_node](schema_fixtures/manifest.invalid.wrong-type-entry_node.json) |
| `entry_node` pattern `^node_[0-9a-f]{32}$...` | pattern | jsonschema | — | [manifest-invalid-pattern-entry_node](schema_fixtures/manifest.invalid.pattern-entry_node.json) |
| `world` (type=object) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-world](schema_fixtures/manifest.invalid.missing-world.json) |
| `world` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-world](schema_fixtures/manifest.invalid.wrong-type-world.json) |
| `artifacts` (type=array) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-artifacts](schema_fixtures/manifest.invalid.missing-artifacts.json) |
| `artifacts` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-artifacts](schema_fixtures/manifest.invalid.wrong-type-artifacts.json) |
| `node_assets` (type=object) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-node_assets](schema_fixtures/manifest.invalid.missing-node_assets.json) |
| `node_assets` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-node_assets](schema_fixtures/manifest.invalid.wrong-type-node_assets.json) |
| `region_maps` (type=object) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-region_maps](schema_fixtures/manifest.invalid.missing-region_maps.json) |
| `region_maps` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-region_maps](schema_fixtures/manifest.invalid.wrong-type-region_maps.json) |
| `content_hash` (type=string, pattern) | required | jsonschema | [manifest-valid](schema_fixtures/manifest.valid.json) | [manifest-invalid-missing-content_hash](schema_fixtures/manifest.invalid.missing-content_hash.json) |
| `content_hash` type enforcement | type | jsonschema | — | [manifest-invalid-wrong-type-content_hash](schema_fixtures/manifest.invalid.wrong-type-content_hash.json) |
| `content_hash` pattern `^[0-9a-f]{64}$...` | pattern | jsonschema | — | [manifest-invalid-pattern-content_hash](schema_fixtures/manifest.invalid.pattern-content_hash.json) |

_30 traceable rules_

## reconciliation

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [reconciliation-valid](schema_fixtures/reconciliation.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [reconciliation-valid](schema_fixtures/reconciliation.valid.json) | [reconciliation-invalid-extra-property](schema_fixtures/reconciliation.invalid.extra-property.json) |
| `accepted` (type=const) | required | jsonschema | [reconciliation-valid](schema_fixtures/reconciliation.valid.json) | [reconciliation-invalid-missing-accepted](schema_fixtures/reconciliation.invalid.missing-accepted.json) |
| `world_artifact_ids` (type=object) | required | jsonschema | [reconciliation-valid](schema_fixtures/reconciliation.valid.json) | [reconciliation-invalid-missing-world_artifact_ids](schema_fixtures/reconciliation.invalid.missing-world_artifact_ids.json) |
| `world_artifact_ids` type enforcement | type | jsonschema | — | [reconciliation-invalid-wrong-type-world_artifact_ids](schema_fixtures/reconciliation.invalid.wrong-type-world_artifact_ids.json) |
| `world_file_hashes` (type=object) | required | jsonschema | [reconciliation-valid](schema_fixtures/reconciliation.valid.json) | [reconciliation-invalid-missing-world_file_hashes](schema_fixtures/reconciliation.invalid.missing-world_file_hashes.json) |
| `world_file_hashes` type enforcement | type | jsonschema | — | [reconciliation-invalid-wrong-type-world_file_hashes](schema_fixtures/reconciliation.invalid.wrong-type-world_file_hashes.json) |
| `ruleset_version` (type=integer, min=1) | required | jsonschema | [reconciliation-valid](schema_fixtures/reconciliation.valid.json) | [reconciliation-invalid-missing-ruleset_version](schema_fixtures/reconciliation.invalid.missing-ruleset_version.json) |
| `ruleset_version` type enforcement | type | jsonschema | — | [reconciliation-invalid-wrong-type-ruleset_version](schema_fixtures/reconciliation.invalid.wrong-type-ruleset_version.json) |
| `ruleset_version` minimum=1 | range | jsonschema | — | [reconciliation-invalid-below-min-ruleset_version](schema_fixtures/reconciliation.invalid.below-min-ruleset_version.json) |
| `issues` (type=array) | required | jsonschema | [reconciliation-valid](schema_fixtures/reconciliation.valid.json) | [reconciliation-invalid-missing-issues](schema_fixtures/reconciliation.invalid.missing-issues.json) |
| `issues` type enforcement | type | jsonschema | — | [reconciliation-invalid-wrong-type-issues](schema_fixtures/reconciliation.invalid.wrong-type-issues.json) |

_12 traceable rules_

## regions

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [regions-valid](schema_fixtures/regions.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [regions-valid](schema_fixtures/regions.valid.json) | [regions-invalid-extra-property](schema_fixtures/regions.invalid.extra-property.json) |
| `regions` (type=array) | required | jsonschema | [regions-valid](schema_fixtures/regions.valid.json) | [regions-invalid-missing-regions](schema_fixtures/regions.invalid.missing-regions.json) |
| `regions` type enforcement | type | jsonschema | — | [regions-invalid-wrong-type-regions](schema_fixtures/regions.invalid.wrong-type-regions.json) |

_4 traceable rules_

## resources

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [resources-valid](schema_fixtures/resources.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [resources-valid](schema_fixtures/resources.valid.json) | [resources-invalid-extra-property](schema_fixtures/resources.invalid.extra-property.json) |
| `algorithm_version` (type=integer, min=1) | required | jsonschema | [resources-valid](schema_fixtures/resources.valid.json) | [resources-invalid-missing-algorithm_version](schema_fixtures/resources.invalid.missing-algorithm_version.json) |
| `algorithm_version` type enforcement | type | jsonschema | — | [resources-invalid-wrong-type-algorithm_version](schema_fixtures/resources.invalid.wrong-type-algorithm_version.json) |
| `algorithm_version` minimum=1 | range | jsonschema | — | [resources-invalid-below-min-algorithm_version](schema_fixtures/resources.invalid.below-min-algorithm_version.json) |
| `deposits` (type=array) | required | jsonschema | [resources-valid](schema_fixtures/resources.valid.json) | [resources-invalid-missing-deposits](schema_fixtures/resources.invalid.missing-deposits.json) |
| `deposits` type enforcement | type | jsonschema | — | [resources-invalid-wrong-type-deposits](schema_fixtures/resources.invalid.wrong-type-deposits.json) |

_7 traceable rules_

## routes

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [routes-valid](schema_fixtures/routes.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [routes-valid](schema_fixtures/routes.valid.json) | [routes-invalid-extra-property](schema_fixtures/routes.invalid.extra-property.json) |
| `routes` (type=array) | required | jsonschema | [routes-valid](schema_fixtures/routes.valid.json) | [routes-invalid-missing-routes](schema_fixtures/routes.invalid.missing-routes.json) |
| `routes` type enforcement | type | jsonschema | — | [routes-invalid-wrong-type-routes](schema_fixtures/routes.invalid.wrong-type-routes.json) |

_4 traceable rules_

## sites

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [sites-valid](schema_fixtures/sites.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [sites-valid](schema_fixtures/sites.valid.json) | [sites-invalid-extra-property](schema_fixtures/sites.invalid.extra-property.json) |
| `sites` (type=array) | required | jsonschema | [sites-valid](schema_fixtures/sites.valid.json) | [sites-invalid-missing-sites](schema_fixtures/sites.invalid.missing-sites.json) |
| `sites` type enforcement | type | jsonschema | — | [sites-invalid-wrong-type-sites](schema_fixtures/sites.invalid.wrong-type-sites.json) |

_4 traceable rules_

## snapshots

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|

_0 traceable rules_

## story

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [story-valid](schema_fixtures/story.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [story-valid](schema_fixtures/story.valid.json) | [story-invalid-extra-property](schema_fixtures/story.invalid.extra-property.json) |
| `schema_version` (type=const) | required | jsonschema | [story-valid](schema_fixtures/story.valid.json) | [story-invalid-missing-schema_version](schema_fixtures/story.invalid.missing-schema_version.json) |
| `title` (type=string) | required | jsonschema | [story-valid](schema_fixtures/story.valid.json) | [story-invalid-missing-title](schema_fixtures/story.invalid.missing-title.json) |
| `title` type enforcement | type | jsonschema | — | [story-invalid-wrong-type-title](schema_fixtures/story.invalid.wrong-type-title.json) |
| `world_artifact_ids` (type=array) | required | jsonschema | [story-valid](schema_fixtures/story.valid.json) | [story-invalid-missing-world_artifact_ids](schema_fixtures/story.invalid.missing-world_artifact_ids.json) |
| `world_artifact_ids` type enforcement | type | jsonschema | — | [story-invalid-wrong-type-world_artifact_ids](schema_fixtures/story.invalid.wrong-type-world_artifact_ids.json) |
| `bible_hash` (type=string, pattern) | required | jsonschema | [story-valid](schema_fixtures/story.valid.json) | [story-invalid-missing-bible_hash](schema_fixtures/story.invalid.missing-bible_hash.json) |
| `bible_hash` type enforcement | type | jsonschema | — | [story-invalid-wrong-type-bible_hash](schema_fixtures/story.invalid.wrong-type-bible_hash.json) |
| `bible_hash` pattern `^[0-9a-f]{64}$...` | pattern | jsonschema | — | [story-invalid-pattern-bible_hash](schema_fixtures/story.invalid.pattern-bible_hash.json) |
| `reconciliation_hash` (type=string, pattern) | required | jsonschema | [story-valid](schema_fixtures/story.valid.json) | [story-invalid-missing-reconciliation_hash](schema_fixtures/story.invalid.missing-reconciliation_hash.json) |
| `reconciliation_hash` type enforcement | type | jsonschema | — | [story-invalid-wrong-type-reconciliation_hash](schema_fixtures/story.invalid.wrong-type-reconciliation_hash.json) |
| `reconciliation_hash` pattern `^[0-9a-f]{64}$...` | pattern | jsonschema | — | [story-invalid-pattern-reconciliation_hash](schema_fixtures/story.invalid.pattern-reconciliation_hash.json) |
| `scenes` (type=array) | required | jsonschema | [story-valid](schema_fixtures/story.valid.json) | [story-invalid-missing-scenes](schema_fixtures/story.invalid.missing-scenes.json) |
| `scenes` type enforcement | type | jsonschema | — | [story-invalid-wrong-type-scenes](schema_fixtures/story.invalid.wrong-type-scenes.json) |

_15 traceable rules_

## structured-score

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-extra-property](schema_fixtures/structured-score.invalid.extra-property.json) |
| `schema_version` (type=const) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-schema_version](schema_fixtures/structured-score.invalid.missing-schema_version.json) |
| `node_id` (type=string, pattern) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-node_id](schema_fixtures/structured-score.invalid.missing-node_id.json) |
| `node_id` type enforcement | type | jsonschema | — | [structured-score-invalid-wrong-type-node_id](schema_fixtures/structured-score.invalid.wrong-type-node_id.json) |
| `node_id` pattern `^node_[0-9a-f]{32}$...` | pattern | jsonschema | — | [structured-score-invalid-pattern-node_id](schema_fixtures/structured-score.invalid.pattern-node_id.json) |
| `ppq` (type=const) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-ppq](schema_fixtures/structured-score.invalid.missing-ppq.json) |
| `duration` (type=object) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-duration](schema_fixtures/structured-score.invalid.missing-duration.json) |
| `duration` type enforcement | type | jsonschema | — | [structured-score-invalid-wrong-type-duration](schema_fixtures/structured-score.invalid.wrong-type-duration.json) |
| `tempo_map` (type=array) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-tempo_map](schema_fixtures/structured-score.invalid.missing-tempo_map.json) |
| `tempo_map` type enforcement | type | jsonschema | — | [structured-score-invalid-wrong-type-tempo_map](schema_fixtures/structured-score.invalid.wrong-type-tempo_map.json) |
| `time_signature_map` (type=array) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-time_signature_map](schema_fixtures/structured-score.invalid.missing-time_signature_map.json) |
| `time_signature_map` type enforcement | type | jsonschema | — | [structured-score-invalid-wrong-type-time_signature_map](schema_fixtures/structured-score.invalid.wrong-type-time_signature_map.json) |
| `key_signature_map` (type=array) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-key_signature_map](schema_fixtures/structured-score.invalid.missing-key_signature_map.json) |
| `key_signature_map` type enforcement | type | jsonschema | — | [structured-score-invalid-wrong-type-key_signature_map](schema_fixtures/structured-score.invalid.wrong-type-key_signature_map.json) |
| `tracks` (type=array) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-tracks](schema_fixtures/structured-score.invalid.missing-tracks.json) |
| `tracks` type enforcement | type | jsonschema | — | [structured-score-invalid-wrong-type-tracks](schema_fixtures/structured-score.invalid.wrong-type-tracks.json) |
| `markers` (type=object) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-markers](schema_fixtures/structured-score.invalid.missing-markers.json) |
| `markers` type enforcement | type | jsonschema | — | [structured-score-invalid-wrong-type-markers](schema_fixtures/structured-score.invalid.wrong-type-markers.json) |
| `source_ids` (type=array) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-source_ids](schema_fixtures/structured-score.invalid.missing-source_ids.json) |
| `source_ids` type enforcement | type | jsonschema | — | [structured-score-invalid-wrong-type-source_ids](schema_fixtures/structured-score.invalid.wrong-type-source_ids.json) |
| `producer_fingerprint` (type=string, pattern) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-producer_fingerprint](schema_fixtures/structured-score.invalid.missing-producer_fingerprint.json) |
| `producer_fingerprint` type enforcement | type | jsonschema | — | [structured-score-invalid-wrong-type-producer_fingerprint](schema_fixtures/structured-score.invalid.wrong-type-producer_fingerprint.json) |
| `producer_fingerprint` pattern `^[0-9a-f]{64}$...` | pattern | jsonschema | — | [structured-score-invalid-pattern-producer_fingerprint](schema_fixtures/structured-score.invalid.pattern-producer_fingerprint.json) |
| `expected_midi_sha256` (type=string, pattern) | required | jsonschema | [structured-score-valid](schema_fixtures/structured-score.valid.json) | [structured-score-invalid-missing-expected_midi_sha256](schema_fixtures/structured-score.invalid.missing-expected_midi_sha256.json) |
| `expected_midi_sha256` type enforcement | type | jsonschema | — | [structured-score-invalid-wrong-type-expected_midi_sha256](schema_fixtures/structured-score.invalid.wrong-type-expected_midi_sha256.json) |
| `expected_midi_sha256` pattern `^[0-9a-f]{64}$...` | pattern | jsonschema | — | [structured-score-invalid-pattern-expected_midi_sha256](schema_fixtures/structured-score.invalid.pattern-expected_midi_sha256.json) |

_27 traceable rules_

## style

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [style-valid](schema_fixtures/style.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [style-valid](schema_fixtures/style.valid.json) | [style-invalid-extra-property](schema_fixtures/style.invalid.extra-property.json) |
| `map_artifact_id` (type=string, pattern) | required | jsonschema | [style-valid](schema_fixtures/style.valid.json) | [style-invalid-missing-map_artifact_id](schema_fixtures/style.invalid.missing-map_artifact_id.json) |
| `map_artifact_id` type enforcement | type | jsonschema | — | [style-invalid-wrong-type-map_artifact_id](schema_fixtures/style.invalid.wrong-type-map_artifact_id.json) |
| `map_artifact_id` pattern `^[a-z][a-z0-9]*_[0-9a-f]{32}$...` | pattern | jsonschema | — | [style-invalid-pattern-map_artifact_id](schema_fixtures/style.invalid.pattern-map_artifact_id.json) |
| `climate_artifact_id` (type=string, pattern) | required | jsonschema | [style-valid](schema_fixtures/style.valid.json) | [style-invalid-missing-climate_artifact_id](schema_fixtures/style.invalid.missing-climate_artifact_id.json) |
| `climate_artifact_id` type enforcement | type | jsonschema | — | [style-invalid-wrong-type-climate_artifact_id](schema_fixtures/style.invalid.wrong-type-climate_artifact_id.json) |
| `climate_artifact_id` pattern `^[a-z][a-z0-9]*_[0-9a-f]{32}$...` | pattern | jsonschema | — | [style-invalid-pattern-climate_artifact_id](schema_fixtures/style.invalid.pattern-climate_artifact_id.json) |
| `accepted_bible_refs` (type=array) | required | jsonschema | [style-valid](schema_fixtures/style.valid.json) | [style-invalid-missing-accepted_bible_refs](schema_fixtures/style.invalid.missing-accepted_bible_refs.json) |
| `accepted_bible_refs` type enforcement | type | jsonschema | — | [style-invalid-wrong-type-accepted_bible_refs](schema_fixtures/style.invalid.wrong-type-accepted_bible_refs.json) |
| `climate_palettes` (type=object) | required | jsonschema | [style-valid](schema_fixtures/style.valid.json) | [style-invalid-missing-climate_palettes](schema_fixtures/style.invalid.missing-climate_palettes.json) |
| `climate_palettes` type enforcement | type | jsonschema | — | [style-invalid-wrong-type-climate_palettes](schema_fixtures/style.invalid.wrong-type-climate_palettes.json) |
| `culture_motifs` (type=object) | required | jsonschema | [style-valid](schema_fixtures/style.valid.json) | [style-invalid-missing-culture_motifs](schema_fixtures/style.invalid.missing-culture_motifs.json) |
| `culture_motifs` type enforcement | type | jsonschema | — | [style-invalid-wrong-type-culture_motifs](schema_fixtures/style.invalid.wrong-type-culture_motifs.json) |
| `world_map` (type=string, pattern) | required | jsonschema | [style-valid](schema_fixtures/style.valid.json) | [style-invalid-missing-world_map](schema_fixtures/style.invalid.missing-world_map.json) |
| `world_map` type enforcement | type | jsonschema | — | [style-invalid-wrong-type-world_map](schema_fixtures/style.invalid.wrong-type-world_map.json) |
| `world_map` pattern `^(?!/)(?!.*(?:^|/)\.\.(?:/|$))...` | pattern | jsonschema | — | [style-invalid-pattern-world_map](schema_fixtures/style.invalid.pattern-world_map.json) |

_17 traceable rules_

## terrain

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [terrain-valid](schema_fixtures/terrain.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [terrain-valid](schema_fixtures/terrain.valid.json) | [terrain-invalid-extra-property](schema_fixtures/terrain.invalid.extra-property.json) |
| `format` (type=const) | required | jsonschema | [terrain-valid](schema_fixtures/terrain.valid.json) | [terrain-invalid-missing-format](schema_fixtures/terrain.invalid.missing-format.json) |
| `width` (type=integer, min=1) | required | jsonschema | [terrain-valid](schema_fixtures/terrain.valid.json) | [terrain-invalid-missing-width](schema_fixtures/terrain.invalid.missing-width.json) |
| `width` type enforcement | type | jsonschema | — | [terrain-invalid-wrong-type-width](schema_fixtures/terrain.invalid.wrong-type-width.json) |
| `width` minimum=1 | range | jsonschema | — | [terrain-invalid-below-min-width](schema_fixtures/terrain.invalid.below-min-width.json) |
| `height` (type=integer, min=1) | required | jsonschema | [terrain-valid](schema_fixtures/terrain.valid.json) | [terrain-invalid-missing-height](schema_fixtures/terrain.invalid.missing-height.json) |
| `height` type enforcement | type | jsonschema | — | [terrain-invalid-wrong-type-height](schema_fixtures/terrain.invalid.wrong-type-height.json) |
| `height` minimum=1 | range | jsonschema | — | [terrain-invalid-below-min-height](schema_fixtures/terrain.invalid.below-min-height.json) |
| `layers` (type=object) | required | jsonschema | [terrain-valid](schema_fixtures/terrain.valid.json) | [terrain-invalid-missing-layers](schema_fixtures/terrain.invalid.missing-layers.json) |
| `layers` type enforcement | type | jsonschema | — | [terrain-invalid-wrong-type-layers](schema_fixtures/terrain.invalid.wrong-type-layers.json) |

_11 traceable rules_

## world-index

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [world-index-valid](schema_fixtures/world-index.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [world-index-valid](schema_fixtures/world-index.valid.json) | [world-index-invalid-extra-property](schema_fixtures/world-index.invalid.extra-property.json) |
| `width` (type=integer, min=1) | required | jsonschema | [world-index-valid](schema_fixtures/world-index.valid.json) | [world-index-invalid-missing-width](schema_fixtures/world-index.invalid.missing-width.json) |
| `width` type enforcement | type | jsonschema | — | [world-index-invalid-wrong-type-width](schema_fixtures/world-index.invalid.wrong-type-width.json) |
| `width` minimum=1 | range | jsonschema | — | [world-index-invalid-below-min-width](schema_fixtures/world-index.invalid.below-min-width.json) |
| `height` (type=integer, min=1) | required | jsonschema | [world-index-valid](schema_fixtures/world-index.valid.json) | [world-index-invalid-missing-height](schema_fixtures/world-index.invalid.missing-height.json) |
| `height` type enforcement | type | jsonschema | — | [world-index-invalid-wrong-type-height](schema_fixtures/world-index.invalid.wrong-type-height.json) |
| `height` minimum=1 | range | jsonschema | — | [world-index-invalid-below-min-height](schema_fixtures/world-index.invalid.below-min-height.json) |
| `present_year` (type=integer, min=0) | required | jsonschema | [world-index-valid](schema_fixtures/world-index.valid.json) | [world-index-invalid-missing-present_year](schema_fixtures/world-index.invalid.missing-present_year.json) |
| `present_year` type enforcement | type | jsonschema | — | [world-index-invalid-wrong-type-present_year](schema_fixtures/world-index.invalid.wrong-type-present_year.json) |
| `domains` (type=array) | required | jsonschema | [world-index-valid](schema_fixtures/world-index.valid.json) | [world-index-invalid-missing-domains](schema_fixtures/world-index.invalid.missing-domains.json) |
| `domains` type enforcement | type | jsonschema | — | [world-index-invalid-wrong-type-domains](schema_fixtures/world-index.invalid.wrong-type-domains.json) |

_12 traceable rules_

## world-source-coverage

| Rule | Type | Validator | Valid Fixture | Invalid Fixture |
|---|---|---|---|---|
| Root type: `object` | type | metaschema | [world-source-coverage-valid](schema_fixtures/world-source-coverage.valid.json) | — |
| `additionalProperties: false` | constraint | jsonschema | [world-source-coverage-valid](schema_fixtures/world-source-coverage.valid.json) | [world-source-coverage-invalid-extra-property](schema_fixtures/world-source-coverage.invalid.extra-property.json) |
| `format` (type=const) | required | jsonschema | [world-source-coverage-valid](schema_fixtures/world-source-coverage.valid.json) | [world-source-coverage-invalid-missing-format](schema_fixtures/world-source-coverage.invalid.missing-format.json) |
| `required_domains` (type=array) | required | jsonschema | [world-source-coverage-valid](schema_fixtures/world-source-coverage.valid.json) | [world-source-coverage-invalid-missing-required_domains](schema_fixtures/world-source-coverage.invalid.missing-required_domains.json) |
| `required_domains` type enforcement | type | jsonschema | — | [world-source-coverage-invalid-wrong-type-required_domains](schema_fixtures/world-source-coverage.invalid.wrong-type-required_domains.json) |
| `sources` (type=array) | required | jsonschema | [world-source-coverage-valid](schema_fixtures/world-source-coverage.valid.json) | [world-source-coverage-invalid-missing-sources](schema_fixtures/world-source-coverage.invalid.missing-sources.json) |
| `sources` type enforcement | type | jsonschema | — | [world-source-coverage-invalid-wrong-type-sources](schema_fixtures/world-source-coverage.invalid.wrong-type-sources.json) |

_7 traceable rules_
