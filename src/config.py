"""Configuration loader — resolves models.yaml into concrete settings."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ModelConfig:
    """Configuration for a single model."""

    provider: str
    model: str
    quantization: str
    repo: str = ""
    file: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    n_ctx: int = 16384  # Context window size (prompt + response tokens)
    uses: str | None = None  # If this model reuses another (e.g., music uses text)
    size: tuple[int, int] | list[int] | None = None
    steps: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelConfig:
        """Create ModelConfig from a strict mapping."""
        known = set(cls.__dataclass_fields__)
        unknown = set(data) - known
        if unknown:
            raise ValueError(
                "unknown model configuration fields: "
                + ", ".join(sorted(unknown))
            )
        config = cls(**data)
        if not config.provider or not config.model or not config.quantization:
            raise ValueError("provider, model and quantization are required")
        if config.max_tokens < 1 or config.n_ctx < 1:
            raise ValueError("model token limits must be positive")
        if not 0.0 <= config.temperature <= 2.0:
            raise ValueError("model temperature must be within 0.0..2.0")
        if config.steps is not None and config.steps < 1:
            raise ValueError("image steps must be positive")
        if config.size is not None and (
            len(config.size) != 2 or any(int(value) < 1 for value in config.size)
        ):
            raise ValueError("image size must contain two positive dimensions")
        return config


@dataclass
class PipelineConfig:
    """Pipeline execution settings."""

    workers: int = 4
    max_retries: int = 3
    checkpoint_interval: int = 1
    failure_policy: str = "quarantine"
    # Frozen v2 product contract: every prompted/tone node has complete media.
    image_coverage: float = 1.0  # Illustrations are REQUIRED (100%)
    midi_coverage: float = 1.0   # MIDI is REQUIRED (100%)

    def __post_init__(self) -> None:
        if self.workers < 1 or self.max_retries < 0 or self.checkpoint_interval < 1:
            raise ValueError("invalid pipeline worker/retry/checkpoint limits")
        if self.failure_policy not in ("abort", "quarantine"):
            raise ValueError("failure_policy must be abort or quarantine")
        if self.image_coverage != 1.0 or self.midi_coverage != 1.0:
            raise ValueError("v2 packages require complete image and MIDI coverage")


@dataclass
class LimitsConfig:
    """RAM and resource limits."""

    max_ram_mb: int = 10240
    model_unload_threshold: float = 0.9

    def __post_init__(self) -> None:
        if self.max_ram_mb < 1 or not 0.0 < self.model_unload_threshold <= 1.0:
            raise ValueError("invalid resource limits")


@dataclass
class PathsConfig:
    """Filesystem paths.

    Post-flatten conventions (project-root layout):
      prompts_dir  = "src/prompts"  (relative to project root)
      schemas_dir  = "schemas"      (top-level, moved from docs/schemas)
      output_dir   = "tmp/output"   (tmp/ artifacts convention)

    Relative paths are resolved against the project root (not CWD) by
    get_prompt_path/get_schema_path, so the app works from any launch
    directory. In a PyInstaller bundle, _MEIPASS locations win.
    """

    models_dir: str = "~/.storyteller/models"
    prompts_dir: str = "src/prompts"
    schemas_dir: str = "schemas"
    output_dir: str = "tmp/output"

    def __post_init__(self) -> None:
        env_models = os.environ.get("STORYTELLER_MODELS_DIR", "")
        if env_models:
            self.models_dir = env_models
        project_root = Path(__file__).resolve().parent.parent

        def resolve(value: str, *, confined: bool) -> str:
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = project_root / path
            path = path.resolve()
            if confined and path != project_root and project_root not in path.parents:
                raise ValueError(f"configured path escapes project root: {value}")
            return str(path)

        self.models_dir = resolve(self.models_dir, confined=False)
        self.prompts_dir = resolve(self.prompts_dir, confined=True)
        self.schemas_dir = resolve(self.schemas_dir, confined=True)
        self.output_dir = resolve(self.output_dir, confined=True)


@dataclass
class AppConfig:
    """Top-level application configuration loaded from models.yaml."""

    text_generator: ModelConfig
    validator: ModelConfig
    image_generator: ModelConfig
    music_generator: ModelConfig
    game_master: ModelConfig
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    limits: LimitsConfig = field(default_factory=LimitsConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> AppConfig:
        """Load configuration from a YAML file.

        Args:
            path: Path to models.yaml.

        Returns:
            Resolved AppConfig instance.

        Raises:
            FileNotFoundError: If the config file doesn't exist.
            KeyError: If a required generator section is missing.
        """
        with open(path) as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ValueError("configuration root must be a mapping")
        allowed_top = {"generators", "pipeline", "limits", "paths"}
        unknown_top = set(raw) - allowed_top
        if unknown_top:
            raise ValueError(
                "unknown top-level configuration fields: "
                + ", ".join(sorted(unknown_top))
            )

        generators = raw.get("generators", {})
        if not isinstance(generators, dict) or not generators:
            raise KeyError("Missing 'generators' section in config")
        expected_generators = {"text", "validator", "image", "music", "game_master"}
        unknown_generators = set(generators) - expected_generators
        missing_generators = expected_generators - set(generators)
        if unknown_generators:
            raise ValueError("unknown generators: " + ", ".join(sorted(unknown_generators)))
        if missing_generators:
            raise KeyError("missing generators: " + ", ".join(sorted(missing_generators)))

        def strict_section(name: str, target: type[Any]) -> dict[str, Any]:
            value = raw.get(name, {})
            if not isinstance(value, dict):
                raise ValueError(f"{name} must be a mapping")
            unknown = set(value) - set(target.__dataclass_fields__)
            if unknown:
                raise ValueError(f"unknown {name} fields: {', '.join(sorted(unknown))}")
            return value

        # Resolve music generator: if it has 'uses: text', copy text config
        music_raw = dict(generators.get("music", {}))
        if music_raw.get("uses") == "text":
            text_raw = generators.get("text", {})
            music_raw = {**text_raw, **music_raw}

        return cls(
            text_generator=ModelConfig.from_dict(generators.get("text", {})),
            validator=ModelConfig.from_dict(generators.get("validator", {})),
            image_generator=ModelConfig.from_dict(generators.get("image", {})),
            music_generator=ModelConfig.from_dict(music_raw),
            game_master=ModelConfig.from_dict(generators.get("game_master", {})),
            pipeline=PipelineConfig(**strict_section("pipeline", PipelineConfig)),
            limits=LimitsConfig(**strict_section("limits", LimitsConfig)),
            paths=PathsConfig(**strict_section("paths", PathsConfig)),
        )

    def get_model_path(self, config: ModelConfig) -> Path:
        """Resolve the full path to a model file.

        Args:
            config: Model configuration with repo and file fields.

        Returns:
            Absolute path to the GGUF file.
        """
        return Path(self.paths.models_dir) / config.file

    def get_prompt_path(self, template_name: str) -> Path:
        """Resolve the full path to a prompt template.

        Args:
            template_name: Template filename (e.g., 'world_builder_v1.j2').

        Returns:
            Absolute path to the .j2 file.

        Resolution order (post-flatten + PyInstaller audit):
          1. Bundled app: sys._MEIPASS/src/prompts (spec datas target)
          2. Configured absolute path, honored as-is
          3. Relative path: project root (src/config.py → root), not CWD
        """
        base = Path(self.paths.prompts_dir)
        if hasattr(sys, "_MEIPASS"):
            # PyInstaller bundle: prompts extracted to sys._MEIPASS/src/prompts
            base = Path(sys._MEIPASS) / "src" / "prompts"
        elif not base.is_absolute():
            base = Path(__file__).resolve().parent.parent / self.paths.prompts_dir
        return base / template_name

    def get_schema_path(self, schema_name: str) -> Path:
        """Resolve the full path to a JSON schema.

        Args:
            schema_name: Schema filename (e.g., 'bible.schema.json').

        Returns:
            Absolute path to the .schema.json file.

        Resolution order (mirrors get_prompt_path):
          1. Bundled app: sys._MEIPASS/schemas (spec datas target)
          2. Configured absolute path, honored as-is
          3. Relative path: project root (src/config.py → root), not CWD
        """
        base = Path(self.paths.schemas_dir)
        if hasattr(sys, "_MEIPASS"):
            # PyInstaller bundle: schemas extracted to sys._MEIPASS/schemas
            base = Path(sys._MEIPASS) / "schemas"
        elif not base.is_absolute():
            base = Path(__file__).resolve().parent.parent / self.paths.schemas_dir
        return base / schema_name
