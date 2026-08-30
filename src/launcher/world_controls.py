"""P8.WG4 — Shared WorldSpec field metadata used by launcher core, CLI, and GUI.

Every ``WorldSpec`` field gets one ``FieldMeta`` with label, type, range,
default, CLI flag, and an optional "advanced" flag so GUIs can group rarely
tweaked fields behind an expander.  The mapping is authoritative — if a
field appears in ``WorldSpec`` but not here, the launcher cannot control it.

Byte-for-byte equivalence rule
-------------------------------
The launcher builds a ``GenerationRequest`` (and ultimately ``RunSpec``) from
its form state.  After canonicalization (preset expansion, default fill-in),
the effective specification must be identical whether it came from a GUI
configuration file or CLI flags.  An equivalence test in
``tests/test_world_controls_p8wg4.py`` enforces this.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields as dc_fields
from typing import Any

# ── Metadata per field ──────────────────────────────────────────────────


@dataclass(frozen=True)
class FieldMeta:
    """Immutable metadata for one ``WorldSpec`` / ``GenerationRequest`` field."""

    name: str  # Python attribute name (e.g. "continent_count")
    label: str  # Short human-readable label ("Continents")
    type_: type  # Python type (int, float, str)
    default: object  # Default value (when not overridden)
    min_: object | None  # Minimum allowed value (None = unbounded)
    max_: object | None  # Maximum allowed value (None = unbounded)
    cli_flag: str  # e.g. "--continents"
    cli_help: str  # One-line help for --help
    advanced: bool = False  # True → hide behind "Advanced" expander in GUI

    def coerce(self, raw: Any) -> object:
        """Coerce a raw value (e.g. from a GUI text field) to the field type."""
        if self.type_ is int:
            return int(str(raw))
        if self.type_ is float:
            return float(str(raw))
        return str(raw)

    def validate_value(self, value: object) -> str | None:
        """Return an error string if value is invalid, or None."""
        try:
            coerced = self.coerce(value)
        except (ValueError, TypeError):
            return f"{self.label}: invalid {self.type_.__name__} value"
        if self.min_ is not None and coerced < self.min_:  # type: ignore[operator]
            return f"{self.label}: must be ≥ {self.min_}"
        if self.max_ is not None and coerced > self.max_:  # type: ignore[operator]
            return f"{self.label}: must be ≤ {self.max_}"
        return None


# ── Complete field metadata registry ────────────────────────────────────
# Sorted in GUI presentation order: basic layout first, then world-advanced,
# then local-map settings.

_WORLD_FIELDS: list[FieldMeta] = [
    # ── Basic fields (shown by default in all GUIs) ───────────────────
    FieldMeta(
        "seed", "Seed", int, 42, 0, (1 << 63) - 1, "--seed", "Generation seed (0 for random)"
    ),
    FieldMeta("title", "Title", str, "Untitled World", None, None, "--title", "Story title"),
    FieldMeta("width", "Width", int, 1024, 32, 8192, "--width", "World grid width (cells)"),
    FieldMeta("height", "Height", int, 1024, 32, 8192, "--height", "World grid height (cells)"),
    FieldMeta(
        "continent_count", "Continents", int, 1, 1, 256, "--continents", "Number of continents"
    ),
    FieldMeta(
        "history_years",
        "History (years)",
        int,
        500,
        0,
        10000,
        "--history-years",
        "Years of simulated history",
    ),
    FieldMeta(
        "civilization_count",
        "Civilizations",
        int,
        8,
        1,
        256,
        "--civilizations",
        "Target civilization count",
    ),
    FieldMeta(
        "metres_per_world_cell",
        "Cell size (m)",
        int,
        8000,
        250,
        100000,
        "--metres-per-world-cell",
        "Metres per world cell",
    ),
    FieldMeta("plate_count", "Plates", int, 24, 1, 256, "--plate-count", "Tectonic plate count"),
    FieldMeta(
        "minimum_continent_cells",
        "Min continent area",
        int,
        4096,
        1,
        None,
        "--minimum-continent-cells",
        "Minimum cells per continent",
    ),
    FieldMeta(
        "sea_level_ppm",
        "Sea level (ppm)",
        int,
        380_000,
        50000,
        950_000,
        "--sea-level-ppm",
        "Sea level in parts-per-million",
    ),
    FieldMeta(
        "erosion_passes",
        "Erosion passes",
        int,
        32,
        0,
        512,
        "--erosion-passes",
        "Thermal/hydraulic erosion iterations",
    ),
    FieldMeta(
        "climate_relaxation_passes",
        "Climate passes",
        int,
        64,
        8,
        512,
        "--climate-relaxation-passes",
        "Climate relaxation iterations",
    ),
    # history_ticks_per_year and snapshot_interval_years are fixed worldgen-1
    # invariants on the live CLI (WORLD_FIXED_FIELDS in src/cli.py) — no flag
    # exists for them, so they carry no cli_flag and build_argv never emits them.
    FieldMeta(
        "history_ticks_per_year",
        "Ticks/year",
        int,
        12,
        12,
        12,
        "",
        "History ticks per year (worldgen-1 requires 12; fixed, not a CLI flag)",
    ),
    FieldMeta(
        "snapshot_interval_years",
        "Snapshot interval",
        int,
        10,
        10,
        10,
        "",
        "Years between history snapshots (worldgen-1 requires 10; fixed, not a CLI flag)",
    ),
    FieldMeta(
        "axial_tilt_millidegrees",
        "Axial tilt (m°)",
        int,
        23_500,
        None,
        None,
        "--axial-tilt-millidegrees",
        "Planet axial tilt in millidegrees",
    ),
    # ── Local-map fields (advanced) ──────────────────────────────────
    FieldMeta(
        "local_site_width",
        "Site width",
        int,
        128,
        32,
        1024,
        "--local-site-width",
        "Local site grid width",
        advanced=True,
    ),
    FieldMeta(
        "local_site_height",
        "Site height",
        int,
        128,
        32,
        1024,
        "--local-site-height",
        "Local site grid height",
        advanced=True,
    ),
    FieldMeta(
        "local_z_levels",
        "Site Z-levels",
        int,
        32,
        4,
        256,
        "--local-z-levels",
        "Local site vertical levels",
        advanced=True,
    ),
    FieldMeta(
        "local_cell_millimetres",
        "Local cell (mm)",
        int,
        2000,
        1,
        None,
        "--local-cell-millimetres",
        "Local cell size in millimetres",
        advanced=True,
    ),
]

# Build lookup indexes
_FIELD_BY_NAME: dict[str, FieldMeta] = {f.name: f for f in _WORLD_FIELDS}
_ADVANCED_NAMES: frozenset[str] = frozenset(f.name for f in _WORLD_FIELDS if f.advanced)
_BASIC_NAMES: tuple[str, ...] = tuple(f.name for f in _WORLD_FIELDS if not f.advanced)


# ── Public API ──────────────────────────────────────────────────────────


def all_fields() -> list[FieldMeta]:
    """Return the complete ordered list of WorldSpec/Lancher field metadata."""
    return list(_WORLD_FIELDS)


def basic_fields() -> list[FieldMeta]:
    """Return non-advanced fields (shown by default in GUIs)."""
    return [f for f in _WORLD_FIELDS if not f.advanced]


def advanced_fields() -> list[FieldMeta]:
    """Return advanced fields (hidden behind expander in GUIs)."""
    return [f for f in _WORLD_FIELDS if f.advanced]


def get_field(name: str) -> FieldMeta:
    """Look up a field by name.  Raises KeyError if unknown."""
    return _FIELD_BY_NAME[name]


def cli_flag_map() -> dict[str, str]:
    """Return ``{field_name: cli_flag}`` for all fields."""
    return {f.name: f.cli_flag for f in _WORLD_FIELDS}


def field_names() -> tuple[str, ...]:
    """Return all field names in order."""
    return tuple(f.name for f in _WORLD_FIELDS)


def advanced_names() -> frozenset[str]:
    """Return field names tagged as advanced."""
    return _ADVANCED_NAMES


def basic_names() -> tuple[str, ...]:
    """Return non-advanced field names in order."""
    return _BASIC_NAMES


# ── Validation ──────────────────────────────────────────────────────────


def validate_state(
    values: dict[str, Any],
    *,
    skip: frozenset[str] = frozenset(),
) -> list[str]:
    """Validate a dict of field-name → value against FieldMeta constraints.

    Returns a list of human-readable error strings (empty = valid).
    ``skip`` names (e.g., launcher-local fields like "forge_path") are ignored.
    """
    errors: list[str] = []
    for field in _WORLD_FIELDS:
        if field.name in skip:
            continue
        raw = values.get(field.name)
        if raw is None or raw == "" or (isinstance(raw, str) and raw.strip() == ""):
            continue  # optional, use default
        err = field.validate_value(raw)
        if err:
            errors.append(err)
    return errors


# ── Field-name parity check ─────────────────────────────────────────────


def verify_worldspec_parity() -> list[str]:
    """P8.WG4: Verify every WorldSpec field has a FieldMeta entry.

    Returns a list of missing or extra field names (empty = parity).
    """
    from ..domain.run_spec import WorldSpec

    ws_names = {f.name for f in dc_fields(WorldSpec)}
    missing = ws_names - {f.name for f in _WORLD_FIELDS}
    # Extra fields are RunSpec-level controls rather than WorldSpec fields.
    return [f"Missing from world_controls: {m}" for m in sorted(missing)]
