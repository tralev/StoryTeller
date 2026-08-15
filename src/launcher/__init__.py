"""P8.11 — Toolkit-free launcher core shared by win/, lin/, and mac/ wrappers.

This module must not import src.worldgen, model backends, or pipeline step
implementations. An architecture test enforces this constraint.
"""

from .core import (
    CancelResult,
    ConfigExport,
    ForgeProcess,
    JsonlProgress,
    LauncherState,
    ParseResult,
    ParsedEvent,
    ProgressSnapshot,
    RevealResult,
    build_argv,
    build_full_argv,
    parse_jsonl_line,
    parse_jsonl_stream,
    reduce_progress,
    to_config_dict,
)

__all__ = [
    "build_argv",
    "build_full_argv",
    "CancelResult",
    "ConfigExport",
    "ForgeProcess",
    "JsonlProgress",
    "LauncherState",
    "parse_jsonl_line",
    "parse_jsonl_stream",
    "ParsedEvent",
    "ParseResult",
    "ProgressSnapshot",
    "reduce_progress",
    "RevealResult",
    "to_config_dict",
]
