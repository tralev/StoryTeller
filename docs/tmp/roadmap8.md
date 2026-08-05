# Rewrite Phase 8: Local Game Master and Thin Desktop GUI

## Mission

Complete private local GM behavior on Android and iOS with resumable verified
first-launch model download, strict visited-node knowledge isolation, persistent
conversation history, and chunk streaming. Add a thin Wine-compatible desktop
launcher that configures and controls Forge through its CLI/event contract.

## Entry state audit

| Current area | Disposition | Gap |
|---|---|---|
| Android `LlamaEngine`/JNI and iOS `LlamaEngine`/bridge | Retain bridge boundary, rewrite lifecycle/streaming | Native integration exists but target chunk/download/cancellation contracts are incomplete |
| Mobile `GmIndex` | Replace in Phase 7, extend | Must retrieve complete v2 world/history knowledge with source/reveal IDs |
| GM screens/views | Rebind | Need persistent history, chunks, cancellation, local flagging |
| `src/backends/gm_backend.py` | Remove from product path or keep test reference only | Player GM is native; Python may provide contract reference logic |
| `win/`, `lin/`, `mac/` | Expand with launcher packaging | Current scripts/specs package Forge but no target GUI process contract |
| JSONL events | Retain and finalize | Launcher needs complete versioned progress semantics |

## Action plan

- [ ] **P8.1 (M, depends Phase 7):** Define release model registry entries with
  role, repository/revision, filename, size, SHA-256, license link/notices, and
  minimum device requirements.
- [ ] **P8.2 (XL, depends P8.1):** Implement first-launch mobile downloader on
  both platforms: explicit consent, temporary file, resume/range support,
  cancellation, storage checks, checksum, atomic install, delete/re-download.
- [ ] **P8.3 (L, depends P8.2):** Rewrite native model lifecycle for load,
  bounded context, cancellation, unload, memory warning, and app background.
- [ ] **P8.4 (L, depends Phase 7):** Implement identical query normalization,
  candidate ranking, context budgeting, and source ID selection from complete
  v2 GM index.
- [ ] **P8.5 (M, depends P8.4):** Apply strict `reveal_after_nodes` filtering
  before prompt assembly; expose selected source IDs to debug tests but not users.
- [ ] **P8.6 (XL, depends P8.3-P8.5):** Implement native chunk stream events:
  started, non-empty text chunks, completed full text, failed; add backpressure
  and cancellation.
- [ ] **P8.7 (M, depends P8.6):** Persist completed user/assistant turns in local
  save history; do not persist an unmarked partial assistant turn.
- [ ] **P8.8 (M, depends P8.6,P8.7):** Rewrite GM UI for responsive chunks,
  cancel/retry, history clear, and local flag/export flow without automatic upload.
- [ ] **P8.9 (L, depends P8.5-P8.8):** Add spoiler sentinel tests at candidate,
  prompt, output-double, log, and history boundaries on both platforms.
- [ ] **P8.10 (M, depends Phase 1):** Freeze launcher JSONL and final JSON result
  contracts, including progress totals and stable errors.
- [ ] **P8.11 (XL, depends P8.10):** Implement a toolkit-isolated launcher core:
  validated form model, safe argv construction, subprocess lifecycle, event
  parsing, cancel/resume, and final package reveal.
- [ ] **P8.12 (L, depends P8.11):** Choose the smallest suitable GUI toolkit
  after a Wine spike; implement only configure/start/progress/cancel/resume/result.
- [ ] **P8.13 (L, depends P8.12):** Package/test launcher for Windows, Linux,
  macOS, and Wine. Delete any GUI-side generation or log-scraping workaround.

## Integrated `src/worldgen` rewrite work

Phase 8 completes consumption of worldgen fact and reveal indexes.

- [ ] **P8.WG1 (M, depends Phase 7):** Query the complete world/history/local-map
  indexes lazily and return stable fact/source IDs with bounded excerpts.
- [ ] **P8.WG2 (M, depends P8.WG1):** Make candidate scoring account for current
  node, visited routes/sites, persons, events, beliefs, opportunities, and local
  containment while remaining identical across Python, Android, and iOS.
- [ ] **P8.WG3 (L, depends P8.WG1,P8.WG2):** Prove unrevealed global and local
  facts never enter prompt, logs, chunks, or persistent conversation history.
- [ ] **P8.WG4 (S, depends P8.10-P8.12):** Expose the complete `WorldSpec` in the
  launcher through the shared configuration model; the launcher delegates and
  contains no plate, climate, history, or local-map logic.

GM answers may interpret revealed procedural facts but cannot create or persist a
mutation of the immutable world.

## Chunk contract example

```kotlin
sealed interface GmChunk {
    data class Started(val requestId: String) : GmChunk
    data class Text(val requestId: String, val text: String) : GmChunk
    data class Completed(val requestId: String, val fullText: String) : GmChunk
    data class Failed(val requestId: String, val code: String) : GmChunk
}
```

Launcher argv example:

```python
def build_argv(form: LaunchForm, forge: Path) -> list[str]:
    return [
        str(forge), "generate", "--title", form.title,
        "--seed", str(form.seed), "--output", str(form.output_dir),
        "--world-width", str(form.width),
        "--world-height", str(form.height),
        "--history-years", str(form.history_years),
        "--events", str(form.event_path), "--json-result",
    ]
```

Never create a shell command string from form input.

## File operations

Rewrite mobile GM model managers, retrieval, engines, screens, and native bridge
lifecycle. Add model registry/download state. Add `src/launcher/` or a separate
thin launcher package plus platform specs. Keep toolkit behind a small interface.
Remove cloud/network services beyond explicit model download.

## Focused tests

- Download resume/cancel/bad checksum/insufficient storage/atomic install
- Offline restart and model deletion
- Native load/cancel/unload/resource release
- Cross-platform candidate/reveal ID equality
- Sentinel never enters prompt before reveal
- Ordered chunks/backpressure/UI responsiveness
- Completed history persistence and partial cancellation policy
- Launcher argv injection safety and event tolerance
- Launcher cancel/resume/final path
- Wine launch and no GUI generation imports

## Required commands at phase exit

```bash
./droid/gradlew -p droid connectedDebugAndroidTest
xcodebuild -scheme StoryTeller -project ios/StoryTeller.xcodeproj \
  -destination 'platform=iOS Simulator,name=iPhone 15' test
.venv/bin/pytest -q tests/contracts/test_gm_retrieval_reference.py
.venv/bin/pytest -q tests/launcher
.venv/bin/python -m src.launcher --smoke-test --forge .venv/bin/forge
wine tmp/packages/storyteller-launcher.exe --smoke-test
```

Physical-device performance thresholds are finalized in Phase 9, but functional
native download/inference tests must pass here.

## Exit checklist

- [ ] Both apps verify and install the GM model after explicit first-launch consent.
- [ ] Post-download reading and GM work with networking blocked.
- [ ] Reveal filtering occurs before prompt assembly and matches across platforms.
- [ ] Responses stream in chunks and completed conversations persist locally.
- [ ] Cancellation releases native resources and handles partial turns consistently.
- [ ] Launcher contains no generation logic and works under Wine.

## Phase 9 handoff

Phase 9 receives feature-complete Forge, v2 Players, local GM, and launcher. It
must prove security, performance, compliance, and distribution readiness.
