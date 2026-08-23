# World-generation references

This document is the durable reference list for StoryTeller's procedural-world
work. It is comparative research, not a second specification: the absorbed
requirements preserved in `worldgen-coverage.generated.md`,
the frozen contracts, and `roadmap.md` remain authoritative.

## Design reference: Dwarf Fortress

Dwarf Fortress is the quality bar for a world whose geography, geology,
climate, hydrology, ecology, settlements, artifacts, and history explain one
another. StoryTeller must pursue the same *causal depth*, without claiming to
reproduce proprietary algorithms or data.

The useful model is a pipeline of retained, inspectable fields and simulations:

1. Generate elevation and geological structure.
2. Derive independent climate and terrain fields such as temperature, rainfall,
   drainage, and volcanism.
3. Classify biomes from intersections of those fields. The supplied rainfall ×
   drainage chart is a useful test-design example: changing one axis must create
   predictable boundaries between desert, grassland, marsh/swamp, shrubland,
   forest, wasteland, and badlands classes.
4. Route water downhill, resolve basins, and apply erosion before ecology and
   settlement suitability consume the terrain.
5. Place flora, fauna, resources, peoples, and settlements only where their
   environmental requirements hold.
6. Simulate history as state transitions with durable causes and effects so a
   ruin, road, border, lineage, conflict, religion, or artifact has traceable
   provenance in the finished world.

These are acceptance heuristics, not permission to invent unverified details
about Dwarf Fortress internals. Prefer public talks, documentation, and
observable behavior when refining this comparison.

## Open-source implementation references

### Dozed12/df-style-worldgen

- Repository: <https://github.com/Dozed12/df-style-worldgen>
- Reviewed commit: `937455d54f4b02df9c4b10ae6418f4c932fd97bf`.
- Status/license: archived read-only prototype; MIT.
- Useful for: separate altitude, precipitation, drainage, temperature, biome,
  and prosperity views; data-driven biome/race/government tables; simple monthly
  civilization expansion and population display.
- Caution: its author explicitly describes the implementation as a learning
  prototype with poor organization. Use it to identify behavior and fixtures,
  not as StoryTeller's architecture.

### kevshakes/dwarf-fortress-simulation

- Repository: <https://github.com/kevshakes/dwarf-fortress-simulation>
- Reviewed commit: `d1c3c40c13e258d1539ef5d5bdb56cfc093ddec2`.
- Status/license: public project; MIT as declared by its repository.
- Useful for: 3D layered terrain, mineral veins, water features, depth-based
  temperature, A* navigation across z-levels, spatial partitioning, path caches,
  agent needs/relationships, production chains, resource flow, fluids, heat, and
  structural-collapse concepts.
- Caution: benchmark its claims and inspect tests before treating any subsystem
  as correct. StoryTeller's deterministic artifact and fixed-point contracts take
  precedence over this project's runtime-oriented design. The 2026-08-12 source
  review found literal `pass` stubs in fluid, heat, structural-integrity, and
  production-manager updates despite README completeness claims; its history
  generator chooses random event labels rather than replaying causal deltas.

### Moneyl/World-Generator

- Repository: <https://github.com/Moneyl/World-Generator>
- Reviewed commit: `3f619aa0f0351044e1d2911af1f3a4f301ded35a`.
- Status/license: archived read-only prototype; BSD-3-Clause.
- Useful for: a staged simplex-heightmap → temperature → rainfall → river
  simulation, multiple diagnostic map views, and visual comparison fixtures.
- Caution: its author recommends a clean redesign rather than reuse because of
  large, poorly documented source files. Treat it as algorithm-discovery and
  visualization material only.

## Rules for using references

1. Record the repository URL, exact commit, files consulted, license, and the
   StoryTeller requirement/test influenced by the research.
2. Prefer independent implementation from documented concepts. Copy or adapt
   source only after compatibility review, preserving every required notice and
   attribution.
3. Never import a reference repository as a production dependency or vendor it
   merely to accelerate a roadmap item.
4. Translate useful behavior into deterministic conformance fixtures: field
   boundary tables, hydrology invariants, geological/resource constraints,
   replayable history, route connectivity, and macro/local reconciliation.
5. Reference output is neither a golden oracle nor proof of correctness. Validate
   against StoryTeller's contracts, physical invariants, cross-platform replay,
   memory limits, and provenance requirements.

## StoryTeller comparison (reviewed 2026-08-13; closure audit refreshed 2026-08-22)

### Already implemented

- Versioned deterministic seeds, SplitMix64, fixed-point fields, canonical
  artifacts, dependency identities, and reproducible golden vectors.
- Plates/continents, terrain, synchronous mass-conserving erosion, deterministic
  D8 priority-flood hydrology, connected lakes/spillways, typed ocean/closed-
  basin terminals, rivers/watersheds/coasts/aquifers/deltas, fixed-point
  latitude/elevation/axial-tilt seasonal temperature, moisture relaxation,
  soils/biomes, geology/resource deposits, species/food webs, regions, routes,
  maps, spatial/reference indexes, civilization sites, monthly demographics and
  economy, causal events, snapshots/replay, and every-site local-map artifacts.
- Directional seasonal winds, orographic lift/rain shadow, evaporation, storms,
  typed soils, resource depletion/recovery, habitat migration/extinction,
  persistent megabeasts, seasonal routing, diagnostic maps, and rebuildable
  spatial/reference indexes.
- Registry-driven languages and historical sound shifts, safe naming, vector
  heraldry, objective magic versus attributed cosmology, religions/cults/relics,
  settlements, trade, households and bounded social/lineage anchors, and rare
  event-created legendary artifacts with immutable provenance.
- Guarantees absent or only sketched in the references: immutable domain
  artifacts, corruption detection, replay validation, canonical hashes,
  macro-to-story reconciliation, and complete package retention.
- Immutable proposal collection and deterministic conflict resolution, sealed
  causal event envelopes, atomic history batches, snapshot-to-final replay,
  restart-safe retention, and selective event-sourced genealogy.
- Complete every-site 3D local maps with typed strata, caves, aquifers,
  construction and occupancy layers, legal hierarchical movement, fluids, heat,
  structural support, macro/micro accounting, content-addressed chunks, and a
  bounded verified reader.

### Explicitly planned but incomplete

- P8.C05H: story opportunities, strict reconciliation, production integration,
  determinism diagnostics, legacy deletion, and zero-gap evidence.

### Not currently promised by the roadmap

- Real-time playable colony management with autonomous on-screen workers, job
  assignment, needs/moods, tactical combat, and a continuous 60 FPS loop.
- Exhaustive individual simulation and complete genealogies for every aggregate
  citizen. P8.C05E retains bounded social anchors and typed relationships;
  P8.C05F now plans selective event-sourced genealogy for consequential people,
  houses, claims, succession, and inheritance.
- A distinct Dwarf-Fortress-style savagery/wildness scalar field; current hazards
  and ecology pressure are not that named independent field.
- Gods as independently acting historical agents; StoryTeller instead plans
  religions, attributed beliefs, and objective magic laws.

Megabeasts and legendary artifact creation are implemented in P8.C05C/E, and
their causal histories plus selective genealogy are complete in P8.C05F.
P8.C05H still owns selective source-backed Bible/story projection. Selective
genealogy is retained, while exhaustive per-citizen family trees are not. A
distinct savagery/wildness scalar remains outside the current requirements unless
accepted by a future product decision. Real-time colony simulation requires a
separate product decision because it changes runtime, UI, save, performance, and
acceptance scope.
