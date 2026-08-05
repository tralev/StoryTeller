# StoryTeller Target Behavioral Design

## Document contract

This document defines logic and user-visible flow. `arch.md` defines code and
data representation. Phase roadmaps in this directory describe delivery;
unchecked items are not implementation claims.

## End-to-end generation flow

```text
Configure run
  -> verify models/resources
  -> generate authoritative procedural world
  -> simulate history through present year
  -> generate World Bible
  -> reconcile Bible against world
  -> direct art
  -> write linear story
  -> create branching graph
  -> generate mandatory per-node music
  -> unload text model / load image model
  -> generate mandatory image + thumbnail per node
  -> build complete reveal-gated GM index
  -> stage v2 package
  -> consumer-equivalent acceptance
  -> atomically publish
```

The order is a correctness rule. Narrative generation cannot begin from a blank
prompt and later retrofit geography.

## Block schemas

These schemas describe logical ownership and data flow. They are behavioral
contracts, not claims about the current implementation.

### System context

```text
┌──────────────────────────── Desktop ────────────────────────────┐
│  User                                                          │
│    │ configuration / cancel / resume                            │
│    ▼                                                            │
│  Thin GUI ─────────────── argv + JSONL ───────────────┐         │
│    │                                                  ▼         │
│    └──────────────────────────────────────────────► Forge CLI   │
│                                                       │         │
│                          local verified models ◄──────┤         │
│                                                       ▼         │
│                                              accepted .story v2 │
└───────────────────────────────────────────────────────┬─────────┘
                                                        │ user file transfer
┌──────────────────────────── Mobile ────────────────────▼─────────┐
│  Player importer -> immutable library -> reader                  │
│                           │             │                         │
│                    local saves      local GM model                │
│                           └────── app-private only ───────────────┘
└──────────────────────────────────────────────────────────────────┘

No StoryTeller server exists between these blocks.
```

### Forge pipeline

```text
┌───────────┐   ┌────────────┐   ┌─────────────┐   ┌──────────────┐
│ RunSpec   │──►│ Physical   │──►│ Civilization│──►│ Full history │
│ + seeds   │   │ world      │   │ simulation  │   │ + snapshots │
└───────────┘   └────────────┘   └─────────────┘   └──────┬───────┘
                                                          │ immutable truth
                                                          ▼
┌───────────┐   ┌────────────┐   ┌─────────────┐   ┌──────────────┐
│ Style     │◄──│ Accepted   │◄──│ Reconcile   │◄──│ World Bible  │
│ Bible     │   │ Bible      │   │ gate        │   │ candidate    │
└─────┬─────┘   └────────────┘   └─────────────┘   └──────────────┘
      │
      ├──────────────┐
      ▼              ▼
┌───────────┐   ┌────────────┐
│ Story     │──►│ Graph      │
└───────────┘   └─────┬──────┘
                      ├────────► image + thumbnail per node
                      ├────────► structured score + MIDI per node
                      └────────► complete reveal-gated GM index
                                      │
                                      ▼
                           manifest -> package -> acceptance -> publish
```

### Procedural world construction

```text
                  ┌───────────┐
                  │ Elevation │
                  │ land/ocean│
                  └─────┬─────┘
                        ▼
┌───────────┐   ┌────────────┐   ┌────────────┐
│ Hydrology │──►│ Climate +  │──►│ Biomes +   │
│ rivers etc│   │ seasons    │   │ resources  │
└─────┬─────┘   └─────┬──────┘   └─────┬──────┘
      └────────────────┼────────────────┘
                       ▼
            ┌────────────────────┐
            │ Regions + routes   │
            │ authoritative grid │
            └─────────┬──────────┘
                      ▼
            ┌────────────────────┐
            │ Sites + civs +     │
            │ economy/diplomacy  │
            └─────────┬──────────┘
                      ▼
            ┌────────────────────┐
            │ Event simulation   │
            │ to present year    │
            └──────┬───────┬─────┘
                   │       └──────► year 0, ten-year, and final snapshots
                   └──────────────► complete causal ledger

Structured coordinates are authoritative. World and regional map PNGs are
derived projections and cannot modify the blocks above them.
```

### Step execution and validation

```text
Verified input ArtifactRefs
          │
          ▼
┌──────────────────┐       acquire        ┌──────────────────────┐
│ Pipeline runner  │─────────────────────►│ Backend + local model│
└────────┬─────────┘                      └──────────┬───────────┘
         │ candidate                                  │ data/bytes
         ▼                                            ▼
┌───────────────────────────────────────────────────────────────┐
│ parse -> schema -> invariants -> cross-reference -> reconcile │
│                         -> optional semantic critic            │
└──────────────────────────────┬────────────────────────────────┘
                               │ valid
                               ▼
                    normalize -> atomic commit
                               │
                               ▼
               ArtifactRef -> checkpoint -> event -> release model

Invalid retryable candidate -> bounded retry with structured feedback.
Terminal/configuration/storage failure -> abort, never quarantine.
```

### Model lifecycle

```text
procedural stages:     [ no model ]
Bible/story/graph:     [ load text ] -> work -> [ unload text ]
optional critique:     [ load critic only when policy permits ] -> unload
music stage:           [ text role ] -> structured score -> deterministic SMF Type 1
image stage:           [ load image ] -> all node images -> [ unload image ]
index/package:         [ no model ]
```

The resource manager admits a role only when its declared memory fits. Pipeline
steps request a capability; they never load a model file themselves.

### `.story` v2 and local state

```text
┌──────────────── immutable `.story` v2 ────────────────┐
│ manifest.json                                          │
│ world/      terrain, water, climate, resources,        │
│             regions, routes, civs, history, snapshots  │
│ narrative/  Bible, reconciliation, style, story,       │
│             graph, GM index                            │
│ assets/     world/region/site maps, node images, thumbs│
│             authoritative scores, and derived MIDI     │
└─────────────────────────┬──────────────────────────────┘
                          │ story_id + content_hash
                          ▼
┌──────────────── app-private mutable state ─────────────┐
│ save_state.json | bookmarks | persistent GM history    │
└────────────────────────────────────────────────────────┘

No `save/` entry exists inside the package.
```

### Safe Player import

```text
selected file
    │
    ▼
preflight ZIP paths/limits/version
    │ v2 only
    ▼
private staging extraction
    │
    ▼
schemas -> hashes -> provenance -> world refs -> graph -> binary media
    │
    ├── invalid ──► delete staging + stable error
    │
    └── valid ────► atomic publish immutable library + create external save
```

### Strict Game Master boundary

```text
question + current node + visited nodes + prior local conversation
                          │
                          ▼
             retrieve from complete GM index
                          │ candidate source IDs
                          ▼
       REMOVE every entry whose reveal nodes are not visited
                          │ eligible facts only
                          ▼
                 build bounded local prompt
                          │
                          ▼
                 local model chunk stream
                          │ completed answer only
                          ▼
                 persistent local GM history
```

Unrevealed content must be absent before prompt construction. UI hiding and
“do not spoil” instructions are not security boundaries.

### Resume and invalidation

```text
checkpoint record + actual file + current dependency refs
                         │
                         ▼
       path confined? hash valid? schema/media valid?
       producer fingerprint and dependency IDs equal?
                 │ yes                    │ no
                 ▼                        ▼
              reuse               invalidate artifact
                                          │
                                          ▼
                              invalidate downstream DAG only
                                          │
                                          ▼
                                      regenerate
```

### Thin GUI boundary

```text
GUI form -> validated argv -> Forge child process
                                 │
                    versioned JSONL progress/events
                                 │
                                 ▼
            phase/status/error/final path shown by GUI

Cancel -> supported child signal/control
Resume -> new Forge invocation using the same output directory
```

The GUI never imports a generation backend or interprets free-form log text.

## 1. Configure

The user selects title, mature-dark-fantasy profile, seed, output directory,
world dimensions, integer metres per world cell, continent count, history years, and
civilization limits. Defaults produce one continent. Advanced model and worker
settings remain optional.

Before work begins, Forge validates configuration, disk space, model checksums,
schema compatibility, output ownership, and RAM feasibility. Invalid input fails
before loading a model.

## 2. Generate the physical world

Forge derives independent deterministic seeds. It builds elevation and
land/ocean, then hydrology, climate/weather, biomes/resources, and regions.
Routes and adjacency emerge from authoritative coordinates and geography.

Validation occurs after every domain. A failure aborts and leaves a resumable
diagnostic state; Forge never falls back to a simpler hidden world.

## 3. Simulate civilizations and history

Civilizations settle suitable sites, build routes/economies, migrate, compete,
ally, fight, change territory, and alter populations through a configurable
number of years. Each material transition emits a causal ledger event.

The result contains:

- Final state at `present_year`
- Full ordered event ledger
- Selected state snapshots for efficient reconstruction/debugging

Annual transient state need not be retained when it can be derived or has no
material effect. The full event ledger is retained even when unused by the
story.

## 4. Build the World Bible

The text model receives structured world summaries and relevant full records.
It enriches facts into mature dark-fantasy lore, magic, religion, factions,
characters, creatures, artifacts, politics, and narrative rules.

It may create local details inside existing authoritative places. It may not
change the map, climate, resources, routes, major civilizations, or simulated
past. Added entities carry a containing procedural ID.

## 5. Reconcile

The reconciliation gate checks the complete Bible, not prompt compliance alone.
Deterministic validators identify contradictions and produce precise retry
feedback. An optional validator model may critique tone and semantic coherence,
but cannot waive deterministic errors.

Retries rewrite the Bible. They never rewrite procedural truth. Exhausted
retries terminate the run at a resumable boundary.

## 6. Create narrative and graph

Art direction derives consistent visual rules from world and Bible. Story
generation creates an outline and checkpointed chapters. Game design extracts
decision points, builds topology, writes nodes, and validates choices, flags,
endings, locations, characters, and causal continuity.

Each node references stable world/narrative IDs and declares its image prompt,
music intent, and GM reveal consequences. Node text generation may resume at
node boundaries without changing completed canonical nodes.

## 7. Generate mandatory media

Music and images use domain-separated per-node seeds. Every node must produce:

- One playable, positive-duration MIDI track
- One correctly sized full PNG
- One correctly sized PNG thumbnail derived from the accepted full image

Workers may run concurrently under a RAM/concurrency policy. Results must be
independent of completion order and worker count. Each accepted file is written
atomically and checkpointed with its hash. A node may retry; no missing asset is
quarantined into a final package.

## 8. Build Game Master knowledge

The index contains the complete procedural world, event ledger, Bible, and
narrative knowledge. Entries retain source artifact/entity IDs and reveal rules.
Story nodes determine reveal progression.

An entry is eligible only when its `reveal_after_nodes` rule is satisfied by the
reader's visited-node set. Filtering happens before prompt assembly. Prompt
instructions are defense in depth, not the spoiler boundary.

## 9. Package and publish

Forge builds in a temporary same-filesystem location. Acceptance reopens the ZIP
as an external consumer and validates safety, schemas, hashes, provenance,
world/narrative references, exact node media coverage, PNGs, MIDI, and version.
Only an accepted v2 archive is renamed to its final path.

## Resume behavior

On resume, Forge compares the current run specification and producer inputs with
checkpoint metadata. It re-hashes disk artifacts and follows dependency edges.

```text
valid artifact + valid dependencies -> reuse
missing/corrupt artifact             -> regenerate it and dependants
changed dependency                   -> invalidate downstream only
changed run identity                 -> reject unsafe resume
```

Cancellation stops new work, lets atomic commits finish or cancels safely,
records the latest consistent state, unloads models, and exits distinctly.

## Thin desktop GUI flow

```text
Launch
 -> model readiness and license/checksum status
 -> generation form
 -> preflight
 -> start Forge subprocess
 -> render JSONL progress
 -> Cancel or Resume
 -> success: show/reveal package path
 -> failure: show stable code and local diagnostic path
```

The GUI does not edit stories, preview worlds, read packages, or call inference
libraries. Its toolkit remains an open decision; Wine compatibility is required.

## Player first launch

1. Explain that the GM is local and requires a large one-time model download.
2. Show model publisher, size, license, source, and storage requirement.
3. Obtain confirmation and respect metered-network choice.
4. Download resumably to a temporary file.
5. Verify pinned SHA-256 and atomically install.
6. Allow later model deletion/re-download.

The rest of the app can import/read stories without loading the GM model.

## Package import

```text
Select file
 -> reject non-v2 with “regenerate using Forge v2”
 -> stage safely in private storage
 -> validate complete archive
 -> reject without publishing on any error
 -> atomically add immutable content to library
 -> create separate empty local save
```

No v1 migration exists. Import never trusts file extension alone and never
extracts directly into the live library.

## Reading flow

The reader opens the saved current node or package entry node. It displays the
full image, narrative text, available choices, and starts/crossfades the node's
MIDI. Selecting a choice atomically updates flags, visited nodes, current node,
and timestamps before navigation is considered complete.

At an ending, the user may restart with a new local playthrough or return to a
previous local decision if that feature is enabled. Package content is never
changed.

## Save behavior

Saves live only in app-private storage keyed by immutable story ID. They include
save schema version, package content hash, current node, visited-node order,
flags, bookmarks, playthrough identity, and persistent GM conversations.

Writes use temporary-file replacement. On load, a save whose package hash does
not match is isolated and explained rather than applied. There is no cloud sync.

## Game Master flow

```text
Question
 -> retrieve candidates from complete index
 -> add current node and conversation context
 -> remove every entry not revealed by visited nodes
 -> enforce context/token budget
 -> run local model
 -> emit bounded text chunks
 -> persist completed exchange locally
```

Chunks should be large enough to avoid per-token UI churn and small enough to
feel responsive. Chunk boundaries are transport/UI details and are not stored as
canonical conversation data. Cancellation stops generation and records either a
clearly marked partial response or no assistant turn; one policy must be shared
by both platforms.

The GM cannot browse files, call tools, access the network, alter saves, or learn
unrevealed facts. Conversation history is persistent until the user clears it or
deletes the story's local data.

## Offline behavior

After model downloads, every core workflow functions with networking disabled.
No background network attempt is made. File transfer through user-selected
providers is an operating-system file action, not StoryTeller cloud sync.

## Error design

Errors have stable codes, category, human explanation, retryability, affected
artifact/node, and local diagnostic reference. Categories include configuration,
dependency, resource, generation, validation, persistence, cancellation,
package, model download, and unsupported version.

Terminal integrity/persistence errors are never retried automatically.
Retryable model generation errors use bounded policy. Mandatory-stage failure
prevents package publication.

## Cross-platform parity

Python, Android, and iOS execute the same machine-readable package scenarios.
They must agree on acceptance, graph behavior, flags, endings, media paths,
save/package mismatch, and spoiler eligibility. Platform UI may differ; contract
outcomes may not.
