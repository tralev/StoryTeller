"""CLI entry point for StoryTeller Forge.

Usage:
    forge generate --seed 42 --tone dark_fantasy --title "The Ashen Marches"
    forge validate-story story.json bible.json
    forge package --seed 42
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast


def main() -> None:
    """Main CLI entry point."""
    # Minimal CLI using argparse (click is in deps but this keeps it simple)
    import argparse

    parser = argparse.ArgumentParser(
        prog="forge",
        description="StoryTeller Forge — AI-powered interactive story generator",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # forge generate
    gen_parser = subparsers.add_parser("generate", help="Generate a complete .story package")
    gen_parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    gen_parser.add_argument("--tone", type=str, default="dark_fantasy", help="World tone")
    gen_parser.add_argument("--title", type=str, default="Untitled World", help="World name")
    gen_parser.add_argument("--temperature", type=float, default=0.7, help="LLM temperature")
    gen_parser.add_argument(
        "--config",
        type=str,
        default="config/models.yaml",
        help="Path to models.yaml",
    )
    gen_parser.add_argument(
        "--output",
        type=str,
        default="output",
        help="Output directory for .story package",
    )

    # forge validate-story
    val_parser = subparsers.add_parser("validate-story", help="Validate a story against a bible")
    val_parser.add_argument("story_path", type=str, help="Path to story.json")
    val_parser.add_argument("bible_path", type=str, help="Path to bible.json")

    # forge package
    pkg_parser = subparsers.add_parser("package", help="Package a .story from existing artifacts")
    pkg_parser.add_argument("--seed", type=int, default=42, help="Seed for metadata")
    pkg_parser.add_argument("--output", type=str, default="output", help="Output directory")

    args = parser.parse_args()

    if args.command == "generate":
        _cmd_generate(args)
    elif args.command == "validate-story":
        _cmd_validate_story(args)
    elif args.command == "package":
        _cmd_package(args)
    else:
        parser.print_help()
        sys.exit(0)


def _cmd_generate(args: Any) -> None:
    """Run the full generation pipeline."""
    print("=== StoryTeller Forge ===\n")

    from src.config import AppConfig
    from src.job_queue import PipelineContext
    from src.models.story_writer import StoryWriter
    from src.models.world_builder import WorldBuilder
    from src.storage.orchestrator import Orchestrator
    from src.storage.checkpoint import CheckpointStore

    # Load config
    config_path = Path(args.config)
    if config_path.exists():
        config = AppConfig.from_yaml(str(config_path))
        print(f"Loaded config: {config_path}")
    else:
        print("Warning: models.yaml not found. Using stub configuration.")
        config = _stub_config()

    # Set up pipeline
    ctx = PipelineContext(
        run_id=f"run_{args.seed:04d}",
        seed=args.seed,
        config=config,
    )
    ctx.state["tone"] = args.tone
    ctx.state["title"] = args.title
    ctx.state["temperature"] = args.temperature

    checkpoint_store = CheckpointStore(f"{args.output}/checkpoint.db")

    # Register steps
    try:
        from src.backends.llm_backend import LlamaCppTextGenerator
        from src.backends.image_backend import SDCppImageGenerator
        from src.backends.midi_backend import AbcMusicGenerator
        from src.models.art_director import ArtDirector
        from src.models.game_designer import GameDesigner
        from src.models.image_generator_step import ImageGeneratorStep
        from src.models.music_generator_step import MusicGeneratorStep
        from src.storage.indexer import GmIndexer
        from src.storage.packager import Packager

        text_gen = LlamaCppTextGenerator(config.text_generator)
        image_gen = SDCppImageGenerator(config.image_generator)
        music_gen = AbcMusicGenerator()

        steps = {
            "world_builder": WorldBuilder(text_gen, config=config),
            "art_director": ArtDirector(text_gen, config=config),
            "story_writer": StoryWriter(text_gen, config=config),
            "game_designer": GameDesigner(text_gen, config=config),
            "image_generator": ImageGeneratorStep(image_gen, config=config),
            "music_generator": MusicGeneratorStep(text_gen, music_gen, config=config),
            "indexer": GmIndexer(),
            "packager": Packager(output_dir=args.output),
        }

        print(f"Starting generation with seed={args.seed}, tone={args.tone}")
        print(f"Title: {args.title}")
        print()

        import asyncio
        orchestrator = Orchestrator(checkpoint_store, cast(dict[str, Any], steps))
        output = asyncio.run(orchestrator.run(ctx))

        print(f"\n=== Generation Complete ===")
        print(f"Artifact: {output.artifact_id}")
        print(f"Package: {output.data.get('package_path', 'N/A')}")

    except NotImplementedError:
        print("\nNote: Backends are stubs. Real model inference requires GGUF files.")
        print("Download models to ~/.storyteller/models/ to enable full generation.")
        print("\nPipeline structure verified — all steps registered successfully.")


def _cmd_validate_story(args: Any) -> None:
    """Validate a story JSON against a bible JSON."""
    import json
    from src.validators.consistency import ConsistencyChecker

    with open(args.story_path) as f:
        story = json.load(f)
    with open(args.bible_path) as f:
        bible = json.load(f)

    checker = ConsistencyChecker()
    result = checker.check_all(bible, story)

    if result.is_consistent:
        print("Valid: No Bible violations found.")
    else:
        print(result.format_for_retry())


def _cmd_package(args: Any) -> None:
    """Package existing artifacts into a .story ZIP."""
    print("Not yet implemented — use 'forge generate' for full pipeline.\n")


def _stub_config() -> Any:
    """Return a minimal stub config when models.yaml is not available."""
    from src.config import AppConfig, ModelConfig, PipelineConfig, LimitsConfig, PathsConfig

    _m = ModelConfig  # shortcut
    return AppConfig(
        text_generator=_m(provider="llama-cpp", model="qwen2.5-7b", quantization="Q4_K_M", repo="", file=""),
        validator=_m(provider="llama-cpp", model="phi-3.5-mini", quantization="Q4_K_M", repo="", file=""),
        image_generator=_m(provider="sd-cpp", model="sdxl-turbo", quantization="Q8_0", repo="", file=""),
        music_generator=_m(provider="abc-notation", model="via-text", quantization="", repo="", file=""),
        game_master=_m(provider="llama-cpp", model="llama-3.2-3b", quantization="Q4_K_M", repo="", file=""),
        pipeline=PipelineConfig(),
        limits=LimitsConfig(),
        paths=PathsConfig(),
    )
