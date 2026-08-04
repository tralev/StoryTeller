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
from typing import Any, cast

from .models import GenerationRequest, GenerationResult
from ..config import AppConfig
from ..job_queue import PipelineContext
from ..pipeline.artifacts import RunSpec

# RAM estimates for default models (Q4_K_M quantization on CPU)
TEXT_MODEL_RAM_MB = 4700
IMAGE_MODEL_RAM_MB = 5000
VALIDATOR_MODEL_RAM_MB = 2500


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
        manager.register("validator", _validator_instance, role=ModelRole.VALIDATOR,
                         ram_mb=_validator_ram)

        # 6. Compute run fingerprint (before context — used for deterministic run_id)
        from ..storage.checkpoint import CheckpointStore
        from ..storage.orchestrator import Orchestrator

        run_fingerprint = self._compute_run_fingerprint(config, out)

        # 7. Build pipeline context
        # Phase 5.6D: Deterministic run_id — derived from seed + config fingerprint.
        # Same seed + same config = same run_id every time.
        ctx = PipelineContext(
            run_id=f"run_{run_fingerprint[:12]}_{request.seed:08x}",
            seed=request.seed,
            config=config,
            output_dir=str(out),
        )
        # Phase 5.6N N4: typed run spec — the typed channel for
        # title/tone/temperature. State writes below are kept only for
        # backward compatibility with tests inspecting ctx.state.
        ctx.spec = RunSpec(
            title=request.title,
            tone=request.tone,
            temperature=request.temperature,
        )
        ctx.state["tone"] = request.tone
        ctx.state["title"] = request.title
        ctx.state["temperature"] = request.temperature
        ctx.state["start_time"] = time.time()

        # 8. Build step registry
        steps = self._build_steps(text_gen, image_gen, music_gen, config, str(out))

        # 9. Phase 5.6J: Create EventSink + build orchestrator
        from ..pipeline.events import (
            JsonlEventSink, ModelLoaded, ModelUnloaded, NullEventSink,
            PipelineCompleted, PipelineFailed, PipelineStarted,
        )
        run_id = f"run_{run_fingerprint[:12]}_{request.seed:08x}"
        event_sink = JsonlEventSink(str(out / "pipeline_events.jsonl"))
        self._event_sink = event_sink  # For _save_phase_checkpoint access
        self._evt_run_id = run_id

        event_sink.emit(PipelineStarted(
            run_id=run_id, seed=request.seed,
            title=request.title, tone=request.tone,
        ))

        checkpoint = CheckpointStore(str(out / "checkpoint.db"))
        ctx.checkpoint_store = checkpoint  # Phase 5.6L: Sub-step checkpoints for StoryWriter/GameDesigner
        orchestrator = Orchestrator(
            checkpoint, steps, event_sink=event_sink, run_id=run_id,
        )
        orchestrator.run_fingerprint = run_fingerprint

        # ── Phase 5.6H: Declarative pipeline plan ──────────────────
        from ..pipeline.plan import PipelinePlan
        plan = PipelinePlan.standard()
        plan.validate()  # raises PlanValidationError if broken

        # ── Phase 5.6B: Resume support ─────────────────────────────
        if not request.resume:
            checkpoint.clear()
            checkpoint.clear_nodes("image_generator")
            checkpoint.clear_nodes("music_generator")
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

        # ── Plan-driven execution by model_role segments ───────────
        for role, steps_in_segment in plan.group_by_model_role():
            segment_start = time.time()
            segment_label = role or "none"

            try:
                if role is not None:
                    # Load the model for this segment, run steps, auto-unload
                    async with manager.resource_scope(role):
                        await self._execute_segment(
                            steps_in_segment, steps, checkpoint, ctx,
                            resume_phase, run_fingerprint, config, out,
                            orchestrator.queue,
                        )
                else:
                    # No model needed (indexer, packager, manifest, acceptance)
                    await self._execute_segment(
                        steps_in_segment, steps, checkpoint, ctx,
                        resume_phase, run_fingerprint, config, out,
                        orchestrator.queue,
                    )
            except Exception as e:
                errors.append(f"{segment_label}_phase: {e}")

            phase_times[f"{segment_label}_s"] = round(time.time() - segment_start, 1)

            # Abort on error from non-quarantine phases
            if errors and any(
                s.failure_policy == "abort" for s in steps_in_segment
            ):
                event_sink.emit(PipelineFailed(run_id=run_id, errors=errors))
                return self._build_result(ctx, out, phase_times, errors, manager)

        # ── Phase 5.6K: Cancellation-safe finalization ───────────
        try:
            result = self._build_result(ctx, out, phase_times, errors, manager)
            if errors:
                event_sink.emit(PipelineFailed(run_id=run_id, errors=errors))
            else:
                event_sink.emit(PipelineCompleted(
                    run_id=run_id,
                    package_path=result.package_path,
                    content_hash=result.content_hash,
                    total_duration_s=result.total_duration_seconds,
                ))
            return result

        except (asyncio.CancelledError, KeyboardInterrupt):
            # Phase 5.6K: Graceful shutdown on cancel
            cancel_msg = "Pipeline cancelled by user (Ctrl+C)"
            errors.append(cancel_msg)
            event_sink.emit(PipelineFailed(run_id=run_id, errors=errors))

            # K4: Save checkpoint for current progress (best-effort)
            try:
                from ..storage.checkpoint import CheckpointStore as _CS
                for step_name in ["world_builder", "art_director", "story_writer",
                                  "game_designer", "music_generator", "image_generator",
                                  "indexer", "packager"]:
                    canonical = _CS.canonical_key(step_name)
                    if ctx.outputs.get(canonical):
                        self._save_phase_checkpoint(
                            checkpoint, step_name, run_fingerprint, ctx,
                            event_sink=event_sink, evt_run_id=run_id,
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
        ctx: PipelineContext,
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
        schemas_dir = self._resolve_schemas_dir()

        for spec in segment:
            # Phase 5.6H: Never skip the packager — it must always run
            # because the .story file may have been deleted.
            # Also never skip batch steps (parallel_per_node) —
            # BatchScheduler handles its own per-node resume logic.
            if spec.id != "packager" and not spec.parallel_per_node and self._should_skip(spec.id, resume_phase, checkpoint):
                continue

            if spec.parallel_per_node:
                await self._execute_batch_step(
                    spec, steps, checkpoint, ctx, run_fingerprint, config, out,
                )
            elif spec.id == "packager":
                # Finalize: indexer → manifest → packager → acceptance.
                # Always runs — never skipped by _should_skip because the
                # .story file may have been deleted even when checkpoint exists.
                await self._execute_finalize(
                    spec, steps, checkpoint, ctx, run_fingerprint, config, out, schemas_dir, queue,
                )
            else:
                # Single-step execution (world_builder, art_director, etc.)
                await queue.execute_step(
                    steps[spec.id], ctx, spec.id,
                )
                self._save_phase_checkpoint(
                    checkpoint, spec.id, run_fingerprint, ctx,
                    event_sink=self._event_sink, evt_run_id=self._evt_run_id,
                )

    async def _execute_batch_step(
        self,
        spec: Any,  # StepSpec
        steps: dict[str, Any],
        checkpoint: Any,
        ctx: PipelineContext,
        run_fingerprint: str,
        config: AppConfig,
        out: Path,
    ) -> None:
        """Execute a parallel-per-node batch step (image or music)."""
        from ..pipeline.batch import BatchScheduler, NodeJob
        from ..pipeline.policy import ExecutionPolicy

        step = steps[spec.id]
        graph = ctx.outputs.get_graph()  # Phase 5.6N N5
        if graph is None:
            return

        if spec.id == "image_generator":
            style_bible = ctx.outputs.get_style_bible()
            if style_bible is None:
                return
            jobs = NodeJob.from_graph(cast(dict[str, Any], graph), key="image_prompt")
            asset_dir = out / "images"
            thumb_dir = out / "thumbnails"
            asset_dir.mkdir(parents=True, exist_ok=True)
            thumb_dir.mkdir(parents=True, exist_ok=True)
            scheduler = BatchScheduler(
                max_concurrency=config.pipeline.workers,
                checkpoint_store=checkpoint,
                step_name=spec.id,
                policy=ExecutionPolicy.from_config(config.pipeline),
                expected_seed=ctx.seed,
            )
            result = await scheduler.run(
                jobs, step.generate_node,
                style_bible, ctx.seed, asset_dir, thumb_dir,
            )
            self._store_batch_result(ctx, result, spec.output_key,
                                     "image_count", asset_dir, ".png")
        else:
            # Music generator
            jobs = NodeJob.from_graph(cast(dict[str, Any], graph), key="music_tone")
            asset_dir = out / "midi"
            asset_dir.mkdir(parents=True, exist_ok=True)
            scheduler = BatchScheduler(
                max_concurrency=config.pipeline.workers,
                checkpoint_store=checkpoint,
                step_name=spec.id,
                policy=ExecutionPolicy.from_config(config.pipeline),
                expected_seed=ctx.seed,
            )
            result = await scheduler.run(
                jobs, step.generate_node,
                ctx.seed, asset_dir,
            )
            self._store_batch_result(ctx, result, spec.output_key,
                                     "music_count", asset_dir, ".mid")

        self._save_phase_checkpoint(
            checkpoint, spec.id, run_fingerprint, ctx,
            event_sink=self._event_sink, evt_run_id=self._evt_run_id,
        )

    async def _execute_finalize(
        self,
        spec: Any,  # StepSpec (ignored — finalize is a multi-step phase)
        steps: dict[str, Any],
        checkpoint: Any,
        ctx: PipelineContext,
        run_fingerprint: str,
        config: AppConfig,
        out: Path,  # noqa: ARG002 — kept for future path use
        schemas_dir: str,
        queue: Any,  # JobQueue
    ) -> None:
        """Execute the finalize phase: manifest → packager → acceptance.

        Note: indexer already ran in _execute_segment (it precedes packager
        in the plan). This method handles the packager-specific finalization.
        """
        # 1. Ensure indexer checkpoint (may have been skipped on resume)
        if "gm_index" not in ctx.outputs or not isinstance(ctx.outputs.get("gm_index"), dict):
            from ..storage.indexer import GmIndexer
            indexer = GmIndexer()
            result = await indexer.run(ctx)
            ctx.outputs["gm_index"] = result.data
            self._save_phase_checkpoint(checkpoint, "indexer", run_fingerprint, ctx, event_sink=self._event_sink, evt_run_id=self._evt_run_id)

        # 2. Build manifest with mandatory schema validation
        from ..storage.manifest_builder import ManifestBuilder
        manifest_builder = ManifestBuilder(schemas_dir=schemas_dir)
        manifest_output = await manifest_builder.run(ctx)
        ctx.outputs["manifest"] = manifest_output.data

        # 3. Package into .story ZIP
        await queue.execute_step(
            steps["packager"], ctx, "packager",
        )
        self._save_phase_checkpoint(checkpoint, "packager", run_fingerprint, ctx, event_sink=self._event_sink, evt_run_id=self._evt_run_id)

        # 4. Package acceptance (unconditional)
        pkg_data = ctx.outputs.get("packager", {})
        if not isinstance(pkg_data, dict):
            from ..pipeline.errors import PackageValidationError
            raise PackageValidationError(
                str(out),
                ["Packager did not produce output — cannot validate package"],
            )
        package_path = pkg_data.get("package_path", "")
        if not package_path:
            from ..pipeline.errors import PackageValidationError
            raise PackageValidationError(
                str(out),
                ["Packager returned empty package_path — cannot validate"],
            )
        from ..storage.package_acceptance import PackageAcceptance
        from ..pipeline.policy import CoveragePolicy
        gate = PackageAcceptance(
            schemas_dir=schemas_dir,
            coverage=CoveragePolicy.from_config(config.pipeline),
        )
        acceptance = gate.validate(package_path)
        if not acceptance.accepted:
            from ..pipeline.errors import PackageValidationError
            raise PackageValidationError(package_path, [acceptance.format_issues()])
        # Phase 5.6 Q5: record media completeness on the packager output so
        # the CLI can distinguish fully complete from incomplete-but-accepted.
        pkg_data["media_complete"] = acceptance.complete
        pkg_data["coverage"] = acceptance.coverage

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
        Warns (no raise): if stored fingerprint is empty (legacy DB).
        """
        stored = checkpoint.get_run_fingerprint()
        if stored is None or stored == "":
            # Legacy DB — no fingerprint was saved. Warn but proceed.
            import warnings
            warnings.warn(
                "Resuming from checkpoint with no stored run fingerprint. "
                "Cannot verify config/model consistency. "
                "If the models have changed, output may be inconsistent.",
                stacklevel=2,
            )
            return

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
        ctx: PipelineContext,
        checkpoint: Any,  # CheckpointStore
    ) -> None:
        """Restore all saved checkpoints into context.outputs.

        Reads the canonical output_key for each step and restores
        the artifact into ctx.outputs so downstream steps can access
        it. E.g., "world_builder" → ctx.outputs["bible"].
        """
        from ..storage.checkpoint import CheckpointStore as _CS
        entries = checkpoint.load_all()
        for entry in entries:
            key = entry.output_key or _CS.canonical_key(entry.step_name)
            if key and entry.output_json:
                ctx.outputs[key] = json.loads(entry.output_json)

    @staticmethod
    def _save_phase_checkpoint(
        checkpoint: Any,
        step_name: str,
        run_fingerprint: str,
        ctx: PipelineContext,
        event_sink: Any = None,  # Phase 5.6J
        evt_run_id: str = "",  # Phase 5.6J
    ) -> None:
        """Save a checkpoint after a phase completes."""
        from ..storage.checkpoint import CheckpointStore

        _PHASE_MAP: dict[str, int] = {
            "world_builder": 1,
            "art_director": 2,
            "story_writer": 3,
            "game_designer": 4,
            "music_generator": 5,
            "image_generator": 5,
            "indexer": 6,
            "packager": 7,
        }

        canonical = CheckpointStore.canonical_key(step_name)
        output_data = ctx.outputs.get(canonical)
        if output_data is None:
            # Try the step_name directly (image_generator stores as "images", etc.)
            output_data = ctx.outputs.get(step_name)
        if output_data is not None:
            phase_num = _PHASE_MAP.get(step_name, 0)
            checkpoint.save(
                step_name=step_name,
                output_key=canonical,
                phase=phase_num,
                seed=ctx.seed,
                output=output_data if isinstance(output_data, dict) else {"data": str(output_data)},
                run_fingerprint=run_fingerprint,
            )
            # Phase 5.6J: Emit CheckpointSaved event
            if event_sink is not None:
                from ..pipeline.events import CheckpointSaved as EvtCs
                event_sink.emit(EvtCs(
                    run_id=evt_run_id, step_id=step_name, phase=phase_num,
                ))

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
    def _compute_run_fingerprint(config: AppConfig, out: Path) -> str:
        """Compute a deterministic fingerprint of the run configuration.

        Includes: config hash + model file hashes.
        Two runs with the same fingerprint and seed SHOULD produce
        identical canonical content.

        Phase 5.6D: Excludes seed — fingerprint is per-(config,models),
        while run_id combines seed + fingerprint for uniqueness.
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

        # Hash model files if they exist
        models_dir = Path(config.paths.models_dir)
        for model_info in [
            config.text_generator, config.validator,
            config.image_generator,
        ]:
            model_path = models_dir / model_info.file
            if model_path.exists():
                file_hash = hashlib.sha256(model_path.read_bytes()).hexdigest()
                hasher.update(f"{model_info.file}:{file_hash}".encode())

        return hasher.hexdigest()

    # ── result building ──────────────────────────────────────────────────

    @staticmethod
    def _build_result(
        ctx: PipelineContext,
        out: Path,
        phase_times: dict[str, float],
        errors: list[str],
        manager: Any,  # ModelManager
    ) -> GenerationResult:
        """Build a GenerationResult from context state."""
        total = time.time() - ctx.state["start_time"]

        pkg_data = ctx.outputs.get_packager() or {}
        pkg_manifest = ctx.outputs.get_manifest() or {}
        if isinstance(pkg_data, dict) and isinstance(pkg_manifest, dict):
            package_path = pkg_data.get("package_path", str(out / "output.story"))
            package_size = pkg_data.get("package_size", 0)
            content_hash = pkg_manifest.get("content_hash", "")
            # Phase 5.6 Q5: media completeness from acceptance
            _coverage = pkg_data.get("coverage", {}) if isinstance(pkg_data, dict) else {}
            _image_cov = float(_coverage.get("images", 1.0))
            _midi_cov = float(_coverage.get("midi", 1.0))
            # artifact_id is content-derived, in meta sub-object
            meta = pkg_manifest.get("meta", {}) if isinstance(pkg_manifest, dict) else {}
            artifact_id = meta.get("artifact_id", f"package_{content_hash[:8]}")
            # Update peak RAM in operational metadata
            if isinstance(meta, dict):
                meta["peak_ram_mb"] = manager.peak_ram_mb
        else:
            package_path = str(out / "output.story")
            package_size = 0
            content_hash = ""
            artifact_id = "unknown"

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
            image_coverage=_image_cov if isinstance(pkg_data, dict) else 1.0,
            midi_coverage=_midi_cov if isinstance(pkg_data, dict) else 1.0,
            media_complete=bool(pkg_data.get("media_complete", True))
            if isinstance(pkg_data, dict) else True,
        )

    # ── internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _store_batch_result(
        ctx: PipelineContext,
        result: Any,  # BatchResult
        output_key: str,
        count_key: str,
        asset_dir: Path,
        extension: str,
    ) -> None:
        """Store BatchScheduler results in context.outputs.

        Aggregates completed + quarantined node results into the
        expected output shape for downstream steps (Packager, ManifestBuilder).
        """
        aggregated: dict[str, dict[str, Any]] = {}
        total_bytes = 0

        # Completed items already have their data
        for nid, meta in result.completed.items():
            aggregated[nid] = meta
            total_bytes += meta.get("image_bytes", meta.get("midi_bytes", 0))

        # Quarantined items get structured records with stable error codes
        # (Phase 5.6 P4) — persisted through ArtifactStore → manifest.
        for nid, rec in result.quarantined.items():
            aggregated[nid] = rec.to_dict()

        ctx.outputs[output_key] = {
            output_key: aggregated,
            count_key: len(result.completed),
            "quarantined": len(result.quarantined),
            "total_bytes": total_bytes,
            "skipped": result.skipped,
        }

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
        return ProviderRegistry.create_music(ModelConfig(
            provider="abc-notation", model="via-text", quantization="",
        ))

    @staticmethod
    def _create_validator(config: AppConfig) -> Any:
        """Phase 5.6E+F: Use ProviderRegistry for validator backend."""
        from ..backends.registry import ProviderRegistry
        return ProviderRegistry.create_validator(config.validator, strict=True)

    @staticmethod
    def _build_steps(
        text_gen: Any,
        image_gen: Any,
        music_gen: Any,
        config: AppConfig,
        output_dir: str,
    ) -> dict[str, Any]:
        from ..models.art_director import ArtDirector
        from ..models.game_designer import GameDesigner
        from ..models.image_generator_step import ImageGeneratorStep
        from ..models.music_generator_step import MusicGeneratorStep
        from ..models.story_writer import StoryWriter
        from ..models.world_builder import WorldBuilder
        from ..storage.indexer import GmIndexer
        from ..storage.packager import Packager
        from ..validators.composite import ValidationPlan, DeterministicValidator
        from ..pipeline.policy import ExecutionPolicy  # Phase 5.6G

        policy = ExecutionPolicy.from_config(config.pipeline)

        # Resolve schemas directory (project_root/schemas/ or PyInstaller bundle)
        schemas_dir = GenerateStory._resolve_schemas_dir()

        # Build validators for each artifact type
        bible_v = DeterministicValidator(
            ValidationPlan(schema="bible", cross_refs=True), schemas_dir,
        )
        style_v = DeterministicValidator(
            ValidationPlan(schema="style_bible"), schemas_dir,
        )
        story_v = DeterministicValidator(
            ValidationPlan(schema="story", cross_refs=True, consistency=True), schemas_dir,
        )
        graph_v = DeterministicValidator(
            ValidationPlan(schema="graph", cross_refs=True, graph_structure=True), schemas_dir,
        )
        gm_index_v = DeterministicValidator(
            ValidationPlan(schema="gm_index"), schemas_dir,
        )
        manifest_v = DeterministicValidator(
            ValidationPlan(schema="manifest"), schemas_dir,
        )

        return {
            "world_builder": WorldBuilder(text_gen, validator=bible_v, config=config, policy=policy),
            "art_director": ArtDirector(text_gen, validator=style_v, config=config, policy=policy),
            "story_writer": StoryWriter(text_gen, validator=story_v, config=config, policy=policy),
            "game_designer": GameDesigner(text_gen, validator=graph_v, config=config, policy=policy),
            "image_generator": ImageGeneratorStep(image_gen, config=config, output_dir=output_dir, policy=policy),
            "music_generator": MusicGeneratorStep(text_gen, music_gen, config=config, output_dir=output_dir, policy=policy),
            "indexer": GmIndexer(),
            "packager": Packager(output_dir=output_dir),
        }

    @staticmethod
    def _stub_config() -> AppConfig:
        from ..config import ModelConfig, PipelineConfig, LimitsConfig, PathsConfig
        _m = ModelConfig
        return AppConfig(
            text_generator=_m(provider="llama_cpp", model="qwen2.5-7b-instruct",
                              quantization="Q4_K_M", repo="Qwen/Qwen2.5-7B-Instruct-GGUF",
                              file="Qwen2.5-7B-Instruct-Q4_K_M.gguf"),
            validator=_m(provider="llama_cpp", model="phi-3.5-mini-instruct",
                         quantization="Q4_K_M", repo="microsoft/Phi-3.5-mini-instruct-GGUF",
                         file="phi-3.5-mini-instruct-q4_k_m.gguf"),
            image_generator=_m(provider="stable_diffusion_cpp", model="sdxl-turbo",
                               quantization="Q8_0", repo="stabilityai/sdxl-turbo-gguf",
                               file="sd_xl_turbo_1.0.q8_0.gguf"),
            music_generator=_m(provider="abc-notation", model="via-text",
                               quantization="", repo="", file=""),
            game_master=_m(provider="llama_cpp", model="llama-3.2-3b-instruct",
                           quantization="Q4_K_M", repo="meta-llama/Llama-3.2-3B-Instruct-GGUF",
                           file="llama-3.2-3b-instruct-q4_k_m.gguf"),
            pipeline=PipelineConfig(),
            limits=LimitsConfig(),
            paths=PathsConfig(),
        )
