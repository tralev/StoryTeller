# StoryTeller Remaining Roadmap

## Purpose and authority

This file contains only unfinished delivery work. Completed implementation is
defined by the authoritative contracts linked from `docs/index.md` and guarded
by source tests; it is deliberately not preserved here as a historical diary.

Delivery-log entries added while executing this roadmap are retained in place:
completed steps are marked `[x]` and followed by the recommended next step.

The active item is **P8.8 — native lifecycle/accessibility evidence**; the first
combined P8.9 isolation slice has also started. P8.WG1, its canonical local-map
archive prerequisite, P8.WG3, P8.6, and P8.7 were completed on 2026-08-31; their
retained delivery logs follow below.
The procedural-first pipeline (P8.C0), worldgen
P8.C05A–H, closed v2 schemas (P8.C1), three-validator parity (P8.C2), and
procedural scoring (P8.WG2) are implemented. Treat them as regression gates,
not future work. Reopen one only after an explicit contract change or a
reproducible defect.

Work in dependency order:

```text
P8.WG1 -> P8.WG1 local-map prerequisite -> P8.WG3
P8.6 -> P8.7 -> P8.8 -> P8.9
P8.10 -> P8.11 -> P8.12 -> P8.WG4 -> P8.13
Phase 8 gate -> Phase 9 evidence -> release
```

## Phase 8A — Reveal-safe local Game Master

### P8.WG1 — Lazy complete-world lookup

- [x] Add a bounded `KnowledgeSource` interface: IDs/query tokens in, typed
  excerpts out, with bytes-read, chunks-opened, and records-decoded counters.
  - [x] **2026-08-31 — port frozen:** added the runtime-checkable
    `KnowledgeSource` contract with ID/token inputs, reveal state, independent
    record/byte bounds, typed excerpts, and per-read physical I/O counters.
  - **Suggested next:** implement the Python package-backed catalog/index reader
    behind this port and connect retrieval without constructing `WorldView`.
  - [x] **2026-08-31 — Python content-addressed reader:** implemented a bounded
    directory/package-member reader over locator-only indexes and independently
    hashed excerpt chunks. Reveal eligibility is decided before opening a chunk;
    traversal, duplicate IDs, hash/identity/reveal drift, zero limits, and exact
    bytes/chunks/records counters are enforced.
  - **Suggested next:** publish this locator/chunk representation from the v2 GM
    index stage and teach `retrieve_knowledge` to consume `KnowledgeSource`.
  - [x] **2026-08-31 — retrieval adapter:** added a source-driven retrieval
    entry point with separate source record/byte budgets, unchanged deterministic
    ranking and prompt budgets, and returned physical I/O evidence.
  - **Suggested next:** make the producer publish the locator catalog and excerpt
    chunks alongside `gm_index.json`, then package and validate those members.
  - [x] **2026-08-31 — producer publication:** the GM-index stage now emits one
    canonical content-addressed excerpt chunk per entry plus a locator-only token
    index; v2 packaging retains those members and their provenance dependencies
    while preserving `gm_index.json` for validator/native migration.
  - **Suggested next:** validate locator-to-chunk identity and complete entry
    parity during package acceptance, then open the packaged directory through
    `DirectoryKnowledgeSource` in a consumer-equivalent test.
  - [x] **2026-08-31 — Python migration validation:** when bounded members are
    present, v2 validation enforces exact sorted one-to-one locator coverage,
    safe content-derived paths, reveal parity, locator size/hash identity, and
    semantic equality with each legacy GM entry. Pre-slice packages remain valid
    until Kotlin/Swift readers and shared fixtures make the members mandatory.
  - **Suggested next:** add shared corrupt-index/chunk scenarios and implement
    the equivalent checks/readers in Kotlin and Swift before switching either
    mobile GM screen away from the legacy whole-index parser.
  - [x] **2026-08-31 — consumer-equivalent Python proof:** the integrated v2
    package test extracts only the packaged bounded-reader namespace, opens it
    through `DirectoryKnowledgeSource`, resolves a chosen ID, and proves exactly
    one chunk and one record were touched.
  - **Suggested next:** implement the same locator/chunk source contract in
    Kotlin, including bounds/counters and reveal-before-open tests; Swift follows
    against the identical packaged representation.
  - [x] **2026-08-31 — Kotlin bounded reader:** Android now has the same
    content-addressed locator reader, independent record/byte limits, physical
    counters, confinement/hash/identity checks, and reveal-before-open sentinel
    test as Python.
  - **Suggested next:** implement and verify the equivalent Swift reader, then
    move both repositories/GM screens from eager `GmIndex` parsing to their
    bounded sources in separate platform slices.
  - [x] **2026-08-31 — Swift bounded reader:** iOS now mirrors the Python/Kotlin
    locator source, physical counters, record/byte limits, confinement and
    content identity checks, and reveal-before-open sentinel contract.
  - **Suggested next:** expose the knowledge namespace from `StoryPackage`, wire
    `StoryRepository` retrieval through the bounded reader on Android and iOS,
    and retain eager `GmIndex` only as a pre-slice package compatibility path.
  - [x] **2026-08-31 — native query-path migration:** both `StoryPackage` models
    expose the immutable knowledge namespace and both repositories now answer GM
    lookup through bounded sources when available, with eager `GmIndex` retained
    only for accepted pre-slice v2 packages. Excerpts cap normalized text at 2048
    UTF-8 bytes before publication.
  - **Suggested next:** add repository-level native tests proving the GM screens
    select bounded lookup, expose read counters for diagnostics/tests, and add
    shared corrupt locator/chunk scenarios before making the namespace mandatory.
  - [x] **2026-08-31 — observable native lookup:** Android and iOS repositories
    expose whether bounded lookup was selected and its bytes/chunks/records
    counters while the GM screens continue consuming a plain prompt string.
  - **Suggested next:** add repository-level fixture tests for bounded selection
    and compatibility fallback, then extend the shared v2 scenario catalog with
    missing-index, locator drift, hash drift, and reveal drift cases.
  - [x] **2026-08-31 — native repository selection evidence:** focused Android
    and iOS fixtures now construct accepted-layout story directories, exercise
    repository lookup, and assert the bounded path plus one opened/decoded chunk.
  - **Suggested next:** add explicit pre-slice fallback tests and shared corrupt
    package scenarios; only then make bounded members a mandatory v2 layout gate.
  - [x] **2026-08-31 — compatibility fallback evidence:** native repository
    fixtures without the new namespace prove accepted pre-slice v2 packages use
    eager retrieval explicitly, report no bounded counters, and remain playable.
  - **Suggested next:** regenerate the shared corpus with bounded members and
    corrupt locator/chunk vectors, implement validator parity, then retire this
    fallback only after the frozen feature declaration changes.
  - [x] **2026-08-31 — shared corruption vectors authored:** the corpus producer
    now emits bounded members in its complete package and defines independently
    re-signed reveal-drift, chunk-identity, and locator-coverage failures.
  - **Suggested next:** regenerate the corpus, implement the three new issue
    codes in Kotlin and Swift validation, and run the 3-validator catalog before
    making bounded members mandatory.
  - [x] **2026-08-31 — native migration validation:** Kotlin and Swift now mirror
    Python's optional-during-migration locator order/coverage, reveal parity,
    content size/hash, bounded-text, and semantic-identity checks with the same
    three issue codes.
  - **Suggested next:** run all three validators over the regenerated 76-scenario
    corpus, correct any precedence drift, then make the namespace a required
    layout member simultaneously on all platforms.
- [x] Use published world, history, and local-map indexes without constructing a
  full `WorldView` or parsing the complete `gm_index` on the GM query path.
- [x] Store locators and bounded normalized text in lookup indexes, not complete
  authority records.
- [x] Implement equivalent package-backed readers in Python, Kotlin, and Swift.
- [x] Apply the reveal gate before prompt construction in every backend. In
  particular, remove the unfiltered `relevant_lore` path in `gm_backend.py`.
  - [x] **2026-08-31 — Python backend boundary:** `LlamaCppGameMaster` now
    rechecks typed `reveal_after_nodes` requirements against visited nodes at
    the last possible boundary, rejects malformed lore records, and never adds
    an unrevealed record to its prompt.
  - **Suggested next:** define the bounded `KnowledgeSource` port and its I/O
    counters, then make Python retrieval consume typed excerpts from that port
    instead of accepting a fully materialized iterable.
- [x] Align malformed-index behavior across all three consumers.
  - [x] **2026-08-31 — legacy parser parity:** Kotlin now matches Swift by
    rejecting an entry without an identity without crashing; focused tests on
    both platforms preserve safe empty-result behavior for pre-slice packages.
  - **Suggested next:** add hostile path, duplicate-ID, malformed token/reveal,
    Unicode, and exact byte-bound cases to a shared bounded-source catalog.
  - [x] **2026-08-31 — pre-read budget hardening:** all three readers validate
    canonical locator paths/tokens/reveal lists/hash syntax and compare filesystem
    size with the signed declaration before reading chunk bytes, closing a hostile
    size-declaration budget bypass.
  - **Suggested next:** add the matching hostile locator and exact-bound vectors
    on all platforms, then record measured counter parity in the roadmap.
  - [x] **2026-08-31 — Python hostile/bound vectors:** tests cover traversal,
    unsorted tokens, malformed hashes, duplicate IDs, exact declared-byte reads,
    zero-I/O bounds, corruption, and valid UTF-8 truncation at 2048 bytes.
  - **Suggested next:** mirror these cases in Kotlin and Swift source tests and
    run the focused native suites before assessing the remaining WG1 bullets.
  - [x] **2026-08-31 — native hostile locator vectors:** Android and iOS focused
    tests reject traversal and duplicate identities during catalog construction,
    before any excerpt chunk can be opened; existing tests retain exact counter,
    reveal, corruption, selection, and fallback coverage.
    The Swift contract runner also executes an exact-byte read/counter check and
    a traversal rejection, so this evidence is part of the normal native gate.
  - **Suggested next:** run focused native reader suites, audit all WG1 exit
    bullets against code/evidence, and close only those now fully satisfied.
  - [x] **2026-08-31 — shared-package reader parity:** Python and Android extract
    the identical `complete.story` bounded namespace and resolve the same entry
    with one opened/decoded chunk; the Swift contract runner exercises the same
    representation and counter contract alongside its 76-scenario validator run.
  - **Suggested next:** finish the WG1 evidence audit, close satisfied checklist
    bullets, and carry any genuinely missing cross-platform proof forward without
    weakening the frozen v2 compatibility promise.
- [x] Prove catalog parity, bounded I/O, hostile-ID handling, Unicode behavior,
  excerpt limits, and that unopened-chunk sentinels never enter candidates.
  - [x] **2026-08-31 — P8.WG1 closure audit:** new Forge packages always publish
    bounded locators/chunks; Python, Android, and iOS consume them without
    `WorldView` or whole-`gm_index` query loading; all platforms enforce reveal
    before chunk/prompt access. The 76-package validator catalog, 17-scenario GM
    catalog, shared-package reader checks, hostile vectors, and physical counters
    pass. Compatibility fallback remains only for previously accepted v2 files.
  - **Suggested next:** reconcile D021 local-map `.bin` encoding before WG3 so
    spoiler sentinels exercise the final canonical local-map member format.

### P8.WG1 prerequisite — Canonical local-map archive encoding

- [x] Reconcile the current content-addressed local-map JSON chunks with D021
  and `package-v2.md`, which specify `world/local/<site>/chunks/*.bin`.
  - [x] **2026-08-31 — canonical envelope implementation:** introduced the
    uncompressed `STLCBIN1` local-chunk envelope with canonical family/payload
    metadata, big-endian header length, and SHA-256 over exact encoded bytes.
    Material, natural occupancy, and construction identities now derive from
    that representation.
  - **Suggested next:** migrate Forge persistence, lazy reading, v2 packaging,
    Python acceptance, and the shared fixture producer to `.bin`, then implement
    equivalent native envelope validation before removing `.json` assumptions.
  - [x] **2026-08-31 — Python production migration:** local-map publication,
    bounded lazy reads/storage audits, package construction, package acceptance,
    completeness tests, and fixture generation now use family-qualified `.bin`
    members and decode the canonical envelope before semantic validation.
  - **Suggested next:** regenerate shared packages and update Kotlin/Swift local
    validators to require/decode the same magic, length, canonical header, family,
    byte hash, and semantic payload.
- [x] **2026-08-31 — three-validator binary parity:** the regenerated shared
    corpus contains 77 scenarios, including a re-signed corrupt local binary.
    Python, Kotlin, and Swift require `.bin`, verify `STLCBIN1`, header length and
    canonical JSON, family/payload identity, exact byte hash, and embedded-map
    semantic equality. The Python catalog and focused local suites, Android
    catalog, and Swift contract runner pass.
  - **Suggested next:** begin P8.WG3 with a shared typed sentinel catalog that
    covers every authority surface and proves reveal-before-open on the final
    local-map binary representation.
- [x] Freeze one canonical representation, update producer/schema/validators on
  all platforms, add corruption vectors, and remove the obsolete form.

### P8.WG3 — Procedural spoiler proof

- [x] Put unique sentinels in unrevealed global facts, history, beliefs, local
  maps, opportunities, identifiers, and source identifiers.
  - [x] **2026-08-31 — shared cross-domain catalog:** added deterministic unique
    hidden text, entry-ID, and source-ID sentinels for global facts, history,
    beliefs, local maps, and opportunities. Python consumes the catalog and
    proves every domain absent before reveal and present after its exact visit;
    matching Android/iOS catalog tests exercise the same records and scenarios.
  - **Suggested next:** materialize this catalog through the content-addressed
    `KnowledgeSource` representation (including a canonical local-map `.bin`
    source) and prove unopened hidden chunks contribute zero bytes and records.
  - [x] **2026-08-31 — Python physical-I/O sentinel:** the shared local-map
    sentinel is materialized as an independently hashed bounded excerpt chunk.
    Before its visit, a matching-token read returns zero excerpts, bytes, opened
    chunks, and decoded records; after the visit it opens exactly that one chunk.
  - **Suggested next:** mirror this physical read/counter scenario through the
    Android and iOS bounded readers, then bind the local sentinel source ID to a
    real `STLCBIN1` member and test package-level reveal isolation.
  - [x] **2026-08-31 — native physical-I/O parity:** Android and iOS now consume
    the same shared local-domain record through their content-addressed readers.
    Their uncached focused/contract runs prove zero physical work before reveal
    and exactly one opened and decoded chunk after the required visit.
  - **Suggested next:** create a package-level sentinel fixture whose local-map
    source resolves to a real `STLCBIN1` member, then assert that retrieval never
    reads or serializes that member before reveal on every consumer.
  - [x] **2026-08-31 — authority-boundary clarification:** the GM lookup contract
    intentionally never resolves a knowledge `source_id` into the authoritative
    raw local-map member; doing so would defeat bounded excerpts. `STLCBIN1`
    integrity is independently enforced by all package validators, while the
    reveal sentinel belongs in the local-map excerpt that can reach the prompt.
  - **Suggested next:** finish the native prompt/diagnostic/history matrix and
    close WG3 without adding a forbidden raw-authority read to the GM path.
- [x] Assert absence from candidates, ranking diagnostics, prompts, errors,
  logs, and saved history before reveal, and presence after the required visit.
  - [x] **2026-08-31 — Python runtime boundary matrix:** the shared sentinels are
    exercised through real filtering/ranking/prompt formatting and the atomic
    conversation-history store. Candidate state, diagnostics, prompt, stable
    error text, captured logs, and saved JSON are clean before reveal; entry ID,
    text, and source ID become observable only after the exact required visit.
  - **Suggested next:** implement this same boundary matrix around Android and
    iOS repository prompt construction and conversation-history persistence,
    including clean errors/log output before reveal.
  - [x] **2026-08-31 — native runtime boundary matrix:** Android and iOS run the
    shared catalog through reveal filtering, ranking/debug representation,
    prompt assembly, stable content-free diagnostics, and serialized history.
    iOS additionally round-trips the prompt through its transactional history
    store; Android's host-JVM envelope check avoids the platform `org.json` stub,
    leaving its real store round-trip appropriately in P8.7 device evidence.
  - **Suggested next:** run the complete three-platform WG3 evidence set, audit
    exact before/after behavior, then advance to P8.6 only if every sentinel
    domain and boundary is covered.
- [x] Run the same sentinel catalog through Python, Android, and iOS.
  - [x] **2026-08-31 — P8.WG3 closure audit:** all five authority domains plus
    text, entry-ID, and source-ID sentinels share one repository fixture. Python,
    Android, and iOS prove absence before reveal, exact presence after reveal,
    and reveal-before-open with zero physical I/O. Python's 38 focused tests,
    uncached Android reader/index tests, and the Swift contract runner pass.
  - **Suggested next:** implement P8.6's real native semantic chunk stream;
    preserve this sentinel catalog as a regression gate and extend it through
    streamed text/cancellation once the actual stream replaces UI word slicing.

### P8.6 — Real native semantic chunk stream

- [x] Replace JNI/Swift whole-string generation and UI word slicing with ordered
  `started`, nonempty `text`, and exactly one terminal event.
  - [x] **2026-08-31 — Android native semantic callback:** the JNI token loop now
    emits non-empty valid-UTF-8 substrings directly to Kotlin instead of waiting
    for a whole answer. `LlamaEngine.generateStreaming` preserves those callback
    boundaries, and the GM UI consumes a bounded 64-chunk channel with no word
    slicing or artificial delay. JVM lifecycle tests and the arm64 NDK build pass.
  - **Suggested next:** wrap the Android callback in the frozen typed
    `Started/Text/Completed/Failed/Cancelled` stream (including one-terminal
    enforcement), then implement the equivalent C-to-Swift callback and remove
    iOS word slicing.
  - [x] **2026-08-31 — Android typed stream/UI migration:** `LlamaEngine.stream`
    now wraps native callbacks as ordered `Started`, non-empty `Text`, and one
    terminal event over the frozen 64-chunk backpressure boundary. The GM UI
    collects those events directly and persists only after completion. Focused
    tests prove exact native chunk preservation and one terminal event.
  - **Suggested next:** implement the equivalent C-to-Swift callback and typed
    `AsyncStream`, migrate `GameMasterView` off whole-string word slicing, and
    verify simulator lifecycle plus physical-device cancellation separately.
  - [x] **2026-08-31 — iOS native semantic stream/UI migration:**
    `LlamaBridge.c` now emits valid-UTF-8 token substrings through the checked-in
    Swift bridge; the bridge is a source of both `project.yml` and the app target.
    `LlamaEngine.stream` exposes ordered typed events through a lossless bounded
    channel, and `GameMasterView` renders those chunks directly and commits only
    a completed answer. The arm64 simulator app builds and links, while the Swift
    contract runner proves exact text/sequence ordering.
  - [x] **2026-08-31 — cross-platform backpressure correction:** Android's
    auxiliary `BoundedChunkChannel` and the active iOS channel now both enforce
    the frozen capacity of 64 by suspending/blocking the producer. Neither drops,
    rewrites, nor merges token callbacks. Focused Android lifecycle tests and the
    77-case/2,878-schema Swift contract run pass.
  - **Suggested next:** add deterministic cancellation-during-prompt,
    cancellation-during-token, slow-consumer saturation, and no-post-terminal
    tests on both native clients; close the remaining P8.6 rows only when those
    tests prove the documented semantics.
- [x] Support cancellation during prompt decoding and token generation without
  emitting post-terminal chunks.
- [x] Freeze queue capacity, backpressure, chunk size, and error semantics in
  `docs/api.md`; add ordering, cancellation, and slow-consumer tests.
  - [x] **2026-08-31 — P8.6 closure:** both native bridges expose cancellation
    to llama.cpp during prompt decode and token decode, translate it to one
    `cancelled` terminal, and reject post-terminal sends. Deterministic Android
    tests cover native `-2`, exactly one cancellation terminal, and an 80-event
    slow consumer; the Swift runner covers the same 80-event lossless boundary,
    consumer cancellation, and post-terminal suppression. The frozen API uses
    valid UTF-8 semantic callbacks, capacity 64, producer backpressure, stable
    error codes, and no drop/rewrite/merge behavior.
  - **Suggested next:** implement P8.7 transaction ownership around this stream:
    stage the user turn, atomically persist user plus assistant only after
    `completed`, and leave the prior ledger byte-identical after `failed` or
    `cancelled`, first in Android and then in Swift.

### P8.7 — Transactional conversation history

- [x] Persist a user/assistant exchange atomically only after successful stream
  completion; preserve the previous ledger after failure or cancellation.
  - [x] **2026-08-31 — production store wiring:** both GM screens now restore
    completed exchanges from their platform `ConversationHistoryStore` and call
    its fsync-plus-atomic-replace transaction only after the stream completes
    with non-empty text. Failure/cancellation paths never call the store; a store
    failure also prevents the assistant answer from being accepted in the UI.
    Android Kotlin compilation and the linked iOS simulator build pass.
  - **Suggested next:** extract the completion boundary behind an injectable
    transaction coordinator and prove that completed commits exactly one paired
    exchange while failed/cancelled streams leave the pre-existing history bytes
    unchanged on Android and Swift.
  - [x] **2026-08-31 — typed transaction ownership evidence:** Android and Swift
    now route the production stream through an equivalent
    `ConversationTurnTransaction`. It buffers only the active assistant text,
    commits exactly one paired exchange on `completed`, ignores every event after
    a terminal, and never writes on `failed` or `cancelled`. Native tests preserve
    an existing ledger byte-for-byte across both unsuccessful terminals and prove
    that repeated completion cannot duplicate a turn.
  - **Suggested next:** migrate legacy paired `SaveState.gmHistory` into the
    durable store once, remove duplicate production writes, and retain a bounded
    compatibility decoder so upgrades do not discard existing conversations.
- [x] Restore history after restart and enforce schema, size, and reveal limits.
  - [x] **2026-08-31 — restart and identity binding:** both GM screens restore
    the durable paired-exchange ledger on construction. Readers now bind saved
    history to the exact `story_id` and package `content_hash`, reject cross-story
    reuse with `HISTORY_IDENTITY_MISMATCH`, validate both user and assistant byte
    limits, and retain the existing version/order/hash/total-size gates. Android
    compilation and the full Swift contract catalog pass.
  - **Suggested next:** add native store fixtures for identity mismatch, oversized
    assistant text, corrupt/truncated temp files, and restart parity; then remove
    the transitional duplicate `SaveState.gmHistory` write once migration behavior
    for existing installs is explicitly covered.
  - [x] **2026-08-31 — hostile native history fixtures:** Android JVM tests and
    the Swift contract runner now cover restart restoration, immutable-package
    identity mismatch, truncated JSON, oversized assistant text, exact paired
    completion, and byte-identical failure/cancellation. Text-size limits are
    enforced before writing as well as while loading.
  - **Suggested next:** implement and test the one-time legacy migration, then
    mark the first two P8.7 exit rows complete and run both native suites together.
- [x] Prove equivalent behavior in both native clients.
  - [x] **2026-08-31 — P8.7 closure and legacy migration:** both clients perform
    a one-time atomic conversion of valid alternating legacy GM turns into stable
    `legacy-NNNNNNNN` paired exchanges, preserve an existing durable ledger on
    repeated startup, clear the legacy copy only after successful migration, and
    no longer duplicate new exchanges into `SaveState.gmHistory`. Focused Android
    tests, the complete Swift contract runner, Android production compilation,
    and the linked iOS simulator application pass.
  - **Suggested next:** begin P8.8 by extracting a lifecycle-aware presentation
    reducer shared by each native screen's tests; prove incremental rendering,
    retry/cancel state transitions, and rotation/background restoration without
    changing the now-closed stream or history contracts.
  - [x] **2026-08-31 — post-closure P8.7 audit:** removed Android's unsafe
    delete-then-rename fallback and now fail closed unless a same-directory
    `ATOMIC_MOVE` replacement succeeds. Both native stores reject invalid first
    sequences, gaps, duplicate/empty exchange IDs, bad ordering, oversized text,
    wrong immutable identity, corruption, and post-terminal duplication before
    publication. Python reference tests report 66 passing; focused Android
    retrieval/stream/history tests and the full Swift contract runner pass.
  - **Suggested next:** retain P8.7 as a regression gate while P8.8/P8.9 add UI
    recreation and successful revealed-stream coverage; any future store format
    change requires shared migration and hostile fixtures before publication.

### P8.8 — Responsive GM experience

- [x] Render chunks incrementally without blocking the UI thread.
  - [x] **2026-08-31 — native incremental presentation:** Android Compose and
    SwiftUI consume the bounded semantic stream asynchronously, update one live
    partial-answer bubble per text callback, and never wait for a whole answer.
    Android focused stream/history tests and the linked iOS simulator build pass.
  - **Suggested next:** preserve these rendering semantics while closing retry,
    lifecycle, and accessibility state transitions; do not introduce a second
    chunking or buffering layer in the UI.
- [x] Provide visible loading, cancellation, retry, and actionable failure states.
  - [x] **2026-08-31 — terminal interaction repair:** both input bars now accept
    a new question after completion or cancellation. Swift's unreachable retry
    guard was replaced with an exact failed-state gate; Android retry removes the
    failed attempt before re-adding it, so it no longer duplicates the user turn.
    Loading, stop, stable failure, retry, and accessibility labels remain visible.
  - **Suggested next:** prove background/rotation disposal cancels the active
    native request while leaving durable history unchanged, then restore the
    completed ledger and an enabled input after recreation.
- [ ] Verify rotation/background/restart behavior and accessibility.
  - [x] **2026-08-31 — lifecycle-safe cancellation implementation:** Android
    observes `ON_STOP` and composable disposal; iOS observes inactive/background
    scene phases. Both cancel the task and native decode before the view can be
    recreated, so partial text remains transient and P8.7 history is untouched.
  - **Suggested next:** add automated recreation/background and semantics tests
    on each native UI harness; keep this row open until those tests and physical
    accessibility checks exist.

### P8.9 — End-to-end isolation

- [ ] Exercise retrieval, streaming, cancellation, persistence, and reveal
  sentinels together on Android and iOS.
  - [x] **2026-08-31 — first combined native isolation slice:** Android and iOS
    load the shared cross-domain spoiler catalog, prove the hidden query produces
    no prompt context, carry that result through typed stream cancellation, keep
    the prior durable history byte-identical, and rescan the saved bytes for every
    hidden text/ID/source sentinel. Focused Android retrieval/stream/history tests
    and the complete Swift contract runner pass.
  - **Suggested next:** extend the same combined scenario through a successful
    revealed completion and actual UI lifecycle recreation, then add network
    observation before closing either P8.9 row.
- [ ] Prove no telemetry or unintended network access after package/model setup.

## Phase 8B — Thin desktop launcher

### P8.10 — Freeze the Forge process contract

- [ ] Make live `forge generate`/`resume` accept the launcher’s versioned JSONL
  events and final-result options, or remove unsupported argv from the launcher.
- [ ] Change `GenerationRequest.resume` to the documented default and bind
  generate/resume explicitly.
- [ ] Align the CLI and generated world-control names from one source table.
- [ ] Implement documented exit codes 2/3/4/5/130 instead of generic exit 1.
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
  remove the shared `tmp/pytest` collision hazard.
- [ ] **P9.5:** Prove clean-run and resume identity across supported process modes.
  Real per-node image/music production now uses bounded `BatchScheduler` jobs,
  atomic node checkpoints, graph-order aggregation, and structured-score-to-MIDI
  output. Retain clean-run/interruption/resume canonical-byte equivalence evidence.
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

- [ ] Freeze optional critic failure semantics. The validator now runs in the
  explicit `reconcile_world` v2 plan segment over actual Bible, story, and graph
  documents and records semantic evidence; decide whether its evidenced
  fail-open status remains advisory for release acceptance.
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
  duplicates, malformed encodings, hash confusion, and resource exhaustion. The
  iOS hostile-input path is now free of force-casts/force-unwraps and the shared
  catalog includes a resigned world-index type-confusion package. Route the iOS
  command-line and Xcode scenario harnesses through one reusable fixture runner
  so their behavior cannot drift.
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
  legacy class. Production has no remaining importer; the retained legacy-test
  consumers are `test_phase56q.py`, `test_phase56r.py`, `test_phase56x.py`, and
  `test_story_fixtures.py`. Remove orphaned `V2CheckpointStore` only after
  confirming no retained resume evidence depends on its semantics. Either wire
  the documented error taxonomy at real raise sites or delete unused decorative
  error classes.
  - [x] **2026-08-31 — legacy acceptance migration:** mapped every retained v1
    guarantee to named frozen-v2 catalog scenarios, migrated all four test
    consumers, verified no production or test import remains, deleted
    `src/storage/package_acceptance.py`, and synchronized the public API wording.
  - **Suggested next:** inventory `V2CheckpointStore` semantics and consumers,
    migrate any unique restart evidence to `CheckpointStore`, then delete it only
    after focused resume tests prove no behavior was lost.
  - [x] **2026-08-31 — checkpoint-store consolidation:** confirmed the live
    `CheckpointStore` already covers run fingerprints, producer/dependency
    invalidation, verified file hashes, per-node attempts, mixed regeneration,
    and interrupted media resume. The only `V2CheckpointStore` consumer was its
    isolated duplicate test, so both orphaned files were removed after the live
    resume suites remained authoritative.
  - **Suggested next:** audit `src/pipeline/errors.py` against real raise/catch
    sites; wire only error types that support documented exit/retry behavior and
    remove decorative classes that have no distinct operational semantics.
  - [x] **2026-08-31 — operational error boundaries:** model-load failures now
    raise `ModelLoadError`, RAM denials remain a typed `ResourceError`, atomic
    write failures raise `PersistenceError` after cleanup, missing stage inputs
    raise `DependencyError`, and rejected final packages raise
    `PackageValidationError`. Focused lifecycle, storage, pipeline, and package
    tests pass (84 tests), with Ruff and mypy clean for the changed boundaries.
  - **Suggested next:** return to active P8.WG1 and introduce the bounded
    `KnowledgeSource` contract before changing any native storage format.

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
