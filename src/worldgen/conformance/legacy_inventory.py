"""P8.C05H — Legacy symbol inventory (historical record).

As of P8.C05H, all legacy worldgen modules (adapter.py, step.py, generator.py,
models.py) have been deleted. This module's LEGACY_SYMBOLS inventory is now
empty, and the architecture import fence is no longer needed — Python enforces
via ModuleNotFoundError.

KNOWN_DEFECT_IDS preserve historical names; current target-invariant regression
tests are linked from the coverage ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class LegacySymbol:
    """One legacy worldgen symbol tracked for migration."""

    symbol: str
    """The Python symbol name (e.g., 'GridCell', 'generate_world')."""

    definition: str
    """Module path where the symbol is defined."""

    callers: tuple[str, ...]
    """Modules that still import or call this symbol."""

    disposition: Literal["migrate", "delete", "characterize"]
    """What to do with it."""

    notes: str
    """Why it still exists and what replaces it."""


# Deleted modules are recorded explicitly so architecture tests prove they stay
# absent instead of trusting an empty inventory.
LEGACY_MODULES: tuple[str, ...] = (
    "adapter", "generator", "models", "step", "terrain", "biomes", "regions", "climate",
)

LEGACY_SYMBOLS: tuple[LegacySymbol, ...] = ()

# Historical names retained for traceability to executable target regressions.
KNOWN_DEFECT_IDS: frozenset[str] = frozenset({
    "WG-PHYS-drainage-sink",
    "WG-HIST-skipped-years",
    "WG-INTEGRATION-order-dependence",
    "WG-LOCAL-incomplete-maps",
    "WG-KERNEL-mutable-overrides",
    "WG-KERNEL-inconsistent-ids",
})
