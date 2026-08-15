"""Normative deterministic numeric profile for worldgen-1."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable, Iterable
from concurrent.futures import Executor, Future
from dataclasses import dataclass
from typing import Any, ClassVar, TypeVar

from ..domain.run_spec import derive_seed

MASK64 = (1 << 64) - 1
MAX_I64 = (1 << 63) - 1
MIN_I64 = -(1 << 63)
PPM = 1_000_000


def checked_i64(value: int) -> int:
    if not MIN_I64 <= value <= MAX_I64:
        raise OverflowError("worldgen signed 64-bit overflow")
    return value


def div_round_half_up(numerator: int, denominator: int) -> int:
    """Divide with nearest-half-away-from-zero rounding and checked i64 output."""
    if denominator <= 0:
        raise ValueError("canonical division requires a positive denominator")
    quotient, remainder = divmod(abs(numerator), denominator)
    if remainder * 2 >= denominator:
        quotient += 1
    return checked_i64(quotient if numerator >= 0 else -quotient)


def mul_ppm(left: int, right: int) -> int:
    return div_round_half_up(left * right, PPM)


def div_floor_exact(numerator: int, denominator: int) -> int:
    """Floor division for exact addressing/partition arithmetic, never scaling."""
    if denominator <= 0:
        raise ValueError("exact division requires a positive denominator")
    quotient, _ = divmod(numerator, denominator)
    return quotient


@dataclass(frozen=True)
class FixedUnit:
    """Immutable signed-64-bit scalar whose concrete class carries its unit."""

    value: int
    unit: ClassVar[str] = "integer"

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise TypeError(f"{type(self).__name__} requires an integer")
        checked_i64(self.value)


class Distance(FixedUnit):
    unit = "millimetres"


class Elevation(FixedUnit):
    unit = "millimetres"


class Temperature(FixedUnit):
    unit = "millicelsius"


class Rainfall(FixedUnit):
    unit = "milligrams_per_square_metre"


class Moisture(FixedUnit):
    unit = "parts_per_million"


class Mass(FixedUnit):
    unit = "kilograms"


class Energy(FixedUnit):
    unit = "kilojoules"


class Population(FixedUnit):
    unit = "heads"


class Time(FixedUnit):
    unit = "ticks"


class Probability(FixedUnit):
    unit = "parts_per_million"

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 0 <= self.value <= PPM:
            raise ValueError("probability must be within 0..1,000,000 ppm")


class Price(FixedUnit):
    unit = "base_currency_units"


class Capacity(FixedUnit):
    unit = "integer_capacity"


FIXED_UNIT_TYPES: tuple[type[FixedUnit], ...] = (
    Distance, Elevation, Temperature, Rainfall, Moisture, Mass, Energy,
    Population, Time, Probability, Price, Capacity,
)


class SplitMix64:
    """Version-stable pseudo-random stream; never shared across domains."""

    def __init__(self, seed: int) -> None:
        self.state = seed & MASK64

    def next_u64(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & MASK64
        value = self.state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
        return (value ^ (value >> 31)) & MASK64

    def below(self, exclusive_upper: int) -> int:
        if exclusive_upper <= 0:
            raise ValueError("upper bound must be positive")
        limit = div_floor_exact(1 << 64, exclusive_upper) * exclusive_upper
        while True:
            value = self.next_u64()
            if value < limit:
                return value % exclusive_upper

    def chance_ppm(self, probability: int) -> bool:
        if not 0 <= probability <= PPM:
            raise ValueError("probability must be within 0..1,000,000 ppm")
        return self.below(PPM) < probability


def rng_for(master_seed: int, domain: str, *parts: object) -> SplitMix64:
    return SplitMix64(derive_seed(master_seed, domain, *parts))


def rng_for_decision(
    master_seed: int, domain: str, stable_entity_id: object, decision_label: object,
) -> SplitMix64:
    """Create an entity-local stream for one explicitly named decision."""
    return SplitMix64(
        derive_seed(master_seed, domain, stable_entity_id, decision_label)
    )


STABLE_ID_VERSION = "storyteller.id.sha256.v1"
_ID_KIND = re.compile(r"^[a-z][a-z0-9_]*$")
_IDENTITY_LABEL = re.compile(r"^[a-z][a-z0-9_]*$")
_DISPLAY_LABELS = frozenset({"name", "display_name", "title"})


@dataclass(frozen=True)
class IdentityComponent:
    """One typed, semantically labelled input to a stable entity identity.

    Only canonical scalar values are accepted. This deliberately excludes
    unordered containers and makes accidental use of mutable display names
    visible at the call site and invalid at runtime.
    """

    label: str
    value: int | str

    def __post_init__(self) -> None:
        if not _IDENTITY_LABEL.fullmatch(self.label):
            raise ValueError("identity component label must be lowercase snake_case")
        if self.label in _DISPLAY_LABELS or self.label.endswith("_name"):
            raise ValueError("display names and titles cannot define stable identity")
        if isinstance(self.value, bool) or not isinstance(self.value, (int, str)):
            raise TypeError("identity component value must be an int or string")
        if isinstance(self.value, str):
            if not self.value:
                raise ValueError("string identity component cannot be empty")
            if unicodedata.normalize("NFC", self.value) != self.value:
                raise ValueError("string identity component must use NFC normalization")


def identity(label: str, value: int | str) -> IdentityComponent:
    """Declare one canonical identity input at a stable-ID call site."""
    return IdentityComponent(label, value)


def _frame(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return str(len(encoded)).encode("ascii") + b":" + encoded


def stable_id(kind: str, master_seed: int, *components: IdentityComponent) -> str:
    """Derive a versioned stable ID from canonical, typed identity inputs."""
    if not _ID_KIND.fullmatch(kind):
        raise ValueError("stable ID kind must be lowercase snake_case")
    if isinstance(master_seed, bool) or not isinstance(master_seed, int):
        raise TypeError("stable ID master seed must be an integer")
    if not components:
        raise ValueError("stable ID requires at least one identity component")
    payload = bytearray()
    for value in (STABLE_ID_VERSION, kind, "i", str(master_seed)):
        payload.extend(_frame(value))
    for component in components:
        if not isinstance(component, IdentityComponent):
            raise TypeError("stable ID inputs must be created with identity()")
        value_type = "i" if isinstance(component.value, int) else "s"
        for value in (component.label, value_type, str(component.value)):
            payload.extend(_frame(value))
    return f"{kind}_{hashlib.sha256(payload).hexdigest()[:32]}"


# ── Fixed-point bounded arithmetic ────────────────────────────────────

def clamp(value: int, low: int, high: int) -> int:
    """Saturate an integer into [low, high]."""
    return max(low, min(high, value))


def clamp_int(value: int, low: int, high: int) -> int:
    """Canonical spec name for bounded integer saturation.

    ``generation.md`` uses ``clamp_int`` as the normative symbol;
    ``clamp`` is retained as a conventional alias.
    """
    return clamp(value, low, high)


# ── Fixed-point value noise (generation.md Stage 1) ───────────────────

def _fade_ppm(value_ppm: int) -> int:
    squared = div_round_half_up(value_ppm * value_ppm, PPM)
    return div_round_half_up(squared * (3 * PPM - 2 * value_ppm), PPM)


def _lattice_ppm(seed: int, x: int, y: int) -> int:
    value = derive_seed(seed, "noise.lattice", f"cell:{x}:{y}", "value")
    return div_round_half_up(value * (2 * PPM), MASK64) - PPM


def noise2_ppm(x_ppm: int, y_ppm: int, seed: int) -> int:
    """Deterministic fixed-point value noise in [-PPM, PPM].

    Implements the generation.md noise2_ppm exactly: four-corner lattice
    interpolation with fade curves.
    """
    x0 = div_floor_exact(x_ppm, PPM)
    y0 = div_floor_exact(y_ppm, PPM)
    x1, y1 = x0 + 1, y0 + 1
    tx = _fade_ppm(x_ppm - x0 * PPM)
    ty = _fade_ppm(y_ppm - y0 * PPM)
    a = div_round_half_up(
        _lattice_ppm(seed, x0, y0) * (PPM - tx)
        + _lattice_ppm(seed, x1, y0) * tx,
        PPM,
    )
    b = div_round_half_up(
        _lattice_ppm(seed, x0, y1) * (PPM - tx)
        + _lattice_ppm(seed, x1, y1) * tx,
        PPM,
    )
    return div_round_half_up(a * (PPM - ty) + b * ty, PPM)


def fractal_noise_ppm(x: int, y: int, seed: int, octaves: int = 5) -> int:
    """Multi-octave fixed-point fractal noise.

    Each octave doubles frequency and halves amplitude.
    """
    total = 0
    amplitude = PPM
    frequency = 1
    weight = 0
    for octave in range(octaves):
        derived = derive_seed(seed, "noise.octave", f"octave:{octave}", "seed")
        sample = noise2_ppm(x * frequency * PPM, y * frequency * PPM, derived)
        total += div_round_half_up(amplitude * sample, PPM)
        weight += amplitude
        amplitude = div_round_half_up(amplitude, 2)
        frequency *= 2
    return div_round_half_up(total * PPM, max(1, weight))


# ── Climate cosine (generation.md Stage 3) ────────────────────────────

def cos_lookup_ppm(angle_mdeg: int) -> int:
    """Deterministic Bhaskara-I cosine approximation in parts per million.

    Returns cos(angle_mdeg / 1000 degrees) * PPM, with angle in
    millidegrees (0-360,000).
    """
    angle = angle_mdeg % 360_000
    if angle > 180_000:
        angle = 360_000 - angle
    sign = 1 if angle <= 90_000 else -1
    sine_angle = 90_000 - angle if angle <= 90_000 else angle - 90_000
    x = sine_angle
    product = x * (180_000 - x)
    denominator = 40_500_000_000 - product
    magnitude = div_round_half_up(4 * product * PPM, max(1, denominator))
    return sign * magnitude


# ── SplitMix64 golden vectors ─────────────────────────────────────────

SPLITMIX64_ZERO_GOLDEN: tuple[int, ...] = (
    0xe220a8397b1dcdaf,
    0x6e789e6aa1b965f4,
    0x06c45d188009454f,
    0xf88bb8a8724c81ec,
    0x1b39896a51a8749b,
    0x53cb9f0c747ea2ea,
    0x2c829abe1f4532e1,
    0xc584133ac916ab3c,
    0x3ee5789041c98ac3,
    0xf3b8488c368cb0a6,
    0x657eecdd3cb13d09,
    0xc2d326e0055bdef6,
    0x8621a03fe0bbdb7b,
    0x8e1f7555983aa92f,
    0xb54e0f1600cc4d19,
    0x84bb3f97971d80ab,
)


def verify_splitmix64_golden() -> bool:
    """Confirm SplitMix64 matches frozen golden vectors."""
    rng = SplitMix64(0)
    for i, expected in enumerate(SPLITMIX64_ZERO_GOLDEN):
        if rng.next_u64() != expected:
            return False
    return True


# ── Deterministic parallelism (generation.md Determinism) ─────────────

K = TypeVar("K")
V = TypeVar("V")


def deterministic_map(
    executor: Executor, fn: Callable[[K], V], keys: Iterable[K],
) -> tuple[tuple[K, V], ...]:
    """Execute fn on each key in sorted order; workers may run in parallel
    but results are collected and returned in canonical key order.

    Required by generation.md: worker 1 == worker N must produce identical
    bytes when the caller commits results in the returned order.
    """
    ordered: tuple[Any, ...] = tuple(sorted(keys))
    futures: dict[Any, Future[V]] = {
        key: executor.submit(fn, key) for key in ordered
    }
    return tuple((key, futures[key].result()) for key in ordered)
