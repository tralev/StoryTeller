"""Normative deterministic numeric profile for worldgen-1."""

from __future__ import annotations

import hashlib

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
    if denominator <= 0 or numerator < 0:
        raise ValueError("canonical division requires nonnegative numerator and positive denominator")
    return checked_i64((checked_i64(numerator) + denominator // 2) // denominator)


def mul_ppm(left: int, right: int) -> int:
    return div_round_half_up(checked_i64(left * right), PPM)


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
        limit = ((1 << 64) // exclusive_upper) * exclusive_upper
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


def stable_id(kind: str, master_seed: int, *parts: object) -> str:
    if not kind or not kind.replace("_", "").isalnum():
        raise ValueError("stable ID kind must be alphanumeric/underscore")
    payload = "\x1f".join((str(master_seed), kind, *(str(p) for p in parts)))
    return f"{kind}_{hashlib.sha256(payload.encode()).hexdigest()[:32]}"
