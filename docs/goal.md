# StoryTeller Target Product

## Status of this document

This document defines the normative product target. Implementation completion is
recorded by evidence-backed checkboxes in `roadmap.md`.

## Vision

StoryTeller creates complete, offline, mature dark-fantasy interactive books.
The desktop Forge first simulates an authoritative procedural world, then builds
a World Bible and narrative on top of it. Native Android and iOS readers import
the resulting `.story` package and provide illustrated branching reading,
music, local saves, and a private on-device Game Master.

No generation, reading, save, or conversation data is sent to a StoryTeller
service. The applications are free in their stores and contain no telemetry,
analytics, advertising, accounts, or cloud saves.

## Product surfaces

### Forge

The Forge is a local desktop engine for Windows, Linux, and macOS. Its primary
interface is a CLI. A later thin GUI configures a run, starts/cancels/resumes the
CLI process, renders structured progress, and reveals the completed package. It
contains no generation logic. The Windows build and GUI must run under Wine.

The Forge:

1. Downloads and verifies user-selected local models.
2. Generates a configurable world, defaulting to one continent.
3. Simulates terrain, water, climate, weather, biomes, resources, regions,
   civilizations, routes, economies, migration, wars, and history.
4. Stops simulation at a configurable present year.
5. Builds a World Bible without altering authoritative world facts.
6. Reconciles Bible geography, history, and major entities against the world.
7. Creates art direction, a linear story, and a branching narrative graph.
8. Creates a full image, thumbnail, authoritative structured score, and derived
   MIDI track for every graph node.
9. Builds a complete, reveal-gated Game Master index.
10. Packages and validates one immutable `.story` v2 archive.

### Player

The Player is a native Android and iOS application with equivalent behavior. It:

1. Downloads and checksum-verifies its local GM model after first launch.
2. Imports only `.story` v2 packages.
3. Validates package identity, hashes, schemas, references, and binary media.
4. Displays the story, choices, images, thumbnails, and looping MIDI.
5. Stores progress and persistent GM conversations only in app-private storage.
6. Produces chunk-streamed GM answers entirely on-device.
7. Prevents spoilers structurally by exposing knowledge based on visited nodes.

## Authoritative world model

Procedural generation is mandatory and always precedes the World Bible. The
world uses stable entity IDs and integer cell coordinates, with configured
integer `metres_per_world_cell`. Structured map data is authoritative; rendered maps
are derived views.

The physical world and simulated past are immutable after generation. The World
Bible may enrich them and add local-scale buildings, streets, caves, ruins,
items, and minor characters. It may not invent continents, regions, major
civilizations, routes, climate facts, or historical events that contradict the
procedural record.

The package retains the full final procedural state, complete chronological
event ledger, and snapshots at year 0, every ten years, and the final year even
when the narrative uses only a fraction of them.

## Package generations

### v1: prototype contract

Version 1 documents the narrative-first prototype: Bible, story, graph, GM
index, and media. It is useful as design history and test input, but it is not a
supported desktop or mobile product format in the target state.

### v2: product contract

Version 2 begins when procedural generation becomes the required first pipeline
stage. Forge and both readers support v2 only. `package-v2.md` defines its
normative domains. Exact Draft 2020-12 schemas and the shared validation corpus
are frozen in the repository; representative real-world evidence remains a
release gate.

There is no v1 migration or conversion promise. A v1 package is rejected with a
clear instruction to regenerate it using a v2 Forge.

## Content and media guarantees

- Target content profile: mature dark fantasy.
- Every graph node has one full PNG, one thumbnail PNG, and one playable MIDI.
- No package-size ceiling is imposed by Forge.
- Package contents are immutable and content-addressed.
- Saves and GM conversation history never live inside or modify the package.
- Same seed, inputs, model bytes, configuration, and reproducibility profile
  produce the same canonical content on the same supported machine profile.

## Core principles

1. Procedural facts before narrative invention.
2. Structured contracts before prose.
3. Deterministic algorithms wherever possible.
4. Validate and checkpoint every durable boundary.
5. Abort rather than silently degrade authoritative world generation.
6. Mandatory complete media rather than partial packages.
7. Immutable content and separate local mutable state.
8. Strict spoiler isolation by data selection, not prompt instruction.
9. Offline operation after explicit model downloads.
10. Native reader parity and one cross-platform behavior contract.
11. Model/provider abstraction without weakening package contracts.
12. No telemetry, cloud inference, cloud saves, or remote content services.

## Non-goals

- Runtime world generation in the Player
- Cloud generation, accounts, telemetry, or synchronization
- Multiplayer or shared campaigns
- Editing authoritative procedural facts after generation
- A full desktop story reader or editor
- v1 package support in released Forge or Player applications
- A fixed package-size limit
- Exact cross-machine equality for nondeterministic model inference

## Success criteria

StoryTeller reaches its target when a user can generate a v2 package from a
seed, interrupt and resume without changing canonical results, import the
accepted package on either mobile platform, read with complete media, and hold a
persistent chunk-streamed GM conversation that cannot access unrevealed facts.
