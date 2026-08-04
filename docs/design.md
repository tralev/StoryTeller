# StoryTeller — Behavioral Design

## The Four-Stage Pipeline

Every generation job in the Forge follows the same pattern:

```
┌──────────────────────────────────────────────────────────────┐
│                 GENERATOR → VALIDATOR → NORMALIZER → COMMIT   │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  GENERATOR        VALIDATOR         NORMALIZER       COMMIT   │
│  ┌────────┐      ┌──────────┐      ┌──────────┐    ┌──────┐ │
│  │ LLM    │─────►│ Schema   │─────►│ ID format│───►│ Disk │ │
│  │ prompt │      │ check    │      │ naming   │    │ write│ │
│  │ → JSON │      │ Cross-ref│      │ sorting  │    │      │ │
│  └────────┘      │ check    │      │ whitespc │    └──────┘ │
│                  │ Graph    │      │ JSON fmt │             │
│                  │ topology │      │ paths    │             │
│                  └──────────┘      └──────────┘             │
│                                                               │
│  If validation fails → retry generator with error feedback    │
│  If validation passes → normalize → commit                    │
└──────────────────────────────────────────────────────────────┘
```

---

## App B — The Forge: Complete Pipeline

### Phase Map: Sequential vs Parallel

```
┌─────────────────────────────────────────────────────────────────┐
│                        SEQUENTIAL PHASES                         │
│  (each depends on previous output)                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  STEP 1          STEP 2          STEP 3          STEP 4         │
│  World Bible ──► Style Bible ──► Story        ──► Chapters      │
│                 (depends on     Outline          (per chapter,   │
│                  world tone)    (depends on       sequential)    │
│                                  bible)                          │
│      │                                                           │
│      ▼                                                           │
│  STEP 5          STEP 6          STEP 7                          │
│  Full-Story ──► Decision     ──► Graph                           │
│  Consistency    Points          Skeleton                         │
│  (depends on    (depends on     (depends on                      │
│   all chapters)  full story)    decision pts)                    │
│                                                                  │
│                                                                  │
│  STEP 8: NODE GENERATION (sequential — one shared LLM)          ││ (text generation is serial; only one LLM instance)             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Node 01 → Node 02 → Node 03 → ... → Node 15             │  │
│  │  (queued serially on single TextGenerator instance)      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                        PARALLEL PHASES                           │
│  (independent jobs, different model types)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│ STEP 9: ASSET GENERATION (parallel — different models)          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Image 01 │  │ Image 02 │  │ Image 03 │  │ Image ... │       │
│  │ (SDXL)   │  │ (SDXL)   │  │ (SDXL)   │  │ (SDXL)   │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ MIDI  01 │  │ MIDI  02 │  │ MIDI  03 │  │ MIDI  ... │       │
│  │(music21) │  │(music21) │  │(music21) │  │(music21) │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
│                                                                  │
│  Image jobs and MIDI jobs use different RAM pools —              │
│  can run concurrently with each other and with text generation.  │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                        SEQUENTIAL FINISH                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  STEP 10         STEP 11                                        │
│  GM Index     ──► Package                                        │
│  Building        (depends on                                    │
│  (depends on      all assets)                                   │
│   all nodes)                                                     │
└─────────────────────────────────────────────────────────────────┘
```

**Parallelism model:** Text generation is strictly sequential (one shared LLM instance, shared across all node text jobs). Image generation (SDXL) and MIDI conversion (music21) run in parallel across nodes — different models, different RAM pools, no conflict. This gives ~2-3× speedup on the **asset phases only** (images + MIDI). Text generation speed is determined by single-threaded LLM throughput.

---

### Detailed: Sequential Phase (Steps 1-7)

```
USER RUNS: forge generate --title "The Ashen Marches" --seed 42

    ┌──────────────────────────────────────────────────────────────┐
    │ STEP 0: Initialization                                       │
    │ • Load config/models.yaml → resolve interfaces to concrete   │
    │ • Load JSON schemas from docs/schemas/                       │
    │ • Create/verify SQLite checkpoint DB                         │
    │ • Resolve seed (user-provided or random)                     │
    │ • Initialize pipeline steps (text, image, music generators)    │
    └──────────────────────┬───────────────────────────────────────┘
                           │
    ┌──────────────────────▼───────────────────────────────────────┐
    │ STEP 1: World Builder (sequential — single job)              │
    │                                                               │
    │  Job:                                                        │
    │    Generator: TextGenerator (Qwen 7B)                        │
    │    Prompt: world_builder.j2 + tone + title                   │
    │    Schema: bible.schema.json                                 │
    │                                                               │
    │  Generator → raw JSON                                        │
    │  Validator → schema check + cross-ref check                  │
    │  Normalizer → sort entities by id, normalize names           │
    │  Commit → save bible.json with version metadata + seed       │
    └──────────────────────┬───────────────────────────────────────┘
                           │
    ┌──────────────────────▼───────────────────────────────────────┐
    │ STEP 2: Style Bible (sequential)                             │
    │  Generator → Validator → Normalizer → Commit                 │
    │  Output: style_bible.json (with version + seed)              │
    └──────────────────────┬───────────────────────────────────────┘
                           │
    ┌──────────────────────▼───────────────────────────────────────┐
    │ STEP 3-5: Story Generation (sequential per chapter)          │
    │                                                               │
    │  3. Story Outline (single job)                               │
    │     → 3 chapter summaries                                    │
    │                                                               │
    │  4. Per-chapter generation (3 sequential jobs)               │
    │     FOR chapter in [1, 2, 3]:                                │
    │       Generator: write chapter text                          │
    │       Validator: (different model!) check against Bible      │
    │       Normalizer: normalize text formatting                  │
    │       Commit: save chapter                                   │
    │                                                               │
    │  5. Full-story consistency (single job)                      │
    │     Validator reads all 3 chapters + Bible                   │
    │     Flags: contradictions, forgotten threads, tone breaks    │
    └──────────────────────┬───────────────────────────────────────┘
                           │
    ┌──────────────────────▼───────────────────────────────────────┐
    │ STEP 6-7: Graph Construction (sequential)                    │
    │                                                               │
    │  6. Decision Points (single job)                             │
    │     Generator reads full story                               │
    │     Output: list of ~15 moments where a choice matters       │
    │                                                               │
    │  7. Graph Skeleton (single job)                              │
    │     Generator: nodes + connections (no text yet)             │
    │     Validator: graph topology (orphans, cycles, dead ends)   │
    │     Normalizer: sort nodes, normalize IDs                    │
    └──────────────────────┬───────────────────────────────────────┘
```

### Detailed: Parallel Phase (Steps 8-9)

```
    ┌──────────────────────────────────────────────────────────────┐
    │ STEP 8: Node Text Generation (SEQUENTIAL — 15 jobs)          │
    │                                                               │
    │  Orchestrator runs steps sequentially:                         │
    │                                                               │
    │  ┌──────────────────────────────────────────────────────────┐│
    │  │ Shared LLM instance processes nodes serially:            ││
    │  │ Node 01 → Node 02 → Node 03 → ... → Node 15             ││
    │  │ Each: Gen→Val→Norm→Commit                                ││
    │  └──────────────────────────────────────────────────────────┘│
    │                                                               │
    │  When queue drains:                                          │
    │  ✓ Full-graph consistency pass (single Validator job)        │
    │  ✓ Final normalize (sort nodes, validate all cross-refs)     │
    └──────────────────────┬───────────────────────────────────────┘
                           │
    ┌──────────────────────▼───────────────────────────────────────┐
    │ STEP 9: Asset Generation (PARALLEL — 15×2 jobs)              │
    │                                                               │
    │  IMAGE JOBS (15 jobs, parallel)                              │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │ For each node:                                        │   │
    │  │   Generator: TextGenerator → image prompt             │   │
    │  │   Validator: prompt includes style bible suffix       │   │
    │  │   Normalizer: standardize prompt format               │   │
    │  │   Generator: ImageGenerator → 512×512 PNG             │   │
    │  │   Validator: resolution, file format, non-corrupt     │   │
    │  │   Thumbnail: 128×128                                  │   │
    │  │   Commit: save images/node_XX.png, thumbnails/        │   │
    │  └──────────────────────────────────────────────────────┘   │
    │                                                               │
    │  MUSIC JOBS (15 jobs, parallel)                              │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │ For each node:                                        │   │
    │  │   Generator: TextGenerator → music tone + ABC notation│   │
    │  │   Validator: ABC syntax, valid notes, non-empty       │   │
    │  │   Normalizer: strip markdown, normalize ABC header    │   │
    │  │   Converter: music21 → MIDI                           │   │
    │  │   Validator: MIDI playable, non-zero duration         │   │
    │  │   Commit: save midi/node_XX.mid                       │   │
    │  └──────────────────────────────────────────────────────┘   │
    │                                                               │
    │  Image jobs and music jobs for DIFFERENT nodes can run       │
    │  concurrently. Image + music for the SAME node can also      │
    │  run concurrently (they share no state).                     │
    └──────────────────────┬───────────────────────────────────────┘
```

### Detailed: Finalization (Steps 10-11)

```
    ┌──────────────────────────────────────────────────────────────┐
    │ STEP 10: GM Index Building (sequential)                      │
    │                                                               │
    │  Deterministic Python (no LLM):                              │
    │  • Scan all entity names + aliases from bible.json           │
    │  • Generate morphological variants (plurals, possessives)    │
    │  • Build inverted keyword→entity map                         │
    │  • Build entity_cache with one-line summaries                │
    │  • Build node_contexts: for each node, list present entities │
    │                                                               │
    │  Normalizer: sort keywords alphabetically, deduplicate       │
    │  Commit: save gm_index.json                                  │
    └──────────────────────┬───────────────────────────────────────┘
                           │
    ┌──────────────────────▼───────────────────────────────────────┐
    │ STEP 11: Packaging                                          │
    │                                                               │
    │  Validate: all required files present                        │
    │  Normalize: sort file list, normalize paths                  │
    │  Build: deterministic ZIP archive                            │
    │    • Entries sorted alphabetically                           │
    │    • Timestamps normalized to 1980-01-01                     │
    │    • content/ and save/ directories created                  │
    │  Generate: manifest.json + metadata.json                     │
    │                                                               │
    │  ┌──────────────────────────────────────────────────────┐   │
    │  │ ✅ .story file ready                                  │   │
    │  │ SHA256: a1b2c3d4... (same machine)                    │   │
    │  │ Same seed + same models + same machine = reproducible │   │
    │  └──────────────────────────────────────────────────────┘   │
    └────────────────────────────────────────────────────────────────┘
```

---

## App A — The Player: Architecture

### Two-Store Data Model

The `.story` file contains two separate stores:

```
┌─────────────────────────────────────────────────────────────────┐
│                     .story PACKAGE STRUCTURE                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  content/                    save/                               │
│  (IMMUTABLE)                 (MUTABLE)                           │
│  ┌──────────────┐           ┌──────────────────┐               │
│  │ bible.json   │           │ save_state.json  │               │
│  │ story.json   │           │  • current_node  │               │
│  │ graph.json   │           │  • flags: {...}  │               │
│  │ gm_index.json│           │  • visited: [...] │               │
│  │ images/      │           │  • started_at    │               │
│  │ midi/        │           │                  │               │
│  │ thumbnails/  │           │ gm_history.json  │               │
│  └──────────────┘           │  • conversations │               │
│                              │                  │               │
│  Read-only after import     │ bookmarks.json   │               │
│  Shared across devices      │  • user bookmarks│               │
│  (copy once)                └──────────────────┘               │
│                                                                  │
│                              Written to app private storage      │
│                              Synced via cloud (small files)      │
└─────────────────────────────────────────────────────────────────┘
```

**On import:**
1. Extract `content/` to app's read-only content directory
2. If `save/` exists in the .story (resuming from another device), extract to app's mutable save directory
3. If no `save/`, create fresh save state at `node_01`

**Cloud sync only syncs `save/`** — the content never changes, so it never needs re-syncing.

---

### User Experience Flow

```
USER OPENS APP
    │
    ▼
┌─────────────────────────────┐
│ LIBRARY SCREEN               │
│ • List of imported .story    │
│   files with cover art       │
│ • Progress indicators        │
│   ("Chapter 2, Node 7")     │
│ • [+ Import New Story]       │
└─────────────┬───────────────┘
              │ User taps a story
              ▼
┌─────────────────────────────┐
│ STORY LOADING                │
│ • Parse manifest.json        │
│ • Load graph.json            │
│ • Load gm_index.json         │
│ • Load save_state.json       │
│ • Initialize MIDI player     │
│ • Lazy-init Game Master      │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────┐
│ READING SCREEN                                           │
│                                                          │
│  ┌──────────────────────┐  ┌──────────────────────────┐ │
│  │                      │  │  The wind howls fiercely. │ │
│  │   [512×512 Image]    │  │  You grip your sword.     │ │
│  │                      │  │  A goblin leaps from      │ │
│  │                      │  │  shadows.                 │ │
│  │                      │  │  "Die, human!" it        │ │
│  │                      │  │  shrieks.                 │ │
│  │                      │  │  You parry the blade.     │ │
│  │                      │  │  Sparks fly in the dark.  │ │
│  │                      │  │  Your heart pounds.       │ │
│  └──────────────────────┘  │                           │ │
│                             │  What is your next move?  │ │
│  🎵 MIDI music plays        │                           │ │
│     (looping, changing      │  ┌─────────────────────┐ │ │
│      per scene)             │  │ ▶ Attack the goblin │ │ │
│                             │  ├─────────────────────┤ │ │
│  [🎙️ Ask Game Master]      │  │ ▶ Use a smoke bomb  │ │ │
│                             │  └─────────────────────┘ │ │
│                             └──────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
              │                    │
              │ User taps choice   │ User taps 🎙️
              ▼                    ▼
┌──────────────────────┐  ┌──────────────────────────────────┐
│ STATE UPDATE          │  │ GAME MASTER CHAT                  │
│ • Set choice flags    │  │                                   │
│ • Check conditional   │  │  Retrieval (zero-ML):             │
│   text for next node  │  │  ┌─────────────────────────────┐ │
│ • Navigate to target  │  │  │ 1. Extract n-grams from     │ │
│   node                │  │  │    user question             │ │
│ • Load new image      │  │  │ 2. Hash lookup in           │ │
│ • Switch MIDI track   │  │  │    gm_index.keywords         │ │
│ • Crossfade scene     │  │  │ 3. Add current scene context │ │
│ • Save state          │  │  │ 4. Fetch entity summaries    │ │
│   → save_state.json   │  │  │ 5. Assemble GM prompt        │ │
│                       │  │  └─────────────────────────────┘ │
│                       │  │                                   │
│                       │  │  User: "Why is the goblin here?"  │
│                       │  │                                   │
│                       │  │  GM: "The salt wraiths drove      │
│                       │  │  the goblin tribes from the       │
│                       │  │  deep caverns. This one is        │
│                       │  │  desperate, not evil."            │
│                       │  │  ████████████░░░░ (streaming)     │
│                       │  │                                   │
│                       │  │  [Close] [Ask Another]            │
│                       │  └──────────────────────────────────┘
└──────────────────────┘
```

### Ending Screen

```
USER REACHES NODE WITH endings.is_ending = true
    │
    ▼
┌────────────────────────────────────────────┐
│ ENDING SCREEN                               │
│                                             │
│  [Ending Illustration]                      │
│                                             │
│  "The Price of Silence"                     │
│  Bittersweet Ending                         │
│                                             │
│  The Marches claim another keeper of        │
│  secrets. The salt accepts all debts,       │
│  eventually.                                │
│                                             │
│  Your path:                                 │
│  • Stole the God-Heart Shard                │
│  • Spared the Salt Wraith                   │
│  • Trusted the Priest                       │
│                                             │
│  Endings found: 1 of 3                      │
│                                             │
│  [Read Again]  [Choose Differently]         │
└────────────────────────────────────────────┘
```

---

## Model Lifecycle (RAM Management)

Models are loaded and unloaded per-phase, never simultaneously:

```
RAM
10GB ┤
     │
 8GB ┤     ┌─Qwen─────┐     ┌─Qwen─────┐                    ┌─Package
     │     │          │     │          │                    │
 6GB ┤     │  Bible   │     │  Story   │     ┌─SDXL───────┐│
     │     │  Style   │     │  Ch1-3   │     │ Images     ││
 4GB ┤     │          │     │          │     │ (parallel) ││
     │     │          │     │          │     │            ││
 2GB ┤     │          │ ┌Phi┐│          │ ┌Phi┐│           ││
     │     │          │ │   ││          │ │   ││           ││
    0 ─────┴──────────┴─┴───┴┴──────────┴─┴───┴┴───────────┴┴─────► Time
         Step 1-2      Validate   Step 3-4    Validate    Step 9
                       (swap)                 (swap)
```

The Orchestrator manages this: it calls PipelineStep.run() for each phase, loading/unloading models as needed. Sequential phases use one model at a time; parallel phases (images + music) use separate models that can run concurrently.

---

## Transfer Methods

```
APP B (Desktop)                    APP A (Mobile)
     │                                    │
     │  USB cable (file copy)             │
     ├────────────────────────────────────┤
     │                                    │
     │  OneDrive / Google Drive / iCloud  │
     ├────────────────────────────────────┤
     │  (share .story → open in app)      │
     │                                    │
     │  AirDrop / Nearby Share            │
     └────────────────────────────────────┤
                                          │
     For cloud sync of saves only:        │
     content/ stays on device             │
     save/ syncs via iCloud/Google Drive  │
```

---

## Related Documents

- **[arch.md](arch.md)** — Technical architecture: Job Queue, Normalizer, model interfaces
- **[api.md](api.md)** — Interface definitions, config spec, CLI reference
- **[readme.md](readme.md)** — Usage guide for both apps
- **[roadmap.md](roadmap.md)** — Development phases and milestones
