# StoryTeller Target User Experience

## Scope

This document defines the target interaction flow for the thin desktop Forge
launcher and the Android/iOS Player. It complements `design.md`; it does not change
pipeline or package contracts. Every state below must satisfy `accessibility.md`.

## Shared principles

- The product works offline after explicit model downloads.
- No telemetry, account, remote service, or cloud-save feature is required.
- Errors show a stable code, plain-language explanation, safe recovery action, and
  local diagnostic location when available.
- Long-running work exposes stage, progress, elapsed time, and cancellation state.
- Mature dark-fantasy content is disclosed before generation or reading.
- Android and iOS expose equivalent package, save, navigation, and GM behavior.

## Forge launcher

The GUI is a thin configure-and-launch wrapper over the same application service
and configuration model as the CLI. It must be simple enough to package for
Windows/Wine as well as Linux and macOS.

```text
┌─ StoryTeller Forge ───────────────────────────────────────┐
│ Project configuration  [ /path/project.yaml ] [Browse]  │
│ Seed                   [ 184467              ] [Random]  │
│ World preset           [ Standard ▼ ]  Continents [ 1 ] │
│ Text model             [ qwen-local ▼ ]  [Verify]       │
│ Image model            [ sdxl-local ▼ ]  [Verify]       │
│ Output folder          [ /path/output       ] [Browse]  │
│                                                          │
│ [Validate configuration]                    [Generate]   │
└──────────────────────────────────────────────────────────┘
```

Advanced settings are discoverable but do not obscure the standard flow. Product
invariants cannot be disabled. Validation happens before the Generate button
starts work.

## Forge progress and resume

```text
┌─ Generating: The Ashen Marches ───────────────────────────┐
│ Stage 3/8: Civilizations and history                     │
│ [███████████████████░░░░░░░░] 67%                       │
│ Current: year 338 of 500                                 │
│ Elapsed 01:42:17      Estimated time: profile-dependent  │
│ Last checkpoint: 14:31:08                                │
│                                                          │
│ [Show details] [Open diagnostics] [Cancel safely]        │
└──────────────────────────────────────────────────────────┘
```

Progress units must be honest and stage-specific; do not present invented overall
percentages when total work is unknown. Cancellation finishes or rolls back the
current atomic commit. The next launch offers Resume only when the checkpoint and
run fingerprint are valid. Otherwise it explains why a new run is required.

Successful completion links to the accepted `.story` file and verification
summary. Forge never advertises an incomplete package as successful.

## First Player launch

```text
Welcome
  1. Mature-content and privacy disclosure
  2. Choose local model storage location where supported
  3. Download required GM model with size, license, and checksum shown
  4. Verify model
  5. Continue to empty library
```

The user may defer the GM model and still import/read a package if the final Player
design supports this capability split. GM remains unavailable with a clear local
setup action. Download is explicit; afterward normal use is offline.

## Library

```text
┌─ Library ────────────────────────────────────────────────┐
│ [Import .story]                         [Settings]       │
│                                                         │
│ The Ashen Marches      42%      Continue               │
│ The Hollow Crown       Complete  Read again             │
│                                                         │
│ Storage used: package files + local saves               │
└─────────────────────────────────────────────────────────┘
```

Library entries show title, cover, progress, last-opened time, package identity,
and local validation state. Removing a package and deleting its save are separate,
explicit actions with clear consequences.

## Package import

The user chooses a local `.story` file through the platform file picker, share
sheet, USB/shared storage, AirDrop, or another OS-provided local file source. The
source may be backed by a platform provider, but StoryTeller does not implement
cloud saving or synchronization.

Import flow:

```text
Select file
  -> inspect safely without extraction escape
  -> validate manifest, inventory, hashes, schemas, world, graph, media
  -> reject: show stable code and preserve existing library
  -> accept: copy/reference package atomically, create separate local save
  -> open title screen
```

Validation progress is announced accessibly. An invalid package never produces a
partially usable library item.

## Reader

```text
┌─ The Ashen Marches ─────────────── Chapter 2 ────────────┐
│ [Back to library]                         [Text settings] │
│                                                          │
│                     [full node image]                    │
│                                                          │
│ Narrative text…                                          │
│                                                          │
│ Music: [Pause] [Volume] [Mute]                           │
│                                                          │
│ What do you do?                                          │
│  [1] Follow the lanterns                                 │
│  [2] Enter the ruined chapel                            │
│                                              [Ask GM]    │
└──────────────────────────────────────────────────────────┘
```

Text reflows without clipping. Image alternative text, thumbnail, and full image
come from validated package data. MIDI never autoplays against platform policy or
user preference. Choices expose labels, consequence-neutral descriptions where
available, and accessible focus order. Selecting a choice commits visited state
atomically before navigation.

## Ending and replay

The ending screen shows the reached ending, journey summary, discovered locations
and characters, media controls, and options to return to the library or begin a
fresh local playthrough. It must not reveal undiscovered alternate branches.
“Read again” creates a separate playthrough or requires explicit confirmation
before clearing the existing one.

## Save recovery

Saves are external local records bound to package ID and content hash. On startup:

- a valid save resumes at the last committed visited node;
- a corrupt primary save may recover from the last valid atomic backup;
- a package mismatch never silently applies the save;
- recovery explains what was restored and preserves the corrupt record for local
  diagnostics unless the user deletes it.

No network recovery or cloud merge exists.

## Game Master

```text
┌─ Ask the Game Master ────────────────────────────────────┐
│ Knowledge boundary: your journey through Chapter 2      │
│                                                         │
│ You: What do I know about the chapel?                   │
│ GM:  [committed semantic chunk]                         │
│      [next committed semantic chunk]                    │
│                                                         │
│ [Stop]                                       [Close]     │
└─────────────────────────────────────────────────────────┘
```

Only knowledge allowed by visited nodes reaches prompt assembly. Chunks are
semantic, ordered, and persisted after commitment. Stop preserves committed
chunks and discards an incomplete chunk. Reopening the conversation shows the
persistent local transcript. The interface never implies the GM can access the
internet or unrevealed world state.

## Model download and storage

Before download, show model purpose, exact expected size, available space,
license/attribution link, source, and checksum status. Support pause/retry when the
platform permits. Download into a temporary file, verify it, then publish
atomically. An update never deletes the last working model until the replacement
passes verification.

## Accessibility annotations

Every wireframe requires:

- logical screen-reader order and named controls;
- keyboard/switch access where the platform supports it;
- scalable type, reflow, contrast, reduced motion, and non-color status cues;
- captions/text equivalents for meaningful audio and image alternatives;
- announced progress without excessive repeated notifications;
- focus placement on validation errors and after navigation;
- touch targets and gestures consistent with native guidance.

## UX acceptance scenarios

- A first-time user can configure and launch Forge without using a terminal.
- CLI and GUI produce the same validated `RunSpec`.
- Cancellation and resume never misrepresent package completion.
- A malicious/corrupt package leaves the library unchanged.
- A user can read, choose, save, close, and resume fully offline.
- Package removal and save deletion cannot be confused.
- GM stopping/reopening preserves only committed chunks.
- Android and iOS pass the same conceptual interaction fixtures.
- Screen-reader, large-text, keyboard/switch, reduced-motion, and no-audio paths
  complete every primary flow.

