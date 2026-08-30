# `.story` Package Version 2 Frozen Specification

## Status

This prose is the normative frozen contract. The Draft 2020-12 schemas in
`schemas/v2`, reference validator, native validators, and shared fixture corpus
are intended executable expressions of it. Any omission or disagreement is a
release-blocking defect; current schema/validator closure is tracked by
`roadmap.md` P8.C1–P8.C2.

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
world/source/coverage.json
world/source/*.json
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
Every authoritative source envelope requires one byte-identical
`world/source/<name>.json` member and exactly one row in
`world/source/coverage.json`, including envelopes unused by the narrative. The
ledger records source name, archive path, artifact ID, SHA-256, size, and
byte-for-byte retention policy; its set must equal `world/index.json.domains`
and contain every required world domain.

## Forbidden entries

- `save/`, save state, bookmarks, or GM conversations
- Executable/native code, scripts, HTML, or active web content
- Model files or download credentials
- Absolute, parent-relative, link, duplicate, or undeclared paths
- Files with extensions not permitted by the frozen manifest schema

## Canonical ZIP profile

The canonical settings are:

- Entries sorted by UTF-8 path bytes
- Normalized DOS timestamp
- Normalized regular-file permissions
- No platform-specific extra fields or comments
- ZIP `STORE` for PNG and ZIP `DEFLATE` for JSON, MIDI, and raw binary chunks
- Binary chunks have no independent compression wrapper
- No duplicate directory/file aliases
- Manifest produced from final artifact inventory

The ZIP container is never hashed. `content_hash` covers the canonical artifact
inventory and is independent of ZIP compression, entry metadata, ordering, and
operational run metadata.

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

The frozen schema requires model, prompt, schema, algorithm, and code provenance
through artifact producers rather than one ambiguous global version.

### v2 feature registry

Every conforming v2 package declares exactly the six required features shown
above. They name independently testable capabilities but do not make core content
optional.
`optional_features` is empty for the initial v2 profile.
New feature identifiers use `^[a-z][a-z0-9_]*$`.
Adding a feature identifier requires a decision record and schema update.
Feature identifiers are sorted by UTF-8 bytes.
An optional feature may add ignorable declared content only.
An optional feature may not change the interpretation of existing fields or
validation rules.

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

Every package file except `manifest.json` has exactly one artifact record.
Every dependency refers to a declared artifact ID.
Artifact dependencies form an acyclic graph.

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
digest.
Acceptance recomputes artifact IDs and rejects duplicate IDs.
Acceptance rejects a 128-bit collision whose full derivation digest differs.
`content_hash` is the full SHA-256 of the JCS array of all artifact records reduced
to `artifact_id`, `kind`, `path`, `sha256`, `size_bytes`, sorted `depends_on`, and
`producer.fingerprint`, ordered by UTF-8 path bytes.
`story_id` is `story_` plus the first 32 hexadecimal characters of `content_hash`.
There is no separate package-byte hash.
Package verification reopens the archive and hashes the declared internal files.

## World index

`world/index.json` declares grid dimensions, scale, continent count, present
year, algorithm versions, domain artifact IDs/paths, and coordinate conventions.
It does not duplicate full domain data.

## Physical domains

- Terrain catalogs require elevation, plate identity and boundaries, slope,
  land/ocean classification, and continent identity layers.
- Hydrology records require algorithm version, lakes, rivers, and drainage terminals.
- Hydrology catalogs preserve flow topology, watersheds, discharge, coastlines,
  aquifers, salinity, snowpack, glaciers, and deltas.
- Climate catalogs require annual temperature, annual precipitation, and weather
  regime layers.
- Climate catalogs preserve each declared season's temperature, precipitation,
  evaporation, snowpack, ice, storms, wind, and hazards.
- Biome catalogs require biome identity, productivity, and carrying-capacity layers.
- Resource records require algorithm version and deposits.
- Resource catalogs preserve renewable yield; validators enforce geological
  compatibility.
- Region records require stable cells, center, area, boundaries, and adjacency.
  Validators enforce partition topology and symmetric references.
- Route records require endpoints, cells, distance, terrain cost, crossings,
  seasonal risks and capacity, kind, seasonal paths, traversable seasons,
  maintenance cost, and authoritative sources.
- Validators enforce route traversal against the physical world.
- Surface catalogs use separate domain-specific 256×256 binary chunks.
- Local 3D maps use sparse 32×32×16 chunks.
- Only outer boundaries may use partial chunk dimensions.
- Integer layers use schema-declared fixed widths and signedness, big-endian byte
  order, and row-major cells.
- ZIP compression is the only compression layer.

## Social and history domains

- Site records require stable identity, containing region, cell coordinates,
  suitability, water access, resource access, and score components.
- Site region and cell references must resolve against the physical world.
- Civilization records require stable identity, name, culture, government,
  language, capital, capabilities, needs, territory, population, economy, and
  present active state.
- Civilization site, territory, language, diplomacy, and ownership references
  must resolve against declared records.
- Every material history event requires identity, year, month, sequence, kind,
  causes, participants, locations, consequences, and deterministic summary.
- Every snapshot requires year, exact ledger position, state hash, and complete
  replay state.
- Snapshots exist at year 0, every ten years, and the final year.
- Causes refer only to earlier declared events.
- Replaying from a snapshot plus subsequent events must reproduce the corresponding
  recorded state hash.

## Narrative domains

- The Bible record contains the complete required narrative-domain collections
  and a nonempty authoritative-reference inventory.
- Bible major claims and local entity containers resolve to authoritative world
  records; enrichment never replaces those records.
- Reconciliation records nonempty input artifact-ID and file-hash maps, the
  mandatory ruleset version, issues, and an accepted result.
- Reconciliation input IDs and hashes exactly match the accepted world inputs.
- Story and graph records contain their frozen versions and required fields.
- Story and graph world/Bible IDs resolve to accepted package records.
- The graph record declares an entry, nodes, choices, flags, conditions, endings,
  and exact per-node media intent.
- Graph entry, targets, flags, conditions, endings, and media intent are mutually
  consistent and complete for every node.
- Each GM-index entry contains source IDs and `reveal_after_nodes`.
- The GM index covers complete world, history, and narrative knowledge and every
  source and reveal node resolves.

## Media

The fixed PNG profile requires a 4096×4096 world map, a 1024×1024 map for every
region, a 1024×1024 illustration and 256×256 thumbnail for every graph node, and
non-interlaced, non-animated, 8-bit RGBA sRGB encoding for every PNG.
Every node has one authoritative structured-score record. Its schema requires the
frozen version, node and source IDs, 960 PPQ, positive duration, nonempty
tempo/time/key maps and tracks, markers, producer fingerprint, and expected MIDI
SHA-256.
Score source and node IDs resolve to accepted narrative and world records.
Every node also has one derived Standard MIDI File. MIDI policy is SMF Type 1 at
960 PPQ with General MIDI 1-compatible programs and drums, separate role tracks,
explicit tempo/time/key events, standard `LOOP_START`, `LOOP_END`, `INTRO_END`,
and `OUTRO_START` markers, bounded declared pitch bend, and no proprietary SysEx.
Every rational score position is reduced and exactly representable at 960 PPQ;
rounding is forbidden. MIDI rendering uses the canonical event and track order in
`api.md`, so two conforming renderers produce identical bytes. The expected MIDI
SHA-256 is calculated from those bytes and inserted into the final score without
being an input to rendering.
Each manifest node-asset record contains exactly one image, thumbnail, score, and
MIDI relative path.
Manifest node assets form an exact bijection with graph nodes, and the world and
region map inventories cover the world and every declared region exactly once.
Acceptance fully decodes every PNG and verifies its profile and dimensions.
Acceptance validates every score, provenance and source reference; parses every
MIDI; and verifies Type 1, 960 PPQ, allowed events/programs, standard loop markers,
at least one sounding note, positive duration, and the score-derived hash.
Acceptance verifies every media member's hash, size, producer, and dependency IDs.
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
- `required_features` and `optional_features` are duplicate-free.
- `required_features` and `optional_features` are sorted.
- Unknown optional feature: safely ignore its optional behavior and preserve the
  immutable package content as the frozen schema permits.
- Feature flags cannot disable or weaken core v2 validation.
- Breaking representation change: requires a new package-version decision.

## Frozen parser and resource limits

- Maximum JSON nesting depth: 128
- Maximum archive entries: 100,000
- Maximum declared bytes per member: 4 GiB
- Maximum total declared bytes: 32 TiB
- Maximum compression amplification: 1,000:1
- Interoperable authoritative integer range: `[-(2^53-1), 2^53-1]`
- No arbitrary archive-file-size ceiling is imposed
- Extraction requires free space for all declared members plus atomic staging
