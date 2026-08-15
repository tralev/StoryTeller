#!/usr/bin/env python3
"""Run the production-v2 pipeline with deterministic local fake backends."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class DryRunBackend:
    """Bounded inference/image fake; procedural facts remain authoritative."""

    provider = "dry-run"
    model_name = "deterministic-fake"
    quantization = ""
    ram_usage_mb = 0

    async def load(self) -> None:
        return None

    async def unload(self) -> None:
        return None

    async def generate(self, **kwargs: Any) -> Any:
        prompt = kwargs.get("prompt", "")
        if "size" in kwargs:
            from src.narrative.media import deterministic_image
            return deterministic_image(kwargs.get("seed", 0))
        if "Refine the visual wording" in prompt:
            source = json.loads(prompt.split("\n", 1)[1])
            return {
                "climate_palettes": {key: f"Refined {value}" for key, value
                                     in source["climate_palettes"].items()},
                "culture_motifs": {key: f"Refined {value}" for key, value
                                   in source["culture_motifs"].items()},
            }
        if "exactly these scene IDs" in prompt:
            ids = re.findall(r'"scene_id":"([^"]+)"', prompt)
            return {"scenes": {key: {"title": f"Scene {key}",
                                     "summary": f"Recorded pressure at {key}."}
                               for key in ids}}
        if "exactly these IDs" in prompt:
            ids = re.findall(r'"node_id":"([^"]+)"', prompt)
            return {"nodes": {key: f"Recorded tensions sharpen at {key}." for key in ids}}
        if "Refine the image prompt and music mood" in prompt:
            source = json.loads(prompt.split("\n", 1)[1])
            return {"nodes": {key: {
                "image_prompt": f"Refined {value['image_prompt']}",
                "music_mood": f"Refined {value['music_mood']}",
            } for key, value in source.items()}}
        return {"interpretations": ["Old obligations shape the documented age."]}


async def run_application_dry_run(output_dir: Path, seed: int = 7) -> dict[str, bool]:
    """Exercise the sole supported whole-pipeline entry point."""
    from src.application import GenerateStory, GenerationRequest

    backend = DryRunBackend()

    class DryRunService(GenerateStory):
        @staticmethod
        def _create_text_generator(config: Any) -> Any:
            return backend

        @staticmethod
        def _create_image_generator(config: Any) -> Any:
            return backend

        @staticmethod
        def _create_music_generator() -> Any:
            return backend

        @staticmethod
        def _create_validator(config: Any) -> Any:
            return backend

    result = await DryRunService().execute(GenerationRequest(
        seed=seed, title="The Crystal Accord", tone="heroic_fantasy",
        output_dir=str(output_dir), config_path="/nonexistent", resume=False,
        width=32, height=32, continent_count=1, history_years=20,
        civilization_count=2, erosion_passes=1, climate_relaxation_passes=8,
        plate_count=4, minimum_continent_cells=1,
    ))
    for error in result.errors:
        print(f"Dry-run error: {error}", file=sys.stderr)
    package = Path(result.package_path)
    return {"production_v2": not result.errors,
            "accepted_package": bool(package.is_file())}


def main() -> None:
    parser = argparse.ArgumentParser(description="StoryTeller production-v2 deterministic dry run")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output")
    args = parser.parse_args()
    if args.output:
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        results = asyncio.run(run_application_dry_run(output, args.seed))
    else:
        with tempfile.TemporaryDirectory() as temporary:
            results = asyncio.run(run_application_dry_run(Path(temporary), args.seed))
    for name, passed in results.items():
        print(f"{'PASS' if passed else 'FAIL'} {name}")
    raise SystemExit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    main()
