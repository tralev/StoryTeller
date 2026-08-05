#!/usr/bin/env python3
"""Dry-run test for StoryTeller Forge — mock backends, full pipeline.

Runs the entire pipeline end-to-end with mock generators (no real models).
Verifies at every step that:
  1. The step completes without error
  2. The artifact is written to disk (via ArtifactStore)
  3. The .story ZIP is valid and contains all expected files

Use this before the overnight test to confirm the pipeline flow is sound.

Usage:
    python scripts/dry_run.py
    python scripts/dry_run.py --output /tmp/test_output
    python scripts/dry_run.py --node-count 3  # 3-node test
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.job_queue import PipelineContext


# ═══════════════════════════════════════════════════════════════════════════════
# Mock generators — produces valid data through the entire pipeline
# ═══════════════════════════════════════════════════════════════════════════════

class MockTextGenerator:
    """Returns valid JSON matching requested schemas."""

    model_name: str = "mock-7b"
    quantization: str = "Q4"
    call_count: int = 0
    last_prompt: str = ""
    ram_usage_mb: int = 0

    async def load(self) -> None:
        return None

    async def unload(self) -> None:
        return None

    async def generate(
        self,
        prompt: str = "",
        schema: dict[str, Any] | None = None,
        temperature: float = 0.7,
        seed: int | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        self.call_count += 1
        self.last_prompt = prompt

        if '"world_name"' in prompt:
            return self._mock_bible(seed or 0)
        elif '"art_style"' in prompt or "character_design" in prompt:
            return self._mock_style_bible()
        elif "decision_points" in prompt:
            return self._mock_decision_points()
        elif '"nodes"' in prompt and '"node_id"' in prompt:
            return self._mock_graph_skeleton()
        elif "CRITICAL CONSTRAINTS" in prompt and "10 words or fewer" in prompt:
            return self._mock_node_text(prompt)
        elif "Write Chapter " in prompt or "story outline" in prompt:
            return self._mock_chapter(seed or 0)
        elif "image prompt" in prompt:
            return self._mock_image_prompt(seed or 0)
        elif "MUSIC TONE" in prompt or "ABC notation" in prompt or "music_prompt" in prompt:
            return self._mock_music_prompt(seed or 0)
        return {}

    @staticmethod
    def _mock_bible(seed: int) -> dict[str, Any]:
        return {
            "model_versions": {"text_generator": "mock-7b", "validator": "deterministic"},
            "world_name": "The Crystal Accord",
            "narrative_rules": {
                "tone": "heroic_fantasy",
                "forbidden": [],
                "required_themes": ["courage", "unity"],
                "mortality": "low",
                "knowledge_level": "aware",
            },
            "entities": {
                "characters": [
                    {
                        "id": "char_01", "name": "Elena Brightblade",
                        "aliases": ["The Accord Bearer"],
                        "description": "A young knight sworn to unite the fractured kingdoms.",
                        "role": "protagonist", "archetype": "hero",
                        "motivation": "Restore the Crystal Accord",
                        "flaw": "Naivety", "strength": "Conviction",
                        "relationships": [{"target": "char_02", "type": "ally", "description": "Trusted companions"}],
                        "status": "alive", "nodes": ["node_01"],
                    },
                    {
                        "id": "char_02", "name": "Thorn Ironveil",
                        "aliases": ["The Warden"],
                        "description": "An aging dwarf warden guarding the High Pass.",
                        "role": "supporting", "archetype": "guardian",
                        "motivation": "Protect the mountain realm",
                        "flaw": "Stubbornness", "strength": "Resilience",
                        "relationships": [{"target": "char_01", "type": "ally", "description": "Sworn protector"}],
                        "status": "alive", "nodes": ["node_01"],
                    },
                ],
                "locations": [
                    {
                        "id": "loc_01", "name": "High Pass",
                        "aliases": ["The Pass"],
                        "description": "A narrow mountain pass leading to the Crystal Spire.",
                        "type": "wilderness", "mood": "awe-inspiring",
                        "danger": "moderate", "connected_to": ["loc_02"],
                        "nodes": ["node_01"],
                    },
                ],
                "factions": [],
                "creatures": [],
                "artifacts": [],
                "events": [],
            },
            "systems": {
                "magic": {
                    "source": "Crystal resonance",
                    "rules": ["Harmony amplifies power", "Discord shatters"],
                    "costs": ["Emotional balance"],
                    "limitations": "Fades without unity",
                },
                "politics": {"power_structure": "Fractured kingdoms", "conflicts": []},
                "religion": {
                    "gods": [{"name": "The First Light", "domain": "unity", "status": "active"}],
                    "afterlife": "Souls return to the crystal song",
                },
            },
        }

    @staticmethod
    def _mock_style_bible() -> dict[str, Any]:
        return {
            "art_style": {
                "palette": "gold, azure, ivory",
                "lighting": "sunlight, radiant",
                "composition": "centered, symmetrical",
                "linework": "clean, flowing",
                "mood": "heroic, hopeful",
                "forbidden": ["gore", "darkness"],
            },
            "character_design": {
                "char_01": "Knight in silver-gold armor, flowing cape.",
                "char_02": "Stocky dwarf in mountain plate, iron-grey beard.",
            },
            "location_palettes": {
                "loc_01": "Jagged peaks, golden sky, crystal formations.",
            },
        }

    @staticmethod
    def _mock_chapter(seed: int) -> dict[str, Any]:
        return {
            "number": (seed % 3) + 1,
            "title": f"Chapter {(seed % 3) + 1}",
            "summary": "A chapter of the journey.",
            "scenes": [
                {
                    "scene_id": f"scene_{seed:02d}_01",
                    "text": "The pass stretched ahead, narrow and treacherous. "
                           "Elena steadied her grip and looked up at the gleaming spire. "
                           "Thorn grunted behind her, his heavy boots crunching gravel.",
                    "characters_present": ["char_01", "char_02"],
                    "location": "loc_01",
                    "entities_referenced": [],
                    "word_count": 34,
                }
            ],
        }

    @staticmethod
    def _mock_decision_points() -> dict[str, Any]:
        return {
            "decision_points": [
                {
                    "dp_id": "dp_01",
                    "chapter": 1,
                    "scene_ref": "scene_01_01",
                    "description": "Choose which path to take.",
                    "possible_choices": ["Main road", "Hidden trail"],
                    "stakes": "Time vs Safety",
                    "characters_involved": ["char_01", "char_02"],
                    "location": "loc_01",
                },
            ],
        }

    @staticmethod
    def _mock_graph_skeleton() -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []
        for number in range(1, 11):
            is_ending = number >= 9
            choices = [] if is_ending else [{
                "choice_id": f"ch_{number:02d}_a",
                "choice_text": "Continue through the pass.",
                "target_node": f"node_{number + 1:02d}",
                "sets_flags": [f"visited_{number:02d}"],
            }]
            node: dict[str, Any] = {
                "node_id": f"node_{number:02d}",
                "chapter": min(3, 1 + (number - 1) // 4),
                "scene_type": "ending" if is_ending else "exploration",
                "description": "The company advances through the High Pass.",
                "present_characters": ["char_01", "char_02"],
                "present_location": "loc_01",
                "present_creatures": [],
                "mood": "determined",
                "choices": choices,
                "endings": {"is_ending": is_ending},
            }
            if is_ending:
                node["endings"].update({
                    "ending_type": "good" if number == 10 else "bittersweet",
                    "ending_title": "The Accord Restored" if number == 10 else "The Long Vigil",
                })
            nodes.append(node)
        # Make both endings reachable from node 08.
        nodes[7]["choices"].append({
            "choice_id": "ch_08_b", "choice_text": "Stand vigil.",
            "target_node": "node_10", "sets_flags": ["chose_vigil"],
        })
        return {"nodes": nodes}

    @staticmethod
    def _mock_node_text(prompt: str) -> dict[str, Any]:
        return {
            "text": "The pass splits ahead.\n"
                   "Main road winds north.\n"
                   "A hidden trail east.\n"
                   "Thorn waits for you.\n"
                   "Each path holds risk.\n"
                   "The spire gleams ahead.\n"
                   "What path do you take?",
            "mood": "determined",
            "image_prompt": "A knight and dwarf at a mountain pass fork, crystal spire in distance",
            "music_tone": "heroic",
        }

    @staticmethod
    def _mock_image_prompt(seed: int) -> dict[str, Any]:
        return {
            "image_prompt": "Knight and dwarf at mountain pass, golden sky, crystal spire, "
                           "heroic fantasy concept art, clean flowing linework, masterpiece",
            "negative_prompt": "dark, gore, modern",
        }

    @staticmethod
    def _mock_music_prompt(seed: int) -> str:
        return (
            "X:1\n"
            "T:Crystal Pass\n"
            "M:4/4\n"
            "L:1/8\n"
            "K:C\n"
            "C2 E2 G2 c2 | B2 G2 E2 C2 | D2 F2 A2 d2 | c8 |]\n"
        )


class MockImageGenerator:
    """Returns deterministic mock PNG bytes."""

    provider: str = "mock-sd"
    model_name: str = "mock"
    quantization: str = "Q4"
    call_count: int = 0
    ram_usage_mb: int = 0

    async def load(self) -> None:
        return None

    async def unload(self) -> None:
        return None

    async def generate(
        self, prompt: str = "", negative_prompt: str = "",
        size: tuple[int, int] = (512, 512), seed: int | None = None, steps: int = 20,
    ) -> bytes:
        self.call_count += 1
        from src.storage.binary_checks import make_png
        return make_png(size[0], size[1], rgb=((seed or 0) % 256, 64, 96))

    async def generate_thumbnail(
        self, image_bytes: bytes = b"", size: tuple[int, int] = (128, 128),
    ) -> bytes:
        from src.storage.binary_checks import make_png
        return make_png(size[0], size[1])


class MockMusicGenerator:
    """Validates ABC and returns mock MIDI bytes."""

    provider: str = "abc-notation"
    call_count: int = 0
    ram_usage_mb: int = 0

    async def load(self) -> None:
        return None

    async def unload(self) -> None:
        return None

    async def generate(self, scene_text: str = "", mood: str = "", seed: int | None = None) -> str:
        return MockTextGenerator._mock_music_prompt(seed or 0)

    @staticmethod
    def abc_to_midi(abc_notation: str) -> bytes:
        from src.storage.binary_checks import make_midi
        return make_midi(ticks=96)

    @staticmethod
    def validate_abc(abc_notation: str) -> bool:
        return abc_notation.strip().startswith("X:1") and "K:" in abc_notation and "M:" in abc_notation


# ═══════════════════════════════════════════════════════════════════════════════
# Dry-run runner
# ═══════════════════════════════════════════════════════════════════════════════

async def run_application_dry_run(output_dir: Path, seed: int = 7) -> dict[str, bool]:
    """Exercise the only supported whole-pipeline entry point with local fakes."""
    from src.application import GenerateStory, GenerationRequest
    from src.interfaces.validator import ValidationResult, ValidatorStatus

    text = MockTextGenerator()
    image = MockImageGenerator()
    music = MockMusicGenerator()

    class DryRunService(GenerateStory):
        @staticmethod
        def _create_text_generator(config: Any) -> Any:
            return text

        @staticmethod
        def _create_image_generator(config: Any) -> Any:
            return image

        @staticmethod
        def _create_music_generator() -> Any:
            return music

        @staticmethod
        def _create_validator(config: Any) -> Any:
            class ManagedNoopValidator:
                ram_usage_mb = 0

                async def load(self) -> None:
                    return None

                async def unload(self) -> None:
                    return None

                async def validate(self, content: Any, context: Any) -> ValidationResult:
                    return ValidationResult(True, status=ValidatorStatus.SKIPPED)

            return ManagedNoopValidator()

    result = await DryRunService().execute(GenerationRequest(
        seed=seed, title="The Crystal Accord", tone="heroic_fantasy",
        output_dir=str(output_dir), config_path="/nonexistent", resume=False,
        width=64, height=64, history_years=20, civilization_count=2,
    ))
    for error in result.errors:
        print(f"Dry-run error: {error}", file=sys.stderr)
    return {
        "application_service": not result.errors,
        "accepted_package": bool(result.package_path and Path(result.package_path).is_file()),
    }


def check(label: str, ok: bool, detail: str = "") -> bool:
    """Print a checkmark or cross and return the status."""
    status = "\u2713" if ok else "\u2717"
    print(f"  {status} {label}")
    if not ok and detail:
        print(f"    └─ {detail}")
    return ok


async def run_dry_run(output_dir: Path, seed: int = 7) -> dict[str, bool]:
    """Run the full pipeline with mocks and verify every step.

    Returns dict of step_name → passed.
    """
    from src.models.art_director import ArtDirector
    from src.models.game_designer import GameDesigner
    from src.models.image_generator_step import ImageGeneratorStep
    from src.models.music_generator_step import MusicGeneratorStep
    from src.models.story_writer import StoryWriter
    from src.models.world_builder import WorldBuilder
    from src.storage.indexer import GmIndexer
    from src.storage.packager import Packager

    results: dict[str, bool] = {}
    t0 = time.time()

    text_gen = MockTextGenerator()
    img_gen = MockImageGenerator()
    mus_gen = MockMusicGenerator()

    ctx = PipelineContext(
        run_id=f"dry_{seed:04d}",
        seed=seed,
        output_dir=str(output_dir),
    )
    ctx.state["tone"] = "heroic_fantasy"
    ctx.state["title"] = "The Crystal Accord"
    ctx.state["temperature"] = 0.7
    ctx.state["start_time"] = time.time()

    print(f"\n{'='*60}")
    print(f"  StoryTeller Forge — Dry Run")
    print(f"  Seed: {seed}  |  Tone: heroic_fantasy")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}\n")

    # Step 1: World Bible
    print("--- Phase 1: World Bible ---")
    try:
        wb = WorldBuilder(text_gen, config=None)
        output = await wb.run(ctx)
        ctx.outputs["bible"] = output.data
        ok = True
        ok &= check("World Bible generated", True)
        ok &= check("Artifact ID starts with 'world_'", output.artifact_id.startswith("world_"),
                     f"Got: {output.artifact_id}")
        ok &= check("Contains entities", "entities" in output.data)
        ok &= check("Disk: bible.json written", (output_dir / "bible.json").exists())
        results["world_builder"] = ok
        if ok:
            print(f"  ✓ artifact_id: {output.artifact_id}")
    except Exception as e:
        check("World Bible", False, str(e))
        results["world_builder"] = False

    # Step 2: Style Bible
    print("\n--- Phase 2: Style Bible ---")
    try:
        ad = ArtDirector(text_gen, config=None)
        output = await ad.run(ctx)
        ctx.outputs["style_bible"] = output.data
        ok = True
        ok &= check("Style Bible generated", True)
        ok &= check("Contains art_style", "art_style" in output.data)
        ok &= check("Disk: style_bible.json", (output_dir / "style_bible.json").exists())
        results["art_director"] = ok
        if ok:
            print(f"  ✓ artifact_id: {output.artifact_id}")
    except Exception as e:
        check("Style Bible", False, str(e))
        results["art_director"] = False

    # Step 3: Story
    print("\n--- Phase 3: Story ---")
    try:
        sw = StoryWriter(text_gen, config=None)
        output = await sw.run(ctx)
        ctx.outputs["story"] = output.data
        ok = True
        ok &= check("Story generated (3 chapters)", len(output.data.get("chapters", [])) == 3,
                     f"Got {len(output.data.get('chapters', []))} chapters")
        ok &= check("Disk: story.json", (output_dir / "story.json").exists())
        results["story_writer"] = ok
        if ok:
            print(f"  ✓ artifact_id: {output.artifact_id}")
    except Exception as e:
        check("Story", False, str(e))
        results["story_writer"] = False

    # Step 4: CYOA Graph
    print("\n--- Phase 4: CYOA Graph ---")
    try:
        gd = GameDesigner(text_gen, config=None)
        output = await gd.run(ctx)
        ctx.outputs["graph"] = output.data
        ok = True
        ok &= check("Graph generated", len(output.data.get("nodes", [])) >= 1)
        ok &= check("Disk: graph.json", (output_dir / "graph.json").exists())
        results["game_designer"] = ok
        if ok:
            print(f"  ✓ artifact_id: {output.artifact_id}")
            print(f"  ✓ nodes: {len(output.data['nodes'])}")
    except Exception as e:
        check("Graph", False, str(e))
        results["game_designer"] = False

    # Step 5a: Images
    print("\n--- Phase 5a: Images ---")
    try:
        istep = ImageGeneratorStep(img_gen, config=None, output_dir=str(output_dir))
        output = await istep.run(ctx)
        ctx.outputs["images"] = output.data
        ok = True
        ok &= check("Images generated", output.data.get("image_count", 0) >= 1,
                     f"Got {output.data.get('image_count', 0)} images")
        # Check actual .png files on disk
        img_dir = output_dir / "images"
        png_files = list(img_dir.glob("*.png")) if img_dir.exists() else []
        ok &= check(f"Disk: {len(png_files)} PNG files in images/", len(png_files) >= 1)
        results["image_generator"] = ok
        if ok:
            print(f"  ✓ artifact_id: {output.artifact_id}")
    except Exception as e:
        check("Images", False, str(e))
        results["image_generator"] = False

    # Step 5b: Music
    print("\n--- Phase 5b: Music ---")
    try:
        mstep = MusicGeneratorStep(text_gen, mus_gen, config=None, output_dir=str(output_dir))
        output = await mstep.run(ctx)
        ctx.outputs["midi"] = output.data
        ok = True
        ok &= check("MIDI generated", output.data.get("midi_count", 0) >= 1,
                     f"Got {output.data.get('midi_count', 0)} MIDI files")
        midi_dir = output_dir / "midi"
        mid_files = list(midi_dir.glob("*.mid")) if midi_dir.exists() else []
        ok &= check(f"Disk: {len(mid_files)} .mid files in midi/", len(mid_files) >= 1)
        results["music_generator"] = ok
        if ok:
            print(f"  ✓ artifact_id: {output.artifact_id}")
    except Exception as e:
        check("MIDI", False, str(e))
        results["music_generator"] = False

    # Step 6: GM Index
    print("\n--- Phase 6: GM Index ---")
    try:
        idx = GmIndexer()
        output = await idx.run(ctx)
        ctx.outputs["gm_index"] = output.data
        ok = True
        ok &= check("GM Index built", "keywords" in output.data and "entity_cache" in output.data)
        ok &= check("Disk: gm_index.json", (output_dir / "gm_index.json").exists())
        results["indexer"] = ok
        if ok:
            print(f"  ✓ artifact_id: {output.artifact_id}")
            print(f"  ✓ keywords: {len(output.data['keywords'])} entries")
            print(f"  ✓ entities: {len(output.data['entity_cache'])} cached")
    except Exception as e:
        check("GM Index", False, str(e))
        results["indexer"] = False

    # Step 7: Package
    print("\n--- Phase 7: Package ---")
    try:
        ctx.outputs["manifest"] = {
            "schema_version": 1,
            "generator_version": "0.1.0",
            "pipeline_version": 1,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "model_versions": {"text_generator": "mock-7b-Q4"},
            "seed": seed,
            "title": "The Crystal Accord",
            "artifact_id": f"package_{hashlib.sha256(f'{seed}'.encode()).hexdigest()[:8]}",
            "stats": {},
        }

        pkg = Packager(output_dir=str(output_dir))
        output = await pkg.run(ctx)
        package_path = Path(output.data["package_path"])

        ok = True
        ok &= check("Package created", package_path.exists())
        ok &= check("Has .story extension", package_path.suffix == ".story")
        ok &= check("Non-empty file", package_path.stat().st_size > 0,
                     f"Size: {package_path.stat().st_size} bytes")

        # Verify ZIP contents
        with zipfile.ZipFile(package_path) as zf:
            names = zf.namelist()
            ok &= check("ZIP: manifest.json", "manifest.json" in names)
            ok &= check("ZIP: content/bible.json", "content/bible.json" in names)
            ok &= check("ZIP: content/story.json", "content/story.json" in names)
            ok &= check("ZIP: content/graph.json", "content/graph.json" in names)
            ok &= check("ZIP: content/gm_index.json", "content/gm_index.json" in names)
            ok &= check("ZIP: content/style_bible.json", "content/style_bible.json" in names)
            ok &= check("ZIP: save/.gitkeep", "save/.gitkeep" in names)

            # Check images are in ZIP
            has_images = any(name.startswith("content/images/") and name.endswith(".png") for name in names)
            ok &= check("ZIP: content/images/*.png", has_images)

            # Check MIDI is in ZIP
            has_midi = any(name.startswith("content/midi/") and name.endswith(".mid") for name in names)
            ok &= check("ZIP: content/midi/*.mid", has_midi)

            # Validate ZIP integrity
            corrupt = zf.testzip()
            ok &= check("ZIP: integrity check", corrupt is None,
                        f"Corrupt entry: {corrupt}" if corrupt else "")

        results["packager"] = ok
        if ok:
            print(f"  ✓ package: {package_path}")
            print(f"  ✓ size: {package_path.stat().st_size} bytes")
    except Exception as e:
        check("Package", False, str(e))
        results["packager"] = False

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    # Verify all disk artifacts exist
    print(f"\n{'='*60}")
    print(f"  ArtifactStore Disk Verification")
    print(f"{'='*60}")
    expected_files = [
        "bible.json", "style_bible.json", "story.json", "graph.json",
        "gm_index.json",
    ]
    for fname in expected_files:
        path = output_dir / fname
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        check(f"{fname} ({size} bytes)", exists)

    # Also check for images/ and midi/ directories
    img_files = list((output_dir / "images").glob("*.png")) if (output_dir / "images").exists() else []
    mid_files = list((output_dir / "midi").glob("*.mid")) if (output_dir / "midi").exists() else []
    check(f"images/ ({len(img_files)} PNG files)", len(img_files) > 0)
    check(f"midi/ ({len(mid_files)} MIDI files)", len(mid_files) > 0)

    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} phases passed in {elapsed:.1f}s")
    if passed == total:
        print(f"  \u2714 ALL PHASES PASSED — pipeline is healthy!")
    else:
        print(f"  \u2716 {total - passed} phase(s) failed:")
        for name, ok in results.items():
            if not ok:
                print(f"    - {name}")
    print(f"{'='*60}\n")

    return results


# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="StoryTeller Forge — Dry-Run Pipeline Test (mock backends)",
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--output", type=str, default=None,
        help="Output directory (default: temp dir)",
    )
    parser.add_argument(
        "--keep-output", action="store_true",
        help="Don't delete output directory after run",
    )
    args = parser.parse_args()

    if args.output:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output: {output_dir} (will be kept)")
        results = asyncio.run(run_application_dry_run(output_dir, args.seed))
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            print(f"Output: {output_dir} (temporary — deleted after run)")
            results = asyncio.run(run_application_dry_run(output_dir, args.seed))

    # Exit code
    passed = all(results.values())
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
