# StoryTeller Remaining Roadmap

## Purpose and authority

This file contains only unfinished delivery work. Completed implementation is
defined by the authoritative contracts linked from `docs/index.md` and guarded
by source tests; it is deliberately not preserved here as a historical diary.

The active item is **P8.WG1**. The procedural-first pipeline (P8.C0), worldgen
P8.C05A–H, closed v2 schemas (P8.C1), three-validator parity (P8.C2), and
procedural scoring (P8.WG2) are implemented. Treat them as regression gates,
not future work. Reopen one only after an explicit contract change or a
reproducible defect.

Work in dependency order:

```text
P8.WG1 -> P8.WG3
P8.6 -> P8.7 -> P8.8 -> P8.9
P8.10 -> P8.11 -> P8.12 -> P8.WG4 -> P8.13
Phase 8 gate -> Phase 9 evidence -> release
```

## Phase 8A — Reveal-safe local Game Master

### P8.WG1 — Lazy complete-world lookup

- [ ] Add a bounded `KnowledgeSource` interface: IDs/query tokens in, typed
  excerpts out, with bytes-read, chunks-opened, and records-decoded counters.
- [ ] Use published world, history, and local-map indexes without constructing a
  full `WorldView` or parsing the complete `gm_index` on the GM query path.
- [ ] Store locators and bounded normalized text in lookup indexes, not complete
  authority records.
- [ ] Implement equivalent package-backed readers in Python, Kotlin, and Swift.
- [ ] Apply the reveal gate before prompt construction in every backend. In
  particular, remove the unfiltered `relevant_lore` path in `gm_backend.py`.
- [ ] Align malformed-index behavior across all three consumers.
- [ ] Prove catalog parity, bounded I/O, hostile-ID handling, Unicode behavior,
  excerpt limits, and that unopened-chunk sentinels never enter candidates.

### P8.WG1 prerequisite — Canonical local-map archive encoding

- [ ] Reconcile the current content-addressed local-map JSON chunks with D021
  and `package-v2.md`, which specify `world/local/<site>/chunks/*.bin`.
- [ ] Freeze one canonical representation, update producer/schema/validators on
  all platforms, add corruption vectors, and remove the obsolete form.

### P8.WG3 — Procedural spoiler proof

- [ ] Put unique sentinels in unrevealed global facts, history, beliefs, local
  maps, opportunities, identifiers, and source identifiers.
- [ ] Assert absence from candidates, ranking diagnostics, prompts, errors,
  logs, and saved history before reveal, and presence after the required visit.
- [ ] Run the same sentinel catalog through Python, Android, and iOS.

### P8.6 — Real native semantic chunk stream

- [ ] Replace JNI/Swift whole-string generation and UI word slicing with ordered
  `started`, nonempty `text`, and exactly one terminal event.
- [ ] Support cancellation during prompt decoding and token generation without
  emitting post-terminal chunks.
- [ ] Freeze queue capacity, backpressure, chunk size, and error semantics in
  `docs/api.md`; add ordering, cancellation, and slow-consumer tests.

### P8.7 — Transactional conversation history

- [ ] Persist a user/assistant exchange atomically only after successful stream
  completion; preserve the previous ledger after failure or cancellation.
- [ ] Restore history after restart and enforce schema, size, and reveal limits.
- [ ] Prove equivalent behavior in both native clients.

### P8.8 — Responsive GM experience

- [ ] Render chunks incrementally without blocking the UI thread.
- [ ] Provide visible loading, cancellation, retry, and actionable failure states.
- [ ] Verify rotation/background/restart behavior and accessibility.

### P8.9 — End-to-end isolation

- [ ] Exercise retrieval, streaming, cancellation, persistence, and reveal
  sentinels together on Android and iOS.
- [ ] Prove no telemetry or unintended network access after package/model setup.

## Phase 8B — Thin desktop launcher

### P8.10 — Freeze the Forge process contract

- [ ] Make live `forge generate`/`resume` accept the launcher’s versioned JSONL
  events and final-result options, or remove unsupported argv from the launcher.
- [ ] Change `GenerationRequest.resume` to the documented default and bind
  generate/resume explicitly.
- [ ] Align the CLI and generated world-control names from one source table.
- [ ] Implement documented exit codes 2/3/4/5/130 instead of generic exit 1.
- [ ] Treat any exhausted worldgen stage, rejected proposal, or nonempty
  `GenerationResult.errors` as failure: emit no completion/final-result record,
  print no successful “Generation Complete” banner, and return the appropriate
  nonzero process code from both generate and resume.
- [ ] Remove `forge verify`'s unconditional Package Acceptance success block;
  print acceptance and media claims only from the real v2 validation result.
- [ ] Define malformed/unknown/partial event handling and cancellation semantics.

### P8.11 — Toolkit-independent launcher core

- [ ] Validate requests, construct safe argv, spawn Forge, parse JSONL, expose
  progress, and support cancel/resume without importing pipeline internals.
- [ ] Add injection, partial-line, unknown-event, subprocess, and resume tests.

### P8.12 — Minimal GUI shell

- [ ] Make the GUI call `ForgeProcess`; remove `_simulate_progress` as a success
  path and prohibit imports from worldgen/model internals.
- [ ] Default production construction to subprocess callbacks that invoke
  `ForgeProcess.start()`; retain direct/simulated callbacks only as explicit
  test and Wine-spike dependencies.
- [ ] Provide validation, progress, cancel/resume, output selection, logs, and
  accessible error reporting.
- [ ] Complete a packaged Wine spike before freezing the toolkit.

### P8.WG4 — Complete world controls

- [ ] Expose every supported `WorldSpec` field from the shared binding table.
- [ ] Preserve typed defaults/ranges and prove CLI/GUI/request parity.

### P8.13 — Desktop distribution matrix

- [ ] Package and clean-install smoke-test Forge plus launcher on supported
  macOS, Linux, Windows, and Wine targets.
- [ ] Verify model discovery, spaces/Unicode paths, resume, cancellation, and
  atomic `.story` publication.

## Phase 8 completion gate

- [ ] Both Players install, load, cancel, unload, and reuse the pinned GM model.
- [ ] Retrieval/reveal results match across Python, Android, and iOS.
- [ ] Native responses genuinely stream and completed history survives restart.
- [ ] Spoiler sentinels remain absent from every pre-reveal boundary.
- [ ] The packaged launcher drives real Forge on native desktops and Wine.
- [ ] Functional suites pass sequentially under the aggregate memory policy.

## Phase 9 — Hardening and release evidence

### Verification infrastructure

- [ ] **P9.1:** Separate static/unit, integration, real-model, determinism,
  security, native-device, Wine, and release-candidate gates. Required skips fail.
- [ ] **P9.2:** Make the default deterministic suite green and isolate test state;
  remove the shared `tmp/pytest` collision hazard. Add an early-failure result
  regression so `_build_result` cannot read uninitialized image/MIDI coverage
  locals when packaging outputs are absent or malformed.
- [ ] **P9.5:** Prove clean-run and resume identity across supported process modes.
  Move real per-node image/music production onto bounded scheduling with atomic
  node checkpoints, deterministic output ordering, retry/quarantine evidence,
  and interruption/resume equivalence; preserve the structured-score contract.
- [ ] **P9.15:** Generate contract-facing docs in `--check` mode and correct
  `docs/index.md`, which still describes the delivered C1/C2 work as debt. Drive
  the CLI reference from generated help and reconcile documented Music/Images
  ordering with `PipelinePlan.production_v2()`.

### Real-model and procedural evidence

- [ ] **P9.WG0:** Audit all requirements in `generation.md`, `bible.md`, and
  `package-v2.md` to executable tests or explicitly approved human evidence.
  Freeze a least-authority Bible-enrichment prompt test: its serialized authority
  input contains exactly title, present year, and existing interpretations, has
  a measured token ceiling, and exposes no stable-ID inventory to the model.
- [ ] **P9.3:** Retain one complete real-model v2 run with config, prompt/model
  identities, timings, acceptance output, and package digest. Include an
  end-to-end malformed/truncated LLM response that proves JSON recovery is
  exercised by the production pipeline, not only by its parser unit tests.
- [ ] **P9.4:** Interrupt at defined boundaries and prove resumed canonical
  members equal the uninterrupted run.
- [ ] **P9.WG1:** Remove remaining obsolete worldgen/snapshot authority paths.
- [ ] **P9.WG2:** Add property, mutation, fuzz, and conservation suites; remove
  raw event-order dependencies and unsafe projection budget arithmetic. Preserve
  the real-run seed that exhausted simulation retries as a regression vector;
  prove exploration proposal generation cannot emit an invalid route or a
  duplicate civilization/destination pair accepted earlier in the ledger. Only
  then decompose the oversized simulation scheduler into typed proposal slices,
  guarded by before/after canonical-byte golden vectors.
- [ ] **P9.WG3:** Prove fixed-point and canonical-byte parity across platforms.
- [ ] **P9.WG4:** Retain bounded default 500-year generation evidence.
- [ ] **P9.WG5:** Trace authoritative world facts through Bible, story, GM index,
  package validation, and both mobile clients. Package actual cartographic
  world/region renders from `worldgen.maps` instead of seeded placeholder noise,
  retaining source-artifact dependencies and map-content assertions.
- [ ] **P9.WG6:** Prove full required-data retention and reconstruction. Inspect
  the published causal ledger directly and prove the bounded `history_summary`
  projection cannot be mistaken for, or replace, the D005 authoritative ledger.

### Open correctness and provenance decisions

- [ ] Freeze optional critic failure semantics; current fail-open behavior must
  be either contracted and tested or replaced. The validator backend is
  registered with `ModelManager` but no production-plan segment loads or invokes
  it: either wire an explicit, evidenced validator stage or stop downloading and
  claiming provenance for a model that has no effect. Any deterministic
  validator integration must validate actual v2 documents with typed Bible
  context, not the current stage `{path, root}` envelope.
- [ ] Freeze one production music-generator contract. `AbcMusicGenerator`
  currently returns fixed placeholder ABC while v2 authority requires a
  `StructuredScore` with derived SMF Type 1: adapt it behind that contract with
  deterministic provenance and real model input, or remove the unused backend.
- [ ] Implement prompt identity `{id, version, sha256}` through a registry and
  bind it into checkpoints/package provenance.
- [ ] Make graph chronology mandatory at construction; remove the silent
  `world_year = 0` default.
- [ ] Canonically order exploration events before every derived computation.
- [ ] Replace raw token arithmetic with a typed, saturating budget helper.
- [ ] Close `MagicClaim.epistemic_status` over an explicit enum and reject every
  unknown value before status-specific reconciliation; cover objective, belief,
  uncertain, and metaphorical states.
- [ ] Replace duplicated 200-event Bible projection literals with one named,
  tested contract constant.

### Security, privacy, compliance, and performance

- [ ] **P9.6:** Run adversarial package/import corpora for traversal, bombs,
  duplicates, malformed encodings, hash confusion, and resource exhaustion.
  Remove force-casts/force-unwraps from the iOS package validator's hostile-input
  path and add shared type-confusion fixtures proving rejection rather than a
  process crash. Route the iOS command-line and Xcode scenario harnesses through
  one reusable fixture runner so their behavior cannot drift.
- [ ] **P9.7:** Measure model lifecycle, GM latency, memory, battery, and thermals
  on the supported physical-device matrix. For desktop Forge, record real
  process-tree RSS for text generation at the configured 16,384-token context
  and for image generation separately.
- [ ] **P9.8:** Freeze versioned performance budgets and regression thresholds.
  Replace static `TEXT_MODEL_RAM_MB`/`IMAGE_MODEL_RAM_MB` bookkeeping with
  estimates derived from model metadata and runtime configuration, checked
  against observed peak RSS and the 11/12 GiB process-tree guard.
- [ ] **P9.9:** Prove offline/privacy behavior with dependency and traffic audits.
- [ ] **P9.10:** Complete dated privacy, support, export, deletion, accessibility,
  mature-content, and store-compliance evidence.
- [ ] **P9.11:** Freeze model and dependency licenses with redistributed texts.
- [ ] **P9.13:** Complete human plausibility, spoiler, accessibility, and product
  review with recorded acceptance criteria.

### Packaging and final release

- [ ] **P9.12:** Produce signed/notarized desktop and store-ready mobile artifacts.
- [ ] **P9.14:** Audit every release claim against current retained evidence.
- [ ] **P9.16:** Remove temporary adapters, stale fixtures, duplicate paths, and
  release-only scaffolding after all consumers migrate. Migrate every live
  `PackageAcceptance` consumer to the frozen v2 validator before deleting the
  legacy class; remove orphaned `V2CheckpointStore` only after confirming no
  retained resume evidence depends on its semantics. Either wire the documented
  error taxonomy at real raise sites or delete unused decorative error classes.

## Non-binding investigations

These are not release commitments unless promoted by an explicit product
decision:

- Savagery/evilness-style ecology and extraordinary-region pressure.
- Exhaustive genealogy beyond story- and quest-relevant lineage.
- Simulated gods or mythic actors beyond current belief/cult systems.
- Colony-game mechanics beyond the authored adventure/GM product.
- Revisit the pinned reference implementations only when a live gap needs them:
  `Dozed12/df-style-worldgen`, `kevshakes/dwarf-fortress-simulation`, and
  `Moneyl/World-Generator`; record commit hashes and licenses before reuse.

## Working rules

- Preserve v2-only packaging, content-addressed member identity, complete
  per-node media, reveal-before-prompt, full authoritative retention, and
  every-site local-map requirements.
- Do not hash ZIP container bytes or add `save/` to immutable packages.
- Do not mark mock, scaffold, file presence, or generated fixture count as exit
  evidence when a card requires native, packaged, real-model, Wine, device, or
  human proof.
- Prefer focused tests while iterating. Run heavyweight desktop Forge commands
  sequentially through `scripts/run_with_memory_cap.py`, with a soft stop at 11 GiB
  and hard ceiling 12 GiB. This host policy does not alter phone-side budgets.
- Keep one global heavyweight-test slot; never stack independent memory caps.
- Keep generated output, native caches, and local runs under `tmp/`.

## Release-candidate gate

- [ ] All unfinished implementation items above have retained evidence.
- [ ] A complete real-model package passes acceptance and imports on physical
  Android and iOS devices.
- [ ] Interrupted and uninterrupted runs have identical canonical members.
- [ ] Every node has valid full image, thumbnail, score, and positive-duration MIDI.
- [ ] Device, desktop, Wine, security, privacy, license, store, accessibility,
  performance, and human-review gates pass.
- [ ] No legacy generation path or competing roadmap remains.

Release remains blocked by any unchecked item unless the authoritative product
contracts explicitly change.
