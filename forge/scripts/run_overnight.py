#!/usr/bin/env python3
"""Overnight test runner for StoryTeller Forge.

Produces:
  output/
  ├── <title>_<seed>.story          # The generated package
  ├── pipeline_events.jsonl         # Append-only event log
  ├── checkpoint.db                 # SQLite checkpoint (for resume)
  ├── summary.json                  # Final summary report
  └── ram_samples.jsonl             # RAM usage samples (every 30s)

Sequential RAM strategy (fits 10 GB):
  1. Load text model   (~4.7 GB)
  2. Bible → Story → Graph → Music ABC notation
  3. Unload text model
  4. Load SDXL          (~5.0 GB)
  5. Generate images
  6. Unload SDXL
  7. Indexer → Packager
  ⇒ Peak RAM: ~5.5 GB (model + Python + OS)

Can be interrupted (SIGINT) and resumed — checkpoint is saved
after every successful step.

Usage:
    python forge/scripts/run_overnight.py --seed 7 --tone heroic_fantasy --title "The Crystal Accord"
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


# ── model names (for logging / manifest) ─────────────────────────────────────

TEXT_MODEL_NAME = "qwen2.5-7b-instruct-q4_k_m"
IMAGE_MODEL_NAME = "sdxl-turbo-q8_0"
MUSIC_MODEL_NAME = "qwen2.5-7b-instruct-q4_k_m"


# ── main runner ──────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="StoryTeller Forge — Overnight Generation Runner",
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--tone", type=str, default="heroic_fantasy")
    parser.add_argument("--title", type=str, default="The Crystal Accord")
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
    def _on_sigint(signum: int, frame: Any) -> None:
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
        from src.backends.llm_backend import LlamaCppTextGenerator
        from src.backends.image_backend import SDCppImageGenerator
        from src.backends.midi_backend import AbcMusicGenerator

        text_gen = LlamaCppTextGenerator(config.text_generator)
        image_gen = SDCppImageGenerator(config.image_generator)
        music_gen = AbcMusicGenerator()

        logger.log("backends_initialized",
                     text=TEXT_MODEL_NAME,
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
        "image_generator": ImageGeneratorStep(image_gen, config=config, output_dir=str(out)),
        "music_generator": MusicGeneratorStep(text_gen, music_gen, config=config, output_dir=str(out)),
        "indexer": GmIndexer(),
        "packager": Packager(output_dir=str(out)),
    }

    logger.log("pipeline_configured",
                steps=list(steps.keys()),
                seed=args.seed,
                strategy="sequential_ram")

    # ── model info for manifest ──────────────────────────────────────
    model_info = {
        "text_generator": TEXT_MODEL_NAME,
        "image_generator": IMAGE_MODEL_NAME,
        "music_generator": MUSIC_MODEL_NAME,
    }

    # ── phase: TEXT (load → generate → music → unload) ───────────────
    text_phase_start = time.time()

    logger.log("model_loading", model=TEXT_MODEL_NAME, phase="text+music")
    asyncio.run(text_gen.load())
    logger.log("model_loaded", model=TEXT_MODEL_NAME, ram_mb=text_gen.ram_usage_mb)

    orchestrator = Orchestrator(checkpoint, steps)

    # Phase 1-4: Bible → Story → Graph → Node Texts
    text_steps = ["world_builder", "art_director", "story_writer", "game_designer"]
    for step_name in text_steps:
        step_start = time.time()
        logger.log("step_started", step=step_name, phase="text")
        try:
            result = asyncio.run(orchestrator.execute_step(
                steps[step_name], ctx, step_name,
            ))
            elapsed = time.time() - step_start
            logger.log("step_completed", step=step_name, duration_s=round(elapsed, 1))
        except Exception as e:
            logger.log("step_failed", step=step_name, error=str(e))
            raise

    # Phase 5: Music ABC (uses text model)
    step_start = time.time()
    logger.log("step_started", step="music_generator", phase="text")
    try:
        result = asyncio.run(orchestrator.execute_step(
            steps["music_generator"], ctx, "music_generator",
        ))
        elapsed = time.time() - step_start
        logger.log("step_completed", step="music_generator", duration_s=round(elapsed, 1))
    except Exception as e:
        logger.log("step_failed", step="music_generator", error=str(e))
        raise

    # Unload text model
    logger.log("model_unloading", model=TEXT_MODEL_NAME)
    asyncio.run(text_gen.unload())
    logger.log("model_unloaded", model=TEXT_MODEL_NAME)

    text_phase_elapsed = time.time() - text_phase_start
    logger.log("phase_completed", phase="text+music",
                duration_s=round(text_phase_elapsed, 1),
                steps=text_steps + ["music_generator"])

    # ── phase: IMAGE (load SDXL → generate images → unload) ──────────
    image_phase_start = time.time()

    logger.log("model_loading", model=IMAGE_MODEL_NAME, phase="image")
    try:
        asyncio.run(image_gen.load())
        logger.log("model_loaded", model=IMAGE_MODEL_NAME, ram_mb=image_gen.ram_usage_mb)
    except FileNotFoundError as e:
        logger.log("image_model_skipped",
                    reason="SDXL GGUF not found — using placeholder images",
                    path=str(e))
        print(f"Note: SDXL not found — generating placeholder images. {e}")
    except Exception as e:
        logger.log("image_model_error", error=str(e))
        print(f"Warning: SDXL load failed — using placeholder images. {e}")

    step_start = time.time()
    logger.log("step_started", step="image_generator", phase="image")
    try:
        result = asyncio.run(orchestrator.execute_step(
            steps["image_generator"], ctx, "image_generator",
        ))
        elapsed = time.time() - step_start
        logger.log("step_completed", step="image_generator", duration_s=round(elapsed, 1))
    except Exception as e:
        logger.log("step_failed", step="image_generator", error=str(e))
        raise

    # Unload image model
    logger.log("model_unloading", model=IMAGE_MODEL_NAME)
    try:
        asyncio.run(image_gen.unload())
    except Exception:
        pass
    logger.log("model_unloaded", model=IMAGE_MODEL_NAME)

    image_phase_elapsed = time.time() - image_phase_start
    logger.log("phase_completed", phase="image",
                duration_s=round(image_phase_elapsed, 1))

    # ── phase: FINALIZE (no model needed) ────────────────────────────
    finalize_start = time.time()

    for step_name in ["indexer", "packager"]:
        step_start = time.time()
        logger.log("step_started", step=step_name, phase="finalize")
        try:
            result = asyncio.run(orchestrator.execute_step(
                steps[step_name], ctx, step_name,
            ))
            elapsed = time.time() - step_start
            logger.log("step_completed", step=step_name, duration_s=round(elapsed, 1))
        except Exception as e:
            logger.log("step_failed", step=step_name, error=str(e))
            raise

    finalize_elapsed = time.time() - finalize_start
    logger.log("phase_completed", phase="finalize",
                duration_s=round(finalize_elapsed, 1),
                steps=["indexer", "packager"])

    # ── stop RAM sampler ─────────────────────────────────────────────
    sampler.stop()
    logger.log("pipeline_completed")

    # ── summary report ───────────────────────────────────────────────
    total_time = time.time() - ctx.state.get("start_time", time.time())
    outputs = ctx.outputs

    step_hashes: dict[str, str] = {}
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
        "backends": model_info,
        "ram_strategy": "sequential_load_unload",
        "phases": {
            "text+music_s": round(text_phase_elapsed, 1),
            "image_s": round(image_phase_elapsed, 1),
            "finalize_s": round(finalize_elapsed, 1),
            "total_s": round(total_time, 1),
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
            "artifact_id", "not generated",
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
    print(f"  Title:     {args.title}")
    print(f"  Tone:      {args.tone}")
    print(f"  Seed:      {args.seed}")
    print(f"  Time:      {total_time:.0f}s ({total_time/60:.1f}m)")
    print(f"  RAM:       sequential (peak ~{max(text_gen.ram_usage_mb, image_gen.ram_usage_mb)} MB)")
    print()
    print("  Phases:")
    print(f"    Text+Music:  {text_phase_elapsed:.0f}s ({text_phase_elapsed/60:.1f}m)")
    print(f"    Images:      {image_phase_elapsed:.0f}s ({image_phase_elapsed/60:.1f}m)")
    print(f"    Finalize:    {finalize_elapsed:.0f}s ({finalize_elapsed/60:.1f}m)")
    print()
    print("  Artifacts:")
    for name, h in step_hashes.items():
        status = "\u2713" if h != "error" else "\u2717"
        print(f"    {status} {name}: {h}")
    print()
    print(f"  Events:   {out / 'pipeline_events.jsonl'}")
    print(f"  RAM log:  {out / 'ram_samples.jsonl'}")
    print(f"  Summary:  {out / 'summary.json'}")
    print(f"  Checkpoint: {out / 'checkpoint.db'}")
    print("=" * 60)


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


if __name__ == "__main__":
    main()
