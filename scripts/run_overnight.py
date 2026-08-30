#!/usr/bin/env python3
"""Overnight test runner for StoryTeller Forge.

Produces:
  tmp/output/
  ├── <title>_<seed>.story          # The generated package
  ├── pipeline_events.jsonl         # Typed pipeline events (GenerateStory)
  ├── runner_events.jsonl           # Runner-level lifecycle events
  ├── checkpoint.db                 # SQLite checkpoint (for resume)
  ├── summary.json                  # Final summary report
  ├── ram_samples.jsonl             # RAM usage samples (every 30s)
  └── fatal_error.log               # Traceback only when the runner crashes

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
    python scripts/run_overnight.py --seed 7 --tone heroic_fantasy --title "The Crystal Accord"
    python scripts/run_overnight.py --resume  # Resume from last checkpoint
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add the repository root so the ``src`` package resolves from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
assert (Path(sys.path[0]) / "src").is_dir(), f"src package does not exist below: {sys.path[0]}"


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
    parser.add_argument("--output", type=str, default="tmp/output")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    from src.cli import add_world_spec_arguments, world_spec_cli_kwargs

    add_world_spec_arguments(parser)
    args = parser.parse_args()

    # ── setup output directory ────────────────────────────────────────
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    # ── event log ─────────────────────────────────────────────────────
    # Runner-level lifecycle events live in runner_events.jsonl.
    # GenerateStory writes the typed pipeline event stream to
    # pipeline_events.jsonl — separate files avoid format interleaving.
    logger = EventLogger(str(out / "runner_events.jsonl"))
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

    # ── resolve config (GenerateStory handles stub fallback) ──────
    config_path = Path(args.config)

    # ── build request ──────────────────────────────────────────────
    from src.application import GenerateStory, GenerationRequest

    if args.resume:
        from src.domain.run_spec import RunSpec

        run_spec_path = out / "run_spec.json"
        if not run_spec_path.is_file():
            raise ValueError("--resume requires output/run_spec.json")
        request = GenerationRequest.from_run_spec(
            RunSpec.from_dict(json.loads(run_spec_path.read_text())),
            config_path=str(config_path),
            output_dir=str(out),
            resume=True,
        )
    else:
        request = GenerationRequest(
            seed=args.seed,
            title=args.title,
            tone=args.tone,
            temperature=args.temperature,
            config_path=str(config_path),
            output_dir=str(out),
            resume=False,
            **world_spec_cli_kwargs(args),
        )

    # ── log request ────────────────────────────────────────────────
    logger.log(
        "pipeline_configured",
        seed=request.seed,
        title=request.title,
        tone=request.tone,
        output=str(out),
    )

    # ── run generation through the shared service ─────────────────
    import asyncio
    import traceback

    service = GenerateStory()
    try:
        result = asyncio.run(service.execute(request))
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.log("pipeline_interrupted")
        sampler.stop()
        logger.close()
        raise
    except Exception:
        # Preserve the full traceback for next-day troubleshooting even
        # when the terminal that launched the container is long gone.
        trace = traceback.format_exc()
        logger.log("pipeline_fatal", error=trace[-4000:])
        with open(out / "fatal_error.log", "w") as f:
            f.write(trace)
        sampler.stop()
        logger.close()
        print(trace, file=sys.stderr)
        sys.exit(2)

    # ── stop RAM sampler ──────────────────────────────────────────
    sampler.stop()

    # ── record result ──────────────────────────────────────────────
    if result.errors:
        logger.log("pipeline_failed", errors=result.errors)
    else:
        logger.log("pipeline_completed")

    # ── build summary (observability layer — not in the service) ──
    total_time = result.total_duration_seconds
    text_phase_elapsed = result.phases.get("text_s", 0)
    image_phase_elapsed = result.phases.get("image_s", 0)
    finalize_elapsed = result.phases.get("none_s", 0)

    model_info = {
        "text_generator": TEXT_MODEL_NAME,
        "image_generator": IMAGE_MODEL_NAME,
        "music_generator": MUSIC_MODEL_NAME,
    }

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": request.seed,
        "tone": request.tone,
        "title": request.title,
        "total_duration_seconds": round(total_time, 1),
        "backends": model_info,
        "ram_strategy": "sequential_load_unload",
        "world": {
            "width": request.width,
            "height": request.height,
            "continents": request.continent_count,
            "history_years": request.history_years,
            "civilizations": request.civilization_count,
        },
        "phases": {
            "text_s": round(text_phase_elapsed, 1),
            "image_s": round(image_phase_elapsed, 1),
            "finalize_s": round(finalize_elapsed, 1),
            "total_s": round(total_time, 1),
        },
        "artifacts": result.artifacts,
        "package_path": result.package_path or "not generated",
        "artifact_id": result.artifact_id,
        "content_hash": result.content_hash,
        "errors": result.errors,
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
    print(f"  Title:     {request.title}")
    print(f"  Tone:      {request.tone}")
    print(f"  Seed:      {request.seed}")
    print(f"  Time:      {total_time:.0f}s ({total_time / 60:.1f}m)")
    print()
    print("  Phases:")
    print(f"    Text:        {text_phase_elapsed:.0f}s ({text_phase_elapsed / 60:.1f}m)")
    print(f"    Images:      {image_phase_elapsed:.0f}s ({image_phase_elapsed / 60:.1f}m)")
    print(f"    Finalize:    {finalize_elapsed:.0f}s ({finalize_elapsed / 60:.1f}m)")
    print()
    print("  Artifacts:")
    for name, h in result.artifacts.items():
        status = "\u2713" if h != "error" else "\u2717"
        print(f"    {status} {name}: {h}")
    print()
    print(f"  Artifact ID: {result.artifact_id}")
    if result.errors:
        print(f"  Errors: {len(result.errors)}")
        for e in result.errors:
            print(f"    - {e}")
    print(f"  Events:   {out / 'runner_events.jsonl'} + {out / 'pipeline_events.jsonl'}")
    print(f"  RAM log:  {out / 'ram_samples.jsonl'}")
    print(f"  Summary:  {out / 'summary.json'}")
    print(f"  Checkpoint: {out / 'checkpoint.db'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
