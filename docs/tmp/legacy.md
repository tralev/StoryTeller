# Legacy Documentation Coverage Ledger

## Purpose

This is a non-normative historical ledger. It records material present in the
existing `docs/*.md` files that is
not reproduced in the target-state documents under `docs/tmp/`. It is a coverage
ledger, not a second specification: an omitted item may be useful historical
evidence, a current implementation detail, or an assumption deliberately replaced
by the new design.

All items marked **Import** in the original comparison have since been absorbed
into the appropriate authoritative documents (`prompts.md`, `configuration.md`,
`diagnostics.md`, `ux.md`, `release.md`, `accessibility.md`, `threat-model.md`, or
the core contracts). The per-source entries below preserve audit provenance; they
are not an outstanding-work list.

The comparison covers:

- `docs/api.md`
- `docs/arch.md`
- `docs/compliance.md`
- `docs/design.md`
- `docs/goal.md`
- `docs/readme.md`
- `docs/roadmap.md`
- `docs/test.md`

The target set compared against includes the product, architecture, API, design,
compliance, testing, package, accessibility, security, release, decision, glossary,
index, and nine rewrite-roadmap documents in `docs/tmp/`.

## How to read the dispositions

| Disposition | Meaning |
|---|---|
| **Import** | Valuable material is genuinely absent and should be added to a target document when its contract is known. |
| **Roadmap only** | Current-state or historical evidence belongs in `docs/roadmap.md`, not in future-state specifications. |
| **Generate later** | The information should come from code, configuration, benchmarks, or release evidence after implementation. |
| **Superseded** | An accepted target decision intentionally replaces the old statement. Do not copy it. |
| **Review** | The old material raises a useful question, but should not become normative without a decision. |

## Executive result

The target set covers the intended product more completely than the legacy set in
the areas that define the rewrite: mandatory procedural generation, immutable
procedural facts, full world retention, `.story` v2, strict spoiler isolation,
external local saves, complete per-node media, offline operation, validators,
pipeline and backend boundaries, security, accessibility, and release gates.

The important legacy-only material is mostly operational detail:

1. a concrete prompt-template retention and resolution policy;
2. a future generated configuration reference with effective defaults;
3. detailed end-user troubleshooting and diagnostic guidance;
4. reader, ending, library, and GM interaction wireframes;
5. explicit local transfer/import methods;
6. benchmark records and model resource profiles tied to hardware;
7. current implementation and test inventories that must remain in the current
   roadmap until the rewrite replaces them.

## `docs/goal.md`

### Legacy-only product details

| Material not repeated in the target set | Disposition | Reason |
|---|---|---|
| A linear story of approximately 30 pages before conversion to a choice graph | **Superseded** | The target is world-first and graph-oriented; it deliberately avoids a fixed page count. |
| Approximately 15 story nodes | **Superseded** | The target imposes complete media per node but no fixed node count. |
| Fixed 512×512 illustrations | **Review** | Dimensions belong in the Phase 6 package/media profiles, not the product goal. |
| Forge resource promise of 10 GB RAM and a 2–12 hour, at worst 24-hour, run | **Generate later** | Resource budgets must be measured against the selected model registry and hardware profiles. |
| Mobile GM budget of 3 GB RAM | **Generate later** | This must be established by Android and iOS benchmark evidence. |
| Cloud-drive import and cloud save synchronization | **Superseded** | Packages may arrive through local mechanisms, but saves are local-only and no cloud-save feature is permitted. |
| Token/word streaming as the GM response contract | **Superseded** | The accepted contract is semantic chunk streaming. |
| The original Generator → Validator → Normalizer → Exporter summary | **Import** | Preserve its intent as a short conceptual explanation, while using the target pipeline's typed steps, reconciliation, acceptance, and publication boundaries. |
| Runtime procedural generation listed as a non-goal | **Superseded** | Procedural generation is now a mandatory Forge stage before the World Bible. |
| User editing listed as a non-goal | **Review** | The target does not promise editing, but this should be made explicit in `goal.md` if still intended. |
| Non-fantasy genres listed as a v1 non-goal | **Review** | The accepted initial product is mature dark fantasy; whether other genres remain a permanent non-goal is not decided. |

## `docs/readme.md`

### Current operational instructions absent from the target README

- Exact current prerequisites: Python 3.9+, iOS 16+, Android 13+, disk/RAM
  estimates, and the old package-size estimate.
- Existing installation commands and current `forge` command examples.
- The current overnight runner and monitoring commands.
- Current resume, validation, packaging, and individual-step workflows.
- Current model download script usage and old Qwen/SDXL RAM estimates.
- The current v1 package tree, including its embedded `save/` directory.
- Current model abstraction/provider names and configuration paths.
- The complete current repository tree and its per-file descriptions.
- Current troubleshooting tables for Forge and Player.
- Current limitations for real-model generation, batching, checkpoints, mobile
  native bindings, model bundling, compliance, and documentation.

**Disposition: Roadmap only / Generate later.** These instructions describe the
repository as it existed, whereas `readme.md` is the authoritative target entry
point. Historical working commands are not contracts. After the
rewrite, command and configuration sections should be generated or tested against
the CLI so that examples cannot drift.

### Useful concepts to carry forward

- **Import:** a task-oriented troubleshooting guide keyed by stable error codes,
  including model download, memory pressure, resume rejection, invalid package,
  corrupt media, and mobile import failures.
- **Import:** a concise local transfer section covering file picker, USB/shared
  storage, AirDrop or platform share sheets, and other user-initiated local file
  transfers. None of these mechanisms may imply cloud-save synchronization.
- **Generate later:** an effective configuration reference, supported model list,
  and hardware/resource table derived from the model registry and benchmark
  evidence.
- **Generate later:** a repository map derived from the final source layout after
  the reorganization, rather than preserving the obsolete tree manually.

## `docs/api.md`

### Current API surface not reproduced verbatim

The legacy API document contains concrete signatures and examples for:

- `TextGenerator`, `Validator`, `ImageGenerator`, `MusicGenerator`, and
  `GameMaster`;
- `JobQueue`, dispatch, workers, futures, and shutdown;
- `PipelineContext` and its untyped state/artifact access;
- `ValidationResult` and `Normalizer`;
- the full current `config/models.yaml` sample, worker counts, RAM budget, and
  filesystem paths;
- the existing CLI command and option reference.

**Disposition: Roadmap only.** The target API deliberately replaces these
signatures with typed ports, repositories, run specifications, validation results,
error contracts, CLI behavior, launcher IPC, v2 package data, GM chunks, and local
saves. Copying old signatures into the future API would create two authorities.

### API documentation still needed after implementation

- **Generate later:** a machine-checked CLI reference including exit codes,
  examples, environment variables, and effective configuration precedence.
- **Generate later:** an authoritative configuration schema and sample generated
  from the typed settings model.
- **Import:** normalization/canonicalization rules should be exposed as an explicit
  public contract when Phase 6 freezes v2. They currently appear across the target
  architecture, package candidate, and tests, but not as a single API section.
- **Import:** stable diagnostic codes need a catalog mapping each code to retry,
  abort, quarantine, or user-action semantics.

## `docs/arch.md`

### Current implementation detail absent from target architecture

- The exact legacy `JobQueue + PipelineStep` implementation and its current
  sequential/parallel dispatch pattern.
- The old Python, Swift, Kotlin, framework, media library, SQLite, ZIP, and
  PyInstaller technology inventory.
- The complete current source tree and concrete module names.
- The v1 artifact envelope examples, version numbers, and v1 `.story` schemas.
- Concrete JSONL event examples from the current pipeline.
- The current normalizer implementation and validator-retry snippets.
- The current same-machine reproducibility profile, including architecture,
  thread count, quantization, model, and prompt versions.
- Legacy partial-failure behavior that allowed a package with missing node assets.

**Disposition: Roadmap only**, except where explicitly noted below. The target
architecture defines the replacement and the rewrite roadmaps say when obsolete
modules are removed.

### Architecture policies worth preserving

- **Import:** prompt templates are versioned assets; published prompt versions are
  immutable, old versions are retained, and a pipeline/configuration version
  resolves the exact prompt version. Provenance must record the selected prompt
  ID and content hash. This should become a normative subsection of
  `arch.md`.
- **Import:** make the distinction between ephemeral pipeline state and durable
  project/artifact state explicit with a lifecycle table. The target persistence
  design contains the mechanics, but the old explanation remains useful.
- **Import:** retain structured append-only event examples once the target event
  schema is frozen; examples should include run, step, node, attempt, error code,
  duration, and artifact ID.
- **Superseded:** do not retain partial-package acceptance. Every narrative node
  requires a full image, thumbnail, authoritative score, and MIDI track, and generation aborts if the
  mandatory set cannot be completed.

## `docs/design.md`

### Detailed legacy flow not repeated

- The old four-stage and eleven-step pipeline diagrams.
- Exact story-shape heuristics: three chapters, about fifteen nodes, seven to ten
  short lines per node, and ten words per line.
- The old ordering of World Bible, style, story, graph, music, images, GM index,
  and packaging.
- Detailed ASCII layouts for reader screens, choices, GM chat, and ending screens.
- The embedded two-store package model in which mutable saves lived inside the
  package and could be cloud synchronized.
- The Qwen/Phi/SDXL load/unload RAM diagram and fixed memory figures.
- Transfer examples such as USB, cloud-drive file import, and AirDrop.

### Design disposition

- **Superseded:** the old pipeline order. The accepted order is procedural physical
  world → civilizations/history → World Bible → reconciliation → narrative graph
  → mandatory media → GM knowledge → accepted package.
- **Superseded:** the embedded save store and cloud synchronization. Saves are
  external, local, package-bound, and persistent.
- **Superseded:** fixed narrative size and prose-shape rules unless they become
  configurable content-profile defaults.
- **Generate later:** model memory figures and load/unload diagrams from measured
  backend profiles.
- **Import:** reader, library, ending, choice, progress, model-download, and GM
  wireframes should become a dedicated UX document. Accessibility requirements
  must be annotated directly on those flows.
- **Import:** local import/transfer behavior should distinguish source of a file
  from storage of a save. A package may be selected through a platform file
  provider; StoryTeller itself still provides no cloud saves or remote service.

## `docs/compliance.md`

### Legacy-only assertions

- A fixed table of candidate model licenses and attribution statements.
- A specific “Built with Llama” attribution instruction.
- Assumed Apple and Google age-rating outcomes.
- Old claims about a 200 MB download threshold and Wi-Fi-only model download.
- A fixed generated-content disclaimer.
- Privacy language allowing optional cloud sync.

### Compliance disposition

- **Superseded:** optional cloud sync, because the accepted privacy model is
  local-only saves, offline execution after explicit downloads, no telemetry, and
  no remote StoryTeller service.
- **Review:** model attribution and license statements must be derived from the
  exact release allowlist and reviewed license texts; the old assertions must not
  be treated as legal conclusions.
- **Generate later:** store age rating and large-download disclosures must be
  verified against the store rules and actual artifact sizes at release time.
- **Import:** define a reviewed, localized generated-content and mature-content
  disclosure template. `compliance.md` requires disclosure but does not
  freeze its user-facing wording.

## `docs/test.md`

### Current test evidence absent from target tests

- The old file-by-file test inventory and counts.
- Claims about current real-model loading and generation times.
- Fixed time budgets for Bible, chapter, image, and full-story generation.
- Fixed mobile RAM and time-to-first-token targets.
- The old GitHub Actions cadence and exact local pytest examples.
- Manual prose, image, music, UX, and GM quality categories.
- Legacy tests for cloud synchronization and token streaming.

### Test disposition

- **Roadmap only:** test counts and current pass/fail evidence. They are snapshots,
  not target contracts, and should carry a date, commit, platform, and command.
- **Generate later:** performance thresholds should be stored as named hardware and
  model profiles with regression tolerances. The target test document correctly
  avoids pretending one universal limit is valid.
- **Import:** keep human quality review rubrics, but make them scoreable and tie
  failures to release gates. The target release/test documents establish the gate;
  a later quality rubric should define anchors and reviewer procedure.
- **Generate later:** CI examples must match actual workflow files and should be
  linked rather than maintained as divergent pseudocode.
- **Superseded:** cloud-save and token-streaming scenarios. Replace them with
  local-save isolation and semantic chunk-stream tests.

## `docs/roadmap.md`

Before this documentation set became authoritative, `docs/roadmap.md` was treated
as the current-state authority. Its historical phases,
completed checkboxes, operational evidence, and known gaps are intentionally not
duplicated in future-state documents. The following information is therefore
legacy-only but must remain available until replaced:

- Phase 0 through Phase 5 implementation history.
- Phase 5.6 hardening sections A–X and their completion markers.
- Existing Forge service, artifact, checkpoint, event, acceptance, and policy work.
- Existing Android and iOS scaffolding and incomplete native integration.
- Current procedural-world modules and tests already present in `src/worldgen/`.
- Current test counts, type-check status, real-model proof, and unresolved release
  work.

### Roadmap conflicts that must be corrected, not imported

| Legacy roadmap statement | Target decision |
|---|---|
| Procedural generation is a later Phase 7.5 option | It is the mandatory first generation domain and is rewritten in Phases 1–4. |
| Narrative, procedural, and hybrid generation modes coexist | There is one product flow; procedural facts are always authoritative. |
| `WorldSnapshot` may be a small optional bridge | Full normalized procedural output is retained in `.story` v2, even when narrative does not use it. |
| Phase 8 provides v1-to-v2 migration tools | No migration path is required; mobile and desktop product surfaces consume v2 only. |
| Mobile can import the legacy package layout | Both players implement only the Phase 6 frozen v2 contract. |
| Save data may live in or sync with a package | Saves are external, local, package-bound, and never cloud-synchronized by StoryTeller. |
| Assets can be quarantined while packaging continues | Every node requires a full image, thumbnail, authoritative score, and MIDI; unresolved mandatory media aborts publication. |
| GM responses use token streaming | GM responses use persistent semantic chunks. |

### Current-state consistency issues to audit

- The Phase 5.6 summary and its section checkboxes can disagree about how many
  sections are complete. Recalculate status from code and tests.
- Procedural tasks may still appear unchecked even though `src/worldgen/` and
  related tests exist. Record what is implemented versus what is merely scaffolded.
- Test counts and static-analysis claims are volatile; attach them to a dated
  verification record rather than prose that appears timeless.
- Phase numbers in the legacy roadmap and rewrite roadmaps refer to different
  programs. When the rewrite begins, replace the obsolete phase structure rather
  than merging both sequences.

## Cross-document legacy contradictions

These contradictions exist within the original documentation and are intentionally
resolved by the target set:

1. Saves are described both as mutable package content and as separate state. The
   target uses external local saves only.
2. The old product promises partial asset tolerance while later hardening proposes
   coverage policy. The target requires complete node media.
3. Procedural generation is both a non-goal and a future optional mode. The target
   makes it mandatory and authoritative.
4. Streaming is described at token/word granularity. The target uses semantic
   chunks and persists committed chunks.
5. Package v1 appears as a reader contract in legacy docs. The target documents it
   only as prototype history; product readers support v2 only.
6. Cloud providers are mentioned for import and save synchronization without a
   consistent privacy boundary. The target permits user-initiated local file
   selection but no StoryTeller cloud saves, telemetry, or remote service.
7. Fixed hardware, size, time, and model estimates are presented as stable product
   facts. The target requires measured profiles and does not enforce a maximum
   `.story` size.

## Recommended additions to the target documentation set

The following documents or sections are not yet fully represented by the target
set:

### 1. `prompts.md`

Define prompt IDs, immutable versions, template inputs, output schemas, hash and
provenance rules, deprecation, retention, and the pipeline/configuration mechanism
that resolves a prompt version. This is the strongest architecture policy found
only in the legacy docs.

### 2. `configuration.md`

After Phase 1, generate a self-contained reference from typed settings. Include
defaults, precedence, model registry, world size controls, one-continent default,
seed, worker/resource limits, paths, execution policies, and CLI mappings.

### 3. `ux.md`

Add annotated flows or wireframes for Forge progress, desktop launcher, library,
import, reader, choices, ending, save recovery, model download, and GM chunks.
Reference `accessibility.md` for every interactive state.

### 4. `diagnostics.md`

Catalog stable error codes and recovery actions. Cover configuration, model
availability, checksums, resource exhaustion, invalid worlds, reconciliation,
mandatory media, checkpoint mismatch, malicious/corrupt packages, save mismatch,
and native inference failures.

### 5. Generated operational references

Do not author these as static promises. Produce them from implemented sources:

- CLI help and exit-code reference;
- effective configuration and supported-model matrix;
- repository/module map;
- benchmark and resource profiles;
- test inventory and release evidence;
- package schema/API reference after the Phase 6 freeze.

## Material that should not be copied into target specifications

- fixed 30-page, 15-node, or prose-line limits;
- embedded or cloud-synchronized saves;
- token-level GM streaming;
- optional procedural generation modes;
- v1 reader support or a v1-to-v2 migration promise;
- partial packages with missing required media;
- unverified model-license conclusions or store-policy thresholds;
- stale file trees, test counts, performance numbers, and implementation signatures;
- an imposed maximum `.story` size.

## Completion statement

Every distinct category of material in the eight original Markdown documents is
accounted for above as target-worthy, current-state-only, generated-later,
superseded, or requiring review. The original documents remain necessary only for
historical provenance only. They cannot override any contract or decision in this
directory.
