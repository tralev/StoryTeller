# StoryTeller — Application Goal

## Vision

StoryTeller is a fully automated, offline-capable pipeline that generates interactive, multimedia "Choose Your Own Adventure" (CYOA) experiences from scratch — complete with original lore, branching narratives, illustrations, and music — and delivers them to a mobile reader app where an AI Game Master answers the reader's questions in real time.

## What It Produces

A single `.story` file (a ZIP archive) containing:

- A fully generated fantasy world with history, magic systems, factions, and characters
- A linear 30-page story set in that world
- A branching CYOA gamebook with ~15 interactive nodes
- A 512×512 illustration for every scene, rendered in a consistent art style
- A looping MIDI musical theme for every scene
- A pre-computed index enabling a local Game Master LLM to answer reader questions

## The Two Applications

### App B — The Forge (Desktop)

Runs on Windows, macOS, or Linux (including via Wine). Consumes up to 10 GB of RAM using CPU-only inference. Downloads quantized LLMs from Hugging Face once, then operates fully offline. A full generation run takes 2-4 hours on modern hardware (8+ core CPU). Worst case on low-end hardware (4-core, thermal throttling): up to 24 hours.

**Responsibilities:**
1. Download and manage quantized LLM and image-generation models
2. Generate a structured World Bible (lore, characters, factions, magic, politics)
3. Generate a linear story (~30 pages) consistent with the Bible
4. Convert the linear story into a branching CYOA graph with consequence tracking
5. Generate image prompts and render illustrations via Stable Diffusion
6. Generate music tone descriptions, output ABC notation, compile to MIDI
7. Build a Game Master retrieval index for mobile use
8. Package everything into a reproducible `.story` archive

### App A — The Player (Mobile)

Runs on iOS and Android as native applications. Consumes up to 3 GB of RAM for the local Game Master LLM. Works fully offline after the `.story` file is transferred.

**Responsibilities:**
1. Import and parse `.story` files from local storage, cloud drives, or USB
2. Display the CYOA book with text, images, and MIDI playback
3. Track player choices, consequence flags, and narrative state
4. Run a local LLM as an interactive Game Master
5. Answer reader questions about the current scene, lore, and world — without spoiling the plot
6. Stream Game Master responses word-by-word for an immersive experience
7. Manage separate immutable (story content) and mutable (reader progress) data

## Core Design Principles

1. **Offline-first.** After initial model download, both apps work without internet.
2. **RAM-disciplined.** Every model choice fits within strict memory budgets (10 GB desktop, 3 GB mobile).
3. **Structured over prose.** The World Bible uses relational JSON with explicit IDs and cross-references. This enables deterministic validation and targeted retrieval.
4. **Job Queue architecture.** The orchestrator enqueues jobs; workers execute them independently. Enables parallel generation on multi-core CPUs.
5. **Model abstraction.** Interfaces (TextGenerator, Validator, ImageGenerator, MusicGenerator, GameMaster) decouple pipeline logic from specific models. Swapping models requires only a config change.
6. **Reproducible output.** Same seed + same models + same machine = identical .story file. Sorted JSON keys, fixed floating-point precision, normalized timestamps, reproducibility profile recorded. Cross-machine determinism is not guaranteed due to floating-point non-associativity in CPU inference.
7. **Versioned artifacts.** Every JSON artifact carries schema version, generator version, and model versions. Future-proofed for migration.
8. **Immutable content, mutable saves.** Story content never changes after generation. Reader progress is stored separately. Simplifies sync and save management.
9. **Generator → Validator → Normalizer → Exporter.** Every pipeline stage follows this chain. The Normalizer enforces project-wide conventions before data is committed.
10. **Validatable at every stage.** JSON Schema validation, cross-reference checks, and graph topology validation after each pipeline step.

## Non-Goals

- Real-time or multiplayer experiences
- Procedural generation at runtime (all content is pre-generated)
- Cloud-based inference (the apps are offline-only after setup)
- Support for non-fantasy genres in v1
- User-authored content editing (v1 is purely generative)

---

## Related Documents

- **[arch.md](arch.md)** — Technical architecture: stack, schemas, coding patterns
- **[design.md](design.md)** — Behavioral design: pipeline flows, UX flows
- **[readme.md](readme.md)** — Usage guide for both apps
- **[roadmap.md](roadmap.md)** — Development phases and milestones
