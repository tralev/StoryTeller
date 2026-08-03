# StoryTeller

> Generate interactive, multimedia "Choose Your Own Adventure" books with AI — complete with original lore, branching narratives, illustrations, music, and an AI Game Master.
>
> **Same seed + same models + same machine = reproducible book. Every time.**

## Quick Start

### Prerequisites

**App B (The Forge) — Desktop:**
- Windows, macOS, or Linux (including Wine)
- 16 GB total RAM (10 GB free for models)
- ~20 GB disk space for models and output
- No GPU required

**App A (The Player) — Mobile:**
- iOS 16+ or Android 13+
- 6 GB total RAM (3 GB free for Game Master)
- ~500 MB storage per .story file
- Internet required on first launch (to download the Game Master model, ~2 GB)
- Fully offline after model download

---

## Installation

### App B — The Forge

```bash
git clone https://github.com/yourorg/storyteller.git
cd storyteller/forge

python3.9 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -e .

# Pull text model via Ollama (requires Ollama installed)
ollama pull qwen2.5:7b

# Or use llama-cpp-python backend:
# Download GGUF files to ~/.storyteller/models/
```

---

## Usage

### Generating a Story (App B)

#### Full Pipeline

```bash
# Generate a complete .story file (with a seed for reproducibility)
forge generate \
  --title "The Ashen Marches" \
  --tone dark_fantasy \
  --seed 1234567890 \
  --output ./output

# This runs all 11 pipeline steps:
# Sequential: Bible → Style Bible → Story → Decision Points → Graph Skeleton → Node Texts
# Parallel:   Images (15 jobs) + MIDI (15 jobs) — different models, run concurrently
# Sequential: GM Index → Packaging

# Output: ./output/The_Ashen_Marches.story

# Regenerate the exact same book later:
forge generate \
  --title "The Ashen Marches" \
  --tone dark_fantasy \
  --seed 1234567890 \
  --output ./output

# The .story file will have the SAME SHA256 hash.
```

#### Resuming a Failed Run

The Forge automatically saves checkpoints after each phase. Re-running `forge generate` with the same `--output` directory resumes from the last checkpoint.

#### Individual Steps

```bash
# Generate a complete .story file
forge generate --title "The Iron Schism" --tone heroic_fantasy --seed 42 --output ./output

# Validate a story against its bible (consistency check)
forge validate-story ./output/story.json ./output/bible.json

# Package existing artifacts
forge package --seed 42 --output ./output
```

### Overnight Test

For long-running generation with full logging:

```bash
python forge/scripts/run_overnight.py --seed 42 --tone dark_fantasy --title "The Ashen Marches"

# Monitor progress:
tail -f output/pipeline_events.jsonl
```

#### Configuration

Edit `config/models.yaml` to change models, paths, RAM limits, and worker count. See [api.md](api.md) for the full config reference.

### Reading a Story (App A)

#### Importing a .story File

Transfer the `.story` file to your phone via USB, cloud drive, AirDrop, or email. Open the StoryTeller app, tap **Import Story**, and select the file.

The app splits the package:
- `content/` → read-only storage (shared if reinstalling)
- `save/` → private app storage (synced via cloud if enabled)

#### Reading

- Each page shows an illustration, story text, and choices
- Background MIDI music plays and crossfades between scenes
- Tap a choice to advance — your decisions set flags that affect later scenes
- Progress auto-saves after every choice

#### Talking to the Game Master

- Tap **🎙️ Game Master** on any page
- Ask about the scene, characters, lore, or world
- The GM answers in character, word-by-word, never spoiling the plot
- All conversations saved in `save/gm_history.json`

#### Endings

The story has multiple endings gated by your choices. When you reach one, you'll see which decisions led there and how many endings remain undiscovered.

---

## .story File Format

A `.story` file is a deterministic ZIP archive with two separate stores:

```
story.story
├── content/                  # IMMUTABLE — never changes
│   ├── manifest.json         # Version, seed, model info
│   ├── bible.json            # World Bible
│   ├── style_bible.json      # Art style constraints
│   ├── story.json            # Linear narrative
│   ├── graph.json            # CYOA branching graph
│   ├── gm_index.json         # Pre-computed GM retrieval index
│   ├── images/               # 512×512 PNG illustrations
│   ├── midi/                 # MIDI music files
│   └── thumbnails/           # 128×128 previews
└── save/                     # MUTABLE — reader-created
    ├── save_state.json       # current_node, flags, visited
    ├── gm_history.json       # past GM conversations
    └── bookmarks.json        # user bookmarks
```

**Reproducibility:** Same seed + same models + same machine → identical `content/` (bit-for-bit, verified by SHA256). Cross-machine determinism is not guaranteed. A `reproducibility_profile` (CPU arch, thread count, quantization) is recorded for matching.

---

## Reproducibility

Every generated artifact records its seed and model versions:

```json
{
  "schema_version": 1,
  "generator_version": "0.4.1",
  "pipeline_version": 7,
  "created_at": "2026-08-03T14:22:00Z",
  "seed": 1234567890,
  "model_versions": {
    "text_generator": "qwen2.5-7b-instruct-q4_k_m",
    "validator": "phi-3.5-mini-instruct-q4_k_m",
    "image_generator": "sdxl-turbo-q8_0",
    "music_generator": "qwen2.5-7b-instruct-q4_k_m"
  }
}
```

To regenerate the exact same book: preserve the models, use the same seed.

```bash
forge generate --seed 1234567890 --title "The Ashen Marches" --tone dark_fantasy
forge verify --seed 1234567890 --expected-hash a1b2c3d4...
```

---

## Model Abstraction

The Forge never references specific models directly. It uses interfaces:

- **TextGenerator** — generates structured text from prompts
- **Validator** — validates content against rules and schemas
- **ImageGenerator** — generates images from text prompts
- **MusicGenerator** — generates ABC notation from scene descriptions
- **GameMaster** — answers reader questions with context

Concrete models are mapped in `config/models.yaml`. Swap models by editing one file — no code changes.

---

## Troubleshooting

### App B

| Problem | Solution |
|---|---|
| `forge: command not found` | Activate venv: `source .venv/bin/activate` |
| Out of memory | Reduce RAM limit: `forge config --max-ram 8` |
| Model download fails | Download manually from Hugging Face |
| Pipeline fails at step N | Run `forge resume` |
| Output differs from previous run | Check seed is set. Verify same machine, same thread count, same quantization. Check reproducibility_profile in metadata. |
| Wine: application crashes | Wine ≥ 8.0. Test on native OS first. |

### App A

| Problem | Solution |
|---|---|
| .story won't import | Verify `.story` extension, generated by Forge v1.0+ |
| GM slow on first question | Model loads lazily. First question: 3-5 sec. Subsequent: faster. |
| MIDI sounds wrong | App bundles a dark-fantasy SoundFont. Restart if issues persist. |
| App crashes on older device | Minimum 6 GB RAM, iOS 16 / Android 13. |
| Progress lost | App auto-saves. Cloud sync restores save/ from other devices. |

---

## Project Structure

```
StoryTeller/
├── docs/                 # All documentation
│   ├── goal.md
│   ├── arch.md
│   ├── design.md
│   ├── roadmap.md
│   ├── test.md
│   ├── readme.md
│   ├── api.md
│   └── schemas/          # JSON Schema contracts
├── forge/                # App B — The Forge (Python)
├── droid/                # App A — Android (Kotlin)
├── ios/                  # App A — iOS (Swift)
├── mac/                  # Native macOS launcher (future)
└── windows/              # Native Windows launcher (future)
```

---

## License

[MIT](LICENSE)

---

## Related Documents

- **[goal.md](goal.md)** — Project vision and design principles
- **[arch.md](arch.md)** — Technical architecture: stack, schemas, patterns
- **[design.md](design.md)** — Behavioral design: pipeline flows, UX flows
- **[api.md](api.md)** — Interface definitions and CLI reference
- **[roadmap.md](roadmap.md)** — Development phases and milestones
