# Rewrite Phase 7: Parallel Android and iOS v2 Players

## Mission

Rewrite both native Players in parallel against the frozen v2 package and shared
scenario catalog. This phase covers safe import, immutable repositories, local
saves, graph behavior, images/maps, and MIDI. Local GM inference is Phase 8.

## Entry state audit

| Current area | Disposition | Gap |
|---|---|---|
| Android/Swift `StoryParser` | Replace | v1 `content/save` extraction and insufficient acceptance |
| `StoryPackage`, `GraphNode`, `GmIndex` | Replace from v2 contracts | v1 field/layout assumptions |
| `StoryRepository` | Rewrite | Needs staged import, immutable v2 domain access, and stable outcomes |
| `SaveState` | Rewrite | Save must live outside package and bind content hash |
| Reader UI | Retain interaction ideas, rebind | Must use v2 repositories and exact media |
| MIDI players | Retain adapters, harden | Need validated assets, lifecycle, looping/crossfade parity |
| Existing tests | Replace/expand | Shared scenario outcomes are missing |

Neither platform is the reference. The Python scenario catalog and v2 schemas
are authoritative.

## Target module parity

```text
PackageValidator -> StoryImporter -> StoryRepository (read-only)
                               \-> SaveRepository (app-private)
StorySession -> Reader UI -> Image/Map loader + MidiPlayer
```

## Action plan

- [ ] **P7.1 (M, depends Phase 6):** Generate or hand-maintain equivalent v2
  domain models for Swift `Codable` and Kotlin serialization; test all frozen
  schema fixtures.
- [ ] **P7.2 (XL, depends P7.1):** Implement native pre-extraction ZIP safety and
  acceptance adapters with the same stable issue codes as Python.
- [ ] **P7.3 (L, depends P7.2):** Rewrite import as private staging -> full
  validation -> atomic immutable-library publication; clean staging on failure.
- [ ] **P7.4 (M, depends P7.2):** Return shared conceptual results:
  imported/already imported/unsupported v1/invalid/insufficient storage/cancelled.
- [ ] **P7.5 (L, depends P7.1,P7.3):** Rewrite Story Repository for v2 world and
  narrative files, lazy large-domain access, exact asset paths, and read-only
  content.
- [ ] **P7.6 (L, depends P7.5):** Rewrite local Save Repository keyed by story ID
  and package content hash. Use atomic app-private writes; no package `save/` and
  no cloud API.
- [ ] **P7.7 (L, depends P7.5,P7.6):** Implement identical graph session logic
  for current/visited nodes, choices, flags, conditional text, and endings.
- [ ] **P7.8 (M, depends P7.5):** Rebind full images/thumbnails and make world or
  region maps and all-site local maps available to the internal repository/GM
  without requiring a dedicated map UI.
- [ ] **P7.9 (L, depends P7.5,P7.7):** Harden MIDI lifecycle, loop, node change
  crossfade, interruption, background/foreground, and resource release.
- [ ] **P7.10 (M, depends P7.6,P7.7):** Implement library import/delete; deletion
  explicitly asks whether local save/history should also be removed.
- [ ] **P7.11 (XL, depends P7.1-P7.10):** Run every shared scenario ID on both
  platforms, including invalid packages, behavior, save mismatch, media paths,
  and v1 rejection.
- [ ] **P7.12 (L, depends P7.11):** Build with real Android NDK/llama bridge
  placeholders and Xcode toolchains; fix native project packaging and tests.
- [ ] **P7.13 (M, depends P7.12):** Delete old v1 parsers/models/tests, package
  `save/` handling, cloud wording/code, and duplicate platform fixtures.

## Integrated `src/worldgen` rewrite work

Phase 7 proves native consumption of the frozen full world dataset.

- [ ] **P7.WG1 (M, depends P7.1-P7.5):** Implement lazy bounded readers for
  world index, regions, routes, maps, entities, history, local maps, opportunities,
  and reference/spatial indexes without loading the complete world into RAM.
- [ ] **P7.WG2 (M, depends P7.WG1):** Verify native integer units, stable IDs,
  canonical paths, chunk hashes, and cross-domain references against Python
  scenarios.
- [ ] **P7.WG3 (M, depends P7.WG1,P7.WG2):** Ensure package import retains every
  world artifact read-only even when Player UI does not expose it; saves contain
  references/progress only, never copies or mutations of procedural facts.
- [ ] **P7.WG4 (M, depends P7.WG1-P7.WG3):** Add shared scenarios for large
  chunked worlds, full ledgers, local maps, missing chunks, broken causal links,
  invalid indexes, and package/save world-hash mismatch.

Native Players do not reproduce generation, but their validators and repositories
must preserve and interpret the frozen generation contract identically.

## Target save contract

Kotlin shape:

```kotlin
@Serializable
data class SaveStateV1(
    val saveVersion: Int = 1,
    val storyId: String,
    val packageContentHash: String,
    val playthroughId: String,
    val currentNode: String,
    val visitedNodes: List<String>,
    val flags: Map<String, Boolean>,
    val bookmarks: List<String>,
    val gmHistory: List<ChatTurn> = emptyList(),
)
```

Swift importer outcome:

```swift
enum ImportResult: Equatable {
    case imported(storyID: String)
    case alreadyImported(storyID: String)
    case unsupportedVersion(found: Int, supported: Int)
    case invalid(errorCodes: [String])
    case insufficientStorage(requiredBytes: Int64)
    case cancelled
}
```

## File operations

Replace models, parser/importer, repository, saves, and platform tests under
`droid/` and `ios/`. Add one generated/shared scenario resource location instead
of copied drifting fixtures. Retain llama.cpp bridges but defer GM behavior to
Phase 8. Delete all v1 mobile code after shared scenarios pass.

## Focused tests

- Every v2 valid/invalid shared package scenario
- v1 rejection with regenerate-v2 guidance
- Safe staging/cleanup and no live partial import
- Content immutability and path confinement
- Local atomic save/restart and package-hash mismatch
- Identical graph/flag/ending outcomes
- Exact image/thumbnail/score/MIDI paths and score-derived MIDI agreement
- MIDI loop/crossfade/lifecycle
- Library deletion and local data choice
- Zero cloud/telemetry dependencies

## Required commands at phase exit

```bash
./droid/gradlew -p droid testDebugUnitTest
./droid/gradlew -p droid assembleDebug
xcodebuild -scheme StoryTeller -project ios/StoryTeller.xcodeproj \
  -destination 'platform=iOS Simulator,name=iPhone 15' test
.venv/bin/python scripts/verify_cross_platform_scenarios.py \
  --python-results tmp/contracts/python.json \
  --android-results tmp/contracts/android.json \
  --ios-results tmp/contracts/ios.json
```

The Xcode scheme/project command may be generated during the phase, but it must
exist and pass at exit.

## Exit checklist

- [ ] Both Players import only fully accepted v2.
- [ ] Both reject v1 and provide no migration.
- [ ] Imported content is immutable; saves are external, local, and atomic.
- [ ] Graph outcomes and error codes match shared scenarios.
- [ ] Every required media asset is consumed by its node.
- [ ] Android and iOS native builds/tests pass.
- [ ] No platform-specific fixture copies can drift.

## Phase 8 handoff

Phase 8 receives stable native repositories, local persistent GM history fields,
and a shared reveal reference function/corpus, ready for local inference.
