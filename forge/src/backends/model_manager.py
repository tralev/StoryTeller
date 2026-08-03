"""Model Manager — shared lifecycle and RAM budget enforcement.

All concrete backends use the ModelManager to coordinate model loading.
Ensures the total loaded models never exceed the configured RAM budget.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ModelStatus(Enum):
    """Current state of a model."""
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    UNLOADING = "unloading"


@dataclass
class ModelHandle:
    """Tracks a single loaded model."""

    name: str  # e.g., "text_generator", "validator"
    provider: str
    ram_mb: int
    status: ModelStatus = ModelStatus.UNLOADED
    instance: Any = None  # The actual backend instance


class RamBudgetExceededError(RuntimeError):
    """Raised when loading a model would exceed the RAM budget."""

    def __init__(self, requested_mb: int, used_mb: int, budget_mb: int) -> None:
        super().__init__(
            f"Cannot load model ({requested_mb} MB): "
            f"{used_mb} MB already in use, budget is {budget_mb} MB "
            f"(would exceed by {requested_mb + used_mb - budget_mb} MB)"
        )


class ModelManager:
    """Coordinates model loading/unloading with RAM budget enforcement.

    Usage:
        manager = ModelManager(budget_mb=10240)
        manager.register("text_generator", llm_backend, ram_mb=4700)
        await manager.load("text_generator")  # checks budget, marks loaded
        ...
        await manager.unload("text_generator")  # frees RAM
    """

    def __init__(self, budget_mb: int = 10240) -> None:
        self._budget_mb = budget_mb
        self._handles: Dict[str, ModelHandle] = {}
        self._load_order: List[str] = []  # FIFO for auto-unload

    @property
    def budget_mb(self) -> int:
        return self._budget_mb

    @property
    def used_ram_mb(self) -> int:
        """Total RAM currently consumed by loaded models."""
        return sum(
            h.ram_mb for h in self._handles.values()
            if h.status == ModelStatus.LOADED
        )

    @property
    def available_ram_mb(self) -> int:
        """RAM still available for new models."""
        return self._budget_mb - self.used_ram_mb

    def register(self, name: str, instance: Any, ram_mb: int) -> None:
        """Register a model with the manager.

        Args:
            name: Logical name (e.g., "text_generator").
            instance: The backend instance.
            ram_mb: Peak RAM usage when loaded.

        Raises:
            ValueError: If a model with this name is already registered.
        """
        if name in self._handles:
            raise ValueError(f"Model '{name}' is already registered")
        self._handles[name] = ModelHandle(
            name=name,
            provider=getattr(instance, "provider", "unknown"),
            ram_mb=ram_mb,
            instance=instance,
        )

    def is_loaded(self, name: str) -> bool:
        """Check if a model is currently loaded."""
        handle = self._handles.get(name)
        return handle is not None and handle.status == ModelStatus.LOADED

    def get_loaded_models(self) -> List[str]:
        """Return names of all currently loaded models."""
        return [name for name, h in self._handles.items()
                if h.status == ModelStatus.LOADED]

    async def load(self, name: str) -> None:
        """Load a model, enforcing RAM budget.

        Args:
            name: The registered model name to load.

        Raises:
            KeyError: If the model is not registered.
            RamBudgetExceededError: If loading would exceed the budget.
        """
        handle = self._handles.get(name)
        if handle is None:
            raise KeyError(f"Model '{name}' is not registered")

        if handle.status == ModelStatus.LOADED:
            return  # Already loaded

        # Check budget
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
        except Exception:
            handle.status = ModelStatus.UNLOADED
            raise

    async def unload(self, name: str) -> None:
        """Unload a model to free RAM.

        Args:
            name: The registered model name to unload.

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
            handle.status = ModelStatus.LOADED  # Rollback
            raise

    async def unload_all(self) -> None:
        """Unload all currently loaded models, freeing all RAM."""
        for name in list(self._load_order):  # Copy — unload modifies the list
            await self.unload(name)

    async def unload_to_fit(self, required_mb: int) -> None:
        """Unload models (FIFO order) until enough RAM is available.

        Args:
            required_mb: RAM needed for the new model.

        Raises:
            RamBudgetExceededError: If even after unloading all models,
                                     there isn't enough RAM.
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
