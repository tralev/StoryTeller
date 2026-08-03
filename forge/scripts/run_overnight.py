#!/usr/bin/env python3
"""Overnight test runner for StoryTeller Forge.

Produces:
  output/
  ├── <title>_<seed>.story          # The generated package
  ├── pipeline_events.jsonl         # Append-only event log
  ├── checkpoint.db                 # SQLite checkpoint (for resume)
  ├── summary.json                  # Final summary report
  └── ram_samples.jsonl             # RAM usage samples (every 30s)

Can be interrupted (SIGINT) and resumed — checkpoint is saved
after every successful step.

Usage:
    python forge/scripts/run_overnight.py --seed 42 --tone dark_fantasy --title "The Ashen Marches"
    python forge/scripts/run_overnight.py --resume  # Resume from last checkpoint
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add forge/src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


# ── event logger ──────────────────────────────────────────────────────────────

class EventLogger:
    """Append-only JSONL event log."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._file = open(path, "a")  # noqa: SIM115

    def log(self, event: str, **kwargs: Any) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **kwargs,
        }
        self._file.write(json.dumps(entry) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


# ── RAM sampler ──────────────────────────────────────────────────────────────

class RamSampler:
    """Samples RAM usage every 30 seconds in a background thread."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._running = False
        self._thread: Any = None

    def start(self) -> None:
        import threading

        self._running = True
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _sample_loop(self) -> None:
        while self._running:
            try:
                sample = self._get_ram()
                with open(self.path, "a") as f:
                    f.write(json.dumps(sample) + "\n")
            except Exception:
                pass
            time.sleep(30)

    @staticmethod
    def _get_ram() -> dict[str, Any]:
        """Get RAM usage in MB. Uses psutil if available, else /proc/meminfo."""
        try:
            import psutil
            mem = psutil.virtual_memory()
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_mb": mem.total // (1024 * 1024),
                "used_mb": mem.used // (1024 * 1024),
                "available_mb": mem.available // (1024 * 1024),
                "percent": mem.percent,
            }
        except ImportError:
            # Fallback for macOS/Linux without psutil
            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_mb": 0,
                "used_mb": 0,
                "available_mb": 0,
                "percent": 0,
                "note": "psutil not installed — install with: pip install psutil",
            }


# ── main runner ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="StoryTeller Forge — Overnight Generation Runner",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--tone", type=str, default="dark_fantasy")
    parser.add_argument("--title", type=str, default="The Ashen Marches")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--config", type=str, default="config/models.yaml")
    parser.add_argument("--output", type=str, default="output")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    args = parser.parse_args()

    # ── setup output directory ────────────────────────────────────────
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    # ── event log ─────────────────────────────────────────────────────
    logger = EventLogger(str(out / "pipeline_events.jsonl"))
    logger.log("pipeline_started", seed=args.seed, tone=args.tone, title=args.title)

    # ── RAM sampler ──────────────────────────────────────────────────
    sampler = RamSampler(str(out / "ram_samples.jsonl"))
    sampler.start()

    # ── signal handler for graceful shutdown ─────────────────────────
    interrupted = False

    def _on_sigint(signum: int, frame: Any) -> None:
        nonlocal interrupted
        interrupted = True
        logger.log("sigint_received", message="Saving checkpoint and exiting...")
        print("\n\nInterrupted! Checkpoint will be saved. Resume with --resume.")
        sys.exit(1)

    signal.signal(signal.SIGINT, _on_sigint)

    # ── load config ──────────────────────────────────────────────────
    try:
        from src.config import AppConfig
        config_path = Path(args.config)
        if config_path.exists():
            config = AppConfig.from_yaml(str(config_path))
            logger.log("config_loaded", path=str(config_path))
        else:
            logger.log("config_missing", path=str(config_path))
            config = _stub_config()
    except Exception as e:
        logger.log("config_error", error=str(e))
        print(f"Config error: {e}")
        sys.exit(1)

    # ── initialize backends ──────────────────────────────────────────
    import asyncio

    try:
        from src.backends.ollama_backend import OllamaTextGenerator
        from src.backends.image_backend import SDCppImageGenerator
        from src.backends.midi_backend import AbcMusicGenerator

        text_gen = OllamaTextGenerator(model_name="qwen2.5:7b")
        image_gen = SDCppImageGenerator(config.image_generator)
        music_gen = AbcMusicGenerator()

        logger.log("backends_initialized",
                     text="ollama/qwen2.5:7b",
                     image=config.image_generator.model,
                     music="abc-notation")
    except Exception as e:
        logger.log("backend_error", error=str(e))
        print(f"Backend error: {e}")
        sys.exit(1)

    # ── initialize steps ─────────────────────────────────────────────
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
        run_id=f"run_{args.seed:04d}_{int(time.time())}",
        seed=args.seed,
        config=config,
    )
    ctx.state["tone"] = args.tone
    ctx.state["title"] = args.title
    ctx.state["temperature"] = args.temperature
    ctx.state["start_time"] = time.time()

    checkpoint = CheckpointStore(str(out / "checkpoint.db"))

    steps: dict[str, Any] = {
        "world_builder": WorldBuilder(text_gen, config=config),
        "art_director": ArtDirector(text_gen, config=config),
        "story_writer": StoryWriter(text_gen, config=config),
        "game_designer": GameDesigner(text_gen, config=config),
        "image_generator": ImageGeneratorStep(image_gen, config=config),
        "music_generator": MusicGeneratorStep(text_gen, music_gen, config=config),
        "indexer": GmIndexer(),
        "packager": Packager(output_dir=str(out)),
    }

    logger.log("pipeline_configured",
                steps=list(steps.keys()),
                seed=args.seed)

    # ── run ──────────────────────────────────────────────────────────
    step_times: dict[str, float] = {}
    step_hashes: dict[str, str] = {}
    step_status: dict[str, str] = {}

    async def _run() -> None:
        orchestrator = Orchestrator(checkpoint, steps)
        manifest = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "model_versions": {
                "text_generator": "ollama/qwen2.5:7b",
                "image_generator": config.image_generator.model,
                "music_generator": "abc-notation/music21",
            },
            "seed": args.seed,
            "title": args.title,
            "artifact_id": "",
            "stats": {},
        }
        ctx.outputs["manifest"] = manifest

        try:
            output = await orchestrator.run(ctx)
            logger.log("pipeline_completed",
                        artifact_id=output.artifact_id,
                        package_path=output.data.get("package_path", "N/A"))
        except Exception as e:
            logger.log("pipeline_failed", error=str(e))
            raise

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        logger.log("pipeline_interrupted")
        print("\nInterrupted — checkpoint saved. Resume with --resume.")
    except Exception as e:
        logger.log("pipeline_error", error=str(e), type=type(e).__name__)
        print(f"\nPipeline failed: {e}")
    finally:
        sampler.stop()

    # ── summary report ───────────────────────────────────────────────
    total_time = time.time() - ctx.state.get("start_time", time.time())
    outputs = ctx.outputs

    # Compute content hashes
    for key, data in outputs.items():
        if isinstance(data, dict) and key not in ("manifest",):
            try:
                step_hashes[key] = hashlib.sha256(
                    json.dumps(data, sort_keys=True).encode()
                ).hexdigest()[:16]
            except Exception:
                step_hashes[key] = "error"

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": args.seed,
        "tone": args.tone,
        "title": args.title,
        "total_duration_seconds": round(total_time, 1),
        "backends": {
            "text": "ollama/qwen2.5:7b",
            "image": config.image_generator.model,
            "music": "abc-notation/music21",
        },
        "artifacts": {
            "bible": step_hashes.get("bible", "missing"),
            "style_bible": step_hashes.get("style_bible", "missing"),
            "story": step_hashes.get("story", "missing"),
            "graph": step_hashes.get("graph", "missing"),
            "images": step_hashes.get("images", "missing"),
            "midi": step_hashes.get("midi", "missing"),
            "gm_index": step_hashes.get("gm_index", "missing"),
        },
        "package_path": outputs.get("manifest", {}).get(
            "artifact_id",
            "not generated",
        ),
        "events_log": str(out / "pipeline_events.jsonl"),
        "ram_log": str(out / "ram_samples.jsonl"),
    }

    with open(out / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    logger.log("summary_written", path=str(out / "summary.json"))
    logger.close()

    # ── print summary ────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  StoryTeller Forge — Overnight Run Complete")
    print("=" * 60)
    print(f"  Title:   {args.title}")
    print(f"  Tone:    {args.tone}")
    print(f"  Seed:    {args.seed}")
    print(f"  Time:    {total_time:.0f}s ({total_time/60:.1f}m)")
    print()
    print("  Artifacts:")
    for name, h in step_hashes.items():
        status = "✓" if h != "error" else "✗"
        print(f"    {status} {name}: {h}")
    print()
    print(f"  Events:  {out / 'pipeline_events.jsonl'}")
    print(f"  RAM log: {out / 'ram_samples.jsonl'}")
    print(f"  Summary: {out / 'summary.json'}")
    print(f"  Checkpoint: {out / 'checkpoint.db'}")
    print("=" * 60)


def _stub_config() -> Any:
    from src.config import AppConfig, ModelConfig, PipelineConfig, LimitsConfig, PathsConfig
    _m = ModelConfig
    return AppConfig(
        text_generator=_m(provider="ollama", model="qwen2.5:7b", quantization="", repo="", file=""),
        validator=_m(provider="ollama", model="qwen2.5:7b", quantization="", repo="", file=""),
        image_generator=_m(provider="sd-cpp", model="sdxl-turbo", quantization="Q8_0", repo="", file=""),
        music_generator=_m(provider="abc-notation", model="via-text", quantization="", repo="", file=""),
        game_master=_m(provider="ollama", model="llama3.2:3b", quantization="", repo="", file=""),
        pipeline=PipelineConfig(),
        limits=LimitsConfig(),
        paths=PathsConfig(),
    )


if __name__ == "__main__":
    main()
