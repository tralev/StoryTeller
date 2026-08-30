"""Shared types for package validation without package-builder dependencies."""

from collections.abc import Callable
from typing import Any

JsonLoader = Callable[[bytes, str], Any]
CanonicalEncoder = Callable[[Any], bytes]


class PackageV2Error(ValueError):
    """A package failure carrying a stable cross-platform issue code."""

    def __init__(self, code: str, message: str, path: str = "manifest.json") -> None:
        self.code, self.path = code, path
        super().__init__(f"{code}: {path}: {message}")
