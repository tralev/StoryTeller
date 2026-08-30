# Implementation Audit — 2026-08-30

## Scope and method

This audit traced the repository from the product contract and roadmap through
the procedural world, history/local simulation, narrative projection, v2
packaging, native readers, launchers, and release gates. Evidence included code
inspection, generated-contract checks, strict typing, focused producer/consumer
tests, native fixture parity, and the broad non-integration suite. A checked
roadmap item was treated as implemented only where its code and retained tests
matched the written exit criteria.

The broad default gate completed with 1,582 passes and one workspace-hygiene
failure. Relocating `droid/.gradle` and `ios/.build` under `tmp/` closed that
failure; the hygiene test and script then passed. The final package-focused gate
passed 54 tests, and strict mypy passed all 364 checked source files.

## State by delivery layer

- The deterministic physical world, ecology, regions/routes, causal history,
  genealogy, megabeasts/artifacts, and every-site local 3D maps are substantial
  implementations rather than scaffolds. P8.C05A–H remain credibly closed.
- P8.C1 has deep, closed v2 schemas, generated negative fixtures, and explicit
  prose-to-schema rules. P8.C2 has Python/Kotlin/Swift fixture parity, but this
  audit found that synthetic package fixtures had hidden incompatibilities with
  the real producer.
- Narrative, graph, complete media, GM indexing, and content-addressed packaging
  are wired end to end. Native Player validation is meaningful, but physical
  device, lifecycle, and release evidence correctly remain open in Phase 9.
- The Forge launcher and desktop adapters exist, while signed builds, Wine
  evidence, real-model runs, and clean-install coverage remain future work.

## Findings and repairs

The highest-severity defect was producer/validator disagreement. A package made
from the real Phase 4/5 fixtures was rejected by the newly hardened Python
validator. Repairs made during this audit:

1. Corrected region completeness to partition land, not ocean.
2. Resolved route, graph, score, and GM references across package, retained
   source-artifact, and world-entity identity namespaces.
3. Replayed real history envelopes from the genesis snapshot instead of treating
   event-scoped hashes as one global hash chain.
4. Reconciled Bible authority with retained source inputs (and the compact
   cross-platform fixture profile), including ruleset versions newer than 1.
5. Preserved story authority as a subset when graph nodes legitimately add
   travel references or relocate a reused scene.
6. Updated the frozen schema-bundle hash and repaired strict typing in package
   validation.
7. Corrected package-identity tests so canonical ZIP metadata/order remains an
   acceptance requirement while identity is still derived only from members.

## Critique and recommendations

The architecture is ambitious and generally disciplined: canonical identities,
immutable artifacts, replayable history, typed readers, and fail-closed package
acceptance are strong foundations. Its main weakness is integration density.
`src/storage/package_v2.py` combines ZIP security, schemas, world semantics,
history replay, narrative authority, media, and provenance in one large module;
that made locally plausible validators drift from producer semantics. Split it
into ordered domain validators sharing one typed identity index.

The worktree is also too large for a trustworthy milestone: generated fixtures
and native parity changes are mixed with core code. Land coherent P8.C1/C2 work
before new features. Ruff currently reports 1,058 violations (526 line-length,
125 import-order, 99 semicolon statement issues, 92 unused imports). Treat this
as a measured cleanup program by module; do not apply a repository-wide autofix
inside the current functional rewrite.

The permanent real-producer package acceptance test is now green in the default
test tree. Next, extract package validators by domain. After that, continue
P8.WG1/P8.WG3 and the native/release evidence already listed in the roadmap.

### Follow-up implemented

The first decomposition slice now provides a typed `PackageIdentityIndex`, built
once per accepted archive and shared by graph, structured-score, and GM
validators. This replaces three independent recursive identity collectors. The
index, stable package error, and those validators now live under
`src/storage/validation/`; `package_v2.py` remains the ordered orchestrator and
injects its strict duplicate-safe JSON loader. Acceptance order and issue codes
are unchanged. The next decomposition slice should extract the physical-world
validators by domain. Grid index/chunk integrity, physical layer inventories,
climate-season layer checks, and typed grid reconstruction are now isolated in
`src/storage/validation/grids.py`. The next slice should extract region, site,
and route topology while reusing that module's grid reader. That slice is now
implemented in `src/storage/validation/topology.py`, covering land partition,
symmetric adjacency, site ownership, and canonical/seasonal route continuity.
The next physical slice should extract hydrology and resource/geology catalog
semantics. Those checks now live in `src/storage/validation/hydrology.py` and
`src/storage/validation/resources.py`, including topology, seasonal discharge,
drainage terminals, renewable yields, deposit geometry, and geological
provenance. The next extraction should isolate history inventory, ordering, and
replay validation as one causality-focused module. That work now lives in
`src/storage/validation/history.py`; separate ordered entry points preserve the
existing error precedence for inventory/cadence, causal ordering, and replay.
All-site local-map index and chunk validation now lives in
`src/storage/validation/local_maps.py`, including exact site coverage, map
identity, boundary/summary linkage, all three chunk families, and typed chunk
decoding. The next extraction should isolate civilization references and retained
world/narrative authority validation. These checks now live in
`src/storage/validation/authority.py`, covering civilization ownership, flat
source projections, retained-source coverage, reconciliation inputs, Bible
authority, and cross-reference resolution. Remaining validator extractions are:
archive/JSON security, manifest/provenance/layout, and binary media; the ordered
world-contract coordinator should remain thin orchestration.
