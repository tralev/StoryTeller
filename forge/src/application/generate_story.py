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

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .models import GenerationRequest, GenerationResult
from ..config import AppConfig
from ..job_queue import PipelineContext

# RAM estimates for default models (Q4_K_M quantization on CPU)
TEXT_MODEL_RAM_MB = 4700
IMAGE_MODEL_RAM_MB = 5000
VALIDATOR_MODEL_RAM_MB = 2500


class GenerateStory:
    """Execute a complete story generation pipeline.

    Usage:
        service = GenerateStory()
        request = GenerationRequest(seed=42, title="The Iron Schism")
        result = await service.execute(request)
    """

    # ── public API ──────────────────────────────────────────────────────

    async def execute(self, request: GenerationRequest) -> GenerationResult:
        """Run the full pipeline and return a GenerationResult."""
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

        # 6. Build pipeline context
        ctx = PipelineContext(
            run_id=f"run_{request.seed:04d}_{int(time.time())}",
            seed=request.seed,
            config=config,
            output_dir=str(out),
        )
        ctx.state["tone"] = request.tone
        ctx.state["title"] = request.title
        ctx.state["temperature"] = request.temperature
        ctx.state["start_time"] = time.time()

        # 7. Build step registry
        steps = self._build_steps(text_gen, image_gen, music_gen, config, str(out))

        # 8. Build orchestrator with run fingerprint
        from ..storage.checkpoint import CheckpointStore
        from ..storage.orchestrator import Orchestrator

        run_fingerprint = self._compute_run_fingerprint(config, out)
        checkpoint = CheckpointStore(str(out / "checkpoint.db"))
        orchestrator = Orchestrator(checkpoint, steps)
        orchestrator.run_fingerprint = run_fingerprint

        # ── Phase: TEXT ────────────────────────────────────────────────
        text_start = time.time()
        try:
            async with manager.resource_scope("text"):
                # Bible → Style → Story → Graph (sequential, all use text model)
                for step_name in ["world_builder", "art_director", "story_writer",
                                  "game_designer"]:
                    await orchestrator.queue.execute_step(
                        steps[step_name], ctx, step_name,
                    )

                # ── Music (parallel per-node, uses text model) ──────
                music_step = steps["music_generator"]
                graph = ctx.outputs.get("graph")
                if graph is not None:
                    from ..pipeline.batch import BatchScheduler, NodeJob, BatchResult
                    music_jobs = NodeJob.from_graph(graph, key="music_tone")
                    music_scheduler = BatchScheduler(
                        max_concurrency=config.pipeline.workers,
                        checkpoint_store=checkpoint,
                        step_name="music_generator",
                    )
                    midi_dir = out / "midi"
                    midi_dir.mkdir(parents=True, exist_ok=True)
                    music_result = await music_scheduler.run(
                        music_jobs,
                        music_step.generate_node,
                        ctx.seed, midi_dir,
                    )
                    self._store_batch_result(ctx, music_result, "midi",
                                             "music_count", midi_dir, ".mid")
        except Exception as e:
            errors.append(f"text_phase: {e}")
        phase_times["text+music_s"] = round(time.time() - text_start, 1)

        if errors:
            return self._build_result(ctx, out, phase_times, errors, manager)

        # ── Phase: IMAGE ───────────────────────────────────────────────
        image_start = time.time()
        try:
            async with manager.resource_scope("image"):
                graph = ctx.outputs.get("graph")
                style_bible = ctx.outputs.get("style_bible")
                if graph is not None and style_bible is not None:
                    from ..pipeline.batch import BatchScheduler, NodeJob, BatchResult
                    img_jobs = NodeJob.from_graph(graph, key="image_prompt")
                    img_scheduler = BatchScheduler(
                        max_concurrency=config.pipeline.workers,
                        checkpoint_store=checkpoint,
                        step_name="image_generator",
                    )
                    img_dir = out / "images"
                    thumb_dir = out / "thumbnails"
                    img_dir.mkdir(parents=True, exist_ok=True)
                    thumb_dir.mkdir(parents=True, exist_ok=True)
                    img_step = steps["image_generator"]
                    img_result = await img_scheduler.run(
                        img_jobs,
                        img_step.generate_node,
                        style_bible, ctx.seed, img_dir, thumb_dir,
                    )
                    self._store_batch_result(ctx, img_result, "images",
                                             "image_count", img_dir, ".png")
        except Exception as e:
            errors.append(f"image_phase: {e}")
        phase_times["image_s"] = round(time.time() - image_start, 1)

        # ── Phase: FINALIZE (no model needed) ──────────────────────────
        finalize_start = time.time()
        try:
            # 6a. Build GM index
            await orchestrator.queue.execute_step(
                steps["indexer"], ctx, "indexer",
            )

            # 6b. Build manifest with mandatory schema validation
            from ..storage.manifest_builder import ManifestBuilder
            schemas_dir = self._resolve_schemas_dir()
            manifest_builder = ManifestBuilder(schemas_dir=schemas_dir)
            manifest_output = await manifest_builder.run(ctx)
            ctx.outputs["manifest"] = manifest_output.data

            # 6c. Package into .story ZIP
            await orchestrator.queue.execute_step(
                steps["packager"], ctx, "packager",
            )

            # 6d. Package acceptance (unconditional — A2)
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
            gate = PackageAcceptance(schemas_dir=schemas_dir)
            acceptance = gate.validate(package_path)
            if not acceptance.accepted:
                from ..pipeline.errors import PackageValidationError
                raise PackageValidationError(package_path, [acceptance.format_issues()])
        except Exception as e:
            errors.append(f"finalize_phase: {e}")
        phase_times["finalize_s"] = round(time.time() - finalize_start, 1)

        return self._build_result(ctx, out, phase_times, errors, manager)

    # ── schemas dir ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_schemas_dir() -> str:
        """Resolve the docs/schemas/ directory for manifest/package validation."""
        import os
        return os.environ.get(
            "STORYTELLER_SCHEMAS_DIR",
            str(Path(__file__).resolve().parent.parent.parent.parent / "docs" / "schemas"),
        )

    # ── run fingerprint ───────────────────────────────────────────────────

    @staticmethod
    def _compute_run_fingerprint(config: AppConfig, out: Path) -> str:
        """Compute a deterministic fingerprint of the run configuration.

        Includes: config hash (models.yaml content) + model file hashes.
        Two runs with the same fingerprint SHOULD produce identical
        canonical content (given same seed). Operational metadata
        (timestamps, peak RAM) is excluded.
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

        pkg_data = ctx.outputs.get("packager", {})
        pkg_manifest = ctx.outputs.get("manifest", {})
        if isinstance(pkg_data, dict) and isinstance(pkg_manifest, dict):
            package_path = pkg_data.get("package_path", str(out / "output.story"))
            package_size = pkg_data.get("package_size", 0)
            content_hash = pkg_manifest.get("content_hash", "")
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

        # Quarantined items get placeholder entries
        for nid, err in result.quarantined.items():
            aggregated[nid] = {"error": err, "quarantined": True}

        ctx.outputs[output_key] = {
            output_key: aggregated,
            count_key: len(result.completed),
            "quarantined": len(result.quarantined),
            "total_bytes": total_bytes,
            "skipped": result.skipped,
        }

    @staticmethod
    def _load_config(config_path: str) -> AppConfig:
        path = Path(config_path)
        if path.exists():
            return AppConfig.from_yaml(str(path))
        return GenerateStory._stub_config()

    @staticmethod
    def _create_text_generator(config: AppConfig) -> Any:
        try:
            from ..backends.llm_backend import LlamaCppTextGenerator
            return LlamaCppTextGenerator(config.text_generator)
        except Exception:
            pass
        return GenerateStory._stub_text_gen()

    @staticmethod
    def _create_image_generator(config: AppConfig) -> Any:
        try:
            from ..backends.image_backend import SDCppImageGenerator
            return SDCppImageGenerator(config.image_generator)
        except Exception:
            pass
        return GenerateStory._stub_image_gen()

    @staticmethod
    def _create_music_generator() -> Any:
        from ..backends.midi_backend import AbcMusicGenerator
        return AbcMusicGenerator()

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

        # Resolve schemas directory (project_root/docs/schemas/)
        import os
        schemas_dir = os.environ.get(
            "STORYTELLER_SCHEMAS_DIR",
            str(Path(__file__).resolve().parent.parent.parent.parent / "docs" / "schemas"),
        )

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
            "world_builder": WorldBuilder(text_gen, validator=bible_v, config=config),
            "art_director": ArtDirector(text_gen, validator=style_v, config=config),
            "story_writer": StoryWriter(text_gen, validator=story_v, config=config),
            "game_designer": GameDesigner(text_gen, validator=graph_v, config=config),
            "image_generator": ImageGeneratorStep(image_gen, config=config, output_dir=output_dir),
            "music_generator": MusicGeneratorStep(text_gen, music_gen, config=config, output_dir=output_dir),
            "indexer": GmIndexer(),
            "packager": Packager(output_dir=output_dir),
        }

    # ── stubs ────────────────────────────────────────────────────────────

    @staticmethod
    def _stub_text_gen() -> Any:
        class _Stub:
            provider: str = "stub"
            model_name: str = "mock"
            quantization: str = ""
            ram_usage_mb: int = 0
            async def generate(self, prompt: str = "", **kw: Any) -> dict[str, Any]:
                raise RuntimeError("No text backend loaded")
            async def load(self) -> None: pass
            async def unload(self) -> None: pass
        return _Stub()

    @staticmethod
    def _stub_image_gen() -> Any:
        class _Stub:
            provider: str = "stub"
            model_name: str = "mock"
            quantization: str = ""
            ram_usage_mb: int = 0
            async def generate(self, prompt: str = "", **kw: Any) -> bytes:
                raise RuntimeError("No image backend")
            async def generate_thumbnail(self, image_bytes: bytes = b"", **kw: Any) -> bytes:
                return b""
            async def load(self) -> None: pass
            async def unload(self) -> None: pass
        return _Stub()

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
