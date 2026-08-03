"""CLI entry point for StoryTeller Forge.

Commands:
    forge generate          Full pipeline run
    forge download-models   Download GGUF models from Hugging Face
    forge resume            Resume generation from checkpoint
    forge config            Show/set model configuration
    forge verify            Verify .story file hash
    forge info              Show pipeline checkpoint status
    forge package           Package output directory into .story
    forge validate-all      Validate all artifacts in a directory
    forge validate-story    Validate story against bible
    forge validate-graph    Validate graph against schema
    forge validate-bible    Validate bible against schema
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="forge",
        description="StoryTeller Forge — AI-powered interactive story generator",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ── forge generate ─────────────────────────────────────────────────
    gen_parser = subparsers.add_parser("generate", help="Run the full pipeline")
    gen_parser.add_argument("--seed", type=int, default=42)
    gen_parser.add_argument("--tone", type=str, default="dark_fantasy")
    gen_parser.add_argument("--title", type=str, default="Untitled World")
    gen_parser.add_argument("--temperature", type=float, default=0.7)
    gen_parser.add_argument("--config", type=str, default="config/models.yaml")
    gen_parser.add_argument("--output", type=str, default="output")

    # ── forge download-models ──────────────────────────────────────────
    dl_parser = subparsers.add_parser("download-models", help="Download GGUF models")
    dl_parser.add_argument("--with-images", action="store_true",
                            help="Also download SDXL-Turbo image model")
    dl_parser.add_argument("--models-dir", type=str, default="~/.storyteller/models",
                            help="Models directory")

    # ── forge resume ───────────────────────────────────────────────────
    resume_parser = subparsers.add_parser("resume", help="Resume from checkpoint")
    resume_parser.add_argument("--output", type=str, default="output",
                                help="Output directory with checkpoint.db")
    resume_parser.add_argument("--config", type=str, default="config/models.yaml")

    # ── forge config ───────────────────────────────────────────────────
    cfg_parser = subparsers.add_parser("config", help="Show/edit configuration")
    cfg_parser.add_argument("--set", type=str, nargs=2, metavar=("KEY", "VALUE"),
                              help="Set a config value (e.g., --set text.model qwen2.5-7b)")
    cfg_parser.add_argument("--config", type=str, default="config/models.yaml")

    # ── forge verify ───────────────────────────────────────────────────
    ver_parser = subparsers.add_parser("verify", help="Verify .story hash")
    ver_parser.add_argument("story_path", type=str, help="Path to .story file")
    ver_parser.add_argument("--expected-hash", type=str, default=None,
                              help="Expected SHA256 hash (optional)")

    # ── forge info ─────────────────────────────────────────────────────
    info_parser = subparsers.add_parser("info", help="Show checkpoint/state info")
    info_parser.add_argument("--output", type=str, default="output",
                              help="Output directory")

    # ── forge package ──────────────────────────────────────────────────
    pkg_parser = subparsers.add_parser("package", help="Package into .story")
    pkg_parser.add_argument("--seed", type=int, default=42)
    pkg_parser.add_argument("--output", type=str, default="output")
    pkg_parser.add_argument("--config", type=str, default="config/models.yaml")

    # ── forge validate-story ───────────────────────────────────────────
    val_parser = subparsers.add_parser("validate-story", help="Story vs bible consistency")
    val_parser.add_argument("story_path", type=str)
    val_parser.add_argument("bible_path", type=str)

    # ── forge validate-graph ───────────────────────────────────────────
    vg_parser = subparsers.add_parser("validate-graph", help="Validate graph schema")
    vg_parser.add_argument("graph_path", type=str)
    vg_parser.add_argument("--schemas-dir", type=str, default="docs/schemas")

    # ── forge validate-all ─────────────────────────────────────────────
    va_parser = subparsers.add_parser("validate-all", help="Validate all artifacts in a dir")
    va_parser.add_argument("artifact_dir", type=str, help="Directory with JSON artifacts")
    va_parser.add_argument("--schemas-dir", type=str, default="docs/schemas")

    # ── forge validate-bible ───────────────────────────────────────────
    vb_parser = subparsers.add_parser("validate-bible", help="Validate bible schema")
    vb_parser.add_argument("bible_path", type=str)
    vb_parser.add_argument("--schemas-dir", type=str, default="docs/schemas")

    args = parser.parse_args()

    commands: dict[str, Any] = {
        "generate": _cmd_generate,
        "download-models": _cmd_download_models,
        "resume": _cmd_resume,
        "config": _cmd_config,
        "verify": _cmd_verify,
        "info": _cmd_info,
        "package": _cmd_package,
        "validate-all": _cmd_validate_all,
        "validate-story": _cmd_validate_story,
        "validate-graph": _cmd_validate_graph,
        "validate-bible": _cmd_validate_bible,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(0)


# ═══════════════════════════════════════════════════════════════════════════════
# Command implementations
# ═══════════════════════════════════════════════════════════════════════════════


def _cmd_generate(args: Any) -> None:
    """Run the full generation pipeline."""
    print("=== StoryTeller Forge ===\n")

    config = _load_config(args.config)

    text_gen = _create_text_generator(config)
    image_gen = _create_image_generator(config)
    music_gen = _create_music_generator()

    from src.job_queue import PipelineContext
    from src.models.art_director import ArtDirector
    from src.models.game_designer import GameDesigner
    from src.models.image_generator_step import ImageGeneratorStep
    from src.models.music_generator_step import MusicGeneratorStep
    from src.models.story_writer import StoryWriter
    from src.models.world_builder import WorldBuilder
    from src.storage.checkpoint import CheckpointStore
    from src.storage.indexer import GmIndexer
    from src.storage.orchestrator import Orchestrator
    from src.storage.packager import Packager

    ctx = PipelineContext(
        run_id=f"run_{args.seed:04d}",
        seed=args.seed,
        config=config,
        output_dir=args.output,
    )
    ctx.state["tone"] = args.tone
    ctx.state["title"] = args.title
    ctx.state["temperature"] = args.temperature

    checkpoint_store = CheckpointStore(f"{args.output}/checkpoint.db")

    steps = {
        "world_builder": WorldBuilder(text_gen, config=config),
        "art_director": ArtDirector(text_gen, config=config),
        "story_writer": StoryWriter(text_gen, config=config),
        "game_designer": GameDesigner(text_gen, config=config),
        "image_generator": ImageGeneratorStep(image_gen, config=config, output_dir=args.output),
        "music_generator": MusicGeneratorStep(text_gen, music_gen, config=config, output_dir=args.output),
        "indexer": GmIndexer(),
        "packager": Packager(output_dir=args.output),
    }

    print(f"Text:  llama-cpp/{getattr(text_gen, 'model_name', '?')} ({getattr(text_gen, 'quantization', '?')})")
    print(f"Image: {getattr(image_gen, 'provider', '?')}/{getattr(image_gen, 'model_name', '?')}")
    print(f"Music: {getattr(music_gen, 'provider', '?')}")
    print(f"Seed: {args.seed}, Tone: {args.tone}, Title: {args.title}\n")

    import asyncio
    orchestrator = Orchestrator(checkpoint_store, cast(dict[str, Any], steps))
    output = asyncio.run(orchestrator.run(ctx))

    print(f"\n=== Generation Complete ===")
    print(f"Artifact: {output.artifact_id}")
    print(f"Package: {output.data.get('package_path', 'N/A')}")


def _cmd_download_models(args: Any) -> None:
    """Download GGUF models from Hugging Face."""
    models_dir = str(Path(args.models_dir).expanduser())

    # Find pull_models.sh relative to this file
    script_dir = Path(__file__).resolve().parent.parent / "scripts"
    pull_script = script_dir / "pull_models.sh"

    if not pull_script.exists():
        print(f"Error: Model download script not found at {pull_script}")
        print("Models can be downloaded manually from Hugging Face.")
        print("  Qwen2.5-7B-Instruct-GGUF Q4_K_M → ~/.storyteller/models/")
        print("  SDXL-Turbo Q8_0 → ~/.storyteller/models/")
        sys.exit(1)

    print(f"Downloading GGUF models to {models_dir}...")
    print(f"Running: bash {pull_script}")

    cmd = ["bash", str(pull_script)]
    if args.with_images:
        cmd.append("--with-images")

    try:
        subprocess.run(cmd, check=True)
        print("\nModels downloaded successfully.")
        print(f"Location: {models_dir}")
    except subprocess.CalledProcessError as e:
        print(f"\nDownload failed with exit code {e.returncode}.")
        print("You can download models manually from Hugging Face.")
        sys.exit(1)


def _cmd_resume(args: Any) -> None:
    """Resume generation from a checkpoint."""
    checkpoint_path = Path(args.output) / "checkpoint.db"

    if not checkpoint_path.exists():
        print(f"Error: No checkpoint found at {checkpoint_path}")
        print("Run 'forge generate' first, or specify a different --output directory.")
        sys.exit(1)

    from src.storage.checkpoint import CheckpointStore

    store = CheckpointStore(str(checkpoint_path))
    entries = store.load_all()

    if not entries:
        print("Error: Checkpoint database exists but contains no entries.")
        sys.exit(1)

    print("=== Resume from Checkpoint ===\n")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Completed steps:")

    for entry in entries:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.completed_at))
        print(f"  Phase {entry.phase}: {entry.step_name} "
              f"(seed={entry.seed}, {entry.artifact_id or 'no-id'}, {ts})")

    highest = store.get_highest_completed_phase()
    print(f"\nResuming from phase {highest + 1}...")
    print(f"(8 total phases — {highest} complete, {8 - highest} remaining)\n")

    # Re-run generate with the seed from the first checkpoint
    seed = entries[0].seed
    config = _load_config(args.config)

    from src.job_queue import PipelineContext
    from src.models.art_director import ArtDirector
    from src.models.game_designer import GameDesigner
    from src.models.image_generator_step import ImageGeneratorStep
    from src.models.music_generator_step import MusicGeneratorStep
    from src.models.story_writer import StoryWriter
    from src.models.world_builder import WorldBuilder
    from src.storage.indexer import GmIndexer
    from src.storage.orchestrator import Orchestrator
    from src.storage.packager import Packager

    text_gen = _create_text_generator(config)
    image_gen = _create_image_generator(config)
    music_gen = _create_music_generator()

    ctx = PipelineContext(
        run_id=f"resume_{seed:04d}_{int(time.time())}",
        seed=seed,
        config=config,
        output_dir=args.output,
    )

    steps = {
        "world_builder": WorldBuilder(text_gen, config=config),
        "art_director": ArtDirector(text_gen, config=config),
        "story_writer": StoryWriter(text_gen, config=config),
        "game_designer": GameDesigner(text_gen, config=config),
        "image_generator": ImageGeneratorStep(image_gen, config=config, output_dir=args.output),
        "music_generator": MusicGeneratorStep(text_gen, music_gen, config=config, output_dir=args.output),
        "indexer": GmIndexer(),
        "packager": Packager(output_dir=args.output),
    }

    import asyncio
    orchestrator = Orchestrator(store, cast(dict[str, Any], steps))
    output = asyncio.run(orchestrator.run(ctx))

    print(f"\n=== Resume Complete ===")
    print(f"Artifact: {output.artifact_id}")
    print(f"Package: {output.data.get('package_path', 'N/A')}")


def _cmd_config(args: Any) -> None:
    """Show or edit the model configuration."""
    config_path = Path(args.config)

    if not config_path.exists():
        print(f"No config file found at {config_path}")
        print("Default configuration:")
        config = _stub_config()
        _print_config(config)
        return

    from src.config import AppConfig

    config = AppConfig.from_yaml(str(config_path))

    if args.set:
        key, value = args.set
        print(f"Setting {key} = {value}")
        _set_config_value(config, key, value)
        # Write back
        with open(config_path, "w") as f:
            f.write(_config_to_yaml(config))
        print(f"Updated {config_path}")
    else:
        print(f"Configuration: {config_path}\n")
        _print_config(config)


def _cmd_verify(args: Any) -> None:
    """Verify a .story file hash."""
    story_path = Path(args.story_path)

    if not story_path.exists():
        print(f"Error: File not found: {story_path}")
        sys.exit(1)

    if story_path.suffix != ".story":
        print(f"Warning: File does not have .story extension: {story_path}")

    data = story_path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()

    # Try to read manifest from ZIP for seed/title info
    try:
        import zipfile
        with zipfile.ZipFile(story_path) as zf:
            if "manifest.json" in zf.namelist():
                manifest = json.loads(zf.read("manifest.json"))
                title = manifest.get("title", "?")
                seed = manifest.get("seed", "?")
                print(f"Story:   {title}")
                print(f"Seed:    {seed}")
    except Exception:
        pass

    print(f"SHA256:  {sha}")

    if args.expected_hash:
        if sha == args.expected_hash:
            print(f"\n\u2714 Hash matches expected value.")
        else:
            print(f"\n\u2716 Hash MISMATCH!")
            print(f"  Expected: {args.expected_hash}")
            print(f"  Got:      {sha}")
            sys.exit(1)


def _cmd_info(args: Any) -> None:
    """Show pipeline checkpoint status and output files."""
    output_dir = Path(args.output)

    print("=== Pipeline Info ===\n")
    print(f"Output directory: {output_dir.resolve()}\n")

    # Checkpoint status
    checkpoint_path = output_dir / "checkpoint.db"
    if checkpoint_path.exists():
        from src.storage.checkpoint import CheckpointStore

        store = CheckpointStore(str(checkpoint_path))
        entries = store.load_all()
        highest = store.get_highest_completed_phase()

        print(f"Checkpoint: {checkpoint_path}")
        print(f"Progress: {highest}/8 phases complete\n")

        if entries:
            print("Completed steps:")
            for entry in entries:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.completed_at))
                print(f"  Phase {entry.phase}: {entry.step_name} "
                      f"(seed={entry.seed}, id={entry.artifact_id or '?'}, {ts})")
        else:
            print("  (checkpoint exists but is empty)")
    else:
        print("Checkpoint: not found (no active pipeline run)")
        print("  Run 'forge generate' to start one.\n")

    # Output files
    print(f"\nOutput files:")
    json_files = sorted(output_dir.glob("*.json"))
    story_files = sorted(output_dir.glob("*.story"))
    png_dir = output_dir / "images"
    midi_dir = output_dir / "midi"

    for f in json_files:
        size = f.stat().st_size
        print(f"  {f.name} ({_human_size(size)})")

    for f in story_files:
        size = f.stat().st_size
        print(f"  {f.name} ({_human_size(size)})")

    if png_dir.exists():
        png_count = len(list(png_dir.glob("*.png")))
        print(f"  images/ ({png_count} PNG files)")

    if midi_dir.exists():
        midi_count = len(list(midi_dir.glob("*.mid")))
        print(f"  midi/ ({midi_count} MIDI files)")

    events_log = output_dir / "pipeline_events.jsonl"
    if events_log.exists():
        lines = sum(1 for _ in open(events_log))
        print(f"  pipeline_events.jsonl ({lines} events)")


def _cmd_package(args: Any) -> None:
    """Package output directory into a .story ZIP."""
    output_dir = Path(args.output)

    if not output_dir.exists():
        print(f"Error: Output directory not found: {output_dir}")
        print("Run 'forge generate' first.")
        sys.exit(1)

    # Check for required artifacts
    required = ["bible.json", "story.json", "graph.json"]
    missing = [r for r in required if not (output_dir / r).exists()]
    if missing:
        print(f"Error: Missing required artifacts: {', '.join(missing)}")
        print("Run 'forge generate' first.")
        sys.exit(1)

    print("Packaging .story file...\n")

    config = _load_config(args.config)

    from src.job_queue import PipelineContext
    from src.storage.packager import Packager

    ctx = PipelineContext(
        run_id=f"pkg_{args.seed:04d}",
        seed=args.seed,
        config=config,
        output_dir=str(output_dir),
    )

    # Load artifacts from disk (ArtifactStore pre-loads them)
    for key in ["bible", "style_bible", "story", "graph", "images",
                 "midi", "gm_index", "manifest"]:
        val = ctx.outputs.get(key)
        if val is not None:
            print(f"  Loaded: {key}")

    # Ensure manifest exists
    if ctx.outputs.get("manifest") is None:
        import time
        ctx.outputs["manifest"] = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model_versions": {},
            "seed": args.seed,
            "title": "Packaged Story",
            "artifact_id": "",
            "stats": {},
        }

    import asyncio
    pkg = Packager(output_dir=str(output_dir))
    output = asyncio.run(pkg.run(ctx))

    print(f"\n=== Package Complete ===")
    print(f"Package: {output.data.get('package_path', 'N/A')}")
    print(f"Size:    {output.data.get('package_size', 0):,} bytes")
    sha = output.data.get('content_hash', '?')
    print(f"SHA256:  {sha}")


def _cmd_validate_story(args: Any) -> None:
    """Validate a story JSON against a bible JSON."""
    story_path = Path(args.story_path)
    bible_path = Path(args.bible_path)

    for p, name in [(story_path, "Story"), (bible_path, "Bible")]:
        if not p.exists():
            print(f"Error: {name} file not found: {p}")
            sys.exit(1)

    with open(story_path) as f:
        story = json.load(f)
    with open(bible_path) as f:
        bible = json.load(f)

    from src.validators.consistency import ConsistencyChecker

    checker = ConsistencyChecker()
    result = checker.check_all(bible, story)

    if result.is_consistent:
        print("\u2714 Valid: No Bible violations found.")
    else:
        print(result.format_for_retry())
        sys.exit(1)


def _cmd_validate_graph(args: Any) -> None:
    """Validate a graph JSON against graph.schema.json."""
    _validate_against_schema(args.graph_path, "graph", args.schemas_dir)


def _cmd_validate_all(args: Any) -> None:
    """Validate all JSON artifacts in a directory against their schemas."""
    import os

    artifact_dir = Path(args.artifact_dir)
    if not artifact_dir.exists():
        print(f"Error: Directory not found: {artifact_dir}")
        sys.exit(1)

    # Known artifact → schema mapping
    schema_map: dict[str, str] = {
        "bible": "bible",
        "style_bible": "style_bible",
        "story": "story",
        "graph": "graph",
        "gm_index": "gm_index",
        "manifest": "manifest",
    }

    # Find JSON files matching known artifact names
    json_files = sorted(artifact_dir.glob("*.json"))
    if not json_files:
        print(f"No JSON files found in {artifact_dir}")
        sys.exit(1)

    # Resolve schemas directory
    sd = _resolve_schemas_dir(args.schemas_dir)
    from src.validators.schema_validator import SchemaValidator

    validator = SchemaValidator(str(sd))
    available = set(validator.available_schemas)

    passed = 0
    failed = 0
    skipped = 0

    print(f"Validating artifacts in: {artifact_dir.resolve()}\n")

    for path in json_files:
        name = path.stem  # "bible.json" → "bible"
        schema_name = schema_map.get(name)

        if schema_name is None:
            skipped += 1
            continue

        if schema_name not in available:
            print(f"  ? {path.name}: schema '{schema_name}' not found")
            skipped += 1
            continue

        try:
            with open(path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"  ✗ {path.name}: invalid JSON ({e})")
            failed += 1
            continue

        result = validator.validate(data, schema_name)
        if result.is_valid:
            print(f"  ✓ {path.name}  ({schema_name}.schema.json)")
            passed += 1
        else:
            print(f"  ✗ {path.name}  ({schema_name}.schema.json)")
            for err in result.errors[:5]:  # Show first 5 errors
                loc = f" at {err.path}" if err.path else ""
                print(f"      {loc}: {err.message}")
            if len(result.errors) > 5:
                print(f"      ... and {len(result.errors) - 5} more errors")
            failed += 1

    print(f"\n{'='*50}")
    print(f"  {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'='*50}")

    if failed > 0:
        sys.exit(1)


def _cmd_validate_bible(args: Any) -> None:
    """Validate a bible JSON against bible.schema.json."""
    _validate_against_schema(args.bible_path, "bible", args.schemas_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _load_config(config_path: str) -> Any:
    """Load AppConfig from YAML or return stub."""
    from src.config import AppConfig

    path = Path(config_path)
    if path.exists():
        return AppConfig.from_yaml(str(path))

    print(f"Warning: {config_path} not found. Using stub configuration.")
    return _stub_config()


def _validate_against_schema(file_path: str, schema_name: str, schemas_dir: str) -> None:
    """Validate a JSON file against a named schema."""
    path = Path(file_path)
    if not path.exists():
        print(f"Error: File not found: {path}")
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    sd = _resolve_schemas_dir(schemas_dir)

    from src.validators.schema_validator import SchemaValidator

    validator = SchemaValidator(str(sd))
    result = validator.validate(data, schema_name)

    if result.is_valid:
        print(f"\u2714 {schema_name}.json is valid ({schema_name}.schema.json)")
    else:
        print(result.format_for_retry())
        sys.exit(1)


def _resolve_schemas_dir(schemas_dir: str) -> Path:
    """Find the schemas directory, trying multiple locations."""
    sd = Path(schemas_dir)
    if sd.exists():
        return sd
    # Try relative to forge/
    sd = Path("docs/schemas")
    if sd.exists():
        return sd
    # Try relative to project root
    sd = Path(__file__).resolve().parent.parent.parent / "docs" / "schemas"
    if sd.exists():
        return sd
    print(f"Error: Schemas directory not found: {schemas_dir}")
    print("Expected at: docs/schemas/")
    sys.exit(1)


def _create_text_generator(config: Any) -> Any:
    try:
        from src.backends.llm_backend import LlamaCppTextGenerator
        gen = LlamaCppTextGenerator(config.text_generator)
        print("Backend: llama-cpp (text)")
        return gen
    except Exception:
        pass
    print("Warning: No text backend. Using stub.")
    return _stub_text_gen()


def _create_image_generator(config: Any) -> Any:
    try:
        from src.backends.image_backend import SDCppImageGenerator
        gen = SDCppImageGenerator(config.image_generator)
        print("Backend: SD-CPP (image)")
        return gen
    except Exception:
        pass
    print("Warning: No image backend.")
    return _stub_image_gen()


def _create_music_generator() -> Any:
    from src.backends.midi_backend import AbcMusicGenerator
    return AbcMusicGenerator()


def _stub_text_gen() -> Any:
    class _Stub:
        provider: str = "stub"
        model_name: str = "mock"
        quantization: str = ""
        async def generate(self, prompt: str = "", **kw: Any) -> dict[str, Any]:
            raise RuntimeError("No text backend loaded")
        async def load(self) -> None: pass
        async def unload(self) -> None: pass
    return _Stub()


def _stub_image_gen() -> Any:
    class _Stub:
        provider: str = "stub"
        model_name: str = "mock"
        quantization: str = ""
        async def generate(self, prompt: str = "", **kw: Any) -> bytes:
            raise RuntimeError("No image backend")
        async def generate_thumbnail(self, image_bytes: bytes = b"", **kw: Any) -> bytes:
            return b""
        async def load(self) -> None: pass
        async def unload(self) -> None: pass
    return _Stub()


def _stub_config() -> Any:
    from src.config import AppConfig, ModelConfig, PipelineConfig, LimitsConfig, PathsConfig
    _m = ModelConfig
    return AppConfig(
        text_generator=_m(provider="llama_cpp", model="qwen2.5-7b-instruct",
                          quantization="Q4_K_M", repo="Qwen/Qwen2.5-7B-Instruct-GGUF",
                          file="qwen2.5-7b-instruct-q4_k_m.gguf"),
        validator=_m(provider="llama_cpp", model="phi-3.5-mini-instruct",
                     quantization="Q4_K_M", repo="microsoft/Phi-3.5-mini-instruct-GGUF",
                     file="phi-3.5-mini-instruct-q4_k_m.gguf"),
        image_generator=_m(provider="stable_diffusion_cpp", model="sdxl-turbo",
                           quantization="Q8_0", repo="stabilityai/sdxl-turbo-gguf",
                           file="sdxl-turbo-q8_0.gguf"),
        music_generator=_m(provider="abc-notation", model="via-text",
                           quantization="", repo="", file=""),
        game_master=_m(provider="llama_cpp", model="llama-3.2-3b-instruct",
                       quantization="Q4_K_M", repo="meta-llama/Llama-3.2-3B-Instruct-GGUF",
                       file="llama-3.2-3b-instruct-q4_k_m.gguf"),
        pipeline=PipelineConfig(),
        limits=LimitsConfig(),
        paths=PathsConfig(),
    )


def _print_config(config: Any) -> None:
    """Pretty-print the AppConfig."""
    print("Models:")
    for name in ["text_generator", "validator", "image_generator", "music_generator", "game_master"]:
        m = getattr(config, name)
        print(f"  {name}: {m.provider}/{m.model} ({m.quantization})")
    print(f"\nPipeline:")
    print(f"  workers: {config.pipeline.workers}")
    print(f"  max_retries: {config.pipeline.max_retries}")
    print(f"\nLimits:")
    print(f"  max_ram_mb: {config.limits.max_ram_mb}")
    print(f"  model_unload_threshold: {config.limits.model_unload_threshold}")
    print(f"\nPaths:")
    print(f"  models_dir: {config.paths.models_dir}")
    print(f"  output_dir: {config.paths.output_dir}")


def _set_config_value(config: Any, key: str, value: str) -> None:
    """Set a nested config value by dot-path key."""
    parts = key.split(".")
    obj = config
    for part in parts[:-1]:
        obj = getattr(obj, part)
    setattr(obj, parts[-1], _coerce_value(value))


def _coerce_value(value: str) -> Any:
    """Coerce string value to appropriate type."""
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _config_to_yaml(config: Any) -> str:
    """Serialize AppConfig to YAML string (simple format)."""
    lines: list[str] = []
    lines.append("# StoryTeller Forge — Model Configuration")
    lines.append("# Edit models here — no code changes needed.")
    lines.append("")
    lines.append("generators:")
    for name, label in [("text_generator", "text"), ("validator", "validator"),
                          ("image_generator", "image"), ("music_generator", "music"),
                          ("game_master", "game_master")]:
        m = getattr(config, name)
        lines.append(f"  {label}:")
        lines.append(f"    provider: {m.provider}")
        lines.append(f"    model: {m.model}")
        lines.append(f"    quantization: {m.quantization}")
        if m.repo:
            lines.append(f"    repo: {m.repo}")
        if m.file:
            lines.append(f"    file: {m.file}")

    lines.append("")
    lines.append("pipeline:")
    lines.append(f"  workers: {config.pipeline.workers}")
    lines.append(f"  max_retries: {config.pipeline.max_retries}")
    lines.append(f"  checkpoint_interval: {config.pipeline.checkpoint_interval}")
    lines.append(f"  failure_policy: quarantine")

    lines.append("")
    lines.append("limits:")
    lines.append(f"  max_ram_mb: {config.limits.max_ram_mb}")
    lines.append(f"  model_unload_threshold: {config.limits.model_unload_threshold}")

    lines.append("")
    lines.append("paths:")
    lines.append(f"  models_dir: {config.paths.models_dir}")
    lines.append(f"  prompts_dir: {config.paths.prompts_dir}")
    lines.append(f"  schemas_dir: {config.paths.schemas_dir}")
    lines.append(f"  output_dir: {config.paths.output_dir}")
    return "\n".join(lines) + "\n"


def _human_size(size: int) -> str:
    """Format byte count as human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size} {unit}"
        size //= 1024
    return f"{size} TB"
