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

        # 8. Build orchestrator
        from ..storage.checkpoint import CheckpointStore
        from ..storage.orchestrator import Orchestrator

        checkpoint = CheckpointStore(str(out / "checkpoint.db"))
        orchestrator = Orchestrator(checkpoint, steps)

        # ── Phase: TEXT ────────────────────────────────────────────────
        text_start = time.time()
        try:
            async with manager.resource_scope("text"):
                # Bible → Style → Story → Graph → Music (all use text model)
                for step_name in ["world_builder", "art_director", "story_writer",
                                  "game_designer", "music_generator"]:
                    await orchestrator.queue.execute_step(
                        steps[step_name], ctx, step_name,
                    )
        except Exception as e:
            errors.append(f"text_phase: {e}")
        phase_times["text+music_s"] = round(time.time() - text_start, 1)

        if errors:
            return self._build_result(ctx, out, phase_times, errors, manager)

        # ── Phase: IMAGE ───────────────────────────────────────────────
        image_start = time.time()
        try:
            async with manager.resource_scope("image"):
                await orchestrator.queue.execute_step(
                    steps["image_generator"], ctx, "image_generator",
                )
        except Exception as e:
            errors.append(f"image_phase: {e}")
        phase_times["image_s"] = round(time.time() - image_start, 1)

        # ── Phase: FINALIZE (no model needed) ──────────────────────────
        finalize_start = time.time()
        try:
            for step_name in ["indexer", "packager"]:
                await orchestrator.queue.execute_step(
                    steps[step_name], ctx, step_name,
                )
        except Exception as e:
            errors.append(f"finalize_phase: {e}")
        phase_times["finalize_s"] = round(time.time() - finalize_start, 1)

        return self._build_result(ctx, out, phase_times, errors, manager)

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

        pkg_data = ctx.outputs.get("manifest", {})
        package_path = pkg_data.get("package_path", str(out / "output.story"))
        package_size = pkg_data.get("package_size", 0)
        content_hash = pkg_data.get("content_hash", "")
        artifact_id = pkg_data.get("artifact_id", "unknown")

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

        return {
            "world_builder": WorldBuilder(text_gen, config=config),
            "art_director": ArtDirector(text_gen, config=config),
            "story_writer": StoryWriter(text_gen, config=config),
            "game_designer": GameDesigner(text_gen, config=config),
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
