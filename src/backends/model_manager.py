"""Model Manager — shared lifecycle and RAM budget enforcement.

All concrete backends use the ModelManager to coordinate model loading.
Ensures the total loaded models never exceed the configured RAM budget.

Phase 5.5B: Added resource_scope() async context manager — "load on enter,
unload on exit" pattern replaces manual try/finally blocks in GenerateStory.
Added ModelRole enum for semantic model identification.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ..pipeline.errors import ModelLoadError, ResourceError, StoryTellerError


class ModelRole(Enum):
    """Semantic role of a model in the pipeline."""

    TEXT = "text"
    VALIDATOR = "validator"
    IMAGE = "image"
    MUSIC = "music"
    GAME_MASTER = "game_master"


class ModelStatus(Enum):
    """Current state of a model."""

    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    UNLOADING = "unloading"


@dataclass
class ModelHandle:
    """Tracks a single loaded model."""

    name: str
    role: ModelRole = ModelRole.TEXT
    provider: str = ""
    ram_mb: int = 0
    status: ModelStatus = ModelStatus.UNLOADED
    instance: Any = None


class RamBudgetExceededError(ResourceError):
    """Raised when loading a model would exceed the RAM budget."""

    def __init__(self, requested_mb: int, used_mb: int, budget_mb: int) -> None:
        message = (
            f"Cannot load model ({requested_mb} MB): "
            f"{used_mb} MB already in use, budget is {budget_mb} MB "
            f"(would exceed by {requested_mb + used_mb - budget_mb} MB)"
        )
        super().__init__("ram", message)


class ModelManager:
    """Coordinates model loading/unloading with RAM budget enforcement.

    Usage:
        manager = ModelManager(budget_mb=10240)
        manager.register("text_gen", text_backend, role=ModelRole.TEXT, ram_mb=4700)
        manager.register("image_gen", image_backend, role=ModelRole.IMAGE, ram_mb=5000)

        # Manual load/unload:
        await manager.load("text_gen")
        ... generate text ...
        await manager.unload("text_gen")

        # Resource scope (load on enter, unload on exit):
        async with manager.resource_scope("text_gen"):
            ... generate text ...
        # model is automatically unloaded here — even on exception
    """

    def __init__(self, budget_mb: int = 10240) -> None:
        self._budget_mb = budget_mb
        self._handles: dict[str, ModelHandle] = {}
        self._load_order: list[str] = []  # FIFO for auto-unload
        self._peak_ram_mb: int = 0  # Track peak usage

    # ── properties ───────────────────────────────────────────────────

    @property
    def budget_mb(self) -> int:
        return self._budget_mb

    @property
    def used_ram_mb(self) -> int:
        """Total RAM currently consumed by loaded models."""
        return sum(h.ram_mb for h in self._handles.values() if h.status == ModelStatus.LOADED)

    @property
    def peak_ram_mb(self) -> int:
        """Highest RAM usage observed during this manager's lifetime."""
        return self._peak_ram_mb

    @property
    def available_ram_mb(self) -> int:
        """RAM still available for new models."""
        return self._budget_mb - self.used_ram_mb

    # ── registration ────────────────────────────────────────────────

    def register(
        self,
        name: str,
        instance: Any,
        *,
        role: ModelRole = ModelRole.TEXT,
        ram_mb: int = 0,
    ) -> None:
        """Register a model with the manager.

        Args:
            name: Logical name (e.g., "text_generator").
            instance: The backend instance (must have load()/unload()).
            role: Semantic role for resource scheduling.
            ram_mb: Peak RAM usage when loaded.

        Raises:
            ValueError: If a model with this name is already registered.
        """
        if name in self._handles:
            raise ValueError(f"Model '{name}' is already registered")
        self._handles[name] = ModelHandle(
            name=name,
            role=role,
            provider=getattr(instance, "provider", "unknown"),
            ram_mb=ram_mb,
            instance=instance,
        )

    def is_loaded(self, name: str) -> bool:
        handle = self._handles.get(name)
        return handle is not None and handle.status == ModelStatus.LOADED

    def get_loaded_models(self) -> list[str]:
        return [name for name, h in self._handles.items() if h.status == ModelStatus.LOADED]

    def get_by_role(self, role: ModelRole) -> list[str]:
        """Return names of all registered models with the given role."""
        return [name for name, h in self._handles.items() if h.role == role]

    # ── lifecycle ───────────────────────────────────────────────────

    async def load(self, name: str) -> None:
        """Load a model, enforcing RAM budget.

        Raises:
            KeyError: If the model is not registered.
            RamBudgetExceededError: If loading would exceed the budget.
        """
        handle = self._handles.get(name)
        if handle is None:
            raise KeyError(f"Model '{name}' is not registered")

        if handle.status == ModelStatus.LOADED:
            return

        if handle.ram_mb > self.available_ram_mb:
            raise RamBudgetExceededError(
                requested_mb=handle.ram_mb,
                used_mb=self.used_ram_mb,
                budget_mb=self._budget_mb,
            )

        handle.status = ModelStatus.LOADING
        try:
            if handle.instance and hasattr(handle.instance, "load"):
                await handle.instance.load()
            handle.status = ModelStatus.LOADED
            self._load_order.append(name)
            self._peak_ram_mb = max(self._peak_ram_mb, self.used_ram_mb)
        except StoryTellerError:
            handle.status = ModelStatus.UNLOADED
            raise
        except Exception as error:
            handle.status = ModelStatus.UNLOADED
            raise ModelLoadError(name, str(error)) from error

    async def unload(self, name: str) -> None:
        """Unload a model to free RAM.

        Raises:
            KeyError: If the model is not registered.
        """
        handle = self._handles.get(name)
        if handle is None:
            raise KeyError(f"Model '{name}' is not registered")

        if handle.status != ModelStatus.LOADED:
            return

        handle.status = ModelStatus.UNLOADING
        try:
            if handle.instance and hasattr(handle.instance, "unload"):
                await handle.instance.unload()
            handle.status = ModelStatus.UNLOADED
            if name in self._load_order:
                self._load_order.remove(name)
        except Exception:
            handle.status = ModelStatus.LOADED
            raise

    async def unload_all(self) -> None:
        """Unload all currently loaded models."""
        for name in list(self._load_order):
            await self.unload(name)

    async def unload_to_fit(self, required_mb: int) -> None:
        """Unload models (FIFO) until enough RAM is available.

        Raises:
            RamBudgetExceededError: If even all models aren't enough.
        """
        if required_mb > self._budget_mb:
            raise RamBudgetExceededError(
                requested_mb=required_mb,
                used_mb=self.used_ram_mb,
                budget_mb=self._budget_mb,
            )

        while self.available_ram_mb < required_mb and self._load_order:
            oldest = self._load_order[0]
            await self.unload(oldest)

        if self.available_ram_mb < required_mb:
            raise RamBudgetExceededError(
                requested_mb=required_mb,
                used_mb=self.used_ram_mb,
                budget_mb=self._budget_mb,
            )

    # ── resource scope (Phase 5.5B) ─────────────────────────────────

    @asynccontextmanager
    async def resource_scope(self, name: str) -> AsyncIterator[ModelHandle]:
        """Async context manager: load model on enter, unload on exit.

        Guarantees unload even on exception or KeyboardInterrupt.
        On Ctrl+C: unloads model, emits cancellation event, re-raises.

        Usage:
            async with manager.resource_scope("text_gen") as handle:
                # model is loaded here
                await generate(...)
            # model is unloaded here — guaranteed
        """
        await self.load(name)
        try:
            yield self._handles[name]
        except KeyboardInterrupt:
            import sys

            print(
                f"\n⚠ Interrupted — unloading model '{name}' before exit...",
                file=sys.stderr,
            )
            raise
        finally:
            await self.unload(name)
