# StoryTeller Remaining Roadmap

## Status and authority

This is the sole implementation roadmap. It records only work that remains after
the completed contract, world generation, simulation, Bible, narrative/media,
`.story` v2, native Player, model-registry, model-download, and native model
lifecycle rewrites. Completed work is specified by the other target documents
and verified by source/tests; it is intentionally not repeated here.

The active implementation item is **P8.C05F**, followed by **P8.C05G–P8.C05H**,
**P8.C1**, and **P8.C2**. P8.C1 cannot close while the executable schema-depth
gate reports shallow domain schemas; P8.C2 cannot close before P8.C1. Several
later Phase 8 modules and focused tests already exist, but their checkboxes stay
open until every listed native, packaged, Wine, device, or shared-parity exit
criterion has named evidence. Work should follow dependency order. A
checkbox may be marked complete only when its implementation, automated tests,
and named evidence all exist. Source scaffolding or mock-only success is not
completion where an item explicitly requires native, packaged, real-model, Wine,
physical-device, store, or human evidence.

## Delivery sequence

```text
P8.C0 production wiring -> P8.C05A-H worldgen closure
  -> P8.C1 schemas -> P8.C2 validator parity

P8.6 chunks -> P8.7 history -> P8.8 UI -> P8.9 security

P8.10 launcher contract -> P8.11 launcher core -> P8.12 GUI -> P8.13 packaging

P8.WG1 -> P8.WG2 -> P8.WG3
P8.WG4 depends on the launcher core/GUI

Phase 8 complete -> Phase 9 gates/evidence -> release decision
```

Independent branches may be developed in parallel, but heavyweight verification
must run sequentially under `scripts/run_with_memory_cap.py`: soft stop at 9 GB,
hard ceiling 10 GB across the complete process tree. There is one global
heavyweight-test slot for the entire workspace: before starting a run, verify no
other `pytest`, Gradle, Xcode, Docker-build, model, or capped test process for this
project is active. Never launch several wrappers whose individual 10 GB limits
could add together beyond the machine budget.

## Implemented baseline and evidence boundary

The source contains substantial Phase 1–7 rewrite foundations: typed run/world contracts,
fixed-point procedural artifacts and simulation, Bible reconciliation,
narrative/media/GM-index generation, frozen v2 packaging and acceptance, shared
Python/Android/iOS fixtures, native package/save/model-download/model-lifecycle
implementations, deterministic retrieval, and the pre-prompt reveal gate.

The canonical `forge generate` path now uses the procedural-first 16-stage v2
plan, but that implementation baseline is not a release claim. Several v2 domain schemas currently assert
only a top-level object, and manifest nested structures are shallow; the frozen
prose contract therefore still has the executable-conformance debt P8.C1–P8.C2.
In addition, the baseline does not yet prove a
complete real-model v2 run, physical-device behavior, full simulator reliability
under the 10 GiB host ceiling, default 500-year resource behavior, hostile-corpus
breadth, store compliance, accessibility, Wine/native launcher packaging, or
absence of every legacy worldgen path. The current default Python collection also
discovers provisioned real-model smoke tests; P9.1–P9.2 must isolate that gate.

## Phase 8 prerequisite — Close executable v2 contract debt

- [x] **P8.C0 — Make the production service procedural-first (XL):** Make
  `GenerateStory`/`forge generate` execute one validated plan beginning with the
  authoritative procedural world, followed by Bible projection, reconciliation,
  v2 narrative/media/GM index, v2 packaging, acceptance, and atomic publication.
  Remove the split where `generate-world`, `generate-bible`, and
  `generate-narrative` are the only path through the new subsystems. Make
  `GenerationRequest.to_run_spec()` the single configuration conversion, expose
  or explicitly lock every `WorldSpec` field, use the canonical
  `mature_dark_fantasy` content profile everywhere, and require a typed `RunSpec`
  in pipeline context. Checkpoint/resume/events must include the world and
  reconciliation stages. **Depends on:** existing Phase 1–7 foundations.
- [x] **P8.C05A — Freeze the worldgen contract and coverage ledger (L).**
- [x] **P8.C05B — Finish the deterministic kernel and artifact runtime (XL).**
- [x] **P8.C05C — Finish physical, ecological, and resource generation (XL).**
- [x] **P8.C05D — Finish regions, routes, maps, and rebuildable indexes (XL).**
- [x] **P8.C05E — Finish peoples, cultures, magic, settlements, and economy (XL).**
- [ ] **P8.C05F — Finish causal history, snapshots, and replay (XL).**
- [ ] **P8.C05G — Finish every-site local 3D generation and reconciliation (XL).**
- [ ] **P8.C05H — Integrate, harden, prove coverage, and remove legacy worldgen (XL).**
  P8.C05A–H absorb every retained requirement from `generation.md`,
  `worldgen-rewrite.md`, and `worldgen-legacy.generated.md`. Their detailed
  implementation cards below are normative. The three absorbed documents may
  be deleted only when P8.C05H's generated zero-gap report passes.
- [ ] **P8.C1 — Complete every frozen v2 schema (XL):** Express every required
  field, type, enum, unit/range, ID/hash grammar, ordering/uniqueness constraint,
  nested producer/provenance record, world domain, local map, history change,
  narrative record, media record, and cross-file reference shape from
  `package-v2.md`, `generation.md`, and `api.md`. Use `additionalProperties:
  false` at closed records and reusable `$defs`; a schema that merely accepts an
  arbitrary object is forbidden. Generate one valid and targeted invalid fixture
  per rule and add a prose-to-schema trace matrix. **Closure blocker:**
  `scripts/audit_v2_schema_depth.py` currently reports shallow domain schemas;
  generated fixtures derived from those schemas are not closure evidence.
- [ ] **P8.C2 — Full three-validator parity (XL):** Make Python, Android, and iOS
  enforce the complete frozen schema and acceptance order, including embedded
  trusted-schema identity, internal member hashes (never ZIP bytes), provenance
  DAG, complete domains/history/local maps/media, reference rebuilding, limits,
  unknown features, and stable diagnostic codes. Run the same hostile/valid
  catalog and require exact outcomes. The existing four coarse native archive
  stages are an implementation foundation, not field-level parity.
  **Depends on:** P8.C0, P8.C1.

Acceptance evidence:

- `forge generate` cannot reach Bible generation without an accepted procedural
  world and cannot publish anything except an accepted v2 package.
- CLI, resume, tests, and the future launcher traverse the same application plan.
- No v2 schema consists only of a top-level type assertion.
- A generated matrix maps every normative package rule to schema/validator/tests.
- Python, Kotlin, and Swift produce identical results for every shared scenario.

## Phase 8A — Reveal-safe local Game Master

### Retrieval contract

- [ ] **P8.WG1 — Lazy complete-world lookup (M):** Query world, history, and
  local-map indexes lazily through stable fact/source IDs and bounded excerpts;
  do not deserialize the complete retained world for each question.
- [ ] **P8.WG2 — Procedural-aware scoring (M):** Rank current node, visited
  routes/sites, people, events, beliefs, opportunities, and local containment
  consistently across Python, Android, and iOS. **Depends on:** the completed
  retrieval contract, P8.WG1.
- [ ] **P8.WG3 — Procedural spoiler proof (L):** Use unique sentinels to prove
  unrevealed global and local facts never enter candidates, prompts, native
  chunks, errors, logs, or saved history. **Depends on:** the completed reveal
  gate, P8.WG2.

**Implementation status:** Python lazy lookup, scoring, spoiler filtering, and
focused contract tests exist. These items remain open for the shared
Python/Android/iOS fixture outcomes and complete adversarial/native evidence
required below.

Acceptance evidence:

- `tests/contracts/test_gm_retrieval_reference.py` covers normalization,
  scoring, budgets, ties, source IDs, and reveal filtering.
- Android and iOS consume the same fixture catalog and emit matching result JSON.
- Empty, Unicode, oversized, adversarial, and no-result queries have stable
  outcomes and never bypass reveal filtering.

### Generation stream and history

- [ ] **P8.6 — Native chunk stream (XL):** Replace whole-response GM generation
  with ordered `started`, non-empty `text`, `completed`, and stable `failed`
  events. Bound buffering/backpressure, support cancellation during prompt decode
  and token generation, and emit exactly one terminal event. **Depends on:**
  the completed native model lifecycle and reveal gate.
- [ ] **P8.7 — Transactional local conversation history (M):** Persist only a
  completed user/assistant exchange. On cancellation or failure, remove the
  provisional user turn or retain an explicitly typed incomplete record—choose
  one policy in the save schema and enforce it identically. Keep history local
  and bound it by configurable context-selection policy, not destructive loss.
  **Depends on:** P8.6.
- [ ] **P8.8 — Responsive GM experience (M):** Render chunks without blocking
  navigation; add cancel, retry, clear-history confirmation, model-management,
  and local flag/export controls. Never upload prompts, responses, flags, or
  diagnostics automatically. **Depends on:** P8.6, P8.7.
- [ ] **P8.9 — End-to-end spoiler sentinels (L):** Test candidate, prompt,
  native-output-double, UI, error, log, and persisted-history boundaries on both
  platforms. Include cancellation and retry paths. **Depends on:** P8.6–P8.8,
  P8.WG3.

**Implementation status:** chunk-stream, local-history, native-screen, and
sentinel modules/tests exist. Closure still requires both-platform cancellation,
retry, persistence, resource-release, and offline physical-device evidence.

Acceptance evidence:

- Native tests prove ordered chunks, one terminal event, bounded buffering,
  cancellation latency, and deterministic resource release.
- Restart tests prove completed exchanges survive and partial exchanges follow
  the frozen policy.
- Network-blocked tests prove reading, saves, history, and GM work after the
  model has been installed.

## Phase 8B — Thin desktop launcher

- [ ] **P8.10 — Freeze launcher process contract (M):** Version JSONL progress,
  cancellation, resumability, diagnostics, stable errors, and final JSON result.
  Define forward-compatible unknown-event handling and exact exit-code mapping.
- [ ] **P8.11 — Toolkit-independent launcher core (XL):** Implement validated
  configuration state, complete `WorldSpec`, argv-list construction without a
  shell, Forge subprocess ownership, JSONL parsing, cancel/resume, and final
  package reveal. The launcher must contain no generation logic and must never
  scrape human logs. **Depends on:** P8.10.
- [ ] **P8.12 — Minimal GUI shell (L):** Complete a Wine spike and select the
  smallest maintainable toolkit. Implement only configure, start, progress,
  cancel, resume, failure details, and result reveal. Keep the toolkit behind a
  replaceable adapter. **Depends on:** P8.11.
- [ ] **P8.13 — Desktop distribution matrix (L):** Package and smoke-test the
  launcher plus Forge on Windows, Wine, Linux, and macOS. Test paths containing
  spaces/non-ASCII, clean install, missing Forge/models, cancellation, restart,
  and output reveal. **Depends on:** P8.12.
- [ ] **P8.WG4 — Complete world configuration (S):** Expose the full shared
  `WorldSpec` through launcher controls/config import while delegating all plate,
  terrain, climate, history, and local-map behavior to Forge. **Depends on:**
  P8.11, P8.12.

**Implementation status:** the JSONL contract, toolkit-independent launcher
core, generated world controls, GUI scaffolding, packaging specifications, and a
Wine spike exist with focused tests. The checkboxes remain open for the complete
GUI selection, packaged native/Wine smoke matrix, and distribution evidence.

Required automated coverage:

- [ ] Launcher form validation and safe argv injection tests.
- [ ] JSONL unknown/malformed/partial-line and stable-error tests.
- [ ] Subprocess cancel/resume/final-result integration tests.
- [ ] A Wine smoke test for the packaged executable.
- [ ] An import-boundary test proving the GUI cannot import worldgen or model
  backend modules.

## Phase 8 completion gate

- [ ] Both Players install, load, cancel, unload, and reuse the pinned GM model
  on supported physical devices.
- [ ] Retrieval and reveal IDs match across Python, Android, and iOS.
- [ ] Responses stream responsively and completed history persists locally.
- [ ] Spoiler sentinels remain absent from every pre-reveal boundary.
- [ ] The launcher controls Forge successfully on native desktop targets and Wine.
- [ ] Phase 8 functional suites pass sequentially below the aggregate RAM limit.

## Phase 9 — Hardening and release evidence

### Verification infrastructure

- [ ] **P9.1 — Define enforceable CI gates (M):** Separate static/unit,
  fake-backed contract, v2 cross-platform, provisioned real-model, packaging,
  security, and release-candidate physical/manual gates. Every required skip is
  a failure in its owning gate.
- [ ] **P9.2 — Green deterministic default suite (L):** Make the non-model suite
  reproducible, remove order dependence/flakiness, and keep provisioned tests
  visible without pretending unavailable release assets passed. **Depends on:**
  P9.1.
- [ ] **P9.5 — Determinism matrix (L):** Prove pure procedural identity,
  fake-archive identity, same-machine real-model identity, worker-count
  independence, output-path independence, and informative first-difference
  reports. **Depends on:** P9.2.
- [ ] **P9.15 — Generated documentation drift gate (M):** Generate CLI,
  pipeline, archive-layout, schema, and scenario references from contracts and
  fail CI on drift. Do not hand-maintain volatile test counts. **Depends on:**
  P9.1.

### Real-model and procedural evidence

- [ ] **P9.WG0 — Generation specification coverage audit (L):** Build a
  clause-to-code-and-test matrix for every normative requirement in
  `generation.md`. Implement or explicitly defer every uncovered clause before
  deleting any rewrite/reference document. The audit must include registry-driven
  languages/naming/heraldry, objective magic versus beliefs/religions, conserved
  population/economy/disease/trade/war/succession, complete event causality and
  replay, every-site caves/aquifers/magma/heat/support/movement, opportunity
  extraction, full-data retention, and all mathematical conformance vectors.
- [ ] **P9.3 — Complete real-model v2 run (XL):** Retain git/config/prompt/
  schema/model hashes, model load order, duration, peak process-tree RAM, events,
  package/content hashes, and redacted logs. **Depends on:** P9.1 and Phase 8.
- [ ] **P9.4 — Real interrupted/resumed equivalence (L):** Interrupt at defined
  artifact boundaries, resume, and compare canonical internal files—not ZIP
  container bytes—with an uninterrupted run. **Depends on:** P9.3.
- [ ] **P9.WG1 — Remove obsolete worldgen paths (M):** Delete legacy `GridCell`,
  `WorldSnapshot`, LCG/compact generators, direct prompt adapter,
  narrative/procedural/hybrid modes, prototype schema, and compatibility tests.
  Delete `worldgen-rewrite.md` and `worldgen-legacy.generated.md` only when the
  P9.WG0 matrix proves no unique requirement would be lost. **Depends on:** P9.WG0.
- [ ] **P9.WG2 — Worldgen hardening suites (L):** Add property, mutation, fuzz,
  crash/resume, security, performance, and memory suites for named small,
  default, and large profiles. **Depends on:** P9.WG1.
- [ ] **P9.WG3 — Fixed-point cross-platform proof (L):** Compare canonical
  domain bytes across supported Python/desktop platforms, worker counts, output
  paths, iteration-order perturbations, and resume. Retain first differences.
  **Depends on:** P9.WG2.
- [ ] **P9.WG4 — Default 500-year world evidence (L):** Record stage timings,
  peak memory, chunk/package sizes, invariants, ledger/snapshot replay, and
  artifact/profile/registry hashes. **Depends on:** P9.WG2.
- [ ] **P9.WG5 — Complete world-to-mobile proof (L):** Carry the evidenced
  world through Bible, reconciliation, narrative, all required local maps/media,
  packaging, physical imports, and GM retrieval. **Depends on:** P9.WG3, P9.WG4.
- [ ] **P9.WG6 — Full-data retention audit (M):** Prove every required
  procedural record remains in `.story` even when narrative content never
  references it. **Depends on:** P9.WG1–P9.WG5.

### Non-binding investigation queue

These questions are worth evaluating but are not accepted product requirements
and do not block release unless promoted through `decisions.md`:

- App-upgrade behavior for existing local saves, GM history, downloaded models,
  and imported v2 libraries (distinct from the rejected v1 package migration).
- User-controlled encrypted backup/export of local saves without adding accounts,
  cloud synchronization, telemetry, or an embedded save inside `.story`.
- Reproducible dependency/toolchain builds, SBOM publication, vulnerability-update
  cadence, and long-term availability of pinned model artifacts.
- Optional package publisher authenticity/signatures if real distribution threats
  later justify revisiting D018; ZIP-byte hashing remains forbidden.
- Localization beyond readiness, assistive-technology device labs, and a supported
  low-memory device profile after the English v2 release target is stable.
- Long-term archive preservation and forward inspection tooling for packages too
  large for future mobile hardware, without imposing a Forge size ceiling.

### Security, privacy, compliance, and performance

- [ ] **P9.6 — Package/import adversarial corpus (XL):** Cover traversal,
  duplicate paths, links, bombs, JSON depth/size/count limits, hashes,
  provenance, coordinates, events, media corruption, and executable-content
  rejection in Python, Android, and iOS.
- [ ] **P9.7 — Physical mobile performance (L):** Measure model download,
  first chunk, throughput, RAM, storage, battery, thermal behavior,
  cancellation, background/reload, and offline restart on the supported device
  matrix. **Depends on:** Phase 8.
- [ ] **P9.8 — Versioned performance budgets (M):** Define regression budgets by
  hardware profile from P9.7 evidence. Do not impose a `.story` maximum size.
- [ ] **P9.9 — Offline/privacy traffic proof (L):** Audit dependencies,
  permissions, DNS/socket traffic, and background behavior; prove no telemetry,
  cloud save, account, ads, remote inference, or post-download hidden network
  path. **Depends on:** Phase 8.
- [ ] **P9.10 — Dated compliance record (L):** Finalize privacy/support pages,
  mature/AI disclosures, store questionnaires, local flag/export behavior, data
  deletion, and current Apple/Google policy review. **Depends on:** P9.6, P9.9.
- [ ] **P9.11 — Release model/license freeze (L):** Re-review the allowlist,
  immutable revisions, checksums, publisher/distributor terms, notices, intended
  uses, and UI attribution; bundle required third-party notices. **Depends on:**
  P9.10.
- [ ] **P9.13 — Human product review (M):** Review procedural plausibility,
  historical causality, Bible reconciliation, narrative branches, every-node
  image/thumbnail/score/MIDI, GM accuracy/character/spoilers, accessibility,
  mature content, and prohibited content. **Depends on:** P9.3, P9.7.

### Packaging and final release

- [ ] **P9.12 — Store/distribution artifacts (L):** Produce and validate
  signed/notarized or store-ready Windows, Wine, Linux, macOS, Android, and iOS
  artifacts, including clean install, upgrade where required, uninstall, and
  local-data retention behavior. **Depends on:** Phase 8, P9.11.
- [ ] **P9.14 — Documentation/evidence audit (M):** Verify every current-state
  claim against retained evidence and ensure all documentation agrees with the
  frozen contracts. Replace any competing roadmap with a pointer here.
  **Depends on:** P9.1–P9.13.
- [ ] **P9.16 — Final obsolete-code cleanup (S):** Remove temporary adapters,
  dead v1 references, obsolete scripts, copied fixtures, stale docs, and ignored
  rewrite artifacts; rerun all gates afterward. **Depends on:** P9.14, P9.15.

## Implementation playbook

This section is deliberately explicit so that a smaller coding model can execute
one item without reconstructing project history. It refines the checkboxes above;
it does not add a second roadmap.

### Rules for every item

1. Work on exactly one roadmap ID at a time. Read the named authoritative
   documents and existing tests before editing source.
2. Preserve unrelated worktree changes. Never replace a working implementation
   merely to match an example in documentation.
3. Put every cache, downloaded test dependency, build result, simulator result,
   generated fixture staging tree, and temporary report under repository `tmp/`.
   Run `python3 scripts/check_workspace_hygiene.py` before finishing.
4. Run heavyweight commands sequentially through:

   ```bash
   .venv/bin/python scripts/run_with_memory_cap.py \
     --soft-gb 9 --hard-gb 10 -- <command> <arguments>
   ```

   Add `--include-pattern` for Gradle daemons, Xcode/Simulator helpers, or native
   model processes. Exit code 75 means resource-blocked, not passed.
5. Never compute, store, compare, or document a hash of `.story` ZIP container
   bytes. Reopen the archive and hash declared internal members; derive identity
   from the canonical internal inventory.
6. Do not weaken mandatory world domains, complete history/local maps, per-node
   media, strict configuration, reveal isolation, offline/privacy behavior, or
   v2-only support to make a test pass.
7. Tests must fail before the implementation change and pass afterward. Add the
   smallest focused tests first, then run the relevant cross-platform/aggregate
   suite. A skipped required test is not evidence.
8. Update target docs only when a contract changes. Regenerate generated docs
   with `scripts/generate_interface_docs.py`; never hand-edit generated rows.
9. Completion means implementation, focused tests, aggregate tests, and required
   evidence all exist. Because this roadmap lists only remaining work, remove a
   completed item and repair dependencies instead of leaving a checked historical
   item here.
10. Explicitly rejected legacy proposals must not return: no optional
    narrative/procedural/hybrid generation modes, no lossy `world_snapshot` as
    package authority, no v1 package migration, no save embedded in `.story`, no
    cloud synchronization/telemetry, and no ZIP-container hash. Reveal eligibility
    remains based on visited nodes unless a new accepted decision changes it; do
    not silently add flag-based reveal semantics.

### P8.C0 implementation card — Production procedural-first wiring

**Implementation status (completed 2026-08-12):** Every acceptance, deletion,
and follow-up condition below is implemented. The complete guarded suite passed
1,189 tests at 0.892 GB peak RSS; production dry-run, consumer acceptance, mypy,
generated-document drift, and import/deletion fences also pass.

- [x] The production plan begins with physical generation and simulation, then
  runs Bible projection and reconciliation as terminal checkpointed stages.
- [x] Bible model enrichment is restricted to bounded interpretations; inferred
  output cannot replace authoritative world facts and reconciliation is rerun.
- [x] Art direction is a separate checkpointed text-model stage. Map/climate
  artifact IDs, accepted Bible references, world-map path, and palette/motif key
  sets are deterministic; inference may refine only bounded descriptions.
- [x] Story and graph are separate checkpointed stages. The text model may change
  only scene title/summary and graph-node prose; exact ID sets are required and
  deterministic references, routes, choices, flags, and topology are reparsed
  and validated before publication.
- [x] Media is split into model-refined per-node intents, image-backend
  image/thumbnail generation, deterministic structured score/MIDI generation,
  and final cross-media acceptance. Seeds, tempo, node sets, dependencies, hashes,
  formats, and complete graph coverage remain validated and mandatory.
- [x] Graph travel is authoritative: same-location choices cannot cite routes;
  cross-location choices require a current route whose exact endpoints are the
  source and target regions. Generation expands scene changes into deterministic
  shortest-route hops, and tests reject absent, stale, unnecessary, and
  wrong-endpoint routes.
- [x] Production-v2 checkpoints record canonical output IDs, upstream artifact
  IDs, durable internal-file hashes, and versioned producer/prompt fingerprints.
  Restore deletes a tampered or obsolete checkpoint and transitively invalidates
  dependants instead of reusing altered files.
- [x] The sixteen-stage interruption matrix proves resume behavior at every
  boundary: the valid prefix is reused, the unfinished suffix is scheduled once,
  final publication is deliberately repeated, and tampering at each stage
  invalidates exactly its transitive dependency closure.
- [x] Every `WorldSpec` field is classified in one checked source table: sixteen
  integer controls are exposed by `forge generate`, while twelve history ticks
  per year and ten-year snapshots are explicit worldgen-1 invariants. CLI,
  `GenerationRequest`, canonical mappings, and `RunSpec` round-trip identically;
  unknown fields and invariant override flags are rejected. The generated world
  controls reference is drift-checked.
- [x] V2 packaging retains every authoritative world envelope byte-for-byte,
  including monthly history and records unused by narrative content. A declared
  source coverage ledger binds archive path, artifact ID, SHA-256, and size;
  acceptance requires exact agreement with archive members, world-index domains,
  and the complete required-domain registry.
- [x] Local maps, media, GM index, package construction, package acceptance, and
  publication are explicit mandatory stages.
- [x] Package construction writes a hidden staged candidate. Acceptance reopens
  it as a consumer, and publication revalidates the accepted story/content hashes
  immediately before atomic replacement so a changed candidate cannot publish.
- [x] Product entry points are fenced onto `production_v2`: the base service
  registry exactly matches its sixteen stages, obsolete `narrative_v2` and
  narrative-first registry aliases are unreachable, and CLI/overnight resume
  reconstructs the exact persisted `RunSpec` instead of silently using defaults.
  Resume refuses missing, invalid, or mismatched run specifications.
- [x] The public `PipelinePlan.standard()` legacy factory and its duplicate
  generated-plan document are deleted. Plan unit tests, runner tests, policy
  tests, and generated documentation now derive from `production_v2`; a source
  fence prevents runtime or scripts from reintroducing the legacy factory.
- [x] Checkpoint phase numbers and cancellation recovery are derived from the
  validated active `PipelinePlan`. Production no longer carries hard-coded
  narrative-first phase IDs, shared image/music phase exceptions, or a second
  cancellation-stage list that can drift from the executable plan.
- [x] The shared `InstrumentedGenerateStory` fixture now executes the real
  sixteen-stage production plan against a small procedural world. The legacy
  `_execute_batch_step`, `_execute_finalize`, and batch-result aggregation
  branches are deleted from the application service; v2 mandatory media
  failures are terminal and package assertions use the v2 consumer validator.
- [x] Alternate graph endings remain physically reachable for every seed: the
  branch ending is anchored at its decision region instead of inventing a
  direct edge across a multi-hop route path. The migrated seed matrix exposed
  and now covers this formerly lucky-seed production defect.
- [x] Runtime and diagnostic entry points no longer import absorbed v1 steps.
  `scripts/dry_run.py` is a compact production-v2 generation/acceptance smoke
  test, the legacy adapters are removed from `src.models`/`src.storage` public
  exports, and `forge package` refuses unsafe loose-file v1 repackaging because
  v2 construction, acceptance, and publication are inseparable stages. A source
  fence prevents production code or scripts from restoring those imports.
- [x] The legacy seven-phase storage `Orchestrator` and its duplicate test suite
  are deleted. `GenerateStory`, `PipelinePlan.production_v2`, and
  `PipelineRunner` now have sole ownership of resume verification, model-role
  traversal, cancellation, and execution ordering; a deletion fence prevents
  the competing scheduler from returning.
- [x] The v1 `GmIndexer` and its synthetic Bible/graph integration suites are
  deleted. GM indexing is owned exclusively by `GmIndexV2Stage` and the complete
  source-linked knowledge index: coverage proves every authoritative world
  artifact, event, local map, and incoming/outgoing reference is retained.
- [x] The v1 loose-artifact `Packager` and its v1-only suites are deleted.
  Package identity is proven content-derived across independent staging runs;
  construction remains hidden, consumer acceptance is mandatory, changed
  candidates cannot publish, and final publication is verified to use atomic
  same-directory `os.replace`. A physical deletion fence prevents regression.
- [x] The v1 `ManifestBuilder` is deleted. Package-v2 manifests directly bind a
  unique artifact path/ID inventory, dependency edges, producer component,
  algorithm version, fingerprint, code revision, schema hash, byte hash, and
  size. Independent staged builds prove deterministic manifest identity, while
  v2 acceptance owns schema, complete-media, and source-coverage enforcement.
- [x] The shared archive-hash helper is package-version aware. For v2 it
  recomputes every declared artifact hash and size from member bytes and applies
  the frozen artifact-record identity algorithm; it no longer returns the hash
  of an empty legacy `content/` set. Tampered bytes change the recomputed hash,
  while ZIP compression/metadata remain outside identity. The unused v1
  pre-package JSON hash helper is deleted.
- [x] Narrative-first `WorldBuilder`, `ArtDirector`, `StoryWriter`, and
  `GameDesigner` adapters, their Bible-summary helper, and the isolated v1 test
  island (including the `content/*.json`/batch-node resume harness) are deleted.
  Their production guarantees are owned by bounded v2
  enrichment stages, strict world reconciliation, exact scene/node ID parsing,
  authoritative route validation, mandatory media, and the sixteen-boundary
  resume/tamper matrix. Physical deletion fences prevent compatibility revival.
- [x] The v1 `ImageGeneratorStep` and `MusicGeneratorStep` adapters and their
  quarantine-oriented test suites are deleted. `ImageMediaV2Stage`,
  `MusicMediaV2Stage`, and `AcceptMediaV2Stage` own exact graph coverage,
  deterministic seeds, verified PNG/thumbnail and structured-score/MIDI bytes,
  atomic publication, bounded retry, corruption recovery, dependency hashes,
  and terminal failure. The retained V2 media tests cover binary rejection,
  worker-order determinism, crash windows, mandatory coverage, and refusal to
  publish after persistent generation failure; deletion fences prevent revival.

**P8.C05B progress:** The versioned seed-plan contract is implemented. Every
derived seed now hashes the frozen algorithm version before its domain and
identity parts; `SeedPlan.for_decision()` names the stable-entity/decision-label
tuple explicitly. Golden vectors prove version, domain, entity, and label
separation, and `WG-KERNEL-003` is complete in the generated coverage ledger.
The twelve immutable signed-64-bit unit types are now consolidated in the
numeric kernel, including bounded probability, and `WG-KERNEL-001` is complete.
The shared division helper now has frozen signed-half, zero, extrema, invalid
denominator, and overflow vectors, but `WG-KERNEL-002` remains partial until all
production worldgen arithmetic has migrated to it. The deterministic numeric
kernel itself is migrated: scaled noise, interpolation, octave weighting, PPM
multiplication, and cosine approximation use checked nearest rounding, while
cell addressing and rejection-sampling partition arithmetic use the named exact
floor helper. An AST regression test forbids raw division operators in the
kernel. Terrain is also migrated: continent-radius partitioning is explicitly
exact, while normalized radial distance, relief, ocean depth, and erosion
transfer use canonical signed rounding. Its canonical artifact hash is refreshed
and an AST fence prevents raw division from returning to the module. Hydrology
now classifies river-threshold and snow-line partitioning as exact, applies
canonical rounding to seasonal discharge, publishes a canonical artifact hash,
and has the same raw-division AST fence. Climate/weather now uses canonical
rounding for axial tilt, latitude scaling, temperature lapse, aquifer moisture,
neighbor relaxation, rain shadow, and annual temperature; hemisphere selection
uses named exact partitioning. Its canonical artifact hash and raw-division AST
fence are frozen.

Biome, resource, and ecology layers are migrated as well: wetland density uses
named exact partitioning, while productivity, carrying capacity, renewable
yields, deposit quantities, trophic energy, and food-web transfer use canonical
rounding. All three modules have raw-division AST fences and canonical artifact
hashes.
Region centroids and route risk/resource averages now use canonical rounding;
route risk bands remain named exact partitions, while seasonal capacity uses
checked rounding. Region and route modules have raw-division AST fences and
canonical artifact hashes.
Local-map surface and three-axis center selection now route through named exact
addressing division. The generator has a raw-division AST fence and a canonical
every-site local-map collection hash over the conformance fixture.
Simulation demographics now use a dedicated canonical monthly calculation:
birth and baseline/outbreak death rates round symmetrically, carrying capacity
bounds births before deaths are applied, and literal low-population/half-rate
vectors cover the boundary behavior. The 55-year history-ledger and snapshot
artifact hashes are frozen after the migration.
Simulation economy now has a dedicated monthly calculation for production,
consumption, grain balance, materials, and bounded price formation. Annual trade
and migration quantities use the same canonical rounding policy. The scheduler
has no raw floor-division operators, literal scarcity/price boundary vectors are
covered, and replay ledger/snapshot hashes are refreshed.
The repository-wide division audit is complete (`WG-KERNEL-002`): production
world-state scaling routes through canonical checked rounding, coordinate and
discrete partitions use the named exact helper, raw floor division is forbidden
across `src/worldgen`, and the remaining true-division expressions are frozen
Path composition plus the generated coverage percentage. Grid addressing, map
dimming, and the embedded reference generator are migrated; its replacement
reference-world SHA-256 is frozen.
The PRNG decision contract is complete (`WG-KERNEL-004`). Worldgen random calls
now require domain, stable entity identity, and decision label; plate motion,
cell texture/jitter, deposits, local voxels, civilization identity, disease, and
reference decisions no longer depend on traversal position alone. An AST audit
rejects direct streams/underspecified seeds, and a machine-readable diagnostic
fixture freezes seed derivation plus SplitMix64 output for future native tools.

The stable-identity contract is complete (`WG-KERNEL-006`). Entity IDs now use
the frozen `storyteller.id.sha256.v1` derivation with length-framed UTF-8 and
typed, semantically labelled scalar components. Runtime validation rejects
unordered containers, mutable display-name/title inputs, non-NFC strings, and
unlabelled components. Sites, civilizations, cohorts, settlements, religions,
resources, species, history events, local features, and narrative projections
derive identity from canonical world facts instead of selection ordinals. A
machine-readable diagnostic fixture freezes representative region, site, and
event vectors for independent implementations.

The first `WG-KERNEL-005` boundary is now migrated. Declarative stages receive
an immutable `StageInputs` contract containing the frozen `WorldSpec` and a
canonically ordered read-only dependency collection. Runs return an immutable,
mapping-compatible `StageRunResult` of typed outputs instead of exposing the
runner's working dictionary. Validation now has frozen diagnostics with stable
`WG-*` codes, severity, message, and optional subject identity; error results
fail before publication. Mutation rejection, diagnostic ordering, canonical
JSON round trips, checkpoint compatibility, and structured failure are covered.

The second `WG-KERNEL-005` boundary is now migrated. `WorldArtifact` freezes
every JSON-shaped mapping and list recursively both when built and when loaded;
mutating the caller's original nested containers can no longer change the
artifact, its hash, or later publication. Frozen maps retain mapping reads and
structural equality, frozen sequences retain sequence reads, and canonical JSON
emits the same bytes before and after repository round trips. The Phase 2
generator now returns a frozen, mapping-compatible `PhysicalWorldResult` rather
than a mutable summary dictionary, with an explicit dictionary adapter only at
the CLI serialization boundary.

The third `WG-KERNEL-005` boundary is now migrated. Surface-world XY,
local-world XYZ, and chunk XY coordinates are distinct frozen contracts with
nonnegative integer invariants. Grid chunks validate canonical layer names,
coordinates, dimensions, value counts, and signed-int32 bounds at construction.
Decoding rejects oversized encoded input and headers before JSON parsing or
cell allocation, bounds each axis to 256, requires the exact header field set,
and rejects noncanonical byte encodings. A machine-readable diagnostic fixture
freezes the big-endian header/payload bytes and SHA-256, while malformed-vector
tests cover negative coordinates, oversized axes/headers, truncated headers,
out-of-range cells, and noncanonical JSON. `WG-KERNEL-005` remains partial only
at this checkpoint; typed dependency edges/producer fingerprints and the
physical pipeline's internal stage-input contracts were the remaining work.

The fourth and final `WG-KERNEL-005` boundary is complete. Artifact IDs,
dependency references, and producer fingerprints are validated immutable scalar
types that remain wire-compatible strings. Artifact construction/loading
normalizes them, rejects malformed hashes and identities, sorts dependency
references, and rejects duplicates. Every physical artifact publication now
passes through a frozen `PhysicalStageCommit` that deep-freezes its payload,
canonically orders dependencies, and carries a typed producer fingerprint.
An architecture assertion covers the complete immutable contract family, while
behavioral vectors cover mutation rejection, invalid identities/fingerprints,
duplicate dependencies, canonical serialization, and repository round trips.
`WG-KERNEL-005` is now complete.

The first `WG-KERNEL-007/008` slice is implemented. Dense integer grids can now
be streamed into canonical row-major chunks through `iter_grid_chunks`, with an
immutable `storyteller.dense-grid-manifest.v1` describing exact full and partial
edge coverage. Every descriptor hashes the canonical uncompressed chunk header
and signed-i32be payload, never ZIP or container bytes. Reconstruction accepts
any arrival order but verifies layer, coordinate, dimensions, hash, uniqueness,
and complete coverage before returning the authoritative flat grid. Golden
manifest/hash vectors, reversed-order equality, 300×270 partial edges,
single-chunk memory bounds, missing/duplicate/corrupt rejection, and canonical
round trips are covered. `WG-KERNEL-007/008` remain partial until physical dense
layers are published and read through chunk manifests rather than embedded JSON
value tuples.

Terrain elevation is now the first end-to-end `WG-KERNEL-007/008` migration.
Phase 2 atomically publishes canonical `terrain_elevation_mm` chunk files plus a
terrain manifest (now incorporated into the required terrain grid catalog). It depends on the
terrain artifact, geology explicitly depends on the manifest, and the world
index records it. Verified loading reconstructs the exact authoritative flat
elevation grid and rejects missing, corrupt, or metadata-mismatched chunks.
Phase 3 copies the required artifact and chunk files into the authoritative
world repository, and `WorldView` requires the manifest. Independent generation
runs produce byte-identical chunks.

The terrain-elevation compatibility cutover is complete. `VerifiedTerrainReader`
is now the typed persisted-world entry point: it verifies terrain and manifest
envelopes, requires the manifest's exact terrain dependency, checks its layer and
grid against terrain metadata, verifies every chunk, and returns an immutable
reconstructed elevation grid. `WorldView` exposes this reader. Elevation values
have been removed from both terrain and geology JSON, so chunks are now the sole
authoritative persisted representation. Tests reject dependency tampering and
prove that neither JSON artifact contains a duplicate elevation field.

The complete terrain-grid cutover is implemented. Elevation, plate IDs, plate
boundaries, slope, land mask, and continent IDs now share one immutable,
canonically layer-sorted `terrain_grid_catalog`; all six layers are atomically
published and verified independently. `VerifiedTerrainReader` requires the
exact layer set, common grid, terrain-to-catalog and geology-to-catalog
dependency links, then reconstructs the complete immutable `Terrain` model,
including typed plates and adjustment ledger. Terrain JSON now retains metadata
only, while geology JSON retains its version and catalog reference—neither
contains a dense terrain array. Persisted-world site checks and `WorldView` use
the verified typed reader.

Hydrology is now migrated to the same chunk contract. Filled elevation, flow
targets, accumulation, watersheds, coastline, aquifer capacity, salinity,
snowpack, and glaciers live exclusively in a canonically sorted
`hydrology_grid_catalog`; the hydrology JSON retains only algorithm version,
lakes, and river edges. `VerifiedHydrologyReader` first verifies and reconstructs
terrain, then enforces hydrology catalog dependency, exact nine-layer coverage,
shared grid, chunk integrity, and typed lake/river records before returning the
complete immutable `Hydrology`. Climate and regions depend explicitly on the
catalog. The simulation's mapping compatibility adapter is populated from this
verified reader rather than persisted arrays. Corruption and dependency-tamper
tests cover the new boundary.

Climate is now migrated. The three annual grids plus all five grids for every
season are stored exclusively in a canonically sorted `climate_grid_catalog`;
climate JSON retains only algorithm version and season count. The typed
`VerifiedClimateReader` verifies terrain and hydrology first, then enforces the
catalog dependency, common grid, exact season-derived layer set, and every chunk
before reconstructing the immutable `ClimateLayer` and `SeasonProfile` values.
`WorldView.regions()` now obtains weather regimes from this verified reader.
Soil, biomes, and routes explicitly depend on the climate catalog. Complete
fresh-generation equality plus corruption and dependency-tamper tests cover all
annual and seasonal fields.

Biome and soil persistence is now migrated. Biome ID, net productivity, and
carrying capacity live in the three-layer `biome_grid_catalog`. Soil depth,
fertility, drainage, and erosion class live independently in the four-layer
`soil_grid_catalog`; neither JSON artifact duplicates cell arrays.
`VerifiedSoilReader` and `VerifiedBiomeReader` verify upstream models, exact
layer sets, dependency chains, common grids, and chunk integrity before
reconstructing immutable typed layers.
`WorldView.regions()` and simulation genesis now obtain biome IDs and carrying
capacity through that reader. Resources, species, ecology, regions, and maps
record the catalog dependency. Full-model parity, consumer links, corrupt
chunks, and dependency tampering are covered by tests.

Resource persistence is now migrated. Geology class, strata, parent material,
fault, volcano, and renewable-yield grids live exclusively in the canonical
`resource_grid_catalog`; resource JSON retains only versioned deposit records.
`VerifiedResourceReader` verifies terrain and biome prerequisites, exact
six-layer coverage, the resource-to-catalog dependency, shared grid, typed
deposits, and chunk integrity. Simulation site selection now receives renewable
yield through this verified reader, while `WorldView.regions()` uses its typed
deposit records. Routes explicitly depend on the catalog. Full-model parity,
JSON array removal, corruption, dependency tampering, world-view access, and
simulation consumers are covered by tests.

Region ownership persistence is now migrated. The world-sized `cell_region`
array lives exclusively in `region_grid_catalog`, while region JSON retains the
sparse region graph records (cells, boundaries, centers, and neighbors).
`VerifiedRegionReader` verifies hydrology and biome prerequisites, the exact
ownership layer, common grid, dependency link, sparse record types, and chunk
integrity before reconstructing `RegionLayer`. Simulation setup and
`WorldView.regions()` now use the verified model; routes and maps explicitly
depend on its catalog. Route records were audited and remain sparse per-route
graph geometry and four-season summaries, so creating a fake world-sized
route-cost grid would add duplication rather than remove a dense JSON field.

The physical JSON audit and sparse route reader are implemented.
`VerifiedRouteReader` verifies the authoritative region model and both region
artifact dependencies before reconstructing typed route geometry and exact
four-season risk/capacity records. `WorldView.routes()` now exposes only this
verified reconstruction. `audit_physical_artifacts` recursively rejects both
legacy field names and generic `{spec, values}` grid encodings across every
physical JSON artifact. Fresh-world evidence now proves all known world-sized
physical fields are catalog-backed, so `WG-KERNEL-007` is complete. Canonical
chunk byte coverage remains under `WG-KERNEL-008` until every catalog layer—not
only terrain—is compared across independent generation runs.

Catalog-wide canonical byte verification is now implemented. Independent world
roots generated from the same frozen spec and seed must have identical artifact
IDs, catalog manifests, and raw uncompressed bytes for every chunk across all
six physical catalogs. Every descriptor hash is recomputed from those bytes and
every chunk is decoded again, which enforces canonical bounded headers,
big-endian signed-int32 payloads, coordinates, dimensions, and layer identity.
The current physical model covers 49 independently verified layers. A tampered
resource chunk proves cross-root byte mismatch rejection. Together with the
existing frozen cross-platform chunk vector and malformed/noncanonical-header
tests, this completes `WG-KERNEL-008`.

Artifact repository hardening is now implemented. Artifact kinds are validated
before path construction for both reads and writes; envelopes must contain the
exact contract fields, use canonical JSON, match the requested kind, and pass
typed artifact-ID, content-hash, dependency-ID, and producer-fingerprint
validation. Publishing an identical artifact is an idempotent no-op, while a
same-kind payload, dependency, or fingerprint conflict is rejected rather than
silently overwriting immutable evidence. Fault-injected rename failure proves
that atomic publication leaves neither a visible target nor a temporary file;
the shared writer already fsyncs the completed temp file, atomically replaces
the target, and fsyncs the containing directory. This completes
`WG-KERNEL-009`.

The physical artifact DAG and deterministic parallel chunk publication are now
implemented. `PHYSICAL_STAGE_DAG` is the typed, validated declaration of all 21
physical artifact stages and their exact dependency kinds; every commit is
checked against it, preventing the procedural implementation from silently
drifting from the contract. Dense layers within each catalog may be built and
published concurrently, but `deterministic_map` schedules sorted layer keys and
aggregates results in that same stable order. The physical entry point exposes a
validated `worker_count`. End-to-end generation with one and four workers now
produces identical result summaries, every artifact-envelope byte, all six
catalogs, and all 49 chunk layers. This completes `WG-KERNEL-010`.

Canonical JSON hardening is now complete under `WG-KERNEL-011`. The serializer
requires string object keys, normalizes keys and values to NFC, rejects keys
that collide after normalization, rejects lone UTF-16 surrogates, and rejects
every float—including finite values, NaN, and infinities—in favor of scaled
integers. Object keys remain ordered by UTF-16-BE code units and output uses the
minimal UTF-8 JSON representation. A frozen cross-platform diagnostics fixture
covers hostile ordering, decomposed Unicode, control escaping, signed integer
extremes, and JSON literals. Repository tests prove persisted non-NFC and
normalization-collision envelopes cannot bypass canonical validation.

Provenance-sensitive artifact identity is now complete under `WG-KERNEL-012`.
The full identity digest is SHA-256 over the canonical JCS object containing
sorted dependency IDs, kind, producer fingerprint, and the full payload
SHA-256; the public ID uses the kind plus its first 32 hexadecimal characters.
Build and repository acceptance share the same derivation function. Frozen
cross-platform vectors prove that identical payloads separate by kind,
dependency set, and producer fingerprint, while reversed dependency input order
canonicalizes to the same ID. Repository acceptance rejects the former
payload-only identity formula.

With `WG-KERNEL-001` through `WG-KERNEL-012` complete, P8.C05B's deterministic
kernel is complete.

P8.C05C has started with `WG-PHYS-001` complete. Plate centres use seeded
farthest-point spacing, every cell uses deterministic squared-distance Voronoi
ownership with a frozen plate-order tie break, and plate motion is an explicit
bounded fixed-point vector. Boundary type is now derived from relative motion
projected onto the centre-to-centre normal: closing plates are convergent,
separating plates divergent, and near-tangential motion transform. The physical
validator independently reconstructs ownership and boundary classes. Tests
prove the spacing optimum at every selected centre, ownership for every cell,
motion bounds, and all three boundary-class cases.

`WG-PHYS-002` is now complete. Continent seeds use deterministic farthest-point
spacing over interior cells. Four-octave fixed-point fractal noise perturbs both
the land threshold and terrain relief, replacing the prototype's smooth
elliptical coastlines. Texture-created satellite fragments are removed by
retaining only the four-connected component containing each declared seed, so
the configured continent count remains exact and every label is one connected
landmass. Border cells remain ocean outlets and minimum-area validation runs on
the final retained topology. Tests cover one, two, and three continents,
connectivity, exact labels, border oceans, texture use, and determinism.

`WG-PHYS-003` is now complete. Geology is an authoritative immutable
`GeologyLayer`, generated immediately after terrain rather than being an
incidental resource-stage calculation. Rock class, strata, soil parent
material, faults, convergent-boundary volcanism, and signed tectonic relief are
stored in a dedicated six-layer `geology_grid_catalog` and reconstructed by
`VerifiedGeologyReader`. Soil and resources carry explicit geology-catalog
dependencies. The resource catalog now contains only renewable yield; its typed
reader composes verified geology with resource deposits and yield to preserve
the public `ResourceLayer` contract without duplicate grids. Physical storage
now has eight catalogs and 70 deterministic dense layers after the explicit
hydrology delta layer and seasonal climate water-state layers.

`WG-PHYS-004` is now complete. Each erosion pass computes thermal and hydraulic
transfers from the same immutable elevation snapshot, then applies their deltas
synchronously. Thermal movement is bounded to 16 mm per source cell per pass;
hydraulic movement is independently bounded to 8 mm. Terrain metadata persists
a typed `ErosionPassLedger` containing pass index, mass before, mass moved by
each process, and mass after. Generation asserts zero delta for each process and
total conservation; physical validation independently enforces bounds,
continuity between passes, and equality with final elevation mass. Determinism
and worker-count parity remain covered by the full terrain/catalog tests.

`WG-PHYS-005` is now complete. Hydrology uses a formally deterministic
priority flood over a frozen clockwise D8 neighbourhood. The flood records a
canonical parent and discovery rank for every cell; drainage selects strictly
lower filled terrain first and follows earlier flood ancestry across equal
flats, preventing cycles without index-dependent downhill shortcuts. Physical
validation proves every flow target is D8-adjacent and non-uphill after filling,
while a symmetric-basin regression freezes tie order, flat ancestry, and
acyclic termination.

`WG-PHYS-006` is now complete. Equal-surface depressed cells are partitioned
into deterministic connected lake bodies with stable IDs and one canonical
spillway edge. Watershed IDs are assigned from sorted terminal outlets;
accumulation is independently reconstructed by validation over the drainage
DAG. Hydrology now persists an explicit river-mouth delta grid alongside its
coastline and aquifer layers. Validation covers exact lake partitioning,
spillway continuity, accumulation, watershed ownership, coastline adjacency,
aquifer bounds, and delta classification.

`WG-PHYS-007` is now complete. Hydrology persists a typed, immutable drainage
terminal registry whose stable records distinguish ocean outlets from closed
basins and bind each terminal cell to its canonical watershed ID. Generation
derives the registry from the acyclic D8 graph; the verified reader reconstructs
the enum-backed records; validation rejects missing, reordered, mislabeled, or
nonterminal declarations. Coverage proves every land cell reaches exactly one
declared terminal without a cycle, including a landlocked-world regression
that exercises explicit closed basins.

`WG-PHYS-008` is now complete. Seasonal temperature uses an explicit
fixed-point solar declination model: signed pole-to-pole latitude and configured
axial tilt share one angular scale, four frozen declinations represent the two
solstices and two equinoxes, and temperature follows angular distance from the
seasonal solar latitude. A separate 6 °C/km elevation lapse rate is applied
before physical bounds. Tests prove mirrored hemispheres swap solstices, zero
tilt removes seasonal temperature variation, larger tilt increases seasonal
range, and elevation cooling is exact.

`WG-PHYS-009` is now complete. Climate uses frozen tropical-trade,
mid-latitude-westerly, and polar-easterly circulation bands with mirrored
seasonal meridional flow. Every bounded moisture pass reads one immutable
snapshot and transports moisture from the single upwind cell. Signed elevation
change produces separately bounded windward lift and leeward rain shadow,
which feed precipitation while moisture remains within its fixed domain. Tests
freeze circulation boundaries, pass determinism, ridge lift/shadow placement,
and relaxation bounds.

`WG-PHYS-010` is now complete. Every season persists precipitation,
evaporation, snowpack, ice, and storm fields alongside temperature, winds, and
hazards. Evaporation is temperature-driven and cannot exceed precipitation;
snow derives only from retained sub-freezing water, ice requires sustained cold
snowpack, and storm intensity combines precipitation with vector wind speed.
A typed seasonal water ledger records exact precipitation, evaporation,
snowpack, ice-cell, and final atmospheric-moisture totals. The verified reader
reconstructs all 39 climate grids and ledgers, while validation independently
checks coverage, bounds, phase rules, and every ledger total.

`WG-PHYS-011` is now complete. Soil is generated before biomes as an immutable
typed layer containing depth, fertility, drainage, and erosion class. Its four
grids live in a dedicated verified `soil_grid_catalog`; biome storage no longer
duplicates fertility. Biome selection is a frozen first-match table consuming
independent land, glacier, elevation, annual temperature, precipitation, and
soil-drainage fields, with a final forest rule proving totality. Productivity
and carrying capacity consume typed soil fertility only after classification.

`WG-PHYS-012` is now complete. Mineral generation grows deterministic,
non-overlapping D4-connected bodies within one rock class and stratum. Material
selection is constrained by volcanic, fault, and host-rock provenance; every
deposit persists those geological facts alongside bounded depth and grade.
Quantity is reconstructed exactly from connected area, a frozen per-material
density, and grade. Generation, the verified reader, physical validation, and
tests independently enforce connectivity, unique occupancy, land placement,
geology compatibility, provenance, scalar bounds, and quantity arithmetic.

`WG-PHYS-013` is now complete. Simulation genesis converts every mineral
deposit into a finite typed stock and every founded site's renewable yield into
a capacity-bounded biomass stock with a monthly regeneration rate. Monthly
production deterministically selects accessible territory stocks, caps
extraction by remaining quantity, and creates exactly the extracted amount of
material. Renewable recovery and extraction are explicit event consequences;
the exactly-once applier clamps every transition to zero and capacity, while
snapshots and replay retain the complete stock state. Tests prove selection,
territory isolation, finite depletion, renewable bounds, and equality between
positive material deltas and negative stock deltas.

`WG-PHYS-014` is now complete. Every generated species has an immutable
population record in every physical region, with habitat suitability and a
trophic-level-scaled carrying capacity derived from the biome grids. Four
bounded synchronous ecology years apply explicit recovery and over-capacity
extinction pressure. Excess populations migrate only over canonical region
adjacency into compatible spare habitat; per-region transition ledgers expose
births, deaths, immigration, and emigration, and the ecology validator proves
coverage, nonnegative state, exact transition arithmetic, and global migration
conservation. Regional and species extinction flags are derived from the final
population state.

`WG-PHYS-015` is now complete. Biomes, materials, species templates, and recipes
live in one canonical versioned registry module; biome names/rule order and
deposit densities are derived from it, and history reuses the same material,
species, and recipe entries. Each registry's canonical envelope is validated
for version, identity uniqueness, and balance bounds before hashing. Physical
stage fingerprints include only the registry directly consumed by that stage:
biomes, resources, and species are independently invalidated, while recipes are
recorded at the physical root and consumed directly by the history fingerprint.
All downstream invalidation then follows immutable artifact dependency IDs.

`WG-PHYS-016` is now complete. The terminal physical stage publishes an
immutable `validation_report` that depends on all 21 domain metadata/catalog
artifacts and records each artifact ID, content hash, and exact dependency
list. Report construction independently checks the complete artifact-kind set,
declared DAG edges, absence of embedded dense grids, and all eight canonical
grid catalogs (70 dense layers); it is emitted only after the physical and
ecology invariant validators succeed. `world_index` now binds the report, and
simulation copying plus `WorldView` treat it as required physical evidence.
Tests prove report closure and identical report/artifact bytes at worker counts
one and four.

`WG-PHYS-017` is now complete. `sea_level_ppm`, previously fingerprinted but
unused, now controls the requested ocean fraction. Terrain performs a bounded
deterministic threshold search over the textured continental field, retaining
only each seeded connected component and preserving border-ocean drainage.
Generation and an independent terrain-contract validator enforce the requested
land fraction within 25,000 ppm, exact canonical continent labels/count, and
the frozen -100,000..100,000 mm elevation range. Impossible tiny-grid requests
fail explicitly instead of silently violating the specification. The physical
validation report records `WG-TERRAIN-SPEC`, and tests cover low/default/high
sea levels plus pathological representability. The newly exposed larger land
area also revealed and fixed deposit material selection: fault/volcanic
compatibility is now derived from the complete connected body, matching the
existing validator rather than only its seed cell.

`WG-PHYS-018` is now complete, which completes P8.C05C. The immutable physical
validation report now contains measured evidence rather than check-name claims:
erosion pass count, initial/final mass and thermal/hydraulic movement totals;
land, terminal, lake, river, monotonic-edge, and discharge totals; and four-
season precipitation, evaporation, snowpack, ice, and temperature extrema.
Evidence construction independently recomputes ledger totals, continuity,
river flow/elevation monotonicity, and seasonal grid sums before publication.
Adversarial tests mutate erosion mass, a river flow edge, and precipitation
ledger totals and prove each corrupt report is rejected with its domain code.

**Recommended next implementation:** Begin P8.C05D with `WG-ROUTE-001`:
replace the current seed-growth region segmentation with deterministic multi-
source Dijkstra using biome, watershed, elevation, climate, and travel costs;
retain canonical tie ordering and add cost/provenance evidence before advancing
to split/merge and size-bound requirements.

**P8.C05A–C completion audit (2026-08-13):** P8.C05A has a drift-checked
89-requirement ledger with every row classified and resolvable evidence. All 12
`WG-KERNEL-*` requirements owned by P8.C05B and all 18 `WG-PHYS-*` requirements
owned by P8.C05C are `complete`; their archived defect rows are explicitly
`obsolete`, not open work. The conformance CLI, generated ledger, complete
worldgen suite, static typing, and whitespace audit pass. The stale top-level
P8.C05B/C checkboxes have been corrected to match this evidence.

`WG-ROUTE-001` is now complete. Region ownership is produced by deterministic
multi-source Dijkstra over the land graph, with canonical `(cost, seed, cell)`
heap ordering. Its frozen positive edge cost combines base travel, biome and
watershed transitions, elevation change, annual-temperature change, and annual-
precipitation change. Canonically sampled seeds plus one seed per continent
guarantee reachability; the persisted region metadata records the exact cost
model and now depends explicitly on climate as well as biome and hydrology.
Tests prove same-input equality, complete connected ownership, bounded seed
density, nontrivial physical costs, and downstream dependency propagation.

**Recommended next implementation:** Continue P8.C05D with `WG-ROUTE-002`:
add deterministic split/merge passes with explicit minimum and maximum region
sizes, then independently validate canonical centers/boundaries, symmetric
adjacency, connectivity, and exactly-one-region ownership for every land cell.

`WG-ROUTE-002` is now complete. Dijkstra cells are normalized by deterministic
recursive graph-distance bisection above 256 cells and boundary-contact merging
below 16 cells, preferring a merge that remains within the maximum. Regions are
then canonically renumbered by their minimum cell before centers, boundaries,
and symmetric adjacency are rebuilt. The independent validator proves exact
one-owner land partitioning, sorted identity/order, size bounds, D4
connectivity, centroid-nearest canonical centers, exact boundary cells, and
symmetric adjacency. Adversarial tests reject owner-grid disagreement and a
noncanonical center.

**Recommended next implementation:** Continue P8.C05D with `WG-ROUTE-003`:
expand the route model into deterministic seasonal A* route classes—roads,
trails, navigable rivers, sea lanes, mountain passes, and later settlement
links—while preserving physical endpoints and authoritative source IDs.

`WG-ROUTE-003` is now complete. The route contract has a frozen typed class
registry for roads, trails, navigable rivers, sea lanes, mountain passes, and
settlement links. Physical land routes are classified from river coverage,
slope, and resource access; sea-lane and settlement-link kinds are reserved for
the coastal and post-settlement producers rather than assigned to invalid land
geometry. Each physical route now runs A* independently for all four seasons,
including that season's hazard field in its path cost, and persists four
canonical paths plus explicit traversability flags. The verified reader,
`WorldView`, physical validator, and tests enforce four-path endpoint,
adjacency, land-traversability, risk, and capacity consistency.

**Recommended next implementation:** Continue P8.C05D with `WG-ROUTE-004`:
freeze per-route-class cost units, legal terrain/endpoints, neighbor/tie order,
seasonal hazards, capacity, maintenance, and authoritative source-domain IDs;
add adversarial reader/validator tests for every route-class constraint.

`WG-ROUTE-004` is now complete. A frozen rule table defines every route class's
legal surface, base fixed travel cost, slope scaling, river adjustment, base
capacity, and maintenance per kilometre under the explicit
`fixed_travel_cost` unit. Seasonal A* now applies the selected class's weights
with its season hazard while retaining canonical heap and D4-neighbor ordering.
Each route persists exact endpoint-region source IDs, class-derived annual
maintenance, risk-adjusted seasonal capacity, and legal-surface geometry. The
verified reader and `WorldView` expose the complete contract; independent
validation recomputes provenance, surface legality, traversability, and
maintenance. Adversarial tests reject altered source IDs and maintenance.

**Recommended next implementation:** Continue P8.C05D with `WG-ROUTE-005`:
strengthen route and narrative travel validation to reject disconnected jumps,
wrong endpoint containment, illegal seasonal geometry, and graph transitions
without an authoritative route, including adversarial impossible-travel tests.

`WG-ROUTE-005` is now complete. Physical validation requires each route's
declared regions to be adjacent and its canonical path endpoints to belong to
the corresponding region cell sets, in addition to the existing D4 seasonal
continuity and legal-surface checks. Route generation explicitly orients every
path from the canonical lower endpoint ID to the higher endpoint ID. Narrative
travel delegates to a strict authoritative-transition validator that checks the
exact region pair, physical endpoint containment, and at least one traversable
season before accepting a choice. Existing stale-route, wrong-pair, missing-
route, and same-location tests are supplemented by adversarial disconnected
pair, foreign endpoint cell, all-seasons-closed, and outside-region geometry
tests.

`WG-ROUTE-006` is now complete. The physical DAG publishes a compact typed
`map_layers` catalog whose scalar records reference authoritative terrain,
hydrology, climate, biome, soil, resource, political-region, and hazard grid
artifacts, while vector records reference authoritative region and route feature
IDs. It embeds neither dense grids nor route geometry. The renderer emits a
deterministic full-resolution PNG for every scalar record, a route-vector raster,
the biome/region diagnostics, the composite world map, and one crop per region.
The `maps` artifact binds every exact source catalog plus the layer catalog, so
presentation files cannot silently stand in for or outlive their source facts.

`WG-ROUTE-007` is now complete. Map layers persist frozen semantic colour-table
IDs, nearest-cell resampling, and the explicit no-label placement policy used by
the current cell-resolution renderer. The `maps` payload is a typed raster
catalog: every entry records canonical path, byte hash, pixel dimensions,
contributing layer IDs, exact authoritative source artifact IDs, and renderer
policy. Validation reopens each PNG, verifies its header/dimensions/hash and
recomputes provenance from `map_layers`. Adversarial tests prove corrupted
presentation bytes are rejected without changing or replacing authoritative
layer facts.

**P8.C05D status:** roadmap items 1–3 are complete (`WG-ROUTE-001` through
`WG-ROUTE-007`). Item 4 remains `WG-ROUTE-008/009`: complete spatial,
containment, route, temporal, entity, and reverse-reference indexes, with
canonical delete/rebuild and corruption-isolation proofs. Item 5 then remains:
publish those index artifacts and expose bounded lazy lookups by stable ID,
bounding box, region, route, and time range.

`WG-ROUTE-008` is now complete. The physical DAG publishes `spatial_index` and
`reference_index` artifacts derived from the exact region grid, region, route,
hydrology, resource, species, and ecology artifacts. The spatial index stores
canonical bounding boxes and route adjacency while delegating point containment
to the verified authoritative region grid. The reference index stores compact
entity locators, cell/reverse-reference edges, and physical-world validity
ranges without copying entity records. Typed readers expose stable-ID, point,
bounding-box, region, cell, reverse-reference, and temporal-range queries; every
multi-result query is canonically ordered and capped at 256 results. The former
prototype's square-grid inference and dead construction path were removed.

`WG-ROUTE-009` is now complete. `rebuild_physical_indexes()` verifies all
authoritative inputs before touching either disposable target, reconstructs both
artifacts from the persisted world spec/seed and typed domain readers, checks
the rebuilt hashes and artifact IDs against the immutable world index, and then
replaces only `spatial_index.json` and `reference_index.json`. Tests delete both
files and require exact original bytes after rebuilding; a separately corrupted
index is rejected while terrain, regions, and routes remain readable, and is
then repaired without modifying any authoritative artifact.

`WG-ROUTE-010` and P8.C05D item 5 are now complete. `VerifiedWorldIndex` unifies
the two published index readers and exposes bounded queries by stable fact ID,
source artifact ID, route ID, point, bounding box, region, cell, and time range.
It returns compact typed locators/references rather than authoritative records.
Load-budget instrumentation proves all non-point queries use only the two index
envelopes and no dense chunks; point containment lazily adds the verified region
catalog and only its required ownership chunk. All result sets are canonically
ordered and capped at 256. End-to-end `WorldView` tests cover every query form,
cache reuse, exact source provenance, and hostile IDs, coordinates, ranges,
cells, boxes, and oversized result limits.

**P8.C05D is complete:** all five roadmap items and `WG-ROUTE-001` through
`WG-ROUTE-010` are implemented and covered by executable conformance evidence.

**Recommended next implementation:** begin P8.C05E at its first remaining
partial requirement (`WG-SOC-001`): audit and freeze the technology,
occupation, institution, government, belief, magic-vocabulary, and language
registries, hash them into the exact simulation-stage producer fingerprints,
and add selective invalidation tests before extending society generation.

**P8.C05A–D closure audit (2026-08-13):** the requirement catalog, generated
coverage document, frozen contract/profile hashes, retained-source mapping,
legacy import fence, and executable-evidence resolver pass. P8.C05B owns twelve
complete target rows plus two resolved/obsolete defect characterizations;
P8.C05C owns eighteen complete target rows plus one resolved/obsolete defect;
P8.C05D owns ten complete rows. P8.C05A is intentionally infrastructure rather
than a requirement-owner bucket and passes its dedicated contract, profile,
coverage-generation, evidence, and CLI gates. No open A–D target requirement
remains.

`WG-SOC-001` is now complete. Eleven versioned simulation registries cover
people, technologies, occupations, materials, recipes, institutions,
governments, beliefs, magic vocabulary, language phonemes/morphology, and
species. Validation rejects missing sets, unversioned registries, duplicate IDs,
and invalid balance ratios. Each simulation producer selects only its declared
registry hashes: identity, civilization, settlement, history/snapshot,
registry, and index fingerprints invalidate selectively under adversarial hash
changes. The intentional registry-contract expansion is recorded in the frozen
contract hash.

**Test execution policy:** use immutable, hash-verified A–D generated-world
fixtures for read-only P8.C05E–H consumer tests. Generator, persistence,
determinism, provenance, corruption, invalidation, and rebuild tests must create
fresh worlds and must never update the base implicitly. During implementation,
run affected unit/contracts only; at each requirement close, run its phase slice
plus conformance and numeric-inventory gates; run the complete suite when a
roadmap phase closes, a shared artifact/schema contract changes, before release,
and before handoff. This keeps ordinary feedback in seconds while retaining a
single authoritative end-to-end gate.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-002`:
make language phonology/morphology, scripts, flags, heraldry, and environmental
culture traits consume the frozen registries and physical pressures rather than
hard-coded tuples or people/race rules, with stable-ID and different-environment
tests.

`WG-SOC-002` is now complete. Founding-site biome, climate regime, water access,
route connectivity, and local resources form a canonical pressure signature.
That signature and the stable founder identity drive registry-backed morphemes,
names, writing systems, flags, heraldry, and culture traits; biological people
categories are not inputs. Language identity remains stable for the same founder
while environmental expression changes deterministically. Simulation artifacts
retain the pressure signature, flag, and heraldry, with same-input,
different-environment, registry-membership, and input-order validation tests.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-003`:
separate objective magic-law facts from attributed belief claims, require every
effect to cite its source law, and validate epistemic status before expanding
sources, side effects, religions, and schisms in `WG-SOC-004`.

`WG-SOC-003` is now complete. Objective laws, realized effects, and attributed
religious claims are distinct typed records. Every effect cites both its exact
law and registry source, matches the law's effect and paid cost, and is rejected
when uncited or inconsistent. Beliefs record their claimant, epistemic status,
and related objective-law IDs without being promoted to objective fact. These
records are retained in the identities artifact and validated before publication.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-004`:
extend the validated boundary with place-bound magical sources, explicit side
effects, religion institutions and deterministic schisms/cultural
interpretations, while keeping every transformation costed and law-cited.

`WG-SOC-004` is now complete. Registry-defined magical sources are bound to
exact sites and objective laws; realized effects retain their paid costs and
explicit side effects. Religions now own stable site-bound institutions and
rites, deterministic child-institution schisms preserve parentage and disputed
claims, and cultural interpretations remain attributed, epistemically marked
claims referencing exact laws. The validator rejects invalid source locations,
law/source mismatches, uncosted or side-effect-free transformations, broken
institution/religion links, orphan schisms, and unattributed interpretations.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-005`:
replace the current site selector with a typed, auditable suitability score over
fresh water, food/carrying capacity, defense, hazards, routes, resources,
climate, and neighbours, then prove stable tie-breaking and pressure sensitivity.

`WG-SOC-005` is now complete. Capital candidates receive a typed eight-component
integer suitability score for fresh water, food/carrying capacity, defensible
slope, seasonal safety, route connectivity, resources, climate habitability,
and regional neighbours. Frozen weights sum to one million; each published site
retains its component ledger so its total can be independently recomputed.
Selection is deterministic by total score, cell, and stable region ID, with
tests for exact recomputation, bounded components, hazard sensitivity, and
stable ordering.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-006`:
enforce the exact configured civilization count, preflight viable regional
capacity, and abort deterministically with a stable diagnostic when the world
cannot host the requested number instead of silently truncating it.

`WG-SOC-006` is now complete. Site founding admits only regions with positive
food capacity and either fresh-water or resource access, then creates exactly
the configured number of sites and civilizations. Insufficient capacity raises
a typed `WG-CIV-CAPACITY` diagnostic containing requested, viable-region, and
total-region counts; the simulator performs this genesis preflight before
creating or copying any output artifact. Exact-count success and byte-stable
failure diagnostics are covered.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-007`:
introduce explicit settlement lifecycle state and events for founding, growth,
abandonment, land use, construction, workshops, production chains, and
inventories, preserving immutable site identity through every transition.

`WG-SOC-007` is now complete. Settlements retain founding year, inhabited or
abandoned lifecycle state, immutable site identity, land-use practices,
buildings, registry-linked workshops/recipes, and nonnegative typed inventory.
Population events drive settlement growth; construction events now spend
materials and add an actual building and workshop; collapse and recovery events
change lifecycle state without replacing the settlement or site. Genesis and
final publication validate capacity, lifecycle consistency, unique identities,
recipe chains, and inventory invariants, with replay-safe nested reconstruction.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-008`:
make transport capacity constrain trade, then add explicit taxes, maintenance,
depletion/recovery ledgers, and scarcity-driven price behavior across settlement
inventories rather than only civilization-level aggregate balances.

`WG-SOC-008` is now complete. Trade uses a deterministic traversable route path
and is capped by its seasonal bottleneck capacity; ledger records retain exact
route IDs, capacity, and maintenance. Monthly replay appends settlement-level
scarcity/price, finite depletion, renewable recovery, grain trade, annual tax
assessment, and route-maintenance entries. The authoritative `economy` artifact
is replay-derived and validated for unique IDs, nonnegative quantities, allowed
kinds, route scoping, and trade amounts no greater than transport capacity.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-009`:
freeze the complete integer-only price equation and introduce explicit
conservation ledgers proving people, goods, currency, public tax transfers, and
maintenance value across every event rather than relying on aggregate tests.

`WG-SOC-009` is now complete. Grain price formation is frozen as
`grain-scarcity-v1`, uses canonical integer rounding, and publishes its exact
minimum/maximum bounds in the economy artifact. Every history consequence that
changes people, civilization goods, settlement inventory, resource stock, or
currency receives an exact conservation entry classified as source, sink, or
transfer. Validation regenerates the ledger from authoritative events, requires
byte-equivalent coverage and unique IDs, checks source/sink signs, and proves
every trade and migration transfer group nets to zero.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-010`:
extend `WorldSpec` preflight with explicit site/local-map count plus RAM, disk,
and time estimates, stable budget diagnostics, and boundary tests before the
final immutable-site closure in `WG-SOC-011`.

`WG-SOC-010` is now complete. The frozen `world-budget-v1` estimate explicitly
counts configured sites, world cells, cells per local 3D map, and total local
cells, then derives peak RAM, uncompressed disk, and deterministic execution-time
budgets. Preflight returns the typed estimate, preserves the existing RAM-only
call, accepts optional disk/time ceilings, and raises stable typed
`WG-BUDGET-RAM`, `WG-BUDGET-DISK`, or `WG-BUDGET-TIME` diagnostics containing
required amount, allowed amount, resource, and site count before generation.

**Recommended next implementation:** finish P8.C05E with `WG-SOC-011`:
add a dedicated immutable-site lifecycle validator proving abandonment,
recovery, polity collapse, and settlement replacement never mutate or erase the
site record or its historical identity, then run the P8.C05E closure audit.

`WG-SOC-011` is now complete. Site IDs are recomputed from the frozen seed,
region, and cell identity contract; genesis, every snapshot, and final
publication must retain the exact site tuple byte-for-byte. Every historical or
replacement settlement must reference a retained site. Validation rejects site
mutation, deletion, duplicate/forged IDs, and dangling settlement references,
while abandonment, recovery, and polity lifecycle changes remain state changes
around the immutable site.

**P8.C05E requirement-ledger audit (2026-08-13):** all eleven existing
`WG-SOC-001`–`WG-SOC-011` rows are complete with executable evidence. Versioned
registries, environmental identities, objective/subjective magic separation,
site viability and exact civilization capacity, settlement lifecycle and
production, transport/economy accounting, conservation, resource preflight,
and immutable site history are implemented.

The phase is deliberately not closed yet: the audit found retained source
clauses that were mapped too broadly and therefore lack their own executable
rows/evidence. Add and close these before P8.C05F:

1. Language sound change/evolution, syllable-pattern realization, and
   profanity/duplicate/confusable/reserved-name filtering.
2. Contrast-safe vector heraldry whose divisions, motifs, and meanings cite
   cultural beliefs or history.
3. Cosmological layers and celestial cycles; explicitly attributed afterlife,
   deity/spirit/demon/saint/false-entity claims; place-bound supernatural
   hazards/resources, cults, relics, and rites.
4. Households and typed interpersonal/lineage relationships tied to cohorts and
   settlements, without biological race rules.
5. Rare legendary artifacts created only by successful craft/commission events,
   retaining creator, culture, material, workshop/site, objective properties,
   attributed meanings, source IDs, and immutable creation provenance.

These are now explicit `WG-SOC-012`–`WG-SOC-016` missing requirements rather
than hidden inside completed rows. **Recommended next implementation:** begin
with `WG-SOC-012` language evolution and name-safety rules, then proceed through
heraldry, cosmology, relationships, and legendary artifacts. Begin P8.C05F only
after this expanded P8.C05E ledger is fully green.

`WG-SOC-012` is now complete. Registry-backed `CV`, `CVC`, and `VC` patterns
realize morphemes through one checked grammar. Name publication applies NFKC
case-folded confusable skeletons and rejects reserved names, prohibited
fragments, duplicates, and visually confusable duplicates. Stable language IDs
retain deterministic year 0/25/50/100 sound-change stages without rewriting
their founder identity; the identities artifact publishes every stage through
the configured history horizon.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-013`:
replace string-only flags/heraldry with contrast-validated vector parameters,
explicit field divisions and motifs, and attributed cultural/historical meaning
references while preserving deterministic presentation identity.

`WG-SOC-013` is now complete. Each civilization retains a typed vector heraldry
design with a 3:2 aspect ratio, normalized motif position and size, an explicit
field division and angle, and exact registry-backed RGB palette entries. The
validator rejects unknown colors, insufficient luminance contrast, invalid
geometry, unknown divisions or motifs, and meanings without a cultural or
historical source. Motif meanings cite the founding culture-pressure identity;
generation remains deterministic and independent of biological race rules.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-014`:
model cosmological layers and celestial cycles, then add explicitly attributed
entity and afterlife claims plus place-bound cults, relics, rites, supernatural
hazards, and resources without confusing belief claims with objective magic.

`WG-SOC-014` is now complete. The identities artifact retains ordered
cosmological layers, bounded celestial periods/phases, attributed afterlife
claims, and the complete deity/spirit/demon/saint/false-entity vocabulary with
explicit epistemic status. Cults and rites bind religions and claimed entities
to exact sites; sacred relic powers remain attributed claims. Place-bound
hazards/resources separately cite an objective magic law and the matching source
at that exact site. The validator rejects broken layer, cycle, entity, religion,
site, law, source, cult, relic, and attribution relationships.

**Recommended next implementation:** continue P8.C05E with `WG-SOC-015`:
generate households and typed interpersonal/lineage relationships tied to
authoritative cohorts and settlements, with conservation and referential checks
and no biological race rules.

`WG-SOC-015` is now complete. Final authoritative cohorts are partitioned into
stable households of at most five members, with exact per-cohort population
conservation and cohort/civilization/site/settlement agreement. A bounded set of
social anchors supports narrative-scale spouse, parent, and mentor relationships
without materializing every aggregate population member. Relationship types are
registry-backed; the validator rejects dangling or self edges, invalid household
membership, population drift, contradictory references, and cyclic parentage.
Neither households nor social anchors contain biological race classifications.

**Recommended next implementation:** finish P8.C05E with `WG-SOC-016`:
create rare legendary artifacts only from successful craft/commission history
events and retain creator, culture, material, workshop/site, objective
properties, attributed meanings, source IDs, and immutable creation provenance.

`WG-SOC-016` is now complete. A rare commission is attempted only at the
fifty-year cadence and becomes history only when its settlement has sufficient
material and a registered workshop. Each successful commission consumes both
civilization and settlement material and is the sole creation source for one
legendary artifact. The retained artifact separates canonical physical
properties from culturally attributed meaning and cites its creator anchor,
culture, material, workshop, site, and exact creation event. Immutable
year/month/sequence provenance and the complete sorted source set are validated;
forged, duplicate, dangling, or eventless artifacts are rejected.

P8.C05E is now complete: all sixteen `WG-SOC` requirements have production
symbols, retained artifacts, validators, and executable evidence.

**P8.C05A–E closure audit (2026-08-13):** The generated ledger (now 96 rows
after accepting selective genealogy for P8.C05F) and
baseline conformance command are current and valid. P8.C05B has twelve complete
kernel requirements plus two explicitly resolved prototype-defect rows; P8.C05C
has eighteen complete physical requirements plus one resolved drainage-defect
row; P8.C05D is 10/10 complete; and P8.C05E is 16/16 complete. The combined
kernel, artifact, grid, terrain, hydrology, climate, biome/resource, registry,
region/route, map, property, and society suite exposed and corrected one new raw
floor-division violation in household partitioning and refreshed the exact
reviewed path-composition inventory after source-line movement. The comparison
against `Dozed12/df-style-worldgen`, `kevshakes/dwarf-fortress-simulation`, and
`Moneyl/World-Generator` is refreshed in `docs/worldgen-references.md`; their
useful field/map, 3D/local-simulation, and staged climate/hydrology concepts are
covered or explicitly assigned to P8.C05F–H, while real-time colony play,
exhaustive genealogy, and a distinct savagery scalar remain outside scope.

**Recommended next implementation:** begin P8.C05F by auditing its history
requirements against the now-complete society foundation, then implement the
first remaining `WG-HIST` row in dependency order. Keep fast phase-focused tests
for ordinary iterations and reserve the full end-to-end gate for phase closure,
shared-contract changes, release candidates, and handoff.

`WG-HIST-001` is now complete. The simulator publishes a canonical
`history_clock` containing every configured `(year, month)` pair in strict order,
including ticks with no accepted events. Each tick retains its accepted event
IDs, and flattening all ticks must reproduce the complete ledger exactly. Replay
validates clock coverage against the configured horizon and rejects missing,
duplicate, reordered, forged, or out-of-range ticks/events. Zero-year histories
produce an empty clock; all other histories contain exactly `years × 12` ticks.

**Recommended next implementation:** continue P8.C05F with `WG-HIST-002` by
auditing monthly proposal coverage, then add the first absent causal proposal
type with an explicit event/consequence contract rather than treating a summary
sentence as evidence.

The first `WG-HIST-002` slice is implemented. Genesis now partitions each
civilization into child, adult, and elder cohorts without changing its total
population. Every year-end tick proposes explicit child-to-adult and
adult-to-elder transfers; the closed event applier checks positive bounded
amounts, matching civilization/site references, and exact source availability.
Transfers conserve population, replay through snapshots, and disappear when no
nonempty transfer exists. Birth/death net changes target an explicit child or
elder cohort. `WG-HIST-002` remains partial: disasters, crime/conflict, and
event-sourced relationship changes still require dedicated proposal contracts.

**Recommended next implementation:** continue `WG-HIST-002` with bounded
environment-driven disaster proposals whose damage, casualties, site effects,
and causes are explicit replayable consequences; do not encode disasters as
summary-only labels.

The second `WG-HIST-002` slice is implemented. Every civilization-month reads
the authoritative hazard value for its capital cell and current season, then
uses a domain-separated deterministic draw capped at a ten-percent maximum
acceptance probability. Accepted disasters cite the exact climate artifact and
hazard ppm on every consequence, consume only available cohort population and
civilization/settlement materials, retain their causal predecessor and affected
site, and discard zero-effect proposals. Replay and conservation checks cover
the resulting casualties and matched material damage. `WG-HIST-002` remains
partial for crime/internal conflict and event-sourced relationship changes.

**Recommended next implementation:** continue `WG-HIST-002` with bounded crime
or internal-conflict proposals driven by scarcity and institutional pressure,
including an explicit victim/actor, economic consequence, site, cause, and
resolution rather than flavor-only crime labels.

The third `WG-HIST-002` slice is implemented. Scarcity and the inverse of the
civilization's registry-backed government stability form a bounded crime
pressure, resolved through a domain-separated deterministic draw capped at five
percent per civilization-month. Accepted theft events cite distinct nonempty
actor/victim cohort IDs, exact scarcity and stability values, the government
registry entry, site, predecessor cause, resolution, and a currency-bounded
institutional resolution cost. Cohorts are used because named social anchors do
not yet exist at event time; person-to-person property transfer is deliberately
deferred until event-sourced genealogy supplies valid actors and accounts.
`WG-HIST-002` remains partial only for event-sourced relationship changes.

**Recommended next implementation:** finish the monthly-proposal portion of
`WG-HIST-002` by making relationship formation/change arise during history from
accepted events. Build this together with the first `WG-HIST-011` genealogy
slice so named actors exist at event time rather than being derived afterward.

`WG-HIST-002` is now complete, and the first `WG-HIST-011` slice is implemented.
Each civilization begins with one stable house and four consequential adult
anchors whose `population_weight=0` explicitly prevents duplication of cohort
population. Every five years, accepted relationship events add spouse,
parent-of, adopted-parent-of, or house-member facts between existing anchors.
The retained genealogy artifact is projected exclusively from those events and
cites the exact event/year for every edge; unknown people/houses, self edges,
invalid types, reciprocal parentage, and population-bearing anchors are rejected.
`WG-HIST-011` remains partial until succession, disputed claims, inheritance,
death/living state, and deeper lineage-cycle validation are event-sourced.

**Recommended next implementation:** continue P8.C05F with `WG-HIST-003` by
auditing yearly proposal coverage and implementing the first absent yearly
state transition, while extending `WG-HIST-011` when succession or inheritance
needs genealogical claims.

The first `WG-HIST-003` audit slice is implemented. Conquest had existed in the
closed event vocabulary but territorial seizure was incorrectly embedded in a
war event. A successful war now records only diplomacy and conflict costs; a
distinct, same-tick conquest event cites that war as its direct cause and alone
owns the balanced defender-loss/attacker-gain territory transfer. This gives
replay and narrative consumers an unambiguous causal boundary. `WG-HIST-003`
remains partial: religion has no yearly proposal, and the existing construction,
exploration, technology, succession, reform, and schism proposals still need
domain-specific transition audits beyond their current conserved costs.

**Recommended next implementation:** add event-sourced religious patronage as
the next `WG-HIST-003` slice, tied to existing religion and institution IDs and
holy sites. Keep doctrinal schism separate, and project patronage from accepted
events rather than mutating the immutable religion identities.

The religious-patronage slice of `WG-HIST-003` is implemented. Every fifteen
years an active polity can spend conserved currency to patronize one existing
religious institution at its established holy site. The accepted religion event
links all four identities, while a separate `religious_patronage` artifact is
projected exclusively from the ledger. Its validator rejects unknown or
mismatched civilizations, religions, institutions, sites, event kinds, and
duplicate identities. Religion definitions remain immutable epistemic claims;
patronage records what a polity supported, not whether the belief is true.

**Recommended next implementation:** audit succession next and connect it to
`WG-HIST-011` consequential people and houses. A succession event should name an
outgoing and incoming officeholder and cite a genealogical or institutional
claim; it must not remain only an anonymous currency cost.

The succession slice of `WG-HIST-003` and `WG-HIST-011` is implemented. Every
thirty years the selected polity now transfers office between two retained
consequential people instead of emitting an anonymous cost. The event cites an
earlier relationship event as both its causal predecessor and its typed claim,
retains the shared house, and pays the same conserved administrative cost. A
separate `successions` projection validates temporal ordering, event causality,
civilization and house membership, named participants, and the exact genealogy
edge. `WG-HIST-011` remains partial for death/living status, inheritance,
disputed claims, and deeper lineage-cycle validation.

**Recommended next implementation:** strengthen construction as the next
`WG-HIST-003` audit slice. Replace the fixed masonry-storehouse proposal with a
need-driven building choice, retain its originating construction event on the
building/workshop projection, and prove material/inventory costs reconcile.

The construction audit slice of `WG-HIST-003` is implemented. At each scheduled
construction year the selected settlement compares per-capita inventory for its
declared civilization needs and deterministically chooses a corresponding
building/workshop design. Every consequence carries one stable project ID, the
addressed need, workshop ID, and material cost. A retained
`construction_projects` projection cites the originating event and validates
the civilization, settlement, need, building, workshop, and exact mirrored
civilization/settlement material deductions. This adds provenance without
placing mutable event IDs inside immutable settlement identities.

**Recommended next implementation:** audit technology next. Replace the fixed
material charge with an event-sourced capability unlock that validates registry
prerequisites, names the enabling settlement/workshop, and retains the discovery
event; existing capabilities must remain stable and duplicate unlocks rejected.

The technology audit slice of `WG-HIST-003` is implemented. At each scheduled
research year the selected polity deterministically chooses the first unknown
technology whose registry prerequisites are already present. A successful event
spends the bounded material cost, adds the capability to immutable simulation
state, and cites its enabling settlement, workshop, prerequisites, and cost. The
retained `technology_discoveries` projection reconstructs initial knowledge and
validates prerequisite order across the ledger, registry membership, workshop
ownership, exact event shape, and duplicate unlock rejection. When nothing is
eligible, no synthetic discovery or material charge is emitted.

**Recommended next implementation:** audit exploration next. Replace its fixed
currency sink with a route-bounded expedition from a real settlement to a known
but unclaimed region or site, retain the traversed route IDs and discovery fact,
and reject teleportation, duplicate discoveries, and destinations already owned.

The exploration audit slice of `WG-HIST-003` is implemented. A scheduled
expedition now begins at the sponsoring polity's real capital settlement,
selects a known region that no polity owns and no earlier expedition discovered,
and traverses a deterministic season-four path through the authoritative route
graph. Currency is charged only when such a path and destination exist. The
retained `exploration_discoveries` projection records origin, destination,
settlement, ordered route IDs, cost, and event, and validates every route's
seasonal traversability and endpoint continuity. Teleportation, unknown or owned
destinations, invalid origins, and duplicate discoveries are rejected.

**Recommended next implementation:** audit reform next. Replace its anonymous
currency cost with a typed government or institution policy transition, retain
the prior/new value and pressure evidence, and make repeated no-op reforms
impossible. Keep schism as a distinct religious-institution transition.

The government-reform audit slice of `WG-HIST-003` is implemented. Scheduled
reform now selects a different government from the frozen registry, preferring
the most stable alternative, and applies the change to replayed civilization
state. Each event retains its prior/new government, a bounded scarcity or
institutional-instability pressure, and its conserved administrative cost. The
`government_reforms` projection validates registry membership, transition-chain
continuity, final-state agreement, causal participants/location, pressure bounds,
and duplicate identities. No-op transitions and government changes outside a
reform event are rejected; religious schism remains a separate event kind.

**Recommended next implementation:** audit schism next. Connect it to the
existing religion, parent institution, and generated child institution; retain
the disputed claim and holy site, and reject duplicate child institutions or a
schism that mutates the immutable parent religion.

The religious-schism audit slice of `WG-HIST-003` is implemented. Every thirty-
five years an accepted schism event now cites an existing religion and parent
institution, creates a stable child-institution identity, retains the disputed
claim, rite, registry identity, holy site, sponsoring polity, and conserved
administrative cost, and leaves the parent identity unchanged. The verified
`religious_schisms` projection rejects forged ancestry, duplicate child IDs,
invalid event shapes, and mismatched participants or locations.

**Recommended next implementation:** finish the `WG-HIST-003` audit by checking
diplomacy, war, collapse, and recovery against the same typed-transition bar.
Close the row only when each yearly kind has domain-specific consequences and
focused evidence; then restructure immutable proposal collection for
`WG-HIST-004`.

The diplomacy/war audit slice of `WG-HIST-003` is implemented. Relation events
now retain their prior and new status; the typed `diplomatic_transitions`
projection replays the chain from genesis to final relations and verifies the
closed transition table, bounded influence, polity/capital identities, and war
costs. Non-war diplomacy cannot spend material, while conquest remains a
distinct event caused by war. Diplomatic events also become the latest causal
event for both participating polities.

**Recommended next implementation:** audit collapse and recovery next. Record
the prior/new polity and settlement lifecycle states explicitly, require a
recovery to cite the collapse it reverses, and project retained collapse cycles
without deleting the civilization or settlement identity. Then reassess whether
all `WG-HIST-003` yearly kinds meet closure.

The collapse/recovery audit slice is implemented and `WG-HIST-003` is complete.
Collapse records paired active-to-inactive and inhabited-to-abandoned changes;
recovery records their inverse and must cite the exact collapse being reversed.
The `polity_lifecycle` projection replays those pairs, verifies participants and
capital location, rejects unpaired or forged transitions, agrees with final
state, and retains the original civilization, settlement, and site identities.

**Recommended next implementation:** begin `WG-HIST-004`. Separate proposal
collection from application for one annual conflict family, derive every
proposal from the immutable start-of-tick state, sort by an explicit frozen
conflict key, and resolve a contested resource exactly once before generalizing
the scheduler architecture.

**Reference-generator review:** `docs/worldgen-references.md` compares
the three requested Dwarf-Fortress-inspired repositories with StoryTeller.
A distinct savagery/wildness field remains outside current requirements unless
accepted by a future product decision. Megabeasts and legendary artifact
creation are implemented in P8.C05C/E; P8.C05F/H own their deeper histories and
projection. Bounded social relationships are implemented, while exhaustive
genealogy and real-time colony gameplay remain outside current scope.

**Required P8.C0 follow-ups:**

1. [x] Add route/location validation proving every graph transition is physically
   possible in the authoritative route network, including adversarial impossible
   travel tests.
2. [x] Complete CLI/config-to-`RunSpec` coverage for every `WorldSpec` field and add
   generated documentation for intentionally fixed defaults.
3. [x] Add interruption/resume and stale-checkpoint tests after every new stage,
   including internal-file hashes and producer/prompt fingerprints for enriched
   story and graph prose.
4. [x] Route `forge generate`, `forge resume`, and overnight execution through
   only `production_v2`; remove the reachable legacy narrative-first registry and
   obsolete artifact alias; enforce this with an entry-point import/source fence.
   The public legacy plan factory is also deleted; removal of the isolated
   legacy component harness and execution branches is tracked above.
5. [x] Add package coverage tests showing that every authoritative world record is
   retained even when no narrative scene references it, and run the full focused
   command/evidence set before checking P8.C0 itself.

**Read first:** `design.md` end-to-end flow, `arch.md` target pipeline,
`configuration.md`, `worldgen-rewrite.md` WP8, current `src/cli.py`,
`src/application/generate_story.py`, `src/pipeline/plan.py`,
`src/worldgen/step.py`, `src/world/builder.py`, and `src/narrative/pipeline.py`.

1. Add explicit plan stages and artifact keys for procedural world, Bible,
   reconciliation, v2 story/graph, local maps/media, GM index, v2 package, and
   acceptance/publish. Every `requires` key must be produced earlier. World and
   reconciliation failures are terminal; mandatory media cannot remain
   quarantined at publication.
2. Register the corresponding implementations in `GenerateStory._build_steps`.
   Prefer adapters around the existing new services over copying their logic.
   `forge generate`, `resume`, overnight runs, and tests must use this plan.
3. Add world/reconciliation stages to checkpoint phase mapping, cancellation,
   invalidation, progress totals, generated pipeline docs, and resume ordering.
   Resume validates `RunSpec`, dependency IDs, producer fingerprints, paths, and
   internal file hashes before reuse.
4. Add `GenerationRequest.to_run_spec()` and construct it once. Pass the same
   immutable spec into pipeline context; remove any reachable fallback that
   reconstructs defaults or uses `dict` state as configuration authority. Expose
   all world fields through CLI/config, or mark invariant/default-only fields in
   the generated configuration reference.
5. Normalize the product profile to `mature_dark_fantasy` in request, CLI,
   context, config, manifests, examples, and tests. Keep other tone vocabulary
   only where it is explicitly narrative content rather than product profile.
6. Make Bible projection require the accepted world/repository and source IDs;
   remove the orphan lossy `src/worldgen/adapter.py` after `rg` proves it has no
   production caller. The LLM may enrich but never replace/mutate world facts.
7. Add route/location validation so graph choices cannot jump between
   disconnected places or cite a route that does not connect source and target.

**Tests:** plan order/dependency/resource segments; all entry points use the same
plan; missing world/reconciliation aborts before models/downstream writes; CLI ↔
`RunSpec` round trip for every field; canonical content profile; checkpoint phase
and invalidation; interruption after each new stage; accepted package contains all
world records even when unused by narrative; impossible travel rejection.

**Focused commands:**

```bash
.venv/bin/pytest -q tests/test_pipeline_plan_v2.py tests/test_pipeline_runner.py \
  tests/test_run_spec.py tests/test_world_builder_v2.py tests/test_world_reconciler.py \
  tests/test_p8c0.py tests/test_production_wiring.py tests/test_gm_index_v2.py
.venv/bin/python scripts/generate_interface_docs.py --check
```

**Do not:** add optional narrative/procedural/hybrid modes; preserve a
narrative-first fallback; feed a lossy legacy snapshot instead of retaining full
world artifacts; or renumber checkpoint phases without migration/invalidation
tests.

### P8.C05A–H implementation cards — Complete worldgen and retire absorbed documents

These eight items are a migration with observable exit gates, not permission to
rewrite working code blindly. At the start of each item, mark existing behavior
`complete`, `partial`, `missing`, or `obsolete`; retain complete code and close
only the measured gaps. All algorithms use integers/fixed-point in committed
state, stable iteration order, domain-separated seeds, immutable artifacts, and
atomic publication. A failed validator aborts its dependent stages. No stage may
silently substitute a default, random source, floating-point implementation, or
lossy world snapshot.

Use `worldgen-references.md` during P8.C05A–H research. Its Dwarf Fortress
comparison and three open-source generators are implementation references, not
contract authorities. Any adapted idea must be mapped to a stable coverage-ledger
requirement and test; any adapted code additionally requires commit-pinned
provenance, license review, notices, and attribution. Add reference-derived
conformance cases for rainfall × drainage biome boundaries, staged hydrology,
geology/resource compatibility, civilization expansion, z-level navigation,
resource flow, fluids/heat/support, and history causality where the relevant
P8.C05 card owns that subsystem.

**Primary file ownership for a simpler implementation agent:** P8.C05A owns
`src/worldgen/conformance/`, the generated coverage document, profiles, and
legacy import fences. P8.C05B owns `numeric.py`, `rng.py`, `grid.py`,
`artifacts.py`, typed stage contracts/runner, and repository tests. P8.C05C owns
terrain/plates, hydrology, weather/climate, geology/soil, biome/resource/ecology
modules and validators. P8.C05D owns regions, routes, maps, geometry/spatial and
reference indexes. P8.C05E owns registries plus civilization, identity, magic,
settlement, production/trade/economy modules. P8.C05F owns
`src/worldgen/simulation/` events, scheduler, snapshots, replay, and history
storage. P8.C05G owns local-map/3D chunks, fluids/heat/support, local navigation,
and macro/micro reconciliation. P8.C05H owns application/pipeline adapters,
Bible/narrative world references, v2 packaging, legacy deletion, and final
cross-platform evidence. If current filenames differ, discover them with `rg`
and record the resolved symbol in the coverage ledger; do not create a second
implementation beside a working module.

#### P8.C05A — Freeze the contract and build a zero-gap coverage ledger

**Goal:** turn every useful statement in the three absorbed worldgen documents
into a machine-checkable implementation obligation before deleting any source
document.

**Implementation status (completed 2026-08-12; refreshed 2026-08-13):** The checked ledger contains 96 classified
requirements and no unclassified/missing-status row. Its validator now enforces
the ID grammar, every required column, source-document enum, status enum, and
test evidence. The generated document is drift-checked. Named expanded profiles,
the baseline CLI, and explicit legacy-module import fences pass. Four residual
broken prototype modules (`terrain`, `biomes`, `regions`, and `climate`) that
still imported the deleted object-grid model were found by the audit and removed.
requirements. The worldgen-1 profile, validated
builtin registries, and exact schema bundle now have literal frozen SHA-256
values; `forge worldgen conformance check` rejects drift in names, membership,
or bytes. The 40 normative feature rows recoverable from the retained pre-deletion
audit now map one-to-one to stable requirement IDs; the generated ledger and CLI
reject unmapped rows, stale anchors, duplicate clause IDs, or unknown requirements.
Every `WorldSpec` field now appears exactly once in the frozen defaults, validation
rules, and each fully expanded preset. Literal tiny/conformance/default profile
hashes match across fresh Python processes, every scalar min/max/constant boundary
is executable, and axial tilt's previously missing range is fixed at 0–90 degrees.
The six archived defects now link to executable target-invariant regressions for
declared drainage termination, exact final-year snapshots, worker-order equality,
every-site local-map coverage, frozen committed specs, and a literal stable-ID
vector. Conformance resolves production symbols and exact pytest functions for
every `complete` or `obsolete` row and rejects stale evidence references.
All remaining `partial` rows now also resolve every comma-separated production
symbol and one unique pytest module; stale shorthand test names and pseudo-symbols
were normalized. Partial rows deliberately do not require one exact test function,
because their broader obligations remain unfinished. The lossy-adapter removal
row is promoted to `complete` with the exact legacy-import fence as evidence.

Every requirement now has an explicit P8.C05B–H implementation owner, so partial
domain rows are classified future work rather than gaps in the C05A ledger.

**Recommended next implementation:** Start P8.C05B by versioning seed derivation
inside the digest, updating all call sites and golden vectors, and proving domain,
entity, decision-label, and algorithm-version separation.

1. Create `docs/worldgen-coverage.generated.md` from a checked source file such
   as `src/worldgen/conformance/requirements.py`. Give every requirement a stable
   ID (`WG-KERNEL-*`, `WG-PHYS-*`, `WG-ECO-*`, `WG-ROUTE-*`, `WG-SOC-*`,
   `WG-HIST-*`, `WG-LOCAL-*`, `WG-INTEGRATION-*`), target symbol, artifact kind,
   validator, test, and status. Include every heading, normative “must”, formula,
   required/optional domain, acceptance row, prototype defect, and legacy symbol
   from all three absorbed documents. The generator fails on duplicate IDs,
   missing columns, unknown statuses, or a completed row without a real test.
2. Freeze `worldgen-1`: units, rounding, overflow behavior, PRNG and seed-plan
   versions, default `WorldSpec`, valid ranges, ID grammar, canonical JSON/grid
   encodings, stage order, required artifact kinds, validation codes, snapshot
   cadence, full-retention policy, and default one-continent/500-year profile.
3. Add named profiles: a tiny fast unit profile, a small immutable cross-platform
   conformance profile, and the release default. Presets expand to a complete
   `WorldSpec` before hashing; artifact fingerprints never contain unresolved
   preset names.
4. Inventory every import/caller/config/schema/test for legacy `GridCell`,
   `WorldSnapshot`, `generate_world`, `snapshot_to_bible_context`, old RNGs,
   prototype enums, adapter helpers, and narrative/procedural/hybrid switches.
   Add an architecture test that forbids new imports while migration is active.
5. Preserve several prototype seeds only as characterization fixtures. Record
   known defects—drainage sinks, skipped history years, order dependence,
   incomplete local maps, mutable overrides, inconsistent IDs—as tests that the
   target implementation must reject or improve, never as target golden output.

**Tests and exit:** coverage-generator tests; requirements-to-symbol/test audit;
profile expansion round trips; schema/registry hash stability; architecture
import fence; baseline `worldgen conformance` command. P8.C05A is complete only
when the generated ledger contains every source requirement and no unclassified
row. **Depends on:** P8.C0.

#### P8.C05B — Deterministic kernel, contracts, persistence, and invalidation

**Goal:** provide one versioned runtime on which every later domain can rely.

**Implementation status (2026-08-13):** Step 2's SHA-256 seed-plan portion is
complete (`WG-KERNEL-003`): the payload is `(master seed, algorithm version,
domain, stable entity ID, decision label)`, the explicit decision API is frozen,
and replacement golden/separation vectors are executable. The SplitMix64 stream,
entity-local named decisions, source audit, and native diagnostic fixture are
complete under `WG-KERNEL-004`; completing this portion does not complete P8.C05B.
Step 1's complete fixed-unit registry is implemented (`WG-KERNEL-001`), and the
signed rounding policy has executable boundary vectors. Its call-site migration
is complete under `WG-KERNEL-002`; an exact AST inventory forbids raw floor
division and freezes the non-world-state true-division exceptions. The core
`worldgen.numeric` module is fully
migrated and guarded against raw division operators; terrain now has the same
guarantee, hydrology is migrated and guarded too, and climate/weather is the
same. Biome, resource, and ecology calculations are now migrated and guarded; the
region and route layers are migrated and guarded too. Local maps and simulation
were the next production arithmetic boundaries; local maps are now classified,
guarded, and frozen. Simulation demographic/disease arithmetic is migrated;
economic rates are migrated and guarded too. Discrete calendar scheduling uses
modulo cadence rather than division, and the repository-wide arithmetic audit is
complete. Stable IDs are versioned and typed (`WG-KERNEL-006`). All Step 3
contracts are now immutable and typed (`WG-KERNEL-005`), including stage
inputs/outputs, diagnostics, deep-frozen artifact envelopes, physical commit
inputs, explicit coordinate spaces, bounded chunks, dependency references, and
producer fingerprints. The next boundary is Step 4 under `WG-KERNEL-007/008`.

1. Consolidate fixed-point unit types for distance, elevation, temperature,
   rainfall, moisture, mass, energy, population, time, probability, price, and
   capacity. Route every division through one documented `round_div` rule; use
   checked/saturating behavior only where the requirement explicitly names it.
   Add boundary vectors for negative halves, zero, extrema, and overflow.
2. Implement SHA-256 domain seed derivation plus the frozen SplitMix64 stream.
   A decision uses `(master seed, algorithm version, domain, stable entity ID,
   decision label)` and never loop position alone. Publish golden vectors for
   Python and future native diagnostic tools.
3. Make `WorldSpec`, stage inputs/outputs, coordinates, chunks, artifact
   envelopes, dependency edges, producer fingerprints, diagnostics, and
   validation results immutable typed contracts. Stable IDs derive from
   canonical identity inputs, never names or unordered enumeration.
4. Use flat/chunked integer arrays for dense grids; prohibit per-cell object
   graphs in production. Freeze canonical big-endian grid headers/payloads,
   canonical JSON, chunk coordinates, compression policy, and maximum decoded
   sizes. Hash canonical internal bytes only—never ZIP/container bytes.
5. Make `WorldArtifactRepository` confined and atomic. Verify ID, content hash,
   producer fingerprint, dependency IDs, canonical path, and encoding on every
   reuse. Implement dependency-closure invalidation, crash-safe temporary writes,
   fsync/rename publication, cancellation boundaries, and corrupt/stale artifact
   rejection.
6. Define the declarative world stage DAG and resource classes. Independent
   chunks may run in parallel, but aggregation, conflict resolution, ledgers, and
   publication use stable order and produce identical bytes at worker counts 1
   and N.

**Tests and exit:** numeric/PRNG/ID/chunk golden vectors; property and mutation
tests; unsafe-path/corruption/crash-window tests; dependency invalidation; worker
1-versus-N equality; cancellation/resume after every commit boundary; memory
profile proving flat arrays. No later item starts until this kernel is green.
**Depends on:** P8.C05A.

#### P8.C05C — Physical world, climate, geology, soils, resources, and ecology

**Goal:** generate a complete physically coherent macro world with exact domain
artifacts and validation, not decorative noise.

1. Generate spaced plate centres, deterministic Voronoi ownership, plate motion,
   boundary classes, configurable exact continent count, uplift/rift/transform
   relief, fixed-point multi-octave texture, geological strata, faults, volcanic
   areas, and soil parent material. Apply synchronous thermal and hydraulic
   erosion with an explicit mass ledger.
2. Implement priority-flood depression handling, deterministic D8 flow with
   frozen tie order, accumulation, river thresholds, lakes, spillways,
   watersheds, aquifers, coastlines, deltas, and water-balance checks. Every
   non-ocean surface cell must drain to ocean or a declared closed basin.
3. Implement four-season solar temperature from latitude/elevation/axial tilt,
   stable prevailing winds, orographic lift/rain shadow, bounded moisture
   relaxation, precipitation, evaporation, snow/ice, storms, and derived weather
   regimes. Convergence is bounded by the configured pass count.
4. Produce soil depth/fertility/drainage/erosion classes and a total ordered biome
   table with no later mutation overrides. Generate mineral/deposit geometry,
   depth, grade, quantity, geology compatibility, renewable yields, and depletion
   rules.
5. Generate habitats, species, food-web bounds, carrying capacity, migration
   corridors, extinction pressure, and recovery. Hash versioned material,
   species, biome, and recipe registries into producer fingerprints.
   Generate a rare bounded set of megabeasts as persistent ecological entities
   with stable identity, origin, capabilities, habitat constraints, lair,
   territory, movement limits, current condition, and explicit carrying cost.
6. Publish separate immutable artifacts for plates, terrain, geology, hydrology,
   climate/weather, soils, biomes, resources, species, and ecology, each with
   exact upstream dependencies and domain-specific validators.

**Tests and exit:** exact continent count; land/ocean and elevation bounds; erosion
mass conservation; drainage termination; river monotonicity; seasonal/climate
invariants; biome totality; deposit compatibility; bounded ecology; same-seed
bytes and different-seed divergence; tiny/pathological grid cases. Record stage
time/RSS/disk for tiny, conformance, and default-preflight profiles.
**Depends on:** P8.C05B.

#### P8.C05D — Regions, routes, maps, spatial indexes, and reference indexes

**Goal:** turn physical domains into stable connected places and travel facts
that narrative and local generation can safely reference.

1. Segment regions with deterministic multi-source Dijkstra over biome, basin,
   elevation, climate, and travel costs. Implement deterministic split/merge,
   minimum/maximum sizes, canonical centres/boundaries, symmetric adjacency, and
   full one-region-per-land-cell coverage.
2. Generate seasonal A* routes for roads, trails, navigable rivers, sea lanes,
   mountain passes, and later settlement links. Freeze neighbour/tie ordering,
   cost units, legal endpoints, traversability seasons, hazards, capacity,
   maintenance, and source domain IDs. Reject disconnected jumps and routes whose
   endpoint regions do not contain the path endpoints.
3. Emit canonical scalar/vector layers and deterministic raster maps: world,
   terrain, hydrology, climate, biome, resource, political, travel, hazard, and
   one region map per region. Freeze colour tables, resampling, label placement,
   dimensions, and provenance. Derived presentation maps never replace facts.
4. Build spatial, containment, route, temporal, entity, and reverse-reference
   indexes from authoritative artifacts. Delete and rebuild them in tests and
   require canonical equality. Index corruption invalidates only derived indexes.
5. Publish region/route/map/index artifacts with complete dependencies and expose
   bounded lazy lookup APIs by stable fact/source ID, bounding box, region, route,
   and time range.

**Tests and exit:** region coverage/connectivity/adjacency; route legality and
seasonality; impossible-travel rejection from world through story graph; map
pixel/dimension goldens; index rebuild equality; bounded lookup and hostile query
tests. **Depends on:** P8.C05C.

#### P8.C05E — Peoples, identities, magic, settlement growth, and economy

**Goal:** create inhabitants and institutions from environment/history inputs,
without essentialist race-conditioned shortcuts.

1. Freeze and hash registries for technologies, occupations, materials, recipes,
   institutions, governments, beliefs, magic vocabulary, language phonemes and
   morphology. Generate languages, morphemes, names, scripts, flags, heraldry,
   culture traits, laws, and institutions from stable IDs plus environmental and
   historical pressures—not biological “race” rules.
2. Separate objective magic laws from attributed belief claims. Generate magical
   sources, costs, limits, side effects, religions, schisms, institutions, and
   cultural interpretations; every objective effect cites a law/source and every
   belief remains explicitly attributed.
3. Score initial sites using fresh water, food/carrying capacity, defense,
   hazards, routes, resources, climate, and neighbours. Create exact configured
   civilization count where feasible; otherwise abort with a stable capacity
   diagnostic. Create capitals, cohorts, households/relationships, stockpiles,
   governments, territory, settlements, and diplomatic baselines.
4. Implement settlement founding/growth/abandonment, land use, construction,
   workshops, production chains, inventories, transport capacity, trade,
   scarcity, prices, taxes, maintenance, depletion, and recovery. Freeze a
   bounded integer-only price equation and conservation ledgers for people,
   goods, and currency/value tokens.
   Generate rare legendary artifacts only through successful craft/commission
   events. Each artifact records stable identity, creator, culture, material,
   workshop/site, objective properties, attributed meanings, source IDs, and
   immutable creation provenance; ordinary package artifacts are unrelated.
5. Define an explicit site-count budget and preflight formula covering required
   local-map RAM/disk/time. Sites are immutable identities; abandonment changes
   state, not identity or historical existence.

**Tests and exit:** registry/name/flag goldens; uniqueness and order independence;
magic fact-versus-belief separation; viable capital placement; configured-count
success/failure; population/stockpile/trade conservation; bounded prices;
settlement lifecycle; deterministic economy at worker counts 1 and N.
**Depends on:** P8.C05D.

#### P8.C05F — Monthly causal history, events, snapshots, replay, and retention

**Goal:** simulate the complete configured history as a replayable state machine
whose events explain every committed change.

1. Run all configured years and exactly 12 ticks per year. Monthly proposals cover
   births, deaths, ageing/cohorts, migration, disease, harvest, production,
   consumption, trade, depletion, disasters, crime/conflict, and relationship
   changes. Yearly proposals cover construction, exploration, technology,
   religion, diplomacy, succession, reform, schism, war, conquest, collapse, and
   recovery.
   Include bounded megabeast movement/encounter/hunt/death proposals and
   legendary-artifact creation, gift, inheritance, trade, theft, loss, recovery,
   and destruction proposals. Every present-day lair, scar, owner, ruin, cult,
   and artifact location must be derivable from accepted events.
   Retain selective genealogy for consequential social anchors and houses:
   parent/child, spouse, adoption, disputed lineage, succession, and inheritance.
   These facts arise only from replayable events and may explain claims, feuds,
   offices, and relic ownership; they must not duplicate aggregate cohort
   population or expand into purposeless trees for every simulated citizen.
2. Collect proposals from the immutable start-of-tick state, sort by the frozen
   conflict key, resolve capacity/resource conflicts once, then apply accepted
   events through one event applier. No subsystem may mutate state directly.
3. Every event records stable ID, year/month/sequence, kind, causes,
   participants, locations, before/after deltas, consequences, summary, source
   IDs, and algorithm version. Causes precede effects; participants/locations
   exist at that tick; every material state delta has exactly one event.
4. Commit monthly batches atomically with prefix hashes. Write genesis, every
   ten-year snapshot, and the exact final-year snapshot without duplicates.
   Replay from genesis and from each snapshot to the same final canonical state;
   detect missing/reordered/duplicated/tampered events at the first divergence.
5. Retain the complete ledger, identities, registries, state snapshots, and
   extinct/abandoned entities even when narrative never references them.
   Checkpoint/resume occurs per committed batch and never repeats an applied
   change.
   Retain dead megabeasts and destroyed/lost artifacts with their full histories;
   rarity budgets prevent either system from becoming commonplace decoration.

**Tests and exit:** zero-year and non-multiple-of-ten histories; no skipped final
year; causal DAG; conservation and capacity invariants; succession/war/collapse
scenarios; replay/prefix vectors; corruption and crash-window tests; interrupted
versus uninterrupted byte equality; full 500-year preflight and capped evidence.
**Depends on:** P8.C05E.

#### P8.C05G — Every-site local 3D worlds and macro/micro reconciliation

**Goal:** generate and retain a complete, navigable local world for every
registered site while preserving macro authority.

1. Derive immutable boundary conditions from site, region, terrain, geology,
   hydrology, climate, resource, route, culture, settlement, and present-state
   artifacts. Macro coastline, river, road, elevation, climate, resource, and
   ownership constraints are authoritative at local boundaries.
2. Generate chunked 3D surface, strata, deposits, caves, aquifers, rivers/coasts,
   vegetation, parcels, streets, walls, bridges, culturally coherent buildings,
   workshops, ruins, interiors, items, and persistent smaller local entities.
   Local detail may refine empty space but may not contradict a macro fact.
3. Build legal 3D movement edges for walking, stairs, ramps, doors, bridges,
   climbing and configured traversal; implement hierarchical A* between local
   cells, sites, and macro routes with stable costs/ties.
4. Implement bounded synchronous water/magma flow, heat transfer, and structural
   support/collapse where enabled. Freeze update order, conservation ledgers,
   iteration caps, and failure diagnostics.
5. Reconcile micro-to-macro summaries (population, production, storage,
   resources, routes, damage, ownership) without double counting. Macro updates
   occur only through events; local regeneration uses recorded state and produces
   identical chunks.
6. Publish a local index and required chunks/maps for every historical/present
   registered site. Retain local data in `.story` even if unvisited and unused.
   Use chunk streaming/lazy reader access; generation/publication remains
   complete before package acceptance.

**Tests and exit:** exact every-site coverage; boundary continuity; cave/aquifer
and fluid/heat/support invariants; building access; route-to-door connectivity;
3D path legality; macro/micro conservation; abandoned/ruined sites; chunk resume,
corruption, order independence, memory/disk budget, and full package retention.
**Depends on:** P8.C05F.

#### P8.C05H — Story projection, production integration, hardening, and deletion gate

**Goal:** prove every domain is used safely by the product, remove all prototype
paths, and make this roadmap plus generated evidence sufficient after deleting
the three absorbed documents.

1. Generate deterministic story opportunities from authoritative pressures,
   routes, people, events, beliefs, sites, and local containment. Build bounded
   typed World Bible projection chunks with complete source coverage. Projection
   is intentionally selective; authoritative world artifacts remain immutable
   and complete. Remove `snapshot_to_bible_context` and all lossy adapters.
   Project only historically consequential megabeasts and legendary artifacts
   connected to the selected regions, people, conflicts, beliefs, mysteries, or
   opportunities. The model may enrich description but may not invent origin,
   creator, ownership, movement, encounters, powers, location, or condition.
2. Require strict Bible reconciliation before story generation. Story scenes,
   graph nodes, choices, travel, media intents, and GM entries carry valid stable
   world/source IDs. Validate temporal/entity state and both ends of travel at
   every choice. The LLM may enrich prose but cannot invent or mutate world facts.
3. Make the P8.C0 plan the only product generation/resume plan. Add checkpoint,
   invalidation, cancellation, events, and progress for every domain, history
   batch, local map, projection, reconciliation, narrative, media, package, and
   acceptance boundary. Standalone commands are diagnostics over the same
   services, never an alternate product pipeline.
4. Package every procedural envelope, complete history, every local world, all
   registries/indexes, Bible/reconciliation, narrative, full image/thumbnail/MIDI
   and structured score per node, GM index, maps, schemas, and provenance. Verify
   canonical internal file hashes and dependency DAG; never compute/compare a ZIP
   hash. Publish only after consumer-equivalent v2 acceptance.
5. Remove legacy generator/types/enums/RNG/adapters/config modes/fallbacks and
   migrate or delete characterization tests. Add an architecture test proving no
   production import or CLI/GUI route reaches them. Remove obsolete `src/worldgen/step.py`
   if it remains the lossy snapshot implementation.
6. Run property, mutation, fuzz, hostile-input, determinism, worker-count,
   cancellation, crash recovery, security, performance, disk, and memory suites.
   Run a complete real-model conformance-profile pipeline and a default-profile
   preflight/overnight run sequentially under the 9/10 GB cap. Emit first
   differing artifact/path/JSON pointer/byte offset on determinism failure.
7. Regenerate `docs/worldgen-coverage.generated.md`. Every row must be `complete`,
   link to an existing production symbol and non-skipped test, and have retained
   evidence where required. Add a script that fails if any unique normative term,
   requirement ID, legacy symbol, algorithm, artifact, validator, or acceptance
   row from the three absorbed documents lacks a mapped completed row.
8. Only after step 7 passes, delete `docs/generation.md`,
   `docs/worldgen-rewrite.md`, and `docs/worldgen-legacy.generated.md`; remove all
   links to them; regenerate/check documentation; run the complete Python,
   Android, and iOS contract gates plus workspace hygiene. Commit deletion in the
   same change as the zero-gap evidence so no requirement disappears silently.

**Final exit commands:** a memory-capped sequential Python gate; worldgen
conformance and default preflight; generated-doc `--check`; legacy import/reference
scan; shared v2 fixture catalog on Python/Kotlin/Swift; Android JVM tests; Swift
contract tests; workspace hygiene; and `git diff --check`. P8.C05H is complete
only when all pass, all three absorbed documents are gone, and their zero-gap
generated replacement remains. **Depends on:** P8.C05A–G and P8.C0. P8.C1 may
finish in parallel but deletion also requires any world-schema obligations to be
represented in P8.C1's trace matrix.

### P8.C1 implementation card — Complete v2 schemas

**Read first:** `package-v2.md`, the P8.C05A–H cards and generated worldgen
coverage ledger, `api.md` package contracts, `decisions.md` D020–D029, and every
file in `schemas/v2/`.

**Primary files:** `schemas/v2/*.schema.json`, `tests/fixtures/v2/`,
`scripts/generate_v2_fixtures.py`, `tests/v2/`, and a new generated trace report
such as `docs/schema-trace.generated.md`.

**Order of work:**

1. Inventory each normative JSON record and field. Give every record a `$defs`
   definition with required fields, exact types, closed properties, ID/hash
   patterns, integer ranges, and array uniqueness/order rules that JSON Schema can
   express. Put cross-file semantic rules in the validator trace column.
2. Complete shared primitives first: ID, SHA-256, artifact producer, artifact
   record, coordinate/grid/chunk reference, source/reference list, and diagnostic
   envelope. Reference them rather than copying divergent definitions.
3. Complete world schemas in dependency order: index → terrain/hydrology/climate
   → biomes/resources → regions/routes/sites → civilizations → history/snapshots
   → local maps.
4. Complete narrative/media schemas: Bible, reconciliation, style, story, graph,
   GM index, structured score, node media, then manifest.
5. For every required or forbidden rule add one scenario whose failure is caused
   only by that rule. Give it a stable expected code; do not create dozens of
   hand-edited ZIPs when the fixture generator can produce them deterministically.
6. Generate a rule matrix with columns: normative section, schema path, validator
   function, valid scenario, invalid scenario, and native parity status.

**Minimum tests:** schema metaschema validation; valid minimal and representative
documents; missing/extra/wrong-type/range/pattern cases per record; duplicate IDs;
unsafe paths; unknown features; incomplete inventory; source/reference grammar;
history/local-map/media shapes; graph/world route consistency and impossible
travel. No schema may be only `{type: object}` or contain
an unconstrained object/array where the frozen contract defines its contents.

**Focused command:**

```bash
.venv/bin/pytest -q tests/test_schema_validator.py tests/v2
.venv/bin/python scripts/generate_v2_fixtures.py --check
```

**Do not:** alter the frozen contract to fit existing shallow fixtures; use ZIP
bytes in identity; accept floats in authoritative fixed-point fields; or let
embedded package schemas become trusted acceptance authorities.

### P8.C2 implementation card — Three-validator parity

**Prerequisite:** P8.C1. **Primary files:** `src/storage/package_v2.py`,
`droid/.../engine/V2PackageValidator.kt`, `ios/.../Engine/V2PackageValidator.swift`,
shared `tests/fixtures/v2/catalog.json`, native scenario tests, and
`scripts/verify_cross_platform_scenarios.py`.

1. Write one ordered acceptance-stage table from `package-v2.md`: central-directory
   safety and limits; trusted schema selection; manifest syntax/schema; declared
   member inventory and internal hashes; provenance DAG; domain completeness;
   cross-references/replay/index rebuilding; local/macro reconciliation; binary
   media; mandatory coverage; final content/story identity.
2. Implement the same stable first-error or sorted-multi-error policy on all three
   platforms. Never depend on map iteration order or platform ZIP convenience
   extraction before raw names are validated.
3. Stream/hash bounded members where practical. Preflight declared uncompressed
   bytes and free space before extraction. Stage privately and publish atomically.
4. Extend the catalog with valid small/representative cases and one isolated case
   for every stable diagnostic. Emit result JSON to `tmp/contracts/` and compare
   exact acceptance plus ordered issue codes.
5. Verify that every region-map manifest entry resolves to exactly one declared
   artifact and that every documented required/forbidden archive path matches
   executable acceptance constants.

**Exit commands:** Python v2 suite, Android JVM suite, simulator-free Swift
contract runner, and `scripts/verify_cross_platform_scenarios.py`. Then run the
workspace-hygiene check. Completion requires zero platform-only acceptance rule.
Once behavior is locked, split the growing Python acceptance implementation behind
one stable facade into path/container, manifest/inventory, schema/domain,
references/provenance, and media checks. Preserve acceptance order and public
diagnostics; do not combine refactoring with semantic relaxation.

### P8.WG1–P8.WG3 implementation cards — Complete procedural retrieval

**P8.WG1 files:** `src/narrative/`, `src/world/views.py`, packaged GM/world index
schemas, Kotlin/Swift `GmIndex` and package repositories.

1. Define a bounded `KnowledgeSource`/reader port that accepts IDs or query
   tokens and returns only small typed excerpts. It must read indexes/chunks
   lazily and expose counters in tests.
2. Add indexes for global facts, chronological history, site containment, local
   features, routes, people, beliefs, and opportunities. Store stable source IDs,
   reveal requirements, chunk path/offset, and bounded normalized text.
3. Implement equivalent lazy readers in Python, Kotlin, and Swift. Prove a lookup
   does not deserialize the full world, ledger, or all local maps.

**P8.WG2:** freeze integer scoring features and tie-break order in `api.md`; add
current-node, visited route/site, containment, recency, entity kind, and exact
source boosts; implement the same arithmetic on all platforms; expand the shared
GM catalog and exact result parity script. Do not introduce embeddings or
platform-dependent tokenizers into v2 scoring.

**P8.WG3:** place unique unrelated sentinel strings in unrevealed global facts,
history changes/summaries, local maps, beliefs, opportunities, IDs, and source
IDs. Assert absence from eligible candidates, ranking diagnostics, prompt text,
errors, logs, and saved history before reveal; assert intended presence after all
required nodes are visited. Run Python plus both native scenario suites.

### P8.6 implementation card — Native semantic chunk stream

**Read first:** `api.md` GM chunk stream, `design.md` GM flow, `diagnostics.md`,
and existing Kotlin/Swift `LlamaEngine` lifecycle tests.

1. Define equivalent sealed enum/Swift enum events: `started(request_id)`,
   `text(request_id, sequence, nonempty_text)`, `completed(request_id, usage)`,
   and `failed(request_id, stable_code)`. Cancellation has a typed outcome and
   must not masquerade as failure.
2. Put a bounded channel/async sequence between native callbacks and UI. Choose
   fixed queue and coalescing limits, document them in `api.md`, and never block
   the native callback indefinitely.
3. Make one request own one model lease and cancellation token. Check cancellation
   during prompt decoding and token generation. Close native resources exactly
   once on success, failure, cancellation, navigation, and background pressure.
4. Replace whole-string APIs only after adapters/tests consume the stream. Keep
   final assembled text as a consumer result, not a second generation call.

**Tests:** ordered sequences; no empty text; strictly increasing sequence; exactly
one terminal event; failure before/after text; cancellation latency; queue bound
under slow consumer; concurrent-start rejection/serialization; load-use-unload-
reuse; native double that calls back after cancellation. Run Android and
simulator-free Swift tests first; physical evidence remains a Phase 8 gate.

### P8.7 implementation card — Transactional conversation history

1. Freeze one save-side conversation schema with version, story/content hash,
   conversation ID, exchange ID, completed user and assistant text, timestamps or
   deterministic order, selected source IDs only if debug policy permits, and no
   hidden candidate data.
   Also freeze version behavior: reject an unknown future save version with a
   stable diagnostic; do not silently reinterpret it. Any older-save upgrade is
   an explicit deterministic app-data decision, never v1 package migration.
2. Use the simpler policy: keep a user/assistant exchange only after `completed`;
   discard provisional state on cancel/failure. Write a temporary complete file,
   fsync where supported, then atomically replace.
3. On load validate schema, package binding, node/flag references, ordering, and
   size/count budgets. Isolate corrupt/mismatched history without harming the
   immutable story or valid save.
4. Select bounded prior context without deleting durable history. Configuration
   controls selection, not destructive retention.

**Tests:** crash at every write boundary; cancel/failure leaves no partial turn;
restart round trip; corrupt/mismatched isolation; two stories cannot collide;
history never enters `.story`; hidden sentinels absent.

### P8.8–P8.9 implementation cards — GM UI and end-to-end isolation

**P8.8:** wire observable stream state into both native screens. Implement idle,
loading, streaming, completed, cancelled, and failed states; cancel and retry;
clear-history confirmation; model readiness/delete/re-download; local flag and
review-before-export. Navigation and screen rotation/backgrounding must not leak
or duplicate requests. Add accessibility labels, focus order, live-region chunk
announcements with coalescing, reduced motion, and large-text layouts.
Resolve reader backtracking before changing the save schema: either define its
state/flag/undo semantics identically or remove the ambiguous optional UI. A
bookmark is not automatically an authority to undo flags and visited-node reveal.

**P8.9:** run the same sentinel through candidate source, reveal gate, prompt,
native model double output/error, UI semantics/snapshot, local log capture, retry,
cancellation, and persisted history. Search every captured boundary for hidden ID,
source ID, and text. A prompt instruction saying “do not reveal” is never accepted
as a substitute for absence from input.

### P8.10–P8.13 and P8.WG4 implementation cards — Desktop launcher

**P8.10 contract:** add versioned JSONL event/result types and exit codes to
`api.md`. Specify maximum line length, malformed/partial/unknown event handling,
stdout versus stderr ownership, cancellation acknowledgement, resume command,
final accepted package path, and stable diagnostic envelope. Add CLI contract
tests before GUI work.
Include `artifact_reused`, `artifact_regenerated`, and aggregate reuse counts so
resume progress explains why verification may be slow without exposing hidden
content or scraping human logs.

**P8.11 core:** create a toolkit-free module shared by `win/`, `lin/`, and `mac/`
wrappers. It owns typed form state, configuration import/export, argv-list
construction, child PID/run ID, bounded JSONL parser, progress reducer, cancel,
resume, and result reveal. Use `subprocess` argument arrays with `shell=False`.
An architecture test must fail if this module imports `src.worldgen`, model
backends, or pipeline step implementations.

**P8.12 GUI:** first record a Wine spike in `tmp/evidence/`. Select the smallest
toolkit that passes native Windows and Wine. Keep widgets behind an adapter; the
core must be testable without a display. Implement only configuration, start,
progress, cancel, resume, failure detail, and reveal-output actions.

**P8.WG4:** generate launcher world controls from `WorldSpec` metadata or one
shared mapping. Include all controls or configuration-file passthrough; one
continent is default, not hard-coded. Assert GUI effective configuration equals
CLI effective configuration byte-for-byte after canonicalization.
Presets expand before semantic hashing; the frozen effective spec stores explicit
values rather than an unresolved preset label.

**P8.13:** update the three packaging directories to contain code/specifications
only; all work/dist/packages go under `tmp/`. Test clean install, spaces and
Unicode paths, absent/corrupt models, cancel, process crash, resume, accepted
result, Linux/macOS/Windows, and Wine. Never bundle `ai_models` accidentally.

### P9.1–P9.2 implementation cards — Reliable verification gates

**P9.1:** register strict markers and create explicit commands/scripts for:
static/unit, fake integration, v2 cross-platform, security, determinism,
provisioned desktop models, native packaging, physical devices, and release
candidate. Model discovery must not cause the default suite to load a GGUF.
Locally missing provisioned assets may skip only in the local gate; their owning
release gate converts missing assets to failure. Each command emits JSON summary
under `tmp/evidence/` and propagates nonzero/skipped-required status.
Include a reproducible Docker image build and network-controlled containerized
fake-backed dry run. Container evidence supplements rather than replaces native
desktop/mobile gates. Add stable prompt-domain diagnostics for missing profiles,
render/budget failures, and schema-invalid model output instead of falling back to
an internal-error code.
Enable pytest strict-marker enforcement and a bounded default timeout. Separate
`unit`, `contract`, `integration`, `real_model`, `determinism`, `security`,
`performance`, and `release` ownership so a marker expression always selects a
meaningful nonempty gate. Native suites consume the same fixture bytes/catalog,
not hand-copied variants.
Choose and enforce one supported Python floor across `requires-python`, Ruff,
mypy, CI, packaging, and syntax; the current Python 3.9 versus Ruff 3.11 policy
drift must not remain implicit.

**P9.2:** run the non-model gate repeatedly with randomized order and isolated
temporary roots. Remove shared mutable globals, repository writes, network access,
locale/timezone dependence, leaked processes, and test-order dependence. Split
the suite into memory-safe sequential groups if aggregate cleanup is imperfect;
fix leaks rather than increasing the 10 GiB ceiling.
Require at least three identical ordinary runs and three randomized-order runs.
Record slowest tests, quarantine no flake silently, shrink broad mypy exemptions
file-by-file, and add domain/critical-branch coverage without slowing the default
gate through unconditional coverage collection.

### P9.5 and P9.15 implementation cards — Determinism and generated docs

**P9.5:** build a matrix runner varying worker count, output path including
Unicode/spaces, hash seed, collection order perturbation, resume point, and
supported platform. Compare canonical internal members and domain artifacts, not
ZIP bytes. On mismatch emit the first artifact/path/JSON-pointer/byte offset and
both producer fingerprints.
Define the reproducibility profile recorded in producer fingerprints: engine and
native-runtime revision, model/quantization hash, context length, thread count,
batch size, sampling settings, seed-plan version, prompt/schema hashes, and
algorithm versions. Add a verification command that accepts an effective spec and
expected world/package `content_hash`, regenerates or reopens internal members,
and reports the first mismatch without ever hashing ZIP bytes.

**P9.15:** extend `scripts/generate_interface_docs.py` or split generators for
CLI help, target/runtime pipeline, configuration fields, schema coverage, archive
layout, diagnostics, and scenario catalogs. `--check` must produce no writes and
fail on exact drift. Generated documents require a header naming their source and
whether they are target authority or current evidence.
Generate archive paths from acceptance/schema constants and test them against the
documented layout. Generate a feature-status table limited to `implemented`,
`partial`, or `planned`; current claims must link to tests or retained evidence.

### P9.WG0–P9.WG6 implementation cards — Worldgen closure

**P9.WG0:** parse `generation.md` headings and manually enumerate every MUST,
required domain, equation/vector, invariant, stage output, failure semantic, and
retention rule into a checked trace table. Link each to concrete source symbols
and tests. “Module exists” is not coverage. Implement missing behavior or record
an explicit product decision before marking a row complete.
The matrix must resolve underspecified economic and capacity details: a bounded
integer-only scarcity/distance price rule, an explicit or derived site-count
budget used by memory/disk preflight, and the exact relationship between sites
and mandatory local-map cost.

**P9.WG1:** use `rg` to find every legacy symbol/import/config/schema. Migrate
production callers first, then tests, then delete legacy modules and schema.
Architecture tests must prohibit reintroduction. Delete the two historical
worldgen documents only after P9.WG0 proves their unique requirements are carried
by `generation.md`, code/tests, or this roadmap.

**P9.WG2:** add small/default/large property profiles, mutation testing of every
validator, malformed chunk/index fuzzing, fault injection at every atomic commit,
resume/cancellation, and per-stage time/RSS/disk measurements. Fixed seeds are
regression tests; generated seeds are property evidence and must print a replay
command on failure.
Freeze a named small conformance profile with explicit dimensions, continent and
civilization counts, history duration, site/local-map limits, artifact inventory,
golden vectors, and content hash. It is the routine CI/cross-platform end-to-end
profile and never substitutes for the default 500-year release evidence.
Profile the in-memory kernel: use flat integer arrays/chunks for dense cell
domains and dataclasses for entities, avoid per-cell object graphs, and route all
committed division through one checked `round_div` policy with golden boundary
vectors.

**P9.WG3:** run fixed-point domains on all supported desktop Python/toolchain
profiles with worker/path/order/resume variations. Compare canonical domain bytes
and retain a first-difference report. Model-produced prose is outside this pure
procedural equality proof.

**P9.WG4:** run the default one-continent, 500-year specification under the memory
watchdog. Retain effective spec, seed plan, registry/algorithm hashes, per-stage
duration and peak RSS, artifact sizes, event/snapshot counts, replay/index results,
and validation report. Resource-blocked is not evidence.

**P9.WG5:** feed that exact world through Bible, reconciliation, story/graph,
every-site local maps, every-node media, GM index, v2 packaging, acceptance, and
physical Android/iOS import/retrieval. No smaller replacement world satisfies it.

**P9.WG6:** independently enumerate source domain records and accepted package
inventory, including facts unused by Bible/story/graph. Compare IDs and content
hashes, reconstruct every index, replay history, and prove zero required records
were omitted or summarized in place of full data.

### P9.3–P9.4 implementation cards — Real-model evidence

Preflight exact model registry entries, hashes, licenses, free disk, and memory.
Run models sequentially under the watchdog. P9.3 must generate and accept a full
v2 package while retaining effective config, prompt/schema/model/code hashes,
model lifecycle, redacted events, timing/RSS, and internal inventory/content
hashes. P9.4 interrupts at named committed boundaries, resumes through the public
application service, then compares every canonical internal member with the
uninterrupted run. Never compare ZIP bytes.
Maintain a checked overnight runbook that performs preflight, image/container or
native environment verification, memory-capped launch, structured logs under
`tmp/`, expected output inventory, symptom-to-diagnostic lookup, resume, internal
verification, and next-day human QA. Commands must be generated/checked against
current CLI help rather than copied from temporary notes.

### P9.6–P9.13 implementation cards — Release quality

- **P9.6:** generate a shared hostile corpus rather than platform-specific cases.
  Cover raw ZIP-name attacks, duplicates/case collisions/links, declared-size and
  compression amplification, JSON depth/count/numeric range, broken provenance,
  corrupt chunks/indexes/history/media, and embedded executable content. Require
  stable parity and no partial publication.
- **P9.7:** freeze a device matrix first; measure download, first chunk, tokens/s,
  peak RAM/storage, battery/thermal, cancel, background, unload/reuse, large import,
  and offline restart on physical devices. Record OS/device/model versions.
  Derive minimum supported Android/iOS versions from build and device evidence;
  do not preserve provisional Android 13/iOS 16 labels without proof.
- **P9.8:** derive named budgets from P9.7 percentiles with explicit regression
  tolerance and failure code. Do not invent one universal device budget or package
  size ceiling.
- **P9.9:** run complete post-download flows behind a network deny rule and capture
  DNS/socket attempts. Audit manifests, permissions, dependencies, background
  tasks, and native libraries. Any unexplained connection blocks release.
- **P9.10:** on the actual submission date re-open primary Apple/Google policies;
  complete privacy, AI/mature content, local flag/export, deletion, support, and
  questionnaire records. Do not rely on the older links alone.
- **P9.11:** bind every distributed/downloaded model and native dependency to
  immutable source, revision, bytes, SHA-256, terms, notices, intended use, and
  review date. Generate the third-party notice bundle and verify UI attribution.
  Generate a compatibility matrix by registry ID with capability, prompt/output
  profile, quantization, measured RAM, validated roles/platforms, and the last
  successful evidence record.
- **P9.13:** use a written rubric and several generated packages. Review physical
  plausibility, causal history, reconciliation, branching, complete media, GM
  truth/spoilers, prohibited content, accessibility, and mature-tone quality.
  Record failures and rerun after fixes; one attractive sample is insufficient.
  Automated acceptance and determinism run before human review. Use two
  independent reviewers and a versioned scorecard; review every node for a small
  profile and stratified opening/middle/branch-heavy/ending samples for release
  worlds. Generate a local QA bundle containing maps/region crops, artifact hash
  table, Bible/story extracts, graph visualization, image/thumbnail contact sheet,
  playable MIDI metadata, validator results, and reviewer disagreement/final
  disposition. Also cover dark/light appearance, MIDI transition/crossfade,
  interruption/resume, large text, reduced motion, and screen-reader focus.

### P9.12, P9.14, and P9.16 implementation cards — Final distribution

**P9.12:** build signed/notarized/store-ready artifacts from clean checkouts with
pinned toolchains. Exercise clean install, upgrade, uninstall, local-data choice,
missing model, offline restart, paths with spaces/Unicode, and platform/Wine smoke
tests. Keep build output under `tmp/`; retain final release artifacts/evidence in
the approved release location only.
Build and smoke-test the documented Docker image with a fake-backed dry run and
explicit output mount under `tmp/`. Docker remains an auxiliary Forge path, not a
replacement for Windows/Wine/Linux/macOS packages.

**P9.14:** audit every present-tense claim in docs against retained evidence;
check schema/prose/native parity, generated-doc drift, roadmap dependencies,
compliance dates, and release commands. A target statement need not be implemented,
but it must not be worded as current evidence.

**P9.16:** use import/reference scans and coverage to remove temporary adapters,
v1 artifacts, dead scripts, copied/generated source assets, stale ignores, and
obsolete docs. Do not delete a compatibility path until its production callers
and authoritative requirements are accounted for. Run the complete release gate
after cleanup; cleanup that breaks evidence is incomplete.
Rename `src/models/` pipeline-step implementations to an unambiguous `src/steps/`
boundary after imports are typed and covered; downloaded model descriptors remain
separate. Remove dead context/spec fallbacks once all callers pass `RunSpec`
explicitly, and remove obsolete `ctx.state` configuration keys after compatibility
tests migrate to typed accessors.

## Release-candidate command gate

All commands must exist, be non-interactive in CI, emit machine-readable
summaries, and return nonzero for failed or skipped required work.

```bash
./scripts/verify_release.sh --release-candidate
.venv/bin/mypy src scripts tests
.venv/bin/pytest -q -m "not integration"
.venv/bin/pytest -q -m integration --run-models
.venv/bin/pytest -q -m determinism
.venv/bin/pytest -q -m security
./scripts/build_all_desktop.sh
./scripts/test_wine.sh tmp/packages/storyteller-launcher.exe
./droid/gradlew -p droid testDebugUnitTest connectedDebugAndroidTest bundleRelease
xcodebuild -scheme StoryTeller -project ios/StoryTeller.xcodeproj \
  -derivedDataPath tmp/DerivedData test archive
.venv/bin/python scripts/verify_cross_platform_scenarios.py --release
.venv/bin/python scripts/check_docs_drift.py
```

## Definition of releasable

- [ ] Every remaining implementation item above is complete with retained evidence.
- [ ] One production v2 package from a complete real-model run passes acceptance
  and imports on physical Android and iOS.
- [ ] Interrupted and uninterrupted runs have identical canonical internal files.
- [ ] Every node has a valid full image, thumbnail, authoritative score, and
  positive-duration derived MIDI.
- [ ] Model download, lifecycle, chunks, persistence, offline behavior, RAM,
  battery, and thermal budgets pass on the supported device matrix.
- [ ] Windows/Wine/Linux/macOS Forge and launcher artifacts pass clean-install smoke tests.
- [ ] Security, privacy, licensing, accessibility, mature-content, store, and
  human-review records are dated and approved.
- [ ] The source tree contains no legacy generation path or competing roadmap.

Release remains blocked by any unchecked item unless the product target is
explicitly changed in the authoritative design documents.
