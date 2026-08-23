"""P8.11 — Toolkit-free launcher core shared by win/, lin/, and mac/ wrappers.

Owns typed form state, configuration import/export, argv-list construction,
child PID/run ID, bounded JSONL parser, progress reducer, cancel, resume,
and result reveal.

Uses ``subprocess`` argument arrays with ``shell=False``. Must not import
``src.worldgen``, model backends, or pipeline step implementations.

Architecture rule
-----------------
This module may import from:
- ``src.pipeline.events`` — for event-type parsing constants (JSONL_EVENT_VERSION, etc.)
- ``src.application.models`` — for ``GenerationRequest`` field reflection
- Standard library only

It must NOT import:
- ``src.worldgen`` or any submodule
- ``src.backends`` or any submodule
- ``src.narrative`` or any submodule
- ``src.storage`` or ``src.models`` (step implementations, not data models)
- ``src.pipeline.plan``, ``src.pipeline.orchestrator``, etc.

An architecture test in ``tests/test_launcher_core_p8c11.py`` enforces this.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# ── Allowed imports: events constants + GenerationRequest field names ─────
# These are pure-data / constants, not pipeline or backend implementations.
from .world_controls import (
    all_fields,
    cli_flag_map,
    field_names,
    validate_state,
)

# ── Constants ────────────────────────────────────────────────────────────

# Known event types that affect progress (P8.10 contract).
_PROGRESS_EVENT_TYPES = frozenset(
    {
        "step_started",
        "step_progress",
        "step_completed",
        "step_failed",
        "artifact_reused",
        "artifact_regenerated",
        "artifact_committed",
        "pipeline_started",
        "pipeline_completed",
        "pipeline_failed",
        "pipeline_cancelled",
    }
)

# P8.WG4: CLI flag map generated from shared world_controls metadata.
_REQUEST_CLI_FIELDS: dict[str, str] = cli_flag_map()


# ── Typed form state ─────────────────────────────────────────────────────


@dataclass
class LauncherState:
    """P8.11: Typed form state backing the launcher GUI.

    Every field maps to a ``GenerationRequest`` field or a launcher-local
    setting.  Validation mirrors ``RunSpec`` / ``WorldSpec`` ranges.

    P8.WG4: All ``WorldSpec`` fields are present so that no control is
    missing from the launcher.  Field defaults come from the shared
    ``world_controls`` metadata.
    """

    # ── RunSpec-level fields ─────────────────────────────────────────
    seed: int = 42
    title: str = "Untitled World"
    tone: str = "mature_dark_fantasy"
    temperature: float = 0.7

    # ── WorldSpec fields (P8.WG4: complete set from world_controls) ──
    width: int = 1024
    height: int = 1024
    continent_count: int = 1
    metres_per_world_cell: int = 8_000
    plate_count: int = 24
    minimum_continent_cells: int = 4_096
    history_years: int = 500
    history_ticks_per_year: int = 12
    civilization_count: int = 8
    sea_level_ppm: int = 380_000
    axial_tilt_millidegrees: int = 23_500
    erosion_passes: int = 32
    climate_relaxation_passes: int = 64
    snapshot_interval_years: int = 10
    local_site_width: int = 128
    local_site_height: int = 128
    local_z_levels: int = 32
    local_cell_millimetres: int = 2_000

    # ── Launcher-local state (not in GenerationRequest) ─────────────
    output_dir: str = ""
    config_path: str = "config/models.yaml"
    run_id: str = ""
    forge_path: str = "forge"  # path to the forge binary
    workers: int = 1

    # P8.WG4: Track whether a named preset was expanded.
    preset_name: str = ""  # "" = no preset, "tiny"/"conformance"/"default" = expanded

    def validate(self) -> list[str]:
        """Return a list of validation errors (empty = valid).

        P8.WG4: Uses the shared ``world_controls.validate_state()`` so
        field ranges are defined in one place.
        """
        errors: list[str] = []
        if not self.title.strip():
            errors.append("Title must not be empty")
        if self.tone not in ("mature_dark_fantasy",):
            errors.append(f"Unknown tone: {self.tone}")
        if not 0.0 <= self.temperature <= 2.0:
            errors.append("Temperature must be 0.0 .. 2.0")
        # P8.WG4: Delegate WorldSpec field validation to world_controls
        errors.extend(
            validate_state(
                self.to_value_dict(),
                skip=frozenset(
                    {
                        "seed",
                        "title",
                        "tone",
                        "temperature",
                        "output_dir",
                        "config_path",
                        "run_id",
                        "forge_path",
                        "workers",
                        "preset_name",
                    }
                ),
            )
        )
        return errors

    def is_valid(self) -> bool:
        return len(self.validate()) == 0

    def to_value_dict(self) -> dict[str, object]:
        """P8.WG4: Return all field values as a plain dict for serialization."""
        result: dict[str, object] = {}
        for fname in field_names():
            if hasattr(self, fname):
                result[fname] = getattr(self, fname)
        # Also include non-WorldSpec fields
        for key in (
            "seed",
            "title",
            "tone",
            "temperature",
            "output_dir",
            "config_path",
            "workers",
            "preset_name",
        ):
            if hasattr(self, key):
                result[key] = getattr(self, key)
        return result


# ── Configuration import / export ────────────────────────────────────────


@dataclass
class ConfigExport:
    """P8.11: Serializable snapshot of launcher state for import/export."""

    version: str = "storyteller.launcher-config.v1"
    state: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {"version": self.version, "state": self.state},
            sort_keys=True,
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> ConfigExport:
        data = json.loads(raw)
        if data.get("version") != "storyteller.launcher-config.v1":
            raise ValueError(f"Unsupported config version: {data.get('version')}")
        return cls(state=dict(data.get("state", {})))


def to_config_dict(state: LauncherState) -> dict[str, Any]:
    """P8.WG4: Serialize LauncherState to a JSON-safe dict for export.

    Uses the shared ``world_controls`` field list so all WorldSpec fields
    are included automatically.
    """
    result: dict[str, Any] = {}
    for fname in field_names():
        if hasattr(state, fname):
            result[fname] = getattr(state, fname)
    # P8.WG4: RunSpec-level + launcher-local fields
    result["seed"] = state.seed
    result["title"] = state.title
    result["tone"] = state.tone
    result["temperature"] = state.temperature
    result["output_dir"] = state.output_dir
    result["config_path"] = state.config_path
    result["workers"] = state.workers
    result["preset_name"] = state.preset_name
    return result


def from_config_dict(data: dict[str, Any]) -> LauncherState:
    """P8.WG4: Deserialize a config dict into LauncherState.

    Uses the shared ``world_controls`` field defaults when a field is
    absent from the input dict.
    """
    kwargs: dict[str, Any] = {}
    for field_meta in all_fields():
        key = field_meta.name
        if key in data:
            kwargs[key] = field_meta.coerce(data[key])
        else:
            kwargs[key] = field_meta.default
    # RunSpec-level fields
    kwargs["seed"] = int(data.get("seed", 42))
    kwargs["title"] = str(data.get("title", "Untitled World"))
    kwargs["tone"] = str(data.get("tone", "mature_dark_fantasy"))
    kwargs["temperature"] = float(data.get("temperature", 0.7))
    kwargs["output_dir"] = str(data.get("output_dir", ""))
    kwargs["config_path"] = str(data.get("config_path", "config/models.yaml"))
    kwargs["workers"] = int(data.get("workers", 1))
    kwargs["preset_name"] = str(data.get("preset_name", ""))
    return LauncherState(**kwargs)


# ── argv-list construction ───────────────────────────────────────────────


def build_argv(state: LauncherState, *, resume: bool = False) -> list[str]:
    """P8.WG4: Build a ``subprocess`` argument array from launcher state.

    Uses ``shell=False``.  All ``WorldSpec`` fields are included via the
    shared ``world_controls`` metadata.  Fields at their default value are
    omitted to keep the argv short (canonicalization in the CLI fills them).

    Uses ``shell=False``.  The returned list is safe to pass directly to
    ``subprocess.Popen``.
    """
    argv: list[str] = [state.forge_path]

    argv.extend(["generate" if not resume else "resume"])

    for field_meta in all_fields():
        if not hasattr(state, field_meta.name):
            continue
        value = getattr(state, field_meta.name)
        if value is None:
            continue
        # P8.WG4: omit defaults to keep argv short; CLI fills them
        if value == field_meta.default:
            continue
        argv.extend([field_meta.cli_flag, str(value)])

    if state.output_dir:
        argv.extend(["--output", state.output_dir])
    if state.config_path:
        argv.extend(["--config", state.config_path])
    if state.workers > 1:
        argv.extend(["--workers", str(state.workers)])

    argv.append("--json-result")
    return argv


def build_full_argv(state: LauncherState, *, resume: bool = False) -> list[str]:
    """P8.WG4: Build argv with ALL fields explicit (no default omission).

    Used for byte-for-byte equivalence testing: this ensures two states
    produce identical argvs regardless of which fields were left at default.
    """
    argv: list[str] = [state.forge_path]

    argv.extend(["generate" if not resume else "resume"])

    # P8.WG4: Every field, even defaults, for testing equivalence
    for field_meta in all_fields():
        if not hasattr(state, field_meta.name):
            continue
        value = getattr(state, field_meta.name)
        if value is None:
            continue
        argv.extend([field_meta.cli_flag, str(value)])

    if state.output_dir:
        argv.extend(["--output", state.output_dir])
    if state.config_path:
        argv.extend(["--config", state.config_path])
    if state.workers > 1:
        argv.extend(["--workers", str(state.workers)])

    argv.append("--json-result")
    return argv


# ── ForgeProcess — subprocess lifecycle ──────────────────────────────────


@dataclass
class CancelResult:
    """P8.11: Result of a cancel request."""

    success: bool
    message: str


@dataclass
class RevealResult:
    """P8.11: Result after pipeline completes (or fails/cancels)."""

    status: str  # "complete", "cancelled", "failed"
    package_path: str
    content_hash: str
    exit_code: int
    errors: list[str]


class ForgeProcess:
    """P8.11: Manages a child Forge subprocess.

    - Starts forge with ``subprocess.Popen`` and ``shell=False``.
    - Tracks child PID and run_id.
    - Reads JSONL events from stdout.
    - Supports cancel via SIGINT / terminate.
    - Supports resume by building a resume argv.

    This is a synchronous wrapper; the launcher GUI runs it in a
    background thread.
    """

    def __init__(
        self, state: LauncherState, *, events_path: str | None = None, resume: bool = False
    ) -> None:
        self._state = state
        self._events_path = events_path
        self._resume = resume
        self._process: subprocess.Popen[str] | None = None
        self._pid: int | None = None
        self._run_id: str = ""
        self._started_at: float = 0.0

    @property
    def pid(self) -> int | None:
        return self._pid

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def resume(self) -> bool:
        return self._resume

    def start(self) -> None:
        """P8.11: Launch forge as a subprocess."""
        if self._process is not None:
            raise RuntimeError("Forge is already running")

        self._run_id = f"run_{uuid.uuid4().hex[:12]}"
        argv = build_argv(self._state, resume=self._resume)

        # Open events file if configured (P8.10)
        if self._events_path:
            argv.extend(["--events", self._events_path])

        self._process = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=False,
        )
        self._pid = self._process.pid
        self._started_at = time.time()

    def read_events(self, timeout: float | None = None) -> list[str]:
        """P8.11: Read available JSONL lines from the subprocess stdout.

        Returns a list of raw JSON strings (one per line).  Blocks up to
        ``timeout`` seconds, then returns whatever is available.
        """
        if self._process is None or self._process.stdout is None:
            return []
        import select

        lines: list[str] = []
        try:
            if timeout is not None:
                readable, _, _ = select.select(
                    [self._process.stdout],
                    [],
                    [],
                    timeout,
                )
                if not readable:
                    return []
            while True:
                line = self._process.stdout.readline()
                if not line:
                    break
                stripped = line.strip()
                if stripped:
                    lines.append(stripped)
                if timeout is not None and len(lines) > 0:
                    break
        except (OSError, ValueError):
            pass
        return lines

    def cancel(self) -> CancelResult:
        """P8.11: Cancel the running forge process.

        Sends SIGINT first (graceful cancel), then SIGTERM if still
        alive after 3 seconds.
        """
        if self._process is None:
            return CancelResult(False, "No process running")

        pid = self._pid
        if pid is None:
            return CancelResult(False, "No PID")

        try:
            if sys.platform == "win32":
                self._process.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                os.kill(pid, signal.SIGINT)
        except ProcessLookupError:
            return CancelResult(True, "Process already exited")

        # Wait up to 3s for graceful exit
        try:
            self._process.wait(timeout=3)
            return CancelResult(True, "Cancelled gracefully")
        except subprocess.TimeoutExpired:
            pass

        # Force kill
        try:
            self._process.kill()
            self._process.wait(timeout=2)
            return CancelResult(True, "Force-killed after timeout")
        except (ProcessLookupError, subprocess.TimeoutExpired):
            return CancelResult(False, "Failed to kill process")

    def reveal(self) -> RevealResult:
        """P8.11: Collect the final result after the subprocess exits.

        Reads remaining stdout and stderr, parses the final
        pipeline_completed or pipeline_failed event.
        """
        if self._process is None:
            return RevealResult("failed", "", "", -1, ["No process started"])

        exit_code = self._process.wait()
        stdout = self._process.stdout.read() if self._process.stdout else ""
        stderr = self._process.stderr.read() if self._process.stderr else ""

        package_path = ""
        content_hash = ""
        status = "failed"
        errors: list[str] = []

        # Parse the last pipeline_* event from stdout
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = evt.get("type", "")
            if t == "pipeline_completed":
                status = "complete"
                package_path = evt.get("package_path", "")
                content_hash = evt.get("content_hash", "")
                break
            elif t == "pipeline_cancelled":
                status = "cancelled"
                break
            elif t == "pipeline_failed":
                status = "failed"
                errors = evt.get("errors", [])
                break

        if stderr.strip():
            errors.append(stderr.strip()[-500:])

        return RevealResult(status, package_path, content_hash, exit_code, errors)


# ── Bounded JSONL parser ─────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedEvent:
    """P8.11: One parsed JSONL event with validated envelope."""

    event_type: str
    sequence: int
    run_id: str
    raw: dict[str, Any]


@dataclass
class ParseResult:
    """P8.11: Result of parsing a JSONL stream."""

    events: list[ParsedEvent] = field(default_factory=list)
    malformed_count: int = 0
    truncated_count: int = 0
    unknown_types: list[str] = field(default_factory=list)


def parse_jsonl_line(line: str) -> ParsedEvent | None:
    """P8.11: Parse a single JSONL line into a ParsedEvent.

    Returns None for malformed lines, missing type, or oversized lines
    (truncation sentinel ``...}``).
    """
    line = line.strip()
    if not line:
        return None

    # Truncation sentinel (P8.10)
    if line.endswith("...}"):
        return None

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    event_type = data.get("type")
    if not event_type or not isinstance(event_type, str):
        return None

    return ParsedEvent(
        event_type=event_type,
        sequence=int(data.get("sequence", 0)),
        run_id=str(data.get("run_id", "")),
        raw=data,
    )


def parse_jsonl_stream(
    lines: list[str],
    *,
    known_types: frozenset[str] | None = None,
) -> ParseResult:
    """P8.11: Parse a list of JSONL lines into a ParseResult.

    Args:
        lines: Raw JSONL lines (may include trailing whitespace).
        known_types: If set, events with unknown types are counted but
            not included in ``events`` (forward compatibility).

    Returns:
        ParseResult with parsed events, malformed count, truncated count,
        and unknown type list.
    """
    result = ParseResult()
    known = known_types or _PROGRESS_EVENT_TYPES

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue

        if stripped.endswith("...}"):
            result.truncated_count += 1
            continue

        parsed = parse_jsonl_line(stripped)
        if parsed is None:
            result.malformed_count += 1
            continue

        if parsed.event_type not in known:
            result.unknown_types.append(parsed.event_type)
            continue

        result.events.append(parsed)

    return result


# ── Progress reducer ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class ProgressSnapshot:
    """P8.11: Current pipeline progress derived from JSONL events."""

    current_step: str
    step_index: int
    total_steps: int
    step_completed: int
    step_total: int
    message: str
    artifacts_reused: int
    artifacts_regenerated: int
    is_complete: bool
    is_failed: bool
    is_cancelled: bool
    error_codes: list[str]

    @property
    def fraction(self) -> float:
        """Progress as 0.0..1.0 across all steps."""
        if self.total_steps == 0:
            return 0.0
        step_progress = (
            self.step_completed / max(self.step_total, 1) if self.step_completed > 0 else 0.0
        )
        return (self.step_index + step_progress) / self.total_steps


@dataclass
class JsonlProgress:
    """P8.11: Reducer that accumulates progress from a JSONL event stream.

    Usage::

        progress = JsonlProgress(step_order=["world_builder", "art_director", ...])
        for line in forge_process.read_events():
            event = parse_jsonl_line(line)
            if event:
                snapshot = progress.feed(event)
                # update GUI progress bar with snapshot
    """

    step_order: list[str]
    _current_step: str = ""
    _step_index: int = 0
    _step_completed: int = 0
    _step_total: int = 0
    _message: str = ""
    _artifacts_reused: int = 0
    _artifacts_regenerated: int = 0
    _is_complete: bool = False
    _is_failed: bool = False
    _is_cancelled: bool = False
    _error_codes: list[str] = field(default_factory=list)

    def feed(self, event: ParsedEvent) -> ProgressSnapshot:
        """Feed one parsed event into the reducer, return updated snapshot."""
        t = event.event_type

        if t == "step_started":
            sid = event.raw.get("step_id", "")
            self._current_step = sid
            try:
                self._step_index = self.step_order.index(sid)
            except ValueError:
                self._step_index = 0
            self._step_completed = 0
            self._step_total = 0

        elif t == "step_progress":
            self._step_completed = int(event.raw.get("completed", 0))
            self._step_total = int(event.raw.get("total", 0))
            self._message = str(event.raw.get("message", ""))

        elif t == "artifact_reused":
            self._artifacts_reused += 1

        elif t == "artifact_regenerated":
            self._artifacts_regenerated += 1

        elif t == "pipeline_completed":
            self._is_complete = True

        elif t == "pipeline_failed":
            self._is_failed = True
            self._error_codes = list(event.raw.get("errors", []))

        elif t == "pipeline_cancelled":
            self._is_cancelled = True

        return self.snapshot

    @property
    def snapshot(self) -> ProgressSnapshot:
        return ProgressSnapshot(
            current_step=self._current_step,
            step_index=self._step_index,
            total_steps=len(self.step_order),
            step_completed=self._step_completed,
            step_total=self._step_total,
            message=self._message,
            artifacts_reused=self._artifacts_reused,
            artifacts_regenerated=self._artifacts_regenerated,
            is_complete=self._is_complete,
            is_failed=self._is_failed,
            is_cancelled=self._is_cancelled,
            error_codes=list(self._error_codes),
        )


def reduce_progress(
    events: list[ParsedEvent],
    step_order: list[str],
) -> ProgressSnapshot:
    """P8.11: Reduce a list of parsed events into a single ProgressSnapshot.

    Convenience for batch processing already-parsed event lists.
    """
    progress = JsonlProgress(step_order)
    for event in events:
        progress.feed(event)
    return progress.snapshot
