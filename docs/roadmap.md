# StoryTeller Remaining Roadmap

## Status and authority

This is the sole implementation roadmap. It records only work that remains after
the completed contract, world generation, simulation, Bible, narrative/media,
`.story` v2, native Player, model-registry, model-download, and native model
lifecycle rewrites. Completed work is specified by the other target documents
and verified by source/tests; it is intentionally not repeated here.

The next executable item is **P8.C0**, followed by **P8.C1** and **P8.C2**; **P8.WG1** and
**P8.6** may proceed where they do not depend on incomplete schema detail. Work
should follow dependency order. A
checkbox may be marked complete only when its implementation, automated tests,
and named evidence all exist. Source scaffolding or mock-only success is not
completion where an item explicitly requires native, packaged, real-model, Wine,
physical-device, store, or human evidence.

## Delivery sequence

```text
P8.C0 production wiring -> P8.C1 schemas -> P8.C2 validator parity

P8.6 chunks -> P8.7 history -> P8.8 UI -> P8.9 security

P8.10 launcher contract -> P8.11 launcher core -> P8.12 GUI -> P8.13 packaging

P8.WG1 -> P8.WG2 -> P8.WG3
P8.WG4 depends on the launcher core/GUI

Phase 8 complete -> Phase 9 gates/evidence -> release decision
```

Independent branches may be developed in parallel, but heavyweight verification
must run sequentially under `scripts/run_with_memory_cap.py`: soft stop at 9 GB,
hard ceiling 10 GB across the complete process tree.

## Implemented baseline and evidence boundary

The source contains substantial Phase 1–7 rewrite foundations: typed run/world contracts,
fixed-point procedural artifacts and simulation, Bible reconciliation,
narrative/media/GM-index generation, frozen v2 packaging and acceptance, shared
Python/Android/iOS fixtures, native package/save/model-download/model-lifecycle
implementations, deterministic retrieval, and the pre-prompt reveal gate.

The compatibility `forge generate` path is still narrative-first and does not
yet execute the authoritative procedural-world/Bible/reconciliation/narrative-v2
chain as one application service; P8.C0 closes that integration gap. That baseline
is not a release claim. Several v2 domain schemas currently assert
only a top-level object, and manifest nested structures are shallow; the frozen
prose contract therefore still has the executable-conformance debt P8.C1–P8.C2.
In addition, the baseline does not yet prove a
complete real-model v2 run, physical-device behavior, full simulator reliability
under the 10 GiB host ceiling, default 500-year resource behavior, hostile-corpus
breadth, store compliance, accessibility, Wine/native launcher packaging, or
absence of every legacy worldgen path. The current default Python collection also
discovers provisioned real-model smoke tests; P9.1–P9.2 must isolate that gate.

## Phase 8 prerequisite — Close executable v2 contract debt

- [ ] **P8.C0 — Make the production service procedural-first (XL):** Make
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
- [ ] **P8.C1 — Complete every frozen v2 schema (XL):** Express every required
  field, type, enum, unit/range, ID/hash grammar, ordering/uniqueness constraint,
  nested producer/provenance record, world domain, local map, history change,
  narrative record, media record, and cross-file reference shape from
  `package-v2.md`, `generation.md`, and `api.md`. Use `additionalProperties:
  false` at closed records and reusable `$defs`; a schema that merely accepts an
  arbitrary object is forbidden. Generate one valid and targeted invalid fixture
  per rule and add a prose-to-schema trace matrix.
- [ ] **P8.C2 — Full three-validator parity (XL):** Make Python, Android, and iOS
  enforce the complete frozen schema and acceptance order, including embedded
  trusted-schema identity, internal member hashes (never ZIP bytes), provenance
  DAG, complete domains/history/local maps/media, reference rebuilding, limits,
  unknown features, and stable diagnostic codes. Run the same hostile/valid
  catalog and require exact outcomes. **Depends on:** P8.C0, P8.C1.

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
  tests/test_integration_pipeline.py
.venv/bin/python scripts/generate_interface_docs.py --check
```

**Do not:** add optional narrative/procedural/hybrid modes; preserve a
narrative-first fallback; feed a lossy legacy snapshot instead of retaining full
world artifacts; or renumber checkpoint phases without migration/invalidation
tests.

### P8.C1 implementation card — Complete v2 schemas

**Read first:** `package-v2.md`, `generation.md` data model and retention
sections, `api.md` package contracts, `decisions.md` D020–D029, and every file in
`schemas/v2/`.

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
