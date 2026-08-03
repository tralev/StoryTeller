"""Tests for ModelManager — model lifecycle and RAM budget enforcement."""

from __future__ import annotations

import pytest

from src.backends.model_manager import (
    ModelManager,
    ModelStatus,
    RamBudgetExceededError,
)


class _FakeBackend:
    """Minimal backend stub for testing ModelManager."""

    def __init__(self, provider: str = "test") -> None:
        self.provider = provider
        self.loaded = False

    async def load(self) -> None:
        self.loaded = True

    async def unload(self) -> None:
        self.loaded = False


@pytest.fixture
def manager() -> ModelManager:
    return ModelManager(budget_mb=10240)


@pytest.fixture
def fake_backend() -> _FakeBackend:
    return _FakeBackend()


class TestRegistration:
    """Model registration and lookup."""

    def test_register_new_model(self, manager: ModelManager, fake_backend: _FakeBackend) -> None:
        manager.register("text_gen", fake_backend, ram_mb=4700)
        assert not manager.is_loaded("text_gen")

    def test_duplicate_registration_raises(
        self, manager: ModelManager, fake_backend: _FakeBackend
    ) -> None:
        manager.register("text_gen", fake_backend, ram_mb=4700)
        with pytest.raises(ValueError, match="already registered"):
            manager.register("text_gen", fake_backend, ram_mb=4700)

    def test_register_multiple_models(
        self, manager: ModelManager, fake_backend: _FakeBackend
    ) -> None:
        manager.register("text_gen", fake_backend, ram_mb=4700)
        manager.register("validator", _FakeBackend(), ram_mb=2200)
        manager.register("image", _FakeBackend(), ram_mb=3500)


class TestLoadUnload:
    """Model loading and unloading."""

    @pytest.mark.asyncio
    async def test_load_model(
        self, manager: ModelManager, fake_backend: _FakeBackend
    ) -> None:
        manager.register("text_gen", fake_backend, ram_mb=4700)
        await manager.load("text_gen")
        assert manager.is_loaded("text_gen")
        assert fake_backend.loaded

    @pytest.mark.asyncio
    async def test_unload_model(
        self, manager: ModelManager, fake_backend: _FakeBackend
    ) -> None:
        manager.register("text_gen", fake_backend, ram_mb=4700)
        await manager.load("text_gen")
        await manager.unload("text_gen")
        assert not manager.is_loaded("text_gen")
        assert not fake_backend.loaded

    @pytest.mark.asyncio
    async def test_load_already_loaded_is_noop(
        self, manager: ModelManager, fake_backend: _FakeBackend
    ) -> None:
        manager.register("text_gen", fake_backend, ram_mb=4700)
        await manager.load("text_gen")
        await manager.load("text_gen")  # No-op, no error
        assert manager.is_loaded("text_gen")

    @pytest.mark.asyncio
    async def test_unload_not_loaded_is_noop(
        self, manager: ModelManager, fake_backend: _FakeBackend
    ) -> None:
        manager.register("text_gen", fake_backend, ram_mb=4700)
        await manager.unload("text_gen")  # No-op, no error
        assert not manager.is_loaded("text_gen")

    @pytest.mark.asyncio
    async def test_load_unregistered_raises(
        self, manager: ModelManager
    ) -> None:
        with pytest.raises(KeyError, match="not registered"):
            await manager.load("nonexistent")

    @pytest.mark.asyncio
    async def test_unload_unregistered_raises(
        self, manager: ModelManager
    ) -> None:
        with pytest.raises(KeyError, match="not registered"):
            await manager.unload("nonexistent")


class TestRamBudget:
    """RAM budget enforcement."""

    @pytest.mark.asyncio
    async def test_budget_ok_for_multiple_models(self, manager: ModelManager) -> None:
        manager.register("text_gen", _FakeBackend(), ram_mb=4000)
        manager.register("validator", _FakeBackend(), ram_mb=2000)
        manager.register("image", _FakeBackend(), ram_mb=3000)
        await manager.load("text_gen")
        await manager.load("validator")
        await manager.load("image")
        assert manager.used_ram_mb == 4000 + 2000 + 3000
        assert len(manager.get_loaded_models()) == 3

    @pytest.mark.asyncio
    async def test_exceed_budget_raises(
        self, manager: ModelManager
    ) -> None:
        # Budget is 10240; try to load two 7GB models
        manager.register("big1", _FakeBackend(), ram_mb=7000)
        manager.register("big2", _FakeBackend(), ram_mb=7000)
        await manager.load("big1")
        with pytest.raises(RamBudgetExceededError):
            await manager.load("big2")

    @pytest.mark.asyncio
    async def test_budget_exceeded_error_message(
        self, manager: ModelManager
    ) -> None:
        manager.register("big", _FakeBackend(), ram_mb=7000)
        manager.register("also_big", _FakeBackend(), ram_mb=7000)
        await manager.load("big")
        with pytest.raises(RamBudgetExceededError) as exc:
            await manager.load("also_big")
        assert "7000" in str(exc.value)
        assert "10240" in str(exc.value)

    @pytest.mark.asyncio
    async def test_unload_frees_budget(
        self, manager: ModelManager
    ) -> None:
        manager.register("big1", _FakeBackend(), ram_mb=7000)
        manager.register("big2", _FakeBackend(), ram_mb=7000)
        await manager.load("big1")
        await manager.unload("big1")
        # Now there's room
        await manager.load("big2")
        assert manager.is_loaded("big2")

    @pytest.mark.asyncio
    async def test_model_larger_than_budget_raises(
        self, manager: ModelManager
    ) -> None:
        manager.register("huge", _FakeBackend(), ram_mb=20000)
        with pytest.raises(RamBudgetExceededError):
            await manager.load("huge")


class TestUnloadToFit:
    """FIFO unloading to make room."""

    @pytest.mark.asyncio
    async def test_unload_to_fit_unloads_oldest(self, manager: ModelManager) -> None:
        manager.register("first", _FakeBackend(), ram_mb=4000)
        manager.register("second", _FakeBackend(), ram_mb=4000)
        manager.register("third", _FakeBackend(), ram_mb=4000)
        await manager.load("first")
        await manager.load("second")
        # 8000 used, 2240 available — need 4000 for third
        await manager.unload_to_fit(4000)
        # First should be unloaded, second stays
        assert not manager.is_loaded("first")
        assert manager.is_loaded("second")
        await manager.load("third")
        assert manager.is_loaded("third")

    @pytest.mark.asyncio
    async def test_unload_to_fit_noop_when_enough_room(
        self, manager: ModelManager
    ) -> None:
        manager.register("small", _FakeBackend(), ram_mb=1000)
        await manager.load("small")
        loaded_before = manager.get_loaded_models()
        await manager.unload_to_fit(500)
        assert manager.get_loaded_models() == loaded_before

    @pytest.mark.asyncio
    async def test_unload_to_fit_all_when_still_not_enough(
        self, manager: ModelManager
    ) -> None:
        manager.register("only", _FakeBackend(), ram_mb=1000)
        await manager.load("only")
        with pytest.raises(RamBudgetExceededError):
            await manager.unload_to_fit(11000)  # More than total budget

    @pytest.mark.asyncio
    async def test_unload_all(self, manager: ModelManager) -> None:
        manager.register("a", _FakeBackend(), ram_mb=3000)
        manager.register("b", _FakeBackend(), ram_mb=3000)
        manager.register("c", _FakeBackend(), ram_mb=3000)
        await manager.load("a")
        await manager.load("b")
        await manager.load("c")
        await manager.unload_all()
        assert manager.used_ram_mb == 0
        assert len(manager.get_loaded_models()) == 0


class TestRamTracking:
    """Accurate RAM tracking."""

    def test_initial_ram_is_zero(self, manager: ModelManager) -> None:
        assert manager.used_ram_mb == 0
        assert manager.available_ram_mb == 10240

    @pytest.mark.asyncio
    async def test_ram_updates_on_load(self, manager: ModelManager) -> None:
        manager.register("m", _FakeBackend(), ram_mb=4700)
        await manager.load("m")
        assert manager.used_ram_mb == 4700
        assert manager.available_ram_mb == 10240 - 4700

    @pytest.mark.asyncio
    async def test_ram_updates_on_unload(self, manager: ModelManager) -> None:
        manager.register("m", _FakeBackend(), ram_mb=4700)
        await manager.load("m")
        await manager.unload("m")
        assert manager.used_ram_mb == 0
        assert manager.available_ram_mb == 10240
