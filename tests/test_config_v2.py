from __future__ import annotations

from pathlib import Path

import pytest

from src.application.models import GenerationRequest
from src.config import AppConfig


def test_generation_request_has_no_world_mode() -> None:
    request = GenerationRequest(seed=1)
    assert not hasattr(request, "world_mode")
    assert request.width == request.height == 1024
    assert request.continent_count == 1


def test_unknown_top_level_config_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("generators: {}\ncloud: true\n")
    with pytest.raises(ValueError, match="unknown top-level"):
        AppConfig.from_yaml(path)


def test_invalid_request_world_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="width must be at least 32"):
        GenerationRequest(seed=1, width=8)
