"""Tests for LlamaCppGameMaster stub backend."""

from __future__ import annotations

import pytest

from src.backends.gm_backend import LlamaCppGameMaster
from src.config import ModelConfig
from src.interfaces import GameMasterContext


@pytest.fixture
def gm_backend() -> LlamaCppGameMaster:
    config = ModelConfig.from_dict({
        "provider": "llama_cpp",
        "model": "llama-3.2-3b-instruct",
        "quantization": "Q4_K_M",
    })
    return LlamaCppGameMaster(config)


@pytest.fixture
def gm_context() -> GameMasterContext:
    return GameMasterContext(
        current_scene="The wind howls fiercely.",
        world_rules="Magic fails near running water.",
        relevant_lore=[
            {"name": "Salt Wraith", "summary": "An undead creature."}
        ],
        visited_nodes=["node_01", "node_02"],
        active_flags={"took_shard": True},
    )


class TestGameMasterStub:
    """Stub behavior — raises NotImplementedError until Phase 6."""

    def test_attributes(self, gm_backend: LlamaCppGameMaster) -> None:
        assert gm_backend.provider == "llama_cpp"
        assert gm_backend.model_name == "llama-3.2-3b-instruct"
        assert gm_backend.quantization == "Q4_K_M"
        assert gm_backend.ram_usage_mb == 2020

    @pytest.mark.asyncio
    async def test_answer_raises_not_implemented(
        self, gm_backend: LlamaCppGameMaster, gm_context: GameMasterContext
    ) -> None:
        with pytest.raises(NotImplementedError):
            async for _ in gm_backend.answer("Who is Malachar?", gm_context):
                pass  # Should never yield

    @pytest.mark.asyncio
    async def test_load_sets_loaded(self, gm_backend: LlamaCppGameMaster) -> None:
        assert not gm_backend._loaded
        await gm_backend.load()
        assert gm_backend._loaded

    @pytest.mark.asyncio
    async def test_unload_clears_loaded(self, gm_backend: LlamaCppGameMaster) -> None:
        await gm_backend.load()
        await gm_backend.unload()
        assert not gm_backend._loaded
