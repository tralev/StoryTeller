"""Configuration loader — resolves models.yaml into concrete settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import os

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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelConfig:
        """Create ModelConfig from dict, warning on unrecognized fields."""
        known = set(cls.__dataclass_fields__)
        filtered = {k: v for k, v in data.items() if k in known}
        unknown = set(data) - known
        if unknown:
            import warnings
            warnings.warn(
                f"ModelConfig.from_dict: ignoring unrecognized fields: "
                f"{', '.join(sorted(unknown))}. "
                f"Known fields: {', '.join(sorted(known))}."
            )
        return cls(**filtered)


@dataclass
class PipelineConfig:
    """Pipeline execution settings."""

    workers: int = 4
    max_retries: int = 3
    checkpoint_interval: int = 1
    failure_policy: str = "quarantine"


@dataclass
class LimitsConfig:
    """RAM and resource limits."""

    max_ram_mb: int = 10240
    model_unload_threshold: float = 0.9


@dataclass
class PathsConfig:
    """Filesystem paths."""

    models_dir: str = "~/.storyteller/models"
    prompts_dir: str = "src/prompts"
    schemas_dir: str = "../schemas"
    output_dir: str = "./output"

    def __post_init__(self) -> None:
        env_models = os.environ.get("STORYTELLER_MODELS_DIR", "")
        if env_models:
            self.models_dir = env_models
        self.models_dir = str(Path(self.models_dir).expanduser())


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

        generators = raw.get("generators", {})
        if not generators:
            raise KeyError("Missing 'generators' section in config")

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
            pipeline=PipelineConfig(**raw.get("pipeline", {})),
            limits=LimitsConfig(**raw.get("limits", {})),
            paths=PathsConfig(**raw.get("paths", {})),
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
        """
        return Path(self.paths.prompts_dir) / template_name

    def get_schema_path(self, schema_name: str) -> Path:
        """Resolve the full path to a JSON schema.

        Args:
            schema_name: Schema filename (e.g., 'bible.schema.json').

        Returns:
            Absolute path to the .schema.json file.
        """
        return Path(self.paths.schemas_dir) / schema_name
