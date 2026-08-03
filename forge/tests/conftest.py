"""Shared test fixtures and helpers for all test modules."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, cast

import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(filename: str) -> Dict[str, Any]:
    """Load a JSON fixture file from tests/fixtures/."""
    with open(os.path.join(FIXTURES_DIR, filename)) as f:
        return cast(Dict[str, Any], json.load(f))
