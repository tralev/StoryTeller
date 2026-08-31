"""GenerateStory — Application service for the full generation pipeline.

Phase 5.5 Section A & B: This is the SINGLE entry point for running the
generation pipeline. Both `forge generate` and `scripts/run_overnight.py`
invoke this service.

Phase 5.5B: ModelManager integration — models are registered with RAM
budgets and loaded/unloaded via resource_scope() async context managers.
Replaces manual try/finally blocks. Tracks peak RAM usage.

Model lifecycle (sequential RAM strategy, fits 10 GB):
  1. Load text model   (~4.7 GB)
  2. Bible → Style → Story → Graph → Music
  3. Unload text model  (resource_scope ensures this)
  4. Load image model  (~5.0 GB)
  5. Generate images
  6. Unload image model (resource_scope ensures this)
  7. Indexer → Packager
  ⇒ Peak RAM: ~5.5 GB
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Union

from ..config import AppConfig
from ..job_queue import JobQueue, PipelineContext
from ..pipeline.context import RunContext
from .models import GenerationRequest, GenerationResult

# RAM estimates for default models (Q4_K_M quantization on CPU)
TEXT_MODEL_RAM_MB = 4700
IMAGE_MODEL_RAM_MB = 5000
VALIDATOR_MODEL_RAM_MB = 2500

ExecutionContext = Union[PipelineContext, RunContext]  # noqa: UP007 -- Python 3.9 runtime alias


class GenerateStory:
    """Execute a complete story generation pipeline.

    All resume paths route through this single entry point.
    `forge generate`, `forge resume`, and `run_overnight.py` all
    call `GenerateStory.execute()`.

    Usage:
        service = GenerateStory()
        request = GenerationRequest(seed=42, title="The Iron Schism")
        result = await service.execute(request)

        # Resume from checkpoint:
        request = GenerationRequest(seed=42, resume=True, output_dir="output")
        result = await service.execute(request)

        # Fresh start (clear any existing checkpoints):
        request = GenerationRequest(seed=42, resume=False, output_dir="output")
        result = await service.execute(request)
    """

    # ── public API ──────────────────────────────────────────────────────

    _V2_PRODUCER_VERSIONS: dict[str, str] = {
        "physical_world": "physical-v2",
        "simulate_world": "simulation-v1",
        "world_builder_v2": "bible-prompt-v2",
        "reconcile_world": "reconcile-v1",
        "art_direction_v2": "art-prompt-v2",
        "story_v2": "story-prompt-v2",
        "graph_v2": "graph-prompt-route-v3",
        "media_intents_v2": "media-intent-prompt-v2",
        "image_media_v2": "image-media-v2",
        "local_maps_v2": "local-maps-v1",
        "music_media_v2": "music-media-v1",
        "accept_media_v2": "media-accept-v1",
        "gm_index_v2": "gm-index-v1",
        "package_v2": "package-stage-v1",
        "accept_package_v2": "package-accept-v1",
        "packager": "package-publish-v1",
    }

    @classmethod
    def _checkpoint_producer_fingerprint(cls, step_name: str, run_fingerprint: str) -> str:
        version = cls._V2_PRODUCER_VERSIONS.get(step_name, "legacy-v1")
        return hashlib.sha256(f"{step_name}:{version}:{run_fingerprint}".encode()).hexdigest()

    async def execute(self, request: GenerationRequest) -> GenerationResult:
        """Run the full pipeline and return a GenerationResult.

        Honours request.resume:
          - True (default): load checkpoints, skip completed phases
          - False: clear all checkpoints, start fresh

        Phase 5.6K: Cancellation-safe — on asyncio.CancelledError or
        KeyboardInterrupt, saves checkpoints, unloads models, emits
        PipelineFailed event, then re-raises.
        """
        phase_times: dict[str, float] = {}
        errors: list[str] = []

        # 1. Resolve output directory
        out = Path(request.output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 2. Load configuration
        config = self._load_config(request.config_path)

        # 3. Create ModelManager with configured RAM budget
        from ..backends.model_manager import ModelManager, ModelRole

        budget = config.limits.max_ram_mb
        manager = ModelManager(budget_mb=budget)

        # 4. Create backends
        text_gen = self._create_text_generator(config)
        image_gen = self._create_image_generator(config)
        music_gen = self._create_music_generator()

        # 5. Register backends with ModelManager
        manager.register("text", text_gen, role=ModelRole.TEXT, ram_mb=TEXT_MODEL_RAM_MB)
        manager.register("image", image_gen, role=ModelRole.IMAGE, ram_mb=IMAGE_MODEL_RAM_MB)
        # Phase 5.6E: Register validator — may be deterministic (0 RAM) or LLM-based
        _validator_instance = self._create_validator(config)
        _validator_ram = getattr(_validator_instance, "ram_usage_mb", 0) or 0
        manager.register(
            "validator", _validator_instance, role=ModelRole.VALIDATOR, ram_mb=_validator_ram
        )

        # 6. Compute run fingerprint (before context — used for deterministic run_id)
        from ..storage.checkpoint import CheckpointStore

        # 6b. Compute run fingerprint (config + model file hashes) and,
        # Phase 5.6X X3, the per-model file hashes for manifest provenance
        # (computed once so provenance construction never re-reads multi-GB GGUFs).
        run_fingerprint = self._compute_run_fingerprint(config, out)
        model_file_hashes = self._compute_model_file_hashes(config)

        # 7. Build pipeline context
        # Phase 5.6D: Deterministic run_id — derived from seed + config fingerprint.
        # Same seed + same config = same run_id every time.
        run_spec = request.to_run_spec()
        ctx = RunContext(
            run_id=f"run_{run_fingerprint[:12]}_{request.seed:08x}",
            spec=run_spec,
            config=config,
            output_dir=str(out),
        )
        # Phase 5.6N N4: typed run spec — the typed channel for
        # title/tone/temperature. State writes below are kept only for
        # backward compatibility with tests inspecting ctx.state.
        ctx.state["start_time"] = time.time()
        ctx.state["model_file_hashes"] = model_file_hashes  # Phase 5.6X X3

        # 8. Build step registry
        steps = self._build_steps(
            text_gen,
            image_gen,
            music_gen,
            config,
            str(out),
            validator=_validator_instance,
        )

        # 9. Phase 5.6J: Create EventSink + build orchestrator
        from ..pipeline.events import (
            JsonlEventSink,
            PipelineCompleted,
            PipelineFailed,
        )

        run_id = f"run_{run_fingerprint[:12]}_{request.seed:08x}"
        event_sink = JsonlEventSink(str(out / "pipeline_events.jsonl"))
        self._event_sink = event_sink  # For _save_phase_checkpoint access
        self._evt_run_id = run_id

        ctx.events = event_sink

        checkpoint = CheckpointStore(str(out / "checkpoint.db"))
        ctx.checkpoint_store = checkpoint  # Durable stage/internal checkpoints
        run_spec_path = out / "run_spec.json"
        if request.resume and checkpoint.get_highest_completed_phase() > 0:
            if not run_spec_path.is_file():
                errors.append("resume: stored run_spec.json is missing")
                return self._build_result(ctx, out, phase_times, errors, manager)
            try:
                from ..domain.run_spec import RunSpec

                stored_spec = RunSpec.from_dict(json.loads(run_spec_path.read_text()))
            except (OSError, ValueError, json.JSONDecodeError) as error:
                errors.append(f"resume: invalid stored RunSpec: {error}")
                return self._build_result(ctx, out, phase_times, errors, manager)
            if stored_spec != run_spec:
                errors.append("resume: incoming RunSpec differs from the checkpointed run")
                return self._build_result(ctx, out, phase_times, errors, manager)
        else:
            from ..storage.fs import atomic_write_bytes

            run_spec_bytes = json.dumps(
                run_spec.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
            atomic_write_bytes(run_spec_path, run_spec_bytes)
        queue = JobQueue(event_sink=event_sink, run_id=run_id)

        # ── Phase 5.6H: Declarative pipeline plan ──────────────────
        plan = self._build_plan()
        plan.validate()  # raises PlanValidationError if broken
        ctx.state["checkpoint_phase_map"] = {spec.id: index for index, spec in enumerate(plan, 1)}

        # ── Phase 5.6B: Resume support ─────────────────────────────
        if not request.resume:
            checkpoint.clear()
            ctx.state["resumed_from"] = 0
        else:
            highest = checkpoint.get_highest_completed_phase()
            if highest > 0:
                # Phase 5.6C: Enforce run fingerprint match on resume
                try:
                    self._verify_run_fingerprint(checkpoint, run_fingerprint)
                except Exception as e:
                    errors.append(f"fingerprint: {e}")
                    event_sink.emit(PipelineFailed(run_id=run_id, errors=errors))
                    return self._build_result(ctx, out, phase_times, errors, manager)
                self._restore_checkpoints(ctx, checkpoint)
                ctx.state["resumed_from"] = highest
            else:
                ctx.state["resumed_from"] = 0

        resume_phase = ctx.state.get("resumed_from", 0)

        # ── One production runner owns plan/resource traversal ─────
        from ..pipeline.runner import PipelineRunner

        runner = PipelineRunner(plan=plan, model_manager=manager)

        async def execute_segment(steps_in_segment: list[Any]) -> None:
            role = steps_in_segment[0].model_role if steps_in_segment else None
            segment_label = role or "none"
            segment_start = time.time()
            try:
                await self._execute_segment(
                    steps_in_segment,
                    steps,
                    checkpoint,
                    ctx,
                    resume_phase,
                    run_fingerprint,
                    config,
                    out,
                    queue,
                )
            except Exception as error:
                errors.append(f"{segment_label}_phase: {error}")
                if any(spec.failure_policy == "abort" for spec in steps_in_segment):
                    raise
            finally:
                phase_times[f"{segment_label}_s"] = round(
                    time.time() - segment_start,
                    1,
                )

        try:
            await runner.run(ctx, execute_segment)
        except Exception as error:
            if not errors:
                errors.append(f"pipeline: {error}")
            return self._build_result(ctx, out, phase_times, errors, manager)

        # ── Phase 5.6K: Cancellation-safe finalization ───────────
        try:
            result = self._build_result(ctx, out, phase_times, errors, manager)
            if errors:
                event_sink.emit(PipelineFailed(run_id=run_id, errors=errors))
            else:
                event_sink.emit(
                    PipelineCompleted(
                        run_id=run_id,
                        package_path=result.package_path,
                        content_hash=result.content_hash,
                        total_duration_s=result.total_duration_seconds,
                    )
                )
            return result

        except (asyncio.CancelledError, KeyboardInterrupt):
            # Phase 5.6K: Graceful shutdown on cancel
            cancel_msg = "Pipeline cancelled by user (Ctrl+C)"
            errors.append(cancel_msg)
            event_sink.emit(PipelineFailed(run_id=run_id, errors=errors))

            # K4: Save checkpoint for current progress (best-effort)
            try:
                from ..storage.checkpoint import CheckpointStore

                for step_name in plan.step_ids():
                    canonical = CheckpointStore.canonical_key(step_name)
                    if ctx.outputs.get(canonical):
                        self._save_phase_checkpoint(
                            checkpoint,
                            step_name,
                            run_fingerprint,
                            ctx,
                            event_sink=event_sink,
                            evt_run_id=run_id,
                        )
            except Exception:
                pass

            # K5: Unload all models
            try:
                await manager.unload_all()
            except Exception:
                pass

            # K6: Re-raise so CLI returns non-zero exit code
            raise

    # ── Phase 5.6H: segment execution helper ───────────────────────────

    async def _execute_segment(
        self,
        segment: list[Any],  # list[StepSpec]
        steps: dict[str, Any],
        checkpoint: Any,
        ctx: ExecutionContext,
        resume_phase: int,
        run_fingerprint: str,
        config: AppConfig,
        out: Path,
        queue: Any,  # JobQueue
    ) -> None:
        """Execute a contiguous segment of pipeline steps.

        All steps in a segment share the same model_role (or all None).
        The caller handles model load/unload via resource_scope().
        """
        for spec in segment:
            from ..pipeline.errors import DependencyError

            for requirement in spec.requires:
                if ctx.outputs.get(requirement) is None:
                    raise DependencyError(spec.id, requirement)

            # Phase 5.6H: Never skip the packager — it must always run
            # because the .story file may have been deleted.
            if spec.id != "packager" and self._should_skip(spec.id, resume_phase, checkpoint):
                continue

            if spec.parallel_per_node:
                raise ValueError(f"LEGACY-PLAN: parallel batch step is not supported: {spec.id}")
            elif spec.id == "packager":
                await queue.execute_step(steps["packager"], ctx, "packager")
                self._save_phase_checkpoint(
                    checkpoint,
                    "packager",
                    run_fingerprint,
                    ctx,
                    event_sink=self._event_sink,
                    evt_run_id=self._evt_run_id,
                )
                from ..storage.package_v2 import validate_v2_package

                package = ctx.outputs.get("packager", {}).get("package_path", "")
                acceptance = validate_v2_package(package)
                if not acceptance.accepted:
                    from ..pipeline.errors import PackageValidationError

                    raise PackageValidationError(
                        package,
                        [f"{issue.code}: {issue.message}" for issue in acceptance.issues],
                    )
            else:
                # Execute one production-v2 stage.
                await queue.execute_step(
                    steps[spec.id],
                    ctx,
                    spec.id,
                )
                self._save_phase_checkpoint(
                    checkpoint,
                    spec.id,
                    run_fingerprint,
                    ctx,
                    event_sink=self._event_sink,
                    evt_run_id=self._evt_run_id,
                )

    # ── Phase 5.6B: resume helpers ─────────────────────────────────────

    @staticmethod
    def _verify_run_fingerprint(
        checkpoint: Any,  # CheckpointStore
        incoming: str,
    ) -> None:
        """Phase 5.6C: Reject resume if config/models changed.

        Compares the incoming run fingerprint (computed from current
        config + model files) with the one stored in the checkpoint DB.

        Raises:
            FingerprintMismatchError: if fingerprints differ.
        A missing fingerprint is unverifiable and therefore terminal.
        """
        stored = checkpoint.get_run_fingerprint()
        if stored is None or stored == "":
            from ..pipeline.errors import FingerprintMismatchError

            raise FingerprintMismatchError("<missing>", incoming)

        if stored != incoming:
            from ..pipeline.errors import FingerprintMismatchError

            raise FingerprintMismatchError(stored, incoming)

    @staticmethod
    def _should_skip(
        step_name: str,
        resume_phase: int,
        checkpoint: Any,  # CheckpointStore
    ) -> bool:
        """Determine if a step should be skipped on resume.

        Returns True if the step has a valid checkpoint (output was
        saved to disk AND the checkpoint entry exists). On resume,
        the output is restored from the checkpoint so downstream
        steps can access it.
        """
        if resume_phase < 1:
            return False
        entry = checkpoint.load(step_name)
        return entry is not None

    @staticmethod
    def _restore_checkpoints(
        ctx: ExecutionContext,
        checkpoint: Any,  # CheckpointStore
    ) -> None:
        """Restore all saved checkpoints into context.outputs.

        Reads the canonical output_key for each step and restores
        the artifact into ctx.outputs so downstream steps can access
        it. For example, ``world_builder_v2`` restores ``bible``.

        Phase 5.6X X4: dependency-ID invalidation. Each checkpoint records
        the artifact IDs of its upstream inputs at save time. On restore we
        recompute those upstream IDs from the freshly restored outputs — if
        any upstream changed (or its own checkpoint was dropped), the stored
        depends_on no longer matches and the downstream checkpoint is
        deleted so it regenerates. Entries are phase-ordered, so upstreams
        restore before their dependents are checked.
        """
        from ..storage.checkpoint import CheckpointStore
        from ..storage.provenance import artifact_id

        entries = checkpoint.load_all()
        for entry in entries:
            key = entry.output_key or CheckpointStore.canonical_key(entry.step_name)
            if not (key and entry.output_json):
                continue

            restored = json.loads(entry.output_json)
            expected_producer = GenerateStory._checkpoint_producer_fingerprint(
                entry.step_name,
                entry.run_fingerprint,
            )
            if entry.producer_fingerprint and entry.producer_fingerprint != expected_producer:
                checkpoint.delete(entry.step_name)
                continue
            if entry.artifact_id and artifact_id(key, restored) != entry.artifact_id:
                checkpoint.delete(entry.step_name)
                continue

            stale = False
            for file_name, expected_hash in entry.file_hashes.items():
                path = Path(file_name)
                if (
                    not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash
                ):
                    stale = True
                    break

            # X4: verify stored dependency IDs still match restored upstreams
            for dep_key, dep_id in (entry.depends_on or {}).items():
                if stale:
                    break
                upstream = ctx.outputs.get(dep_key)
                if upstream is None or not isinstance(upstream, dict):
                    stale = True
                    break
                if artifact_id(dep_key, upstream) != dep_id:
                    stale = True
                    break

            if stale:
                # Inputs changed — this checkpoint is stale. Drop it so the
                # step (and everything below it) regenerates.
                checkpoint.delete(entry.step_name)
                continue

            ctx.outputs[key] = restored

    @staticmethod
    def _checkpoint_file_hashes(output: dict[str, Any]) -> dict[str, str]:
        """Hash durable files named by a step output and its JSON media refs."""
        candidates: set[Path] = set()
        for field in ("path", "root", "package_path", "semantic_path"):
            value = output.get(field)
            if not isinstance(value, str) or not value:
                continue
            path = Path(value).resolve()
            if path.is_file():
                candidates.add(path)
            elif path.is_dir():
                candidates.update(item for item in path.rglob("*") if item.is_file())

        # Reference manifests such as image_refs.json and media.json contain
        # paths relative to their narrative-project directory.
        for manifest in tuple(candidates):
            if manifest.suffix != ".json":
                continue
            try:
                payload = json.loads(manifest.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            stack = [payload]
            while stack:
                value = stack.pop()
                if isinstance(value, dict):
                    for key, child in value.items():
                        if key == "path" and isinstance(child, str):
                            referenced = (manifest.parent / child).resolve()
                            if referenced.is_file():
                                candidates.add(referenced)
                        else:
                            stack.append(child)
                elif isinstance(value, list):
                    stack.extend(value)
        return {
            str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(candidates)
        }

    @staticmethod
    def _save_phase_checkpoint(
        checkpoint: Any,
        step_name: str,
        run_fingerprint: str,
        ctx: ExecutionContext,
        event_sink: Any = None,  # Phase 5.6J
        evt_run_id: str = "",  # Phase 5.6J
    ) -> None:
        """Save a checkpoint after a phase completes.

        Phase 5.6X X4: records the upstream dependency artifact IDs
        (``depends_on``) so a resume can detect stale downstream checkpoints
        whose inputs changed and regenerate them.
        """
        from ..storage.checkpoint import CheckpointStore
        from ..storage.provenance import DEPENDENCIES, artifact_id

        canonical = CheckpointStore.canonical_key(step_name)
        output_data = ctx.outputs.get(canonical)
        if output_data is None:
            # Permit stages whose step ID is itself the canonical output key.
            output_data = ctx.outputs.get(step_name)
        if output_data is not None:
            phase_map = ctx.state.get("checkpoint_phase_map", {})
            phase_num = phase_map.get(step_name, 0) if isinstance(phase_map, dict) else 0
            # X4: capture the artifact IDs of this step's upstream inputs
            depends_on: dict[str, str] = {}
            for dep_key in DEPENDENCIES.get(canonical, []):
                dep_data = ctx.outputs.get(dep_key)
                if isinstance(dep_data, dict):
                    depends_on[dep_key] = artifact_id(dep_key, dep_data)
            checkpoint.save(
                step_name=step_name,
                output_key=canonical,
                phase=phase_num,
                seed=ctx.seed,
                output=output_data if isinstance(output_data, dict) else {"data": str(output_data)},
                artifact_id=(
                    artifact_id(canonical, output_data) if isinstance(output_data, dict) else ""
                ),
                run_fingerprint=run_fingerprint,
                depends_on=depends_on,
                file_hashes=GenerateStory._checkpoint_file_hashes(output_data),
                producer_fingerprint=GenerateStory._checkpoint_producer_fingerprint(
                    step_name,
                    run_fingerprint,
                ),
            )
            # Phase 5.6J: Emit CheckpointSaved event
            if event_sink is not None:
                from ..pipeline.events import CheckpointSaved as EvtCs

                event_sink.emit(
                    EvtCs(
                        run_id=evt_run_id,
                        step_id=step_name,
                        phase=phase_num,
                    )
                )

    # ── schemas dir ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_schemas_dir() -> str:
        """Resolve the schemas/ directory for manifest/package validation."""
        import os

        if os.environ.get("STORYTELLER_SCHEMAS_DIR"):
            return os.environ["STORYTELLER_SCHEMAS_DIR"]
        # PyInstaller bundle: schemas are extracted to sys._MEIPASS
        if hasattr(sys, "_MEIPASS"):
            bundled = Path(sys._MEIPASS) / "schemas"
            if bundled.exists():
                return str(bundled)
        return str(Path(__file__).resolve().parent.parent.parent / "schemas")

    # ── run fingerprint ───────────────────────────────────────────────────

    @staticmethod
    def _compute_model_file_hashes(config: AppConfig) -> dict[str, str]:
        """Phase 5.6X X3: SHA-256 per model role (text/validator/image).

        Returns an empty dict when the model files are missing (unit tests,
        stub configs). Used by the manifest's provenance.produced_by section
        to attribute artifacts to the exact model files — computed once here
        so provenance construction never re-reads multi-GB GGUFs.
        """
        hashes: dict[str, str] = {}
        models_dir = Path(config.paths.models_dir)
        roles = {
            "text_generator": config.text_generator,
            "validator": config.validator,
            "image_generator": config.image_generator,
        }
        for role, model_info in roles.items():
            model_path = models_dir / model_info.file
            if model_path.exists():
                hashes[role] = hashlib.sha256(
                    model_path.read_bytes(),
                ).hexdigest()
        return hashes

    @staticmethod
    def _compute_run_fingerprint(config: AppConfig, out: Path) -> str:
        """Compute a deterministic fingerprint of the run configuration.

        Includes: config hash + model file hashes.
        Two runs with the same fingerprint and seed SHOULD produce
        identical canonical content.

        Phase 5.6D: Excludes seed — fingerprint is per-(config,models),
        while run_id combines seed + fingerprint for uniqueness.

        Reuses ``_compute_model_file_hashes`` so the multi-GB GGUF files are
        read exactly once per run (Phase 5.6X X3 needs the same hashes).
        """
        hasher = hashlib.sha256()

        # Hash config (canonical fields only — skip paths, limits)
        config_canonical = {
            "text_generator": config.text_generator.model,
            "text_quantization": config.text_generator.quantization,
            "validator": config.validator.model,
            "validator_quantization": config.validator.quantization,
            "image_generator": config.image_generator.model,
            "image_quantization": config.image_generator.quantization,
            "music_generator": config.music_generator.model,
        }
        hasher.update(json.dumps(config_canonical, sort_keys=True).encode())

        # Hash model files (single read — shared with X3 provenance hashes)
        for role, file_hash in GenerateStory._compute_model_file_hashes(config).items():
            hasher.update(f"{role}:{file_hash}".encode())

        return hasher.hexdigest()

    # ── result building ──────────────────────────────────────────────────

    @staticmethod
    def _build_result(
        ctx: ExecutionContext,
        out: Path,
        phase_times: dict[str, float],
        errors: list[str],
        manager: Any,  # ModelManager
    ) -> GenerationResult:
        """Build a GenerationResult from context state."""
        total = time.time() - ctx.state["start_time"]

        pkg_data = ctx.outputs.get_packager() or {}
        pkg_manifest = ctx.outputs.get_manifest() or {}
        package_path = ""
        package_size = 0
        content_hash = ""
        artifact_id = "unknown"
        image_coverage = 1.0
        midi_coverage = 1.0
        media_complete = False
        if pkg_data and isinstance(pkg_data, dict) and isinstance(pkg_manifest, dict):
            candidate_path = pkg_data.get("package_path")
            candidate_hash = pkg_manifest.get("content_hash", "") or pkg_data.get(
                "content_hash", ""
            )
            if not isinstance(candidate_path, str) or not candidate_path or not Path(
                candidate_path
            ).is_file() or not isinstance(candidate_hash, str) or not candidate_hash:
                if not errors:
                    errors.append("packaging: required package path or content hash is missing")
                candidate_path = ""
                candidate_hash = ""
            package_path = candidate_path
            package_size = pkg_data.get("package_size", 0) if package_path else 0
            content_hash = candidate_hash
            # Phase 5.6 Q5: media completeness from acceptance
            coverage = pkg_data.get("coverage", {})
            if not isinstance(coverage, dict):
                coverage = {}
            image_coverage = float(coverage.get("images", 1.0))
            midi_coverage = float(coverage.get("midi", 1.0))
            media_complete = bool(package_path and pkg_data.get("media_complete", True))
            # artifact_id is content-derived, in meta sub-object
            meta = pkg_manifest.get("meta", {})
            if not isinstance(meta, dict):
                meta = {}
            if package_path:
                artifact_id = meta.get("artifact_id", f"package_{content_hash[:32]}")
            # Update peak RAM in operational metadata
            meta["peak_ram_mb"] = manager.peak_ram_mb

        artifact_hashes: dict[str, str] = {}
        for key, data in ctx.outputs.items():
            if isinstance(data, dict) and key not in ("manifest",):
                try:
                    artifact_hashes[key] = hashlib.sha256(
                        json.dumps(data, sort_keys=True).encode()
                    ).hexdigest()[:16]
                except Exception:
                    artifact_hashes[key] = "error"

        return GenerationResult(
            artifact_id=artifact_id,
            package_path=str(package_path),
            package_size=package_size,
            content_hash=content_hash,
            phases=phase_times,
            artifacts=artifact_hashes,
            total_duration_seconds=round(total, 1),
            peak_ram_mb=manager.peak_ram_mb,
            ram_budget_mb=manager.budget_mb,
            errors=errors,
            image_coverage=image_coverage,
            midi_coverage=midi_coverage,
            media_complete=media_complete,
        )

    # ── internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _load_config(config_path: str) -> AppConfig:
        """Load AppConfig, falling back to the PyInstaller-bundled config.

        Post-flatten audit: the default "config/models.yaml" is CWD-relative;
        in a bundle the config lives at sys._MEIPASS/config/models.yaml.
        Without this fallback, standalone runs silently used the stub config.
        """
        path = Path(config_path)
        if not path.exists() and hasattr(sys, "_MEIPASS"):
            bundled = Path(sys._MEIPASS) / "config" / "models.yaml"
            if bundled.exists():
                path = bundled
        if path.exists():
            return AppConfig.from_yaml(str(path))
        return GenerateStory._stub_config()

    @staticmethod
    def _create_text_generator(config: AppConfig) -> Any:
        """Phase 5.6F: Use ProviderRegistry for backend selection."""
        from ..backends.registry import ProviderRegistry

        return ProviderRegistry.create_text(config.text_generator, strict=True)

    @staticmethod
    def _create_image_generator(config: AppConfig) -> Any:
        """Phase 5.6F: Use ProviderRegistry for backend selection."""
        from ..backends.registry import ProviderRegistry

        return ProviderRegistry.create_image(config.image_generator, strict=True)

    @staticmethod
    def _create_music_generator() -> Any:
        """Phase 5.6F: Use ProviderRegistry for backend selection."""
        from ..backends.registry import ProviderRegistry
        from ..config import ModelConfig

        return ProviderRegistry.create_music(
            ModelConfig(
                provider="abc-notation",
                model="via-text",
                quantization="",
            )
        )

    @staticmethod
    def _create_validator(config: AppConfig) -> Any:
        """Phase 5.6E+F: Use ProviderRegistry for validator backend."""
        from ..backends.registry import ProviderRegistry

        return ProviderRegistry.create_validator(config.validator, strict=True)

    @staticmethod
    def _build_plan() -> Any:
        """Return the single production plan (overridable only by test harnesses)."""
        from ..pipeline.plan import PipelinePlan

        return PipelinePlan.production_v2()

    @staticmethod
    def _build_steps(
        text_gen: Any,
        image_gen: Any,
        music_gen: Any,
        config: AppConfig,
        output_dir: str,
        validator: Any = None,
    ) -> dict[str, Any]:
        from ..pipeline.policy import ExecutionPolicy  # Phase 5.6G
        from .v2_steps import (
            AcceptMediaV2Stage,
            AcceptPackageV2Stage,
            ArtDirectionV2Stage,
            BibleV2Stage,
            GmIndexV2Stage,
            GraphV2Stage,
            ImageMediaV2Stage,
            LocalMapsV2Stage,
            MediaIntentsV2Stage,
            MusicMediaV2Stage,
            PackageV2Stage,
            PhysicalWorldStage,
            PublishPackageV2Stage,
            ReconcileWorldStage,
            SimulateWorldStage,
            StoryV2Stage,
        )

        policy = ExecutionPolicy.from_config(config.pipeline)

        return {
            "physical_world": PhysicalWorldStage(
                "physical_world", "world_physical", output_dir, policy=policy
            ),
            "simulate_world": SimulateWorldStage(
                "simulate_world", "world", output_dir, policy=policy
            ),
            "local_maps_v2": LocalMapsV2Stage(
                "local_maps_v2",
                "local_maps",
                output_dir,
                policy=policy,
            ),
            "world_builder_v2": BibleV2Stage(
                "world_builder_v2",
                "bible",
                output_dir,
                generator=text_gen,
                policy=policy,
            ),
            "reconcile_world": ReconcileWorldStage(
                "reconcile_world",
                "reconciliation",
                output_dir,
                generator=validator,
                policy=policy,
            ),
            "art_direction_v2": ArtDirectionV2Stage(
                "art_direction_v2",
                "style_bible",
                output_dir,
                generator=text_gen,
                policy=policy,
            ),
            "story_v2": StoryV2Stage(
                "story_v2",
                "story",
                output_dir,
                generator=text_gen,
                policy=policy,
            ),
            "graph_v2": GraphV2Stage(
                "graph_v2",
                "narrative_project",
                output_dir,
                generator=text_gen,
                policy=policy,
            ),
            "media_intents_v2": MediaIntentsV2Stage(
                "media_intents_v2",
                "media_intents",
                output_dir,
                generator=text_gen,
                policy=policy,
            ),
            "image_media_v2": ImageMediaV2Stage(
                "image_media_v2",
                "images",
                output_dir,
                generator=image_gen,
                policy=policy,
            ),
            "music_media_v2": MusicMediaV2Stage(
                "music_media_v2",
                "midi",
                output_dir,
                policy=policy,
            ),
            "accept_media_v2": AcceptMediaV2Stage(
                "accept_media_v2",
                "media",
                output_dir,
                policy=policy,
            ),
            "gm_index_v2": GmIndexV2Stage("gm_index_v2", "gm_index", output_dir, policy=policy),
            "package_v2": PackageV2Stage(
                "package_v2", "package_candidate", output_dir, policy=policy
            ),
            "accept_package_v2": AcceptPackageV2Stage(
                "accept_package_v2",
                "package_acceptance",
                output_dir,
                policy=policy,
            ),
            "packager": PublishPackageV2Stage("packager", "packager", output_dir, policy=policy),
        }

    @staticmethod
    def _stub_config() -> AppConfig:
        from ..config import LimitsConfig, ModelConfig, PathsConfig, PipelineConfig

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
