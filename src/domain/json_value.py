"""Recursive JSON value aliases used at persistence boundaries."""

from __future__ import annotations

from typing import Union

from typing_extensions import TypeAlias

JsonScalar: TypeAlias = Union[None, bool, int, float, str]
JsonValue: TypeAlias = Union[JsonScalar, list["JsonValue"], dict[str, "JsonValue"]]
JsonObject: TypeAlias = dict[str, JsonValue]
