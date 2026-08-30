# StoryTeller

StoryTeller is a local-first system for generating and reading complete mature
dark-fantasy interactive books. It combines a deterministic procedural world,
AI-authored narrative, branching choices, illustrations, MIDI music, and a
private on-device Game Master.

> This documentation set is the project truth source. Roadmap checkboxes describe
> delivery state only when backed by the phase's required evidence.

## How it works

```text
Forge desktop application
  procedural world -> Bible -> reconciliation -> story -> graph
  -> image + thumbnail + structured score + MIDI for every node -> GM index
  -> .story v2

Player mobile application
  import + validate -> read + choose + listen -> local save
  -> reveal-filtered context -> chunk-streamed local GM
```

## Product promises

- Procedural world generation is mandatory.
- One continent is the default; scale is configurable.
- Geography and simulated history are authoritative and immutable.
- Full procedural data remains in the package.
- The package includes a generated world map and maps for every region.
- Every node has a full image, thumbnail, authoritative score, and derived MIDI.
- Android and iOS implement the same package and behavior contracts.
- Saves and GM conversations remain local and outside `.story` files.
- There are no accounts, cloud saves, telemetry, ads, or remote inference.
- The apps are free; internet is used only for explicit model download.

## Forge target workflow

### Install

Development installs use Python and the repository source:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Release builds provide platform launchers under `win/`, `lin/`, and `mac/`.
The eventual GUI is a thin wrapper over the same CLI and is Wine-compatible.

### Download models

```bash
forge download-models
```

Downloads must show license/source information, support resume, and verify a
pinned checksum before a model becomes usable.

### Generate

The final CLI shape is defined in `api.md`. A representative invocation is:

```bash
forge generate \
  --title "The Ashen Continent" \
  --tone mature_dark_fantasy \
  --seed 42 \
  --world-width 128 \
  --world-height 128 \
  --metres-per-world-cell 8000 \
  --history-years 500 \
  --continents 1 \
  --output ./output/ashen
```

Generation fails if authoritative world simulation, reconciliation, required
media, provenance, or package acceptance fails. It does not publish a partial
package.

### Resume

```bash
forge resume --output ./output/ashen
```

Resume verifies the run specification and every reused artifact's dependencies,
fingerprint, path, and hash. Missing or invalid work is regenerated; valid work
is not repeated.

### Observe progress

```bash
tail -f ./output/ashen/pipeline_events.jsonl
```

The CLI and GUI use the same versioned JSONL event stream. The GUI may start,
cancel, and resume Forge, but never invokes model backends directly.

### Validate a package

```bash
forge validate-package ./output/ashen/The_Ashen_Continent.story
```

Validation covers ZIP safety, v2 schemas, content hashes, provenance,
cross-references, complete media coverage, PNG decoding/dimensions, MIDI parsing
and duration, and undeclared files.

## Player target workflow

1. Install the free Android or iOS app.
2. On first launch, approve the local GM model download.
3. The app resumes and checksum-verifies the download.
4. Transfer a `.story` v2 file by any user-controlled file mechanism.
5. Import it. The app validates before adding it to the library.
6. Read, choose, and listen entirely offline.
7. Open Game Master chat for chunk-streamed, locally generated answers.

The Player rejects v1 packages; it does not migrate them. The user must
regenerate the story with a v2 Forge.

## Local data

```text
Imported package (read-only)
  <story-id>/content/...

App-private mutable state
  <story-id>/save_state.json
  <story-id>/gm_history.json
  <story-id>/bookmarks.json
```

Deleting a story asks whether its local save history should also be deleted.
Nothing is synchronized to a cloud service.

## `.story` formats

### v1

The prototype narrative-first format contains Bible/story/graph/index/media
content. It remains documented for historical context only; no released component,
schema bundle, or retained fixture supports it.

### v2

The product format contains authoritative procedural domains, the full event
ledger, snapshots at year 0, every ten years and the final year, an explicit
coordinate system, artifact provenance, strict asset inventory, and reveal
policy. `package-v2.md` defines the normative layout; `schemas/v2`, the shared
fixture corpus, and Python/Kotlin/Swift validators make it executable.

## Repository map

| Path | Responsibility |
|---|---|
| `src/worldgen/` | Procedural simulation |
| `src/application/` | Forge use cases |
| `src/pipeline/` | Plans, contracts, execution policy, batches, events |
| `src/models/` | Narrative and media pipeline steps |
| `src/storage/` | Checkpoints, manifests, packages, acceptance |
| `schemas/` | Machine-readable artifact contracts |
| `droid/` | Native Android Player |
| `ios/` | Native iOS Player and llama.cpp bridge |
| `win/`, `lin/`, `mac/` | Desktop packaging and launcher integration |
| `docs/` | Sole authoritative documentation and rewrite plan |

## Documentation

- `goal.md`: product boundaries and success criteria
- `design.md`: generation, reading, save, and GM behavior
- `arch.md`: implementation architecture and v1/v2 formats
- `api.md`: public Python, CLI, event, package, GUI, and reader contracts
- `test.md`: target verification and release gates
- `compliance.md`: licenses, privacy, content, and store obligations
- `roadmap.md`: remaining ordered delivery work and evidence gates

## Support posture

The product targets local operation rather than hosted service availability.
Diagnostics consist of local logs, package validation reports, model checksums,
and reproducibility records that users choose to share.
