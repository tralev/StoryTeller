# Missing World Generation Features

> **Archived 2026-08-12.** This pre-deletion audit is retained as evidence and
> is intentionally stale. Use `missing_wg_features.md` and
> `worldgen-coverage.generated.md` for current status.

> Audit comparing `docs/generation.md`, `docs/worldgen-rewrite.md`,
> `docs/worldgen-legacy.generated.md`, and `docs/worldgen-coverage.generated.md`
> against the current codebase at `src/worldgen/`.
>
> Generated: 2026-08-05

## Executive Summary

| Metric | Count |
|--------|-------|
| Coverage ledger requirements | 89 (83 partial, 0 complete, 6 obsolete) |
| Source files in `src/worldgen/` | 47 Python modules |
| Legacy modules still present | 4 (`adapter.py`, `step.py`, `generator.py`, `models.py`) |
| Missing feature categories | 8 |

All 83 non-obsolete requirements are tagged **partial** — the modules exist and
produce output, but none have full golden-vector validation, cross-domain
invariant proofs, or complete coverage against the normative `generation.md`
acceptance table.

---

## 1. Legacy Modules Not Yet Removed

Per `worldgen-rewrite.md` WP9 and `worldgen-legacy.generated.md`, the following
modules must be deleted after all consumers migrate:

| Module | Lines | Status | Blockers |
|--------|-------|--------|----------|
| `src/worldgen/models.py` | 293 | Still imported by `generator.py`, `adapter.py`, `step.py`, tests | `WorldSnapshot`, `GridCell`, legacy enums still referenced |
| `src/worldgen/adapter.py` | 233 | Deprecation warnings added (P8.C05H); `snapshot_to_bible_context` and `snapshot_dict_to_bible_context` still importable | `WorldBuilder` compatibility path in `src/models/world_builder.py:88-89` |
| `src/worldgen/generator.py` | 76 | Compatibility facade for `generate_world` | `ProceduralWorldStep` in `src/worldgen/step.py` |
| `src/worldgen/step.py` | 66 | `ProceduralWorldStep` bridge | Remaining callers in pipeline compatibility tests |

**`generation.md` requirement**: Remove legacy `GridCell`, `WorldSnapshot`, LCG/compact generators, narrative/procedural/hybrid modes, and `world_snapshot.schema.json`. **Status**: NOT DONE.

---

## 2. Cosmology, Magic Laws, and Belief Systems

`generation.md` defines a complete supernatural rules system that the codebase
partially implements:

### Implemented
- `src/worldgen/simulation/magic.py` — basic magic law structures exist

### Missing
| Feature | Source Doc Ref | Details |
|---------|---------------|---------|
| Cosmological layers, afterlife claims, celestial cycles | `generation.md` §Cosmology | No `src/worldgen/cosmology.py` module |
| Gods, saints, spirits, demons, false entities | `generation.md` §Cosmology | Not represented as typed entities |
| Magic transformation must go through explicit events paying costs | `generation.md` MagicLaw | Validator not enforcing this cross-domain |
| Every belief has `epistemic_status` (true/false/uncertain/metaphorical) | `generation.md` BeliefClaim | Not fully propagated to Bible/narrative |
| Holy sites, relics, taboos, cults, rites, schisms, institutions | `generation.md` §Cosmology | Not generated |
| Supernatural hazards/resources linked to exact places | `generation.md` §Cosmology | Not plumbed into resource/hazard systems |

---

## 3. Language Generation and Naming System

`generation.md` specifies a language/naming subsystem with phoneme inventories,
syllable grammars, morphology, writing systems, and sound-shift rules.

### Implemented
- `src/worldgen/simulation/names.py` — basic name generation
- `generate_name()` function described in `generation.md`

### Missing
| Feature | Source Doc Ref | Details |
|---------|---------------|---------|
| `Language` dataclass with phoneme inventory, syllable patterns, morphemes | `generation.md` §Languages | No `src/worldgen/languages.py` module |
| Writing system generation | `generation.md` | No script/orthography data |
| Sound shifts, language evolution over history | `generation.md` | Not simulated |
| Profanity, duplicate, confusable, reserved-name filters | `generation.md` `generate_name` | Not visible in names.py |
| `realize_syllable` with C/V token replacement | `generation.md` code block | May be in names.py but not verified |

---

## 4. Flags, Heraldry, and Visual Identity

`generation.md` §Stage 6 specifies flag/heraldry generation from grammars.

### Missing
| Feature | Source Doc Ref | Details |
|---------|---------------|---------|
| Deterministic palette with contrast constraints | `generation.md` | No `src/worldgen/heraldry.py` or equivalent |
| Background division and overlay motif | `generation.md` | Not implemented |
| Motif meanings linked to cultural beliefs/history | `generation.md` | Not implemented |
| Vector-like pattern parameters (not only raster) | `generation.md` | Not implemented |

---

## 5. Detailed Deposit and Resource Models

`generation.md` §Stage 4 defines deposit shapes, grade, quantity, depth, access
cost, and discovery mechanics.

### Implemented
- `src/worldgen/resources.py` — basic resource generation

### Missing
| Feature | Source Doc Ref | Details |
|---------|---------------|---------|
| `Deposit` with geometry (shape, cells, depth range, grade, quantity) | `generation.md` dataclass | Current implementation may not match full schema |
| `discovered_year` tracking per deposit | `generation.md` Deposit field | Not verified |
| `GeologyFactors` and `ClimateFactors` type-driven resource suitability | `generation.md` `resource_suitability()` | Not verified in resources.py |
| Rare fantasy materials tied to geological or magical anomalies | `generation.md` | Not visible |

---

## 6. Complete Species and Ecology Model

`generation.md` §Stage 4 requires habitats, species archetypes, food webs,
migration corridors, domestication, extinction, and carrying capacity.

### Implemented
- `src/worldgen/ecology.py` — basic ecology

### Missing
| Feature | Source Doc Ref | Details |
|---------|---------------|---------|
| `Species` dataclass with trophic level, habitat biomes, temperature range, food species | `generation.md` dataclass | Not verified in ecology.py |
| Domestication candidates | `generation.md` | Not verified |
| Migration corridors as spatial artifacts | `generation.md` | Not verified |
| Extinction tracking over history | `generation.md` | Not verified |

---

## 7. Map Rendering and Map Layers

`generation.md` and `worldgen-rewrite.md` WP4 require canonical scalar/vector
layers, deterministic raster maps, label placement, and color tables.

### Implemented
- `src/worldgen/maps.py` — basic map generation

### Missing
| Feature | Source Doc Ref | Details |
|---------|---------------|---------|
| One region map per region | `generation.md` WP4 | `maps.py` may not generate per-region maps |
| Frozen colour tables for all layer types | `generation.md` | Not verified as frozen/versioned |
| Label placement algorithm | `generation.md` | Not verified |
| Political, travel, hazard maps | `generation.md` | May be incomplete |
| Derived presentation maps never replace authoritative facts | `generation.md` | Architecture enforcement not visible |

---

## 8. Story Opportunity Extraction

`worldgen-rewrite.md` WP8 requires deterministic opportunity extraction from
authoritative pressures, routes, people, events, beliefs, sites, and local
containment.

### Implemented
- `src/worldgen/simulation/projections.py` — basic projection/opportunity extraction
- `src/narrative/opportunities.py` — story opportunity generation

### Missing
| Feature | Source Doc Ref | Details |
|---------|---------------|---------|
| Targeted `src/worldgen/simulation/projections.py` module covering all opportunity types | `generation.md` §Story-facing derivations | Module exists but coverage unclear |
| Interesting frontiers, chokepoints, contested resources as opportunity sources | `generation.md` | Not verified |
| Mysteries with factual answers in history/geology | `generation.md` | Not verified |
| Factions with goals, capacity, relationships, credible constraints | `generation.md` | May be in civilization state, not opportunity output |
| Candidate protagonists, antagonists, patrons, witnesses | `generation.md` | Not verified |
| Revealable facts indexed by story nodes | `generation.md` | Partially done via knowledge.py reveal_after_nodes |

---

## 9. Building, Workshop, and Interior Generation

`worldgen-rewrite.md` WP7 requires culturally coherent buildings, workshops,
ruins, interiors, items, and persistent smaller local entities.

### Missing
| Feature | Source Doc Ref | Details |
|---------|---------------|---------|
| Building interiors as separate local-map features | `worldgen-rewrite.md` WP7 | `local_maps.py` has features but interior generation unclear |
| Items as local entities with ownership/stats | `generation.md` | Not visible as typed entity |
| Event scars as spatial features (ruins, abandoned roads, etc.) | `generation.md` §Historical world | `local_maps.py` mentions event scars but coverage unknown |

---

## 10. Resource Preflight and Budget Estimation

`generation.md` requires a preflight estimate for memory, working disk, and output
disk with a resource diagnostic if the world cannot be generated safely.
`worldgen-rewrite.md` WP1 requires resource preflight in `WorldSpec`.

### Missing
| Feature | Source Doc Ref | Details |
|---------|---------------|---------|
| Explicit site-count budget and preflight formula | `generation.md` §Scale model, `worldgen-rewrite.md` WP5 | Not visible as a standalone preflight module |
| Memory, disk, time estimates for requested world size | `generation.md` §Required vs optional domains | Not verified |
| Abort-with-diagnostic on resource overrun | `generation.md` | May not be implemented |

---

## Actionable Priority Order

Based on `roadmap.md` dependency order and the P8.WG1–WG3 work just completed:

1. **P8.C05H step 7–8** (highest priority): Promote all 83 partial requirements
to complete by adding golden vectors, cross-domain invariants, and coverage
evidence. This enables deletion of the three absorbed docs.

2. **Legacy module removal** (P9.WG1): Delete `models.py`, `adapter.py`,
`generator.py`, `step.py` only after P9.WG0 proves no requirements are lost.

3. **Complete local 3D worlds** (P8.C05G hardening): Building interiors, items,
event scars as spatial features.

4. **Cosmology/magic completion** (P8.C05E hardening): Separate magic laws from
beliefs, generate holy sites, relics, taboos.

5. **Language/heraldry subsystems** (P8.C05E hardening): Full `Language` model,
flags, writing systems.

6. **Map rendering completion** (P8.C05D hardening): Per-region maps, frozen
color tables, label placement.

7. **Preflight/budget system** (P8.C05B hardening): Resource estimation before
generation begins.

8. **Story opportunity extraction** (P8.C05H hardening): Typed opportunity module.
