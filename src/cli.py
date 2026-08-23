"""CLI entry point for StoryTeller Forge.

Commands:
    forge worldgen conformance {reference,coverage,check,profiles}
                            P8.C05A worldgen contract conformance
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

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, cast

from typing_extensions import TypedDict


class WorldCliKwargs(TypedDict):
    width: int
    height: int
    continent_count: int
    metres_per_world_cell: int
    plate_count: int
    minimum_continent_cells: int
    history_years: int
    history_ticks_per_year: int
    civilization_count: int
    sea_level_ppm: int
    axial_tilt_millidegrees: int
    erosion_passes: int
    climate_relaxation_passes: int
    snapshot_interval_years: int
    local_site_width: int
    local_site_height: int
    local_z_levels: int
    local_cell_millimetres: int


# Every WorldSpec field must appear in exactly one of these two tables. This is
# checked when the parser is built, so adding a field cannot silently bypass CLI
# and GenerationRequest conversion.
WORLD_CLI_BINDINGS: dict[str, tuple[str, str]] = {
    "width": ("--width", "width"),
    "height": ("--height", "height"),
    "continent_count": ("--continents", "continents"),
    "metres_per_world_cell": ("--metres-per-world-cell", "metres_per_world_cell"),
    "plate_count": ("--plate-count", "plate_count"),
    "minimum_continent_cells": ("--minimum-continent-cells", "minimum_continent_cells"),
    "history_years": ("--history-years", "history_years"),
    "civilization_count": ("--civilizations", "civilizations"),
    "sea_level_ppm": ("--sea-level-ppm", "sea_level_ppm"),
    "axial_tilt_millidegrees": ("--axial-tilt-millidegrees", "axial_tilt_millidegrees"),
    "erosion_passes": ("--erosion-passes", "erosion_passes"),
    "climate_relaxation_passes": ("--climate-relaxation-passes", "climate_relaxation_passes"),
    "local_site_width": ("--local-site-width", "local_site_width"),
    "local_site_height": ("--local-site-height", "local_site_height"),
    "local_z_levels": ("--local-z-levels", "local_z_levels"),
    "local_cell_millimetres": ("--local-cell-millimetres", "local_cell_millimetres"),
}
WORLD_FIXED_FIELDS: dict[str, int] = {
    "history_ticks_per_year": 12,
    "snapshot_interval_years": 10,
}


def add_world_spec_arguments(parser: Any) -> None:
    """Add every configurable WorldSpec field and reject an incomplete table."""
    from dataclasses import fields

    from src.domain.run_spec import WorldSpec

    definitions = {item.name: item for item in fields(WorldSpec)}
    classified = set(WORLD_CLI_BINDINGS) | set(WORLD_FIXED_FIELDS)
    if classified != set(definitions) or set(WORLD_CLI_BINDINGS) & set(WORLD_FIXED_FIELDS):
        raise RuntimeError("WorldSpec CLI classification is incomplete or overlapping")
    defaults = WorldSpec().to_dict()
    for field_name, (flag, destination) in WORLD_CLI_BINDINGS.items():
        parser.add_argument(flag, dest=destination, type=int, default=defaults[field_name])


def world_spec_cli_kwargs(args: Any) -> WorldCliKwargs:
    """Convert parsed CLI controls to complete GenerationRequest world kwargs."""
    values = {
        field_name: int(getattr(args, destination))
        for field_name, (_, destination) in WORLD_CLI_BINDINGS.items()
    }
    values.update(WORLD_FIXED_FIELDS)
    return cast(WorldCliKwargs, values)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="forge",
        description="StoryTeller Forge — AI-powered interactive story generator",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # ── forge worldgen ─────────────────────────────────────────
    wg_parser = subparsers.add_parser("worldgen", help="World generation tools")
    wg_sub = wg_parser.add_subparsers(dest="action", help="Actions")
    # forge worldgen conformance
    wg_conf = wg_sub.add_parser("conformance", help="Run worldgen conformance checks")
    wg_conf.add_argument("profile", choices=["reference", "coverage", "check", "profiles"])

    # ── forge generate-world ──────────────────────────────────────────
    physical_parser = subparsers.add_parser(
        "generate-world",
        help="Generate authoritative physical-world artifacts without AI",
    )
    physical_parser.add_argument("--seed", type=int, default=42)
    physical_parser.add_argument("--output", type=str, required=True)
    physical_parser.add_argument("--width", type=int, default=64)
    physical_parser.add_argument("--height", type=int, default=64)
    physical_parser.add_argument("--metres-per-world-cell", type=int, default=8000)
    physical_parser.add_argument("--continents", type=int, default=1)
    physical_parser.add_argument("--plates", type=int, default=12)
    physical_parser.add_argument("--erosion-passes", type=int, default=8)
    physical_parser.add_argument("--climate-passes", type=int, default=16)

    simulate_parser = subparsers.add_parser(
        "simulate-world",
        help="Run deterministic civilization and history simulation",
    )
    simulate_parser.add_argument("--world", type=str, required=True)
    simulate_parser.add_argument("--history-years", type=int, default=500)
    simulate_parser.add_argument("--output", type=str, required=True)

    validate_world_parser = subparsers.add_parser(
        "validate-world",
        help="Validate and replay a generated historical world",
    )
    validate_world_parser.add_argument("world_path", type=str)

    bible_parser = subparsers.add_parser(
        "generate-bible",
        help="Generate and reconcile a Bible from an immutable world",
    )
    bible_parser.add_argument("--world", type=str, required=True)
    bible_parser.add_argument("--title", type=str, required=True)
    bible_parser.add_argument("--output", type=str, required=True)

    reconcile_parser = subparsers.add_parser(
        "reconcile-world",
        help="Reconcile a Bible against its authoritative world",
    )
    reconcile_parser.add_argument("--world", type=str, required=True)
    reconcile_parser.add_argument("--bible", type=str, required=True)

    narrative_parser = subparsers.add_parser(
        "generate-narrative",
        help="Generate referenced narrative, mandatory media, and GM index",
    )
    narrative_parser.add_argument("--world", type=str, required=True)
    narrative_parser.add_argument("--bible", type=str, required=True)
    narrative_parser.add_argument("--output", type=str, required=True)
    narrative_parser.add_argument("--workers", type=int, default=4)

    project_parser = subparsers.add_parser(
        "validate-project",
        help="Validate a provisional Phase 5 narrative project",
    )
    project_parser.add_argument("project_path", type=str)

    validate_package_parser = subparsers.add_parser(
        "validate-package",
        help="Validate a frozen .story v2 package",
    )
    validate_package_parser.add_argument("package_path", type=str)

    inspect_package_parser = subparsers.add_parser(
        "inspect-package",
        help="Inspect an accepted .story v2 package",
    )
    inspect_package_parser.add_argument("package_path", type=str)
    inspect_package_parser.add_argument("--json", action="store_true", dest="as_json")

    # ── forge generate ─────────────────────────────────────────────────
    gen_parser = subparsers.add_parser("generate", help="Run the full pipeline")
    gen_parser.add_argument("--seed", type=int, default=42)
    gen_parser.add_argument("--tone", type=str, default="mature_dark_fantasy")
    gen_parser.add_argument("--title", type=str, default="Untitled World")
    gen_parser.add_argument("--temperature", type=float, default=0.7)
    add_world_spec_arguments(gen_parser)
    gen_parser.add_argument("--config", type=str, default="config/models.yaml")
    gen_parser.add_argument("--output", type=str, default="tmp/output")

    # ── forge download-models ──────────────────────────────────────────
    dl_parser = subparsers.add_parser("download-models", help="Download GGUF models")
    dl_parser.add_argument(
        "--with-images", action="store_true", help="Also download SDXL-Turbo image model"
    )
    dl_parser.add_argument(
        "--models-dir", type=str, default="~/.storyteller/models", help="Models directory"
    )

    # ── forge resume ───────────────────────────────────────────────────
    resume_parser = subparsers.add_parser("resume", help="Resume from checkpoint")
    resume_parser.add_argument(
        "--output", type=str, default="tmp/output", help="Output directory with checkpoint.db"
    )
    resume_parser.add_argument("--config", type=str, default="config/models.yaml")

    # ── forge config ───────────────────────────────────────────────────
    cfg_parser = subparsers.add_parser("config", help="Show/edit configuration")
    cfg_parser.add_argument(
        "--set",
        type=str,
        nargs=2,
        metavar=("KEY", "VALUE"),
        help="Set a config value (e.g., --set text.model qwen2.5-7b)",
    )
    cfg_parser.add_argument("--config", type=str, default="config/models.yaml")

    # ── forge verify ───────────────────────────────────────────────────
    ver_parser = subparsers.add_parser("verify", help="Verify .story hash")
    ver_parser.add_argument("story_path", type=str, help="Path to .story file")
    ver_parser.add_argument(
        "--expected-hash", type=str, default=None, help="Expected SHA256 hash (optional)"
    )

    # ── forge info ─────────────────────────────────────────────────────
    info_parser = subparsers.add_parser("info", help="Show checkpoint/state info")
    info_parser.add_argument("--output", type=str, default="tmp/output", help="Output directory")

    # ── forge package ──────────────────────────────────────────────────
    pkg_parser = subparsers.add_parser("package", help="Package into .story")
    pkg_parser.add_argument("--seed", type=int, default=42)
    pkg_parser.add_argument("--output", type=str, default="tmp/output")
    pkg_parser.add_argument("--config", type=str, default="config/models.yaml")

    # ── forge validate-story ───────────────────────────────────────────
    val_parser = subparsers.add_parser("validate-story", help="Story vs bible consistency")
    val_parser.add_argument("story_path", type=str)
    val_parser.add_argument("bible_path", type=str)

    # ── forge validate-graph ───────────────────────────────────────────
    vg_parser = subparsers.add_parser("validate-graph", help="Validate graph schema")
    vg_parser.add_argument("graph_path", type=str)
    vg_parser.add_argument("--schemas-dir", type=str, default="schemas")

    # ── forge validate-all ─────────────────────────────────────────────
    va_parser = subparsers.add_parser("validate-all", help="Validate all artifacts in a dir")
    va_parser.add_argument("artifact_dir", type=str, help="Directory with JSON artifacts")
    va_parser.add_argument("--schemas-dir", type=str, default="schemas")

    # ── forge validate-bible ───────────────────────────────────────────
    vb_parser = subparsers.add_parser("validate-bible", help="Validate bible schema")
    vb_parser.add_argument("bible_path", type=str)
    vb_parser.add_argument("--schemas-dir", type=str, default="schemas")

    args = parser.parse_args()

    commands: dict[str, Any] = {
        "worldgen": _cmd_worldgen,
        "generate-world": _cmd_generate_world,
        "simulate-world": _cmd_simulate_world,
        "validate-world": _cmd_validate_world,
        "generate-bible": _cmd_generate_bible,
        "reconcile-world": _cmd_reconcile_world,
        "generate-narrative": _cmd_generate_narrative,
        "validate-project": _cmd_validate_project,
        "validate-package": _cmd_validate_package,
        "inspect-package": _cmd_inspect_package,
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


def _cmd_worldgen(args: Any) -> None:
    """Run deterministic worldgen conformance profiles."""
    if args.action != "conformance":
        raise ValueError("unsupported worldgen command")

    profile = args.profile

    if profile == "reference":
        # P8.C05A: run the embedded reference kernel
        from src.worldgen.reference import verify_reference

        ref_result = verify_reference()
        print(json.dumps(ref_result, sort_keys=True))
        return

    if profile == "coverage":
        # P8.C05A: generate the zero-gap coverage ledger
        from src.worldgen.conformance.generator import write_coverage_doc

        total = write_coverage_doc("docs/worldgen-coverage.generated.md")
        print(
            json.dumps(
                {"written": total, "file": "docs/worldgen-coverage.generated.md"}, sort_keys=True
            )
        )
        return

    if profile == "check":
        # P8.C05A: validate the requirement catalog itself
        from src.worldgen.conformance.requirements import validate_requirements

        errors = validate_requirements()
        from src.worldgen.conformance.source_coverage import validate_source_coverage

        errors.extend(validate_source_coverage())
        from src.worldgen.conformance.profiles import validate_profile_contract

        errors.extend(validate_profile_contract())
        from src.worldgen.conformance.evidence import validate_evidence

        errors.extend(validate_evidence())
        if errors:
            for e in errors:
                print(e, file=sys.stderr)
            raise SystemExit(1)
        # Also check the coverage doc is up-to-date
        from src.worldgen.conformance.generator import check_coverage_doc

        if not check_coverage_doc("docs/worldgen-coverage.generated.md"):
            print("worldgen-coverage.generated.md is stale — run:", file=sys.stderr)
            print("  forge worldgen conformance coverage", file=sys.stderr)
            raise SystemExit(1)
        from src.worldgen.conformance.profiles import verify_contract_hashes
        from src.worldgen.conformance.requirements import REQUIREMENTS as _WG_REQS  # noqa: N811
        from src.worldgen.conformance.source_coverage import SOURCE_CLAUSES

        print(
            json.dumps(
                {
                    "valid": True,
                    "requirements": len(_WG_REQS),
                    "source_clauses": len(SOURCE_CLAUSES),
                    "contract_hashes": verify_contract_hashes(),
                },
                sort_keys=True,
            )
        )
        return

    if profile == "profiles":
        # P8.C05A: validate all named profiles expand to valid WorldSpec
        from src.worldgen.conformance.profiles import (
            PROFILE_CONFORMANCE,
            PROFILE_DEFAULT,
            PROFILE_TINY,
            expand_profile,
            profile_hash,
        )

        profiles = {
            "tiny": PROFILE_TINY,
            "conformance": PROFILE_CONFORMANCE,
            "default": PROFILE_DEFAULT,
        }
        profiles_out: dict[str, Any] = {}
        for name, spec in sorted(profiles.items()):
            # Verify expansion round-trips
            expanded = expand_profile(name)
            h = profile_hash(name)
            profiles_out[name] = {
                "hash": h,
                "width": expanded.width,
                "height": expanded.height,
                "continent_count": expanded.continent_count,
                "history_years": expanded.history_years,
                "civilization_count": expanded.civilization_count,
            }
        print(json.dumps(profiles_out, sort_keys=True, indent=2))
        return

    raise ValueError(f"unsupported worldgen conformance profile: {profile}")


def _cmd_generate_world(args: Any) -> None:
    """Generate and validate Phase 2 artifacts without loading any model."""
    from src.domain.run_spec import WorldSpec
    from src.worldgen.physical_pipeline import generate_physical_world

    spec = WorldSpec(
        width=args.width,
        height=args.height,
        metres_per_world_cell=args.metres_per_world_cell,
        continent_count=args.continents,
        plate_count=args.plates,
        minimum_continent_cells=1,
        erosion_passes=args.erosion_passes,
        climate_relaxation_passes=args.climate_passes,
    )
    result = generate_physical_world(spec, args.seed, args.output)
    print(json.dumps(result.to_dict(), sort_keys=True))


def _cmd_simulate_world(args: Any) -> None:
    from src.worldgen.simulation import simulate_world

    result = simulate_world(args.world, args.history_years, args.output)
    print(json.dumps(result, sort_keys=True))


def _cmd_validate_world(args: Any) -> None:
    from src.worldgen.simulation import validate_simulation_directory

    result = validate_simulation_directory(args.world_path)
    print(json.dumps(result, sort_keys=True))


def _cmd_generate_bible(args: Any) -> None:
    from src.storage.fs import atomic_write_bytes
    from src.world.art_direction import derive_art_direction
    from src.world.builder import WorldBuilderV2
    from src.world.views import WorldView
    from src.worldgen.artifacts import canonical_json

    bible, report = WorldBuilderV2().build(args.world, args.title, args.output)
    style = derive_art_direction(WorldView(args.world), bible)
    atomic_write_bytes(Path(args.output) / "style_bible.json", canonical_json(style))
    print(
        json.dumps(
            {
                "accepted": report.accepted,
                "issues": len(report.issues),
                "bible": str(Path(args.output) / "bible.json"),
            },
            sort_keys=True,
        )
    )


def _cmd_reconcile_world(args: Any) -> None:
    from src.storage.fs import atomic_write_bytes
    from src.validators.world_reconciler import WorldReconciler
    from src.world.models import BibleV2
    from src.world.views import WorldView
    from src.worldgen.artifacts import canonical_json

    bible_path = Path(args.bible)
    bible = BibleV2.from_dict(json.loads(bible_path.read_text()))
    report = WorldReconciler().reconcile(WorldView(args.world), bible)
    atomic_write_bytes(bible_path.parent / "reconciliation.json", canonical_json(report))
    print(json.dumps({"accepted": report.accepted, "issues": len(report.issues)}, sort_keys=True))
    if not report.accepted:
        print(report.retry_feedback())
        raise SystemExit(1)


def _cmd_generate_narrative(args: Any) -> None:
    from src.narrative import generate_narrative

    result = generate_narrative(args.world, args.bible, args.output, workers=args.workers)
    print(json.dumps(result, sort_keys=True))


def _cmd_validate_project(args: Any) -> None:
    from src.narrative import validate_project

    result = validate_project(args.project_path)
    print(json.dumps(result, sort_keys=True))


def _cmd_validate_package(args: Any) -> None:
    from src.storage.package_v2 import validate_v2_package

    result = validate_v2_package(args.package_path)
    value = {
        "accepted": result.accepted,
        "issues": [
            {"code": issue.code, "path": issue.path, "message": issue.message}
            for issue in result.issues
        ],
    }
    print(json.dumps(value, sort_keys=True))
    if not result.accepted:
        raise SystemExit(1)


def _cmd_inspect_package(args: Any) -> None:
    from src.storage.package_v2 import PackageV2Error, inspect_v2_package

    try:
        value = inspect_v2_package(args.package_path)
    except PackageV2Error as error:
        print(
            json.dumps(
                {"accepted": False, "code": error.code, "path": error.path, "message": str(error)},
                sort_keys=True,
            )
        )
        raise SystemExit(1)
    if args.as_json:
        print(json.dumps(value, sort_keys=True))
    else:
        for key, item in value.items():
            print(f"{key}: {item}")


def _cmd_generate(args: Any) -> None:
    """Run the full generation pipeline through the shared GenerateStory service."""
    try:
        from rich.console import Console

        console = Console()
        _rich = True
    except ImportError:
        console = None
        _rich = False

    if console is not None:
        console.print("[bold cyan]=== StoryTeller Forge ===[/bold cyan]\n")
    else:
        print("=== StoryTeller Forge ===\n")

    from src.application import GenerateStory, GenerationRequest

    request = GenerationRequest(
        seed=args.seed,
        title=args.title,
        tone=args.tone,
        temperature=args.temperature,
        config_path=args.config,
        output_dir=args.output,
        **world_spec_cli_kwargs(args),
    )

    print(f"Seed: {args.seed}, Tone: {args.tone}, Title: {args.title}")
    print(
        f"World: {args.width}x{args.height}, {args.continents} continent(s), "
        f"{args.civilizations} civilizations, {args.history_years} years"
    )
    print(f"Output: {args.output}\n")

    import asyncio

    service = GenerateStory()
    result = asyncio.run(service.execute(request))

    print("\n=== Generation Complete ===")
    print(f"Artifact: {result.artifact_id}")
    if result.package_path:
        print(f"Package: {result.package_path}")
        # Phase 5.6 Q5: distinguish fully complete from incomplete-but-accepted
        if result.media_complete:
            print(
                f"Media:   \u2714 fully complete (images {result.image_coverage:.0%}, "
                f"MIDI {result.midi_coverage:.0%})"
            )
        else:
            print(
                f"Media:   \u26a0 incomplete (images {result.image_coverage:.0%}, "
                f"MIDI {result.midi_coverage:.0%}) — accepted per coverage policy"
            )
    if result.errors:
        print(f"Errors: {len(result.errors)}")
        for e in result.errors:
            print(f"  - {e}")
        raise SystemExit(1)


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
    """Resume generation from checkpoint — routes through GenerateStory.

    Phase 5.6B: All resume paths now go through the shared GenerateStory
    service. This command is equivalent to 'forge generate' with the
    same seed/config/output but with resume=True.
    """
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
    print("Completed steps:")

    for entry in entries:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.completed_at))
        print(
            f"  Phase {entry.phase}: {entry.step_name} "
            f"(seed={entry.seed}, {entry.artifact_id or 'no-id'}, {ts})"
        )

    highest = store.get_highest_completed_phase()
    from src.pipeline.plan import PipelinePlan

    phase_count = len(PipelinePlan.production_v2())
    print(f"\nResuming from phase {highest + 1}...")
    print(
        f"({phase_count} phases — {highest} complete, {max(0, phase_count - highest)} remaining)\n"
    )

    # Route through GenerateStory — same as 'forge generate' but with resume=True
    from src.application import GenerateStory, GenerationRequest
    from src.domain.run_spec import RunSpec

    run_spec_path = Path(args.output) / "run_spec.json"
    if not run_spec_path.is_file():
        print("Error: run_spec.json is required for a lossless resume.")
        sys.exit(1)
    try:
        run_spec = RunSpec.from_dict(json.loads(run_spec_path.read_text()))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Error: invalid run_spec.json: {error}")
        sys.exit(1)
    request = GenerationRequest.from_run_spec(
        run_spec,
        output_dir=args.output,
        config_path=args.config,
        resume=True,
    )

    import asyncio

    service = GenerateStory()
    result = asyncio.run(service.execute(request))

    print("\n=== Resume Complete ===")
    print(f"Artifact: {result.artifact_id}")
    if result.package_path:
        print(f"Package: {result.package_path}")
        # Phase 5.6 Q5: distinguish fully complete from incomplete-but-accepted
        if result.media_complete:
            print(
                f"Media:   \u2714 fully complete (images {result.image_coverage:.0%}, "
                f"MIDI {result.midi_coverage:.0%})"
            )
        else:
            print(
                f"Media:   \u26a0 incomplete (images {result.image_coverage:.0%}, "
                f"MIDI {result.midi_coverage:.0%}) — accepted per coverage policy"
            )
    if result.errors:
        print(f"Errors: {len(result.errors)}")
        for e in result.errors:
            print(f"  - {e}")
        raise SystemExit(1)


def _cmd_config(args: Any) -> None:
    """Show or edit the model configuration."""
    config_path = _resolve_config_path(args.config)

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
    """Verify a v2 package from its declared internal files, never ZIP bytes."""
    story_path = Path(args.story_path)

    if not story_path.exists():
        print(f"Error: File not found: {story_path}")
        sys.exit(1)

    if story_path.suffix != ".story":
        print(f"Warning: File does not have .story extension: {story_path}")

    from src.storage.package_v2 import validate_v2_package

    accepted = validate_v2_package(story_path)
    if not accepted.accepted or accepted.manifest is None:
        issue = accepted.issues[0]
        # Diagnostic only, still derived from member paths/bytes rather than
        # the ZIP transport. It helps identify the exact rejected input.
        try:
            from src.storage.content_hash import compute_zip_content_hash

            print(f"Content SHA256: {compute_zip_content_hash(story_path)}")
        except Exception:
            pass
        print("Package acceptance: INVALID")
        print(
            json.dumps(
                {
                    "accepted": False,
                    "code": issue.code,
                    "path": issue.path,
                    "message": issue.message,
                },
                sort_keys=True,
            )
        )
        sys.exit(1)
    sha = str(accepted.manifest["content_hash"])

    # Try to read manifest from ZIP for seed/title info
    try:
        import zipfile

        with zipfile.ZipFile(story_path) as zf:
            if "manifest.json" in zf.namelist():
                manifest = json.loads(zf.read("manifest.json"))
                title = manifest.get("title", "?")
                seed = manifest.get("seed", "?")
                story_id = manifest.get("story_id", "?")
                print(f"Story:     {title}")
                print(f"Seed:      {seed}")
                print(f"Story ID:  {story_id}")
    except Exception:
        pass

    print(f"Content SHA256: {sha}")

    if args.expected_hash:
        if sha == args.expected_hash:
            print("\n\u2714 Hash matches expected value.")
        else:
            print("\n\u2716 Hash MISMATCH!")
            print(f"  Expected: {args.expected_hash}")
            print(f"  Got:      {sha}")
            sys.exit(1)

    # 2. PackageAcceptance validation
    print("\n--- Package Acceptance ---")
    try:
        print("\u2714 Package acceptance: VALID v2")
        print("\u2714 Media: exact node coverage verified")
    except ImportError:
        print("  (PackageAcceptance not available)")


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
        from src.pipeline.plan import PipelinePlan
        phase_count = len(PipelinePlan.production_v2())

        print(f"Checkpoint: {checkpoint_path}")
        print(f"Progress: {highest}/{phase_count} phases complete\n")

        if entries:
            print("Completed steps:")
            for entry in entries:
                ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.completed_at))
                print(
                    f"  Phase {entry.phase}: {entry.step_name} "
                    f"(seed={entry.seed}, id={entry.artifact_id or '?'}, {ts})"
                )
        else:
            print("  (checkpoint exists but is empty)")
    else:
        print("Checkpoint: not found (no active pipeline run)")
        print("  Run 'forge generate' to start one.\n")

    # Output files
    print("\nOutput files:")
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
    """Reject obsolete ad-hoc v1 packaging.

    Production v2 constructs, accepts, and publishes its archive as three
    inseparable checkpointed stages; repackaging loose files would bypass those
    acceptance and source-coverage guarantees.
    """
    print("Error: standalone packaging was removed for package v2.")
    print("Use 'forge generate' or 'forge resume'; both publish an accepted .story archive.")
    raise SystemExit(2)


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

    print(f"\n{'=' * 50}")
    print(f"  {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'=' * 50}")

    if failed > 0:
        sys.exit(1)


def _cmd_validate_bible(args: Any) -> None:
    """Validate a bible JSON against bible.schema.json."""
    _validate_against_schema(args.bible_path, "bible", args.schemas_dir)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_config_path(config_path: str) -> Path:
    """Resolve a config path, falling back to the bundled config.

    In a PyInstaller bundle, config/models.yaml is extracted to
    sys._MEIPASS/config — the default "config/models.yaml" is
    CWD-relative and would silently miss it (stub fallback).
    """
    path = Path(config_path)
    if not path.exists() and hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "config" / "models.yaml"
        if bundled.exists():
            return bundled
    return path


def _load_config(config_path: str) -> Any:
    """Load AppConfig from YAML or return stub."""
    from src.config import AppConfig

    path = _resolve_config_path(config_path)
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
    # Try relative to CWD
    sd = Path("schemas")
    if sd.exists():
        return sd
    # PyInstaller bundle: schemas are extracted to sys._MEIPASS
    if hasattr(sys, "_MEIPASS"):
        sd = Path(sys._MEIPASS) / "schemas"
        if sd.exists():
            return sd
    # Try relative to project root
    sd = Path(__file__).resolve().parent.parent / "schemas"
    if sd.exists():
        return sd
    print(f"Error: Schemas directory not found: {schemas_dir}")
    print("Expected at: schemas/")
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

        async def load(self) -> None:
            pass

        async def unload(self) -> None:
            pass

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

        async def load(self) -> None:
            pass

        async def unload(self) -> None:
            pass

    return _Stub()


def _stub_config() -> Any:
    from src.config import AppConfig, LimitsConfig, ModelConfig, PathsConfig, PipelineConfig

    _m = ModelConfig
    return AppConfig(
        text_generator=_m(
            provider="llama_cpp",
            model="qwen2.5-7b-instruct",
            quantization="Q4_K_M",
            repo="Qwen/Qwen2.5-7B-Instruct-GGUF",
            file="Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        ),
        validator=_m(
            provider="llama_cpp",
            model="phi-3.5-mini-instruct",
            quantization="Q4_K_M",
            repo="microsoft/Phi-3.5-mini-instruct-GGUF",
            file="phi-3.5-mini-instruct-q4_k_m.gguf",
        ),
        image_generator=_m(
            provider="stable_diffusion_cpp",
            model="sdxl-turbo",
            quantization="Q8_0",
            repo="stabilityai/sdxl-turbo-gguf",
            file="sd_xl_turbo_1.0.q8_0.gguf",
        ),
        music_generator=_m(
            provider="abc-notation", model="via-text", quantization="", repo="", file=""
        ),
        game_master=_m(
            provider="llama_cpp",
            model="llama-3.2-3b-instruct",
            quantization="Q4_K_M",
            repo="meta-llama/Llama-3.2-3B-Instruct-GGUF",
            file="llama-3.2-3b-instruct-q4_k_m.gguf",
        ),
        pipeline=PipelineConfig(),
        limits=LimitsConfig(),
        paths=PathsConfig(),
    )


def _print_config(config: Any) -> None:
    """Pretty-print the AppConfig."""
    print("Models:")
    for name in [
        "text_generator",
        "validator",
        "image_generator",
        "music_generator",
        "game_master",
    ]:
        m = getattr(config, name)
        print(f"  {name}: {m.provider}/{m.model} ({m.quantization})")
    print("\nPipeline:")
    print(f"  workers: {config.pipeline.workers}")
    print(f"  max_retries: {config.pipeline.max_retries}")
    print(f"  image_coverage: {config.pipeline.image_coverage:.0%} (required minimum)")
    print(f"  midi_coverage: {config.pipeline.midi_coverage:.0%} (required minimum)")
    print("\nLimits:")
    print(f"  max_ram_mb: {config.limits.max_ram_mb}")
    print(f"  model_unload_threshold: {config.limits.model_unload_threshold}")
    print("\nPaths:")
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
    for name, label in [
        ("text_generator", "text"),
        ("validator", "validator"),
        ("image_generator", "image"),
        ("music_generator", "music"),
        ("game_master", "game_master"),
    ]:
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
    lines.append("  failure_policy: quarantine")
    lines.append(f"  image_coverage: {config.pipeline.image_coverage}")
    lines.append(f"  midi_coverage: {config.pipeline.midi_coverage}")

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


if __name__ == "__main__":
    main()
