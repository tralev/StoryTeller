# `.story` Package Version 2 Target Specification

## Status

This is the normative target derived from accepted product decisions. Rewrite
Phase 6 materializes it as complete JSON Schemas, freezes numeric parser/security
limits, and proves it with the shared fixture corpus. Those artifacts must match
this document; they do not silently supersede it.

Forge and Player target v2 only. v1 is rejected and has no conversion contract.

## Media type and container

- Extension: `.story`
- Container: ZIP
- Package format identifier: `storyteller.story`
- Package version: integer `2`
- Manifest: root `manifest.json`
- Paths: unique relative UTF-8 names using `/`
- Content: immutable
- Mutable saves: prohibited inside package

## Required layout

```text
manifest.json
schemas/*.schema.json
world/index.json
world/terrain/index.json
world/terrain/chunks/*.bin
world/hydrology.json
world/climate/index.json
world/climate/chunks/*.bin
world/biomes/index.json
world/biomes/chunks/*.bin
world/resources.json
world/regions.json
world/routes.json
world/sites.json
world/civilizations.json
world/history/index.json
world/history/events/*.json
world/history/snapshots/*.json
world/local/index.json
world/local/<site-id>/index.json
world/local/<site-id>/chunks/*.bin
narrative/bible.json
narrative/reconciliation.json
narrative/style_bible.json
narrative/story.json
narrative/graph.json
narrative/gm_index.json
assets/maps/world.png
assets/maps/regions/<region-id>.png
assets/images/<node-id>.png
assets/thumbnails/<node-id>.png
assets/music/<node-id>.score.json
assets/midi/<node-id>.mid
```

Every declared region requires one region map. Every registered site requires a
complete local 3D map, whether or not the narrative uses it. Every graph node
requires exactly one image, thumbnail, authoritative score, and MIDI derivative.

## Forbidden entries

- `save/`, save state, bookmarks, or GM conversations
- Executable/native code, scripts, HTML, or active web content
- Model files or download credentials
- Absolute, parent-relative, link, duplicate, or undeclared paths
- Files with extensions not permitted by the frozen manifest schema

## Canonical ZIP profile

Phase 6 freezes exact settings. Candidate rules:

- Entries sorted by UTF-8 path bytes
- Normalized DOS timestamp
- Normalized regular-file permissions
- No platform-specific extra fields or comments
- ZIP `STORE` for PNG and ZIP `DEFLATE` for JSON, MIDI, and raw binary chunks
- Binary chunks have no independent compression wrapper
- No duplicate directory/file aliases
- Manifest produced from final artifact inventory

The package hash covers final ZIP bytes. The content hash covers the canonical
artifact inventory and is independent of operational run metadata.

## Canonical JSON profile

- Canonicalization: RFC 8785 JSON Canonicalization Scheme (JCS)
- Schema dialect: JSON Schema Draft 2020-12
- UTF-8 without BOM
- No duplicate keys
- No NaN, positive/negative infinity, or implementation-dependent numeric text
- Fixed-point integers for authoritative simulation values where required
- Schema-declared number precision elsewhere
- Stable array ordering specified per domain, never incidental map/set order

## Identifier rules

Entity and artifact IDs are ASCII, globally unique where required, type-prefixed,
stable, and never derived from display names alone. Their frozen grammar is a
lowercase type prefix, `_`, then exactly 32 lowercase hexadecimal characters
encoding a deterministic 128-bit value. The exact regular expression is
`^[a-z][a-z0-9]*_[0-9a-f]{32}$`. SHA-256 fields are always the complete 64
lowercase hexadecimal characters; shortening a content or integrity hash is
forbidden.

Candidate forms:

```text
story_9f1c2d3e4a5b67890123456789abcdef
terrain_a4b5c6d7e8f90123456789abcdef0123
region_00000000000000000000000000000012
site_00000000000000000000000000000042
civ_00000000000000000000000000000007
event_00000000000000000000000000001234
node_00000000000000000000000000000001
knowledge_7fd4b8359cae1203d68f441e2a903c57
```

Artifact IDs are content-derived. Entity IDs derive deterministically from
domain seed and stable creation order/identity rules.

## Manifest structure

```json
{
  "package_format": "storyteller.story",
  "package_version": 2,
  "story_id": "story_9f1c2d3e4a5b67890123456789abcdef",
  "title": "The Ashen Continent",
  "content_profile": "mature_dark_fantasy",
  "master_seed": 42,
  "required_features": [
    "all_site_local_maps",
    "complete_history",
    "complete_world",
    "embedded_schemas",
    "fixed_media_profile",
    "structured_score_midi"
  ],
  "optional_features": [],
  "entry_node": "node_00000000000000000000000000000001",
  "world": {
    "index": "world/index.json",
    "present_year": 500,
    "coordinate_system": "world_cell_xy",
    "metres_per_world_cell": 8000
  },
  "artifacts": [],
  "node_assets": {},
  "region_maps": {},
  "content_hash": "<sha256>"
}
```

The frozen schema must require model, prompt, schema, algorithm, and code
provenance through artifact producers rather than one ambiguous global version.

### v2 feature registry

Every conforming v2 package declares the six required features shown above. They
name independently testable capabilities but do not make core content optional.
`optional_features` is empty for the initial v2 profile. New identifiers use
`^[a-z][a-z0-9_]*$`, require a decision record and schema update, and are sorted by
UTF-8 bytes. An optional feature may add ignorable declared content only; it may
not change the interpretation of existing fields or validation rules.

## Artifact record

```json
{
  "artifact_id": "terrain_a4b5c6d7e8f90123456789abcdef0123",
  "kind": "terrain",
  "path": "world/terrain/index.json",
  "sha256": "<64 lowercase hex>",
  "size_bytes": 123456,
  "depends_on": [],
  "producer": {
    "component": "terrain_generator",
    "algorithm_version": 2,
    "model": null,
    "prompt_sha256": null,
    "schema_sha256": "<sha256>",
    "code_revision": "<revision>",
    "fingerprint": "<sha256>"
  }
}
```

All package files except `manifest.json` have exactly one artifact record.
Dependencies form an acyclic graph and refer only to declared artifact IDs.

### Identity derivation

For an artifact, canonicalize this JCS object and hash it with SHA-256:

```json
{
  "depends_on": ["<sorted artifact IDs>"],
  "kind": "terrain",
  "producer_fingerprint": "<64 lowercase hex>",
  "sha256": "<full content SHA-256>"
}
```

The artifact ID is `<kind>_` plus the first 32 hexadecimal characters of that
digest. Acceptance recomputes it and rejects duplicate IDs or a 128-bit collision
whose full derivation digest differs. `content_hash` is the full SHA-256 of the
JCS array of all artifact records reduced to `artifact_id`, `kind`, `path`,
`sha256`, `size_bytes`, sorted `depends_on`, and `producer.fingerprint`, ordered by
UTF-8 path bytes. `story_id` is `story_` plus the first 32 hexadecimal characters
of `content_hash`. `package_sha256` hashes the final deterministic ZIP bytes and
is operational output rather than a field inside the ZIP, avoiding circularity.

## World index

`world/index.json` declares grid dimensions, scale, continent count, present
year, algorithm versions, domain artifact IDs/paths, and coordinate conventions.
It does not duplicate full domain data.

## Physical domains

The frozen schemas must preserve:

- Terrain: grid, elevation, land/ocean, slope, continent identity
- Hydrology: flow topology, watersheds, rivers, lakes, discharge, coastlines
- Climate: temperature, precipitation, wind, seasons, weather regimes
- Biomes: complete relevant cell/region classification
- Resources: geology/natural resource occurrence and compatibility
- Regions: stable cell membership/boundaries, centers, area, adjacency
- Routes: endpoints, geometry/cells, distance, terrain cost, crossings, risks

Large surface grids use separate domain-specific 256×256 binary chunks. Local 3D
maps use sparse 32×32×16 chunks. Only outer boundaries may use partial dimensions.
Integers are fixed-width, signed where required, little-endian, and row-major under
the domain schema. ZIP compression is the only compression layer.

## Social and history domains

- Sites reference coordinates and containing regions.
- Civilizations reference sites, territory, population, government, culture,
  economy, diplomacy, and present state.
- History retains every material event with year, sequence, kind, causes,
  participants, locations, consequences, and deterministic summary.
- Snapshots exist at year 0, every ten years, and the final year. They identify
  exact ledger positions and contain the complete replay state required by schema.

Causes refer to earlier events. Replaying from a snapshot plus subsequent events
must reproduce the corresponding recorded state hash.

## Narrative domains

- Bible enriches authoritative facts and contains references for every major
  claim and every local entity container.
- Reconciliation records exact input artifact IDs and mandatory ruleset result.
- Story and graph reference stable world/Bible IDs.
- Graph declares entry, nodes, choices, flags, conditions, endings, and exact
  per-node media intent.
- GM index covers complete world/history/narrative knowledge; each entry contains
  source IDs and `reveal_after_nodes`.

## Media

Fixed PNG policy:

- World map: 4096×4096
- Every region map: 1024×1024
- Every node illustration: 1024×1024
- Every node thumbnail: 256×256
- All PNGs: non-interlaced, 8-bit RGBA, sRGB, non-animated

Every node also contains an authoritative `score.json` plus a derived Standard
MIDI File. The score records rational musical positions, tempo/time/key maps,
instrument roles, measures, notes/chords/rests, articulation, dynamics/expression,
loop/intro/outro structure, cultural/location/mood sources, provenance, duration,
and expected MIDI hash. MIDI policy is SMF Type 1 at 960 PPQ, General MIDI
1-compatible programs/drums, separate role tracks, explicit tempo/time/key events,
standard `LOOP_START`, `LOOP_END`, `INTRO_END`, and `OUTRO_START` markers, bounded
pitch bend with declared range, and no proprietary SysEx.

Every rational score position is reduced and exactly representable at 960 PPQ;
rounding is forbidden. MIDI rendering uses the event and track ordering in
`api.md`, so two conforming renderers produce identical bytes. The expected MIDI
SHA-256 is calculated from those bytes and inserted into the final score without
being an input to rendering.

Acceptance:

- Decodes every PNG fully and verifies format/dimensions
- Verifies world map and every region map
- Validates every score and its provenance/source references
- Parses every MIDI, verifies Type 1/960 PPQ, allowed events/programs, loop markers,
  at least one sounding note, positive duration, and score-derived hash
- Verifies every graph node has exactly one declared image, thumbnail, score, and MIDI
- Verifies hashes, size, producer, and dependency IDs

No missing-media threshold or optional node-media state exists.

## Operational data

Run ID, absolute paths, timestamps, duration, RAM samples, retry history, event
logs, and checkpoint DB remain beside the package in the Forge output directory.
They are not canonical package content.

## Player saves

Players key app-private saves by `story_id` and `content_hash`. Save schema is a
Player contract, not a package domain. Package replacement with a different
content hash isolates the old save instead of applying it silently.

## Acceptance order

1. Open ZIP without extraction.
2. Enforce path, link, collision, count, and decompression limits.
3. Parse manifest under bounded JSON rules.
4. Require format/version 2 and complete declared inventory.
5. Extract to private staging only.
6. Verify artifact sizes and hashes.
7. Validate schemas and provenance DAG.
8. Validate world, history, narrative, graph, maps, and media invariants.
9. Atomically publish immutable content; otherwise delete staging.

Embedded schemas are informational, inventory-declared, and hash-verified. Players
always validate with their bundled trusted v2 schemas; an embedded schema can never
alter or weaken acceptance.

## Compatibility

- Unknown package version: reject.
- Version 1: reject with regenerate-v2 guidance.
- Unknown required feature flag: reject.
- `required_features` and `optional_features` are sorted and duplicate-free.
- Unknown optional feature: safely ignore its optional behavior and preserve the
  immutable package content as the frozen schema permits.
- Feature flags cannot disable or weaken core v2 validation.
- Breaking representation change: requires a new package-version decision.

## Items to freeze in Phase 6

- Complete JSON Schemas and schema hashes
- ZIP metadata/profile
- Numeric JSON-nesting, entry-count, compression-amplification, parser-budget,
  and storage-preflight thresholds; no arbitrary total package-size ceiling
- Exact shared valid/invalid fixture corpus
