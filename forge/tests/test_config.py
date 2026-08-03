"""Test configuration loading and model resolution."""

import tempfile
from pathlib import Path

import pytest
import yaml

from src.config import AppConfig, ModelConfig


SAMPLE_CONFIG = """
generators:
  text:
    provider: llama_cpp
    model: qwen2.5-7b-instruct
    quantization: Q4_K_M
    repo: Qwen/Qwen2.5-7B-Instruct-GGUF
    file: qwen2.5-7b-instruct-q4_k_m.gguf
    max_tokens: 4096
    temperature: 0.7

  validator:
    provider: llama_cpp
    model: phi-3.5-mini-instruct
    quantization: Q4_K_M
    repo: microsoft/Phi-3.5-mini-instruct-GGUF
    file: phi-3.5-mini-instruct-q4_k_m.gguf
    max_tokens: 2048
    temperature: 0.3

  image:
    provider: stable_diffusion_cpp
    model: sdxl-turbo
    quantization: Q8_0
    repo: stabilityai/sdxl-turbo-gguf
    file: sdxl-turbo-q8_0.gguf
    size: [512, 512]
    steps: 20

  music:
    provider: abc_notation
    uses: text

  game_master:
    provider: llama_cpp
    model: llama-3.2-3b-instruct
    quantization: Q4_K_M
    repo: meta-llama/Llama-3.2-3B-Instruct-GGUF
    file: llama-3.2-3b-instruct-q4_k_m.gguf
    max_tokens: 256
    temperature: 0.8

pipeline:
  workers: 4
  max_retries: 3
  checkpoint_interval: 1
  failure_policy: quarantine

limits:
  max_ram_mb: 10240
  model_unload_threshold: 0.9

paths:
  models_dir: ~/.storyteller/models
  prompts_dir: src/prompts
  schemas_dir: ../docs/schemas
  output_dir: ./output
"""


@pytest.fixture
def config_file() -> Path:
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as f:
        f.write(SAMPLE_CONFIG)
        return Path(f.name)


class TestConfigLoading:
    """Verify AppConfig loads correctly from YAML."""

    def test_load_full_config(self, config_file: Path) -> None:
        """Full config loads without errors."""
        config = AppConfig.from_yaml(config_file)
        assert config is not None

    def test_text_generator_config(self, config_file: Path) -> None:
        """Text generator config is resolved correctly."""
        config = AppConfig.from_yaml(config_file)
        tg = config.text_generator
        assert tg.provider == "llama_cpp"
        assert tg.model == "qwen2.5-7b-instruct"
        assert tg.quantization == "Q4_K_M"
        assert tg.max_tokens == 4096
        assert tg.temperature == 0.7

    def test_validator_config(self, config_file: Path) -> None:
        """Validator config has lower temperature for consistency."""
        config = AppConfig.from_yaml(config_file)
        v = config.validator
        assert v.model == "phi-3.5-mini-instruct"
        assert v.temperature == 0.3

    def test_image_generator_config(self, config_file: Path) -> None:
        """Image generator config is resolved correctly."""
        config = AppConfig.from_yaml(config_file)
        ig = config.image_generator
        assert ig.provider == "stable_diffusion_cpp"
        assert ig.model == "sdxl-turbo"

    def test_music_generator_uses_text(self, config_file: Path) -> None:
        """Music generator inherits text generator config via 'uses'."""
        config = AppConfig.from_yaml(config_file)
        mg = config.music_generator
        # Provider is abc_notation (explicit in music section, overrides text)
        assert mg.provider == "abc_notation"
        # Model is inherited from text (music has no model field, so text's is used)
        assert mg.model == "qwen2.5-7b-instruct"

    def test_game_master_config(self, config_file: Path) -> None:
        """Game Master config for mobile."""
        config = AppConfig.from_yaml(config_file)
        gm = config.game_master
        assert gm.model == "llama-3.2-3b-instruct"
        assert gm.max_tokens == 256

    def test_pipeline_config(self, config_file: Path) -> None:
        """Pipeline settings are loaded."""
        config = AppConfig.from_yaml(config_file)
        assert config.pipeline.workers == 4
        assert config.pipeline.max_retries == 3
        assert config.pipeline.failure_policy == "quarantine"

    def test_limits_config(self, config_file: Path) -> None:
        """RAM limits are loaded."""
        config = AppConfig.from_yaml(config_file)
        assert config.limits.max_ram_mb == 10240
        assert config.limits.model_unload_threshold == 0.9

    def test_paths_config(self, config_file: Path) -> None:
        """Paths are resolved."""
        config = AppConfig.from_yaml(config_file)
        assert "storyteller" in config.paths.models_dir
        assert config.paths.prompts_dir == "src/prompts"

    def test_get_model_path(self, config_file: Path) -> None:
        """Model path resolution."""
        config = AppConfig.from_yaml(config_file)
        path = config.get_model_path(config.text_generator)
        assert path.name == "qwen2.5-7b-instruct-q4_k_m.gguf"

    def test_get_prompt_path(self, config_file: Path) -> None:
        """Prompt path resolution."""
        config = AppConfig.from_yaml(config_file)
        path = config.get_prompt_path("world_builder_v1.j2")
        assert path.name == "world_builder_v1.j2"

    def test_get_schema_path(self, config_file: Path) -> None:
        """Schema path resolution."""
        config = AppConfig.from_yaml(config_file)
        path = config.get_schema_path("bible.schema.json")
        assert path.name == "bible.schema.json"


class TestConfigErrors:
    """Verify config handles errors gracefully."""

    def test_missing_file(self) -> None:
        """Loading a nonexistent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            AppConfig.from_yaml("/nonexistent/config.yaml")

    def test_missing_generators_section(self) -> None:
        """Config without generators section raises KeyError."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("pipeline:\n  workers: 1\n")
            path = Path(f.name)
        with pytest.raises(KeyError, match="generators"):
            AppConfig.from_yaml(path)


class TestModelConfig:
    """Verify ModelConfig dataclass."""

    def test_from_dict(self) -> None:
        """ModelConfig.from_dict filters unknown keys."""
        data = {
            "provider": "llama_cpp",
            "model": "test-model",
            "quantization": "Q4_K_M",
            "unknown_field": "should_be_ignored",
        }
        config = ModelConfig.from_dict(data)
        assert config.provider == "llama_cpp"
        assert config.model == "test-model"
        assert not hasattr(config, "unknown_field")

    def test_defaults(self) -> None:
        """ModelConfig applies defaults for missing fields."""
        config = ModelConfig.from_dict({"provider": "test", "model": "m", "quantization": "q"})
        assert config.max_tokens == 4096  # default
        assert config.temperature == 0.7  # default
