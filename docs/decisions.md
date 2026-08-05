# StoryTeller Accepted Decisions

## How to use this record

These decisions define the target unless superseded by an explicitly recorded
decision. Implementation status remains in the phase roadmaps. New decisions should
include context, choice, consequences, and date.

## D001: Procedural world is mandatory

**Decision:** Every run begins with StoryTeller-owned procedural generation.
There are no narrative-only, procedural-only, or hybrid product modes.

**Reason:** Early Bible tests lacked sufficient geography, climate, weather, and
historical grounding.

**Consequences:** World generation failure aborts resumably. All later artifacts
depend on world artifacts.

## D002: Procedural facts are immutable

**Decision:** Terrain, hydrology, climate, resources, major regions, routes,
civilizations, and simulated history cannot be edited by narrative stages.

**Consequences:** The Bible may add contained local entities. A reconciliation
gate retries the Bible, never the world, when contradictions occur.

## D003: Configurable world, one-continent default

**Decision:** World dimensions, physical scale, continent count, history years,
and civilization limits are configurable; the default is one continent.

## D004: Canonical coordinates are tiles plus scale

**Decision:** Integer world-cell coordinates are authoritative, with
integer `metres_per_world_cell` metadata. Rendered world/region maps are derived assets.

## D005: Retain full procedural output

**Decision:** `.story` stores all final procedural domains, the complete causal
event ledger, and the fixed snapshot series even if narrative content does not use them.

**Rejected alternative:** Store only prompt summaries or narrative-used facts.

## D006: v2 is the only product package

**Decision:** Target Forge emits/reads v2 only; target Players import v2 only.
There is no v1 conversion or package migration promise.

**Transition:** Keep v1 scaffolding until shared v2 acceptance fixtures pass in
rewrite Phase 6, then delete it. v1 rejection explains that regeneration is
required.

## D007: Freeze v2 in rewrite Phase 6

**Decision:** Derive the schema as close to final as possible beforehand, but
freeze only after physical, historical, reconciliation, narrative, index, and
mandatory-media domains stabilize.

## D008: Saves are external and local

**Decision:** No save data exists inside `.story`. Saves, bookmarks, and
persistent GM conversations live in app-private storage keyed by story ID and
content hash. There is no cloud save or synchronization.

## D009: Every node has complete media

**Decision:** Every graph node requires exactly one accepted full PNG, thumbnail,
and positive-duration MIDI. Forge publishes no partial-media package and imposes
no package-size ceiling.

## D010: Complete GM index with strict reveal isolation

**Decision:** GM index includes complete procedural/history/narrative knowledge.
Runtime filters entries using visited nodes before prompt construction.

**Rejected alternative:** Prompt-only “do not spoil” instructions.

## D011: GM output is chunk streamed and persistent

**Decision:** Native GM responses stream in bounded text chunks. Completed
conversations persist locally. Unmarked partial assistant messages do not persist
after cancellation.

## D012: Mobile parity without platform authority

**Decision:** Android and iOS are developed in parallel against shared scenarios.
Neither implementation defines the contract for the other.

## D013: Model download after first launch

**Decision:** Player downloads its local GM model after explicit consent. The
download is resumable, checksum verified, atomically installed, and removable.
Models are not bundled in store binaries.

## D014: Offline and private after downloads

**Decision:** No StoryTeller server, accounts, telemetry, analytics, advertising,
cloud inference, cloud saves, or remote content service exists. After explicit
model downloads, all functionality works with networking blocked.

## D015: Free mature-dark-fantasy product

**Decision:** Both store apps are free and target mature dark fantasy. Store
rating, AI disclosure, local content controls, privacy, licenses, and reporting
requirements remain release gates.

## D016: Thin desktop GUI

**Decision:** The future GUI only configures, launches, observes, cancels,
resumes, and reveals Forge results. It communicates through argv and versioned
JSONL, contains no generation logic, and must run under Wine. Toolkit selection
remains open until the Phase 8 spike.

## D017: StoryTeller owns its generator

**Decision:** Extend existing `src/worldgen/` into a StoryTeller-owned generator.
Do not embed or invoke another procedural-world project as the product engine.

## D018: SHA-256 integrity, no package signing requirement

**Decision:** v2 uses complete inventory/provenance and SHA-256 integrity. A
publisher-authenticity signing system is not a target requirement.

## D019: Determinism scope

**Decision:** Pure procedural domains are cross-platform deterministic. Model
outputs target same-machine/reproducibility-profile identity. Fake-backed
packages and deterministic packaging are byte-identical across directories and
worker counts.

## Open decisions

- Phase 8: desktop GUI toolkit, constrained to a thin process wrapper that works
  natively and under Wine
- Phase 8: exact semantic GM chunk-size, queue, and backpressure defaults
- Phase 9: final supported OS/device matrix and measured performance profiles

## D020: Complete duplicated visual maps

**Decision:** v2 stores canonical geometry plus a 4096×4096 world PNG and a
1024×1024 PNG for every region. Duplication is intentional.

## D021: Local maps for every site

**Decision:** Every registered site has a retained local 3D map, including sites
unused by the narrative. Surface chunks are 256×256; sparse local chunks are
32×32×16; binary chunks use ZIP compression only.

## D022: Fixed media profile

**Decision:** World PNG is 4096×4096; region and node PNGs are 1024×1024;
thumbnails are 256×256. PNG is non-interlaced 8-bit RGBA sRGB and non-animated.

## D023: Structured score plus MIDI

**Decision:** Every node has an authoritative structured score and a derived SMF
Type 1 MIDI at 960 PPQ. The MIDI uses a General MIDI 1-compatible subset, explicit
tempo/time/key metadata, role tracks and standard loop markers. No MIDI 2.0,
MusicXML, rendered audio, package SoundFont, or proprietary SysEx is required.

## D024: History snapshots

**Decision:** Store snapshots at year 0, every ten years, and the final year.
Historical events retain both structured changes and immutable English summaries.

## D025: Embedded schemas are non-authoritative

**Decision:** v2 embeds its complete frozen schema bundle for inspection and hash
verification. Players validate with bundled trusted schemas; embedded schemas can
never redefine acceptance.

## D026: Schema dialect and canonical JSON

**Decision:** All v2 schemas use JSON Schema Draft 2020-12. Canonical JSON uses
RFC 8785 JCS; authoritative simulation quantities that require exact arithmetic
remain integers or explicitly structured rational values.

## D027: Stable identifier grammar

**Decision:** Entity and artifact IDs are a lowercase ASCII type prefix, `_`, and
a deterministic 128-bit value encoded as exactly 32 lowercase hexadecimal
characters, matching `^[a-z][a-z0-9]*_[0-9a-f]{32}$`. Integrity and content hashes
always retain the complete 64-character lowercase SHA-256 value. Display names
never participate as the sole ID input.

## D028: Feature negotiation

**Decision:** The manifest contains sorted, duplicate-free `required_features`
and `optional_features` arrays. A Player rejects an unknown required feature and
may safely ignore an unknown optional feature while preserving accepted immutable
content. The initial required registry is `all_site_local_maps`,
`complete_history`, `complete_world`, `embedded_schemas`, `fixed_media_profile`,
and `structured_score_midi`; the initial optional registry is empty. Feature flags
cannot weaken core v2 validation.

## D029: Size and extraction safety

**Decision:** v2 has no product-level maximum package or world size. Import still
enforces declared sizes, sufficient free storage before extraction, safe paths,
compression-ratio and structural-amplification checks, bounded JSON nesting, and
resource budgets for individual parsers. The interoperable numeric security
limits are frozen in `package-v2.md` and enforced by the reference validator.
