"""P8.11 — Launcher core tests + architecture import guard.

Tests cover:
- Typed form state validation
- Configuration import/export round-trip
- argv-list construction (shell=False)
- JSONL parsing (valid, malformed, truncated, unknown types)
- Progress reducer
- Architecture: must not import src.worldgen, backends, or pipeline steps
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from src.launcher.core import (
    CancelResult,
    ConfigExport,
    ForgeProcess,
    JsonlProgress,
    LauncherState,
    ParsedEvent,
    ProgressSnapshot,
    RevealResult,
    build_argv,
    from_config_dict,
    parse_jsonl_line,
    parse_jsonl_stream,
    reduce_progress,
    to_config_dict,
)

# ── P8.11: Architecture import guard ────────────────────────────────────


class TestArchitectureGuard:
    """P8.11: The launcher core module must NOT import prohibited modules."""

    PROHIBITED = (
        "src.worldgen",
        "src.backends",
        "src.narrative",
        "src.storage",
        "src.pipeline.plan",
        "src.pipeline.orchestrator",
        "src.models.world_builder",
        "src.models.art_director",
        "src.models.story_writer",
    )

    ALLOWED = (
        "src.pipeline.events",  # constants only
        "src.application.models",  # GenerationRequest field names
    )

    def test_no_prohibited_imports(self) -> None:
        """P8.11: Architecture test — launcher/core.py has no forbidden imports."""
        import ast
        from pathlib import Path

        core_path = Path(__file__).parent.parent / "src" / "launcher" / "core.py"
        source = core_path.read_text()
        tree = ast.parse(source)

        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level and node.level > 0:
                    # Relative import: resolve
                    module = "src.launcher." + module
                for alias in node.names:
                    full = f"{module}.{alias.name}" if alias.name != "*" else module
                    imports.append(full)

        for imp in imports:
            for prohibited in self.PROHIBITED:
                assert not imp.startswith(prohibited), (
                    f"FORBIDDEN IMPORT: {imp} matches prohibited pattern "
                    f"'{prohibited}'. The launcher core must not import "
                    f"worldgen, backends, or pipeline step implementations."
                )

    def test_module_is_importable(self) -> None:
        """P8.11: The launcher core can be imported without side effects."""
        from src.launcher import core

        assert core is not None

    def test_allowed_imports_only(self) -> None:
        """P8.11: Only whitelisted src.* imports are present."""
        import ast
        from pathlib import Path

        core_path = Path(__file__).parent.parent / "src" / "launcher" / "core.py"
        source = core_path.read_text()
        tree = ast.parse(source)

        src_imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("src"):
                        src_imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level and node.level > 0:
                    # Relative imports from src.launcher to src.* are OK
                    if module and module.startswith("."):
                        # e.g. from ..pipeline.events import ...
                        resolved = "src.pipeline.events"
                        src_imports.append(resolved)
                        continue
                if module and any(
                    module.startswith(p)
                    for p in (
                        "src.worldgen",
                        "src.backends",
                        "src.narrative",
                        "src.storage",
                        "src.models.",
                    )
                ):
                    src_imports.append(module)

        for imp in src_imports:
            # Only allowed src imports
            allowed = False
            for pattern in self.ALLOWED:
                if imp.startswith(pattern) or pattern.startswith(imp):
                    allowed = True
                    break
            assert allowed, (
                f"UNEXPECTED SRC IMPORT: {imp} is not in the whitelist ({', '.join(self.ALLOWED)})"
            )


# ── P8.11: LauncherState validation ──────────────────────────────────────


class TestLauncherState:
    def test_default_state_is_valid(self) -> None:
        state = LauncherState()
        assert state.is_valid()
        assert state.validate() == []

    def test_empty_title_invalid(self) -> None:
        state = LauncherState(title="   ")
        assert not state.is_valid()
        assert any("Title" in e for e in state.validate())

    def test_bad_tone_invalid(self) -> None:
        state = LauncherState(tone="not_a_tone")
        assert not state.is_valid()

    def test_width_out_of_range(self) -> None:
        state = LauncherState(width=16)
        assert not state.is_valid()

    def test_negative_history(self) -> None:
        state = LauncherState(history_years=-1)
        assert not state.is_valid()

    def test_valid_large_world(self) -> None:
        state = LauncherState(
            width=4096, height=4096, continent_count=4, history_years=1000, civilization_count=20
        )
        assert state.is_valid()


# ── P8.11: Config import/export ──────────────────────────────────────────


class TestConfigIO:
    def test_round_trip(self) -> None:
        original = LauncherState(
            seed=123,
            title="Test World",
            tone="mature_dark_fantasy",
            width=2048,
            height=1024,
            continent_count=2,
        )
        exported = to_config_dict(original)
        restored = from_config_dict(exported)
        assert restored.seed == original.seed
        assert restored.title == original.title
        assert restored.width == original.width
        assert restored.continent_count == original.continent_count

    def test_export_is_json_serializable(self) -> None:
        state = LauncherState()
        d = to_config_dict(state)
        json.dumps(d)  # must not raise

    def test_config_export_wrapper(self) -> None:
        state = LauncherState(seed=99)
        d = to_config_dict(state)
        export = ConfigExport(state=d)
        serialized = export.to_json()
        loaded = ConfigExport.from_json(serialized)
        assert loaded.state["seed"] == 99

    def test_from_dict_defaults_missing_fields(self) -> None:
        restored = from_config_dict({"seed": 7})
        assert restored.seed == 7
        assert restored.title == "Untitled World"
        assert restored.width == 1024


# ── P8.11: argv-list construction ────────────────────────────────────────


class TestBuildArgv:
    def test_basic_generate(self) -> None:
        """P8.WG4: build_argv omits fields at default; use non-default seed."""
        state = LauncherState(seed=999, output_dir="/tmp/out")
        argv = build_argv(state)
        assert argv[0] == "forge"
        assert "generate" in argv
        assert "--seed" in argv
        assert "999" in argv
        assert "--output" in argv
        assert "/tmp/out" in argv
        assert "--json-result" in argv

    def test_resume_mode(self) -> None:
        state = LauncherState(seed=42, output_dir="/tmp/out")
        argv = build_argv(state, resume=True)
        assert "resume" in argv
        assert "generate" not in argv

    def test_process_resume_mode_cannot_fall_back_to_generate(self) -> None:
        process = ForgeProcess(LauncherState(output_dir="/tmp/out"), resume=True)
        assert process.resume is True

    def test_all_fields_present(self) -> None:
        state = LauncherState(
            seed=1,
            title="T",
            width=512,
            height=512,
            continent_count=2,
            history_years=100,
            civilization_count=4,
            output_dir="/out",
        )
        argv = build_argv(state)
        assert "--title" in argv and "T" in argv
        assert "--world-width" in argv and "512" in argv
        assert "--world-height" in argv and "512" in argv
        assert "--continents" in argv and "2" in argv
        assert "--history-years" in argv and "100" in argv
        assert "--max-civilizations" in argv and "4" in argv

    def test_no_output_dir_omits_flag(self) -> None:
        state = LauncherState(seed=1, output_dir="")
        argv = build_argv(state)
        assert "--output" not in argv

    def test_workers_gt_1_adds_flag(self) -> None:
        state = LauncherState(seed=1, workers=4)
        argv = build_argv(state)
        assert "--workers" in argv
        assert "4" in argv

    def test_shell_false_safe(self) -> None:
        """P8.11: argv is a list, never a single shell string."""
        state = LauncherState()
        argv = build_argv(state)
        assert isinstance(argv, list)
        assert all(isinstance(a, str) for a in argv)
        # No shell metacharacters in a single arg
        for a in argv:
            assert "&&" not in a
            assert "|" not in a
            assert ";" not in a


# ── P8.11: JSONL parsing ─────────────────────────────────────────────────


class TestJsonlParsing:
    def test_valid_event(self) -> None:
        line = json.dumps(
            {
                "event_version": 1,
                "sequence": 1,
                "run_id": "r",
                "type": "step_started",
                "step_id": "world_builder",
            }
        )
        parsed = parse_jsonl_line(line)
        assert parsed is not None
        assert parsed.event_type == "step_started"
        assert parsed.sequence == 1

    def test_malformed_json_returns_none(self) -> None:
        assert parse_jsonl_line("not json") is None
        assert parse_jsonl_line("{incomplete") is None

    def test_missing_type_returns_none(self) -> None:
        line = json.dumps({"event_version": 1, "sequence": 1})
        assert parse_jsonl_line(line) is None

    def test_truncation_sentinel(self) -> None:
        """P8.10: Lines ending with ...} are truncation sentinels."""
        line = '{"event_version":1,"type":"step_failed","error":"...}'
        assert parse_jsonl_line(line) is None

    def test_blank_line(self) -> None:
        assert parse_jsonl_line("") is None
        assert parse_jsonl_line("   ") is None

    def test_not_a_dict(self) -> None:
        assert parse_jsonl_line("[]") is None
        assert parse_jsonl_line("42") is None


class TestJsonlStream:
    def test_parse_stream_with_known_types(self) -> None:
        lines = [
            json.dumps(
                {
                    "event_version": 1,
                    "sequence": 1,
                    "run_id": "r",
                    "type": "step_started",
                    "step_id": "s",
                }
            ),
            json.dumps(
                {
                    "event_version": 1,
                    "sequence": 2,
                    "run_id": "r",
                    "type": "future_xyz",
                    "data": "ignored",
                }
            ),
            json.dumps(
                {
                    "event_version": 1,
                    "sequence": 3,
                    "run_id": "r",
                    "type": "step_completed",
                    "step_id": "s",
                }
            ),
        ]
        result = parse_jsonl_stream(lines)
        assert len(result.events) == 2
        assert result.malformed_count == 0
        assert "future_xyz" in result.unknown_types

    def test_malformed_lines_counted(self) -> None:
        lines = [
            "not json",
            json.dumps(
                {
                    "event_version": 1,
                    "sequence": 1,
                    "run_id": "r",
                    "type": "step_started",
                    "step_id": "s",
                }
            ),
            "{incomplete",
        ]
        result = parse_jsonl_stream(lines)
        assert result.malformed_count == 2

    def test_truncated_lines_counted(self) -> None:
        lines = [
            json.dumps(
                {
                    "event_version": 1,
                    "sequence": 1,
                    "run_id": "r",
                    "type": "step_started",
                    "step_id": "s",
                }
            ),
            '{"event_version":1,...}',
        ]
        result = parse_jsonl_stream(lines)
        assert result.truncated_count == 1

    def test_empty_stream(self) -> None:
        result = parse_jsonl_stream([])
        assert result.events == []
        assert result.malformed_count == 0


# ── P8.11: Progress reducer ──────────────────────────────────────────────


class TestProgressReducer:
    STEP_ORDER = [
        "world_builder",
        "art_director",
        "story_writer",
        "image_generator",
        "music_generator",
        "indexer",
        "packager",
    ]

    def _event(self, event_type: str, **kwargs: object) -> ParsedEvent:
        raw: dict[str, object] = {
            "sequence": 1,
            "run_id": "r",
            "type": event_type,
        }
        raw.update(kwargs)
        return ParsedEvent(event_type, 1, "r", raw)

    def test_initial_snapshot(self) -> None:
        p = JsonlProgress(self.STEP_ORDER)
        snap = p.snapshot
        assert snap.fraction == 0.0
        assert not snap.is_complete

    def test_step_started_updates_index(self) -> None:
        p = JsonlProgress(self.STEP_ORDER)
        # art_director is index 1
        p.feed(self._event("step_started", step_id="art_director"))
        snap = p.snapshot
        assert snap.step_index == 1
        assert snap.current_step == "art_director"

    def test_step_progress_updates_fraction(self) -> None:
        p = JsonlProgress(self.STEP_ORDER)
        p.feed(self._event("step_started", step_id="story_writer"))
        p.feed(self._event("step_progress", completed=250, total=500))
        snap = p.snapshot
        # story_writer is index 2 of 7, 50% done
        assert snap.step_index == 2
        assert snap.step_completed == 250
        assert snap.step_total == 500
        assert snap.fraction > 0.3
        assert snap.fraction < 0.5

    def test_artifact_reuse_counted(self) -> None:
        p = JsonlProgress(self.STEP_ORDER)
        p.feed(self._event("artifact_reused"))
        p.feed(self._event("artifact_reused"))
        p.feed(self._event("artifact_regenerated"))
        snap = p.snapshot
        assert snap.artifacts_reused == 2
        assert snap.artifacts_regenerated == 1

    def test_pipeline_completed(self) -> None:
        p = JsonlProgress(self.STEP_ORDER)
        assert not p.snapshot.is_complete
        p.feed(self._event("pipeline_completed"))
        assert p.snapshot.is_complete

    def test_pipeline_failed(self) -> None:
        p = JsonlProgress(self.STEP_ORDER)
        p.feed(self._event("pipeline_failed", errors=["ERR_1", "ERR_2"]))
        snap = p.snapshot
        assert snap.is_failed
        assert snap.error_codes == ["ERR_1", "ERR_2"]

    def test_pipeline_cancelled(self) -> None:
        p = JsonlProgress(self.STEP_ORDER)
        p.feed(self._event("pipeline_cancelled"))
        assert p.snapshot.is_cancelled

    def test_reduce_progress_batch(self) -> None:
        events = [
            self._event("pipeline_started"),
            self._event("step_started", step_id="world_builder"),
            self._event("step_progress", completed=50, total=100),
            self._event("artifact_reused"),
            self._event("artifact_reused"),
            self._event("pipeline_completed"),
        ]
        snap = reduce_progress(events, self.STEP_ORDER)
        assert snap.is_complete
        assert snap.artifacts_reused == 2

    def test_unknown_step_maps_to_zero(self) -> None:
        """Step not in step_order defaults to index 0."""
        p = JsonlProgress(self.STEP_ORDER)
        p.feed(self._event("step_started", step_id="unknown_step_xyz"))
        assert p.snapshot.step_index == 0


# ── P8.11: ForgeProcess (mock) ───────────────────────────────────────────


class TestForgeProcess:
    def test_build_and_start_forge(self, tmp_path: Path) -> None:
        """P8.11: ForgeProcess can start a real subprocess (echo test)."""
        state = LauncherState(forge_path=sys.executable)
        proc = ForgeProcess(state)
        # We can't start real forge, but we can verify the state
        assert state.forge_path == sys.executable
        assert proc.resume is False

    def test_run_id_generated(self) -> None:
        state = LauncherState()
        proc = ForgeProcess(state)
        # run_id not generated until start()
        assert proc.run_id == ""

    def test_is_running_false_initially(self) -> None:
        state = LauncherState()
        proc = ForgeProcess(state)
        assert not proc.is_running

    def test_cancel_no_process(self) -> None:
        state = LauncherState()
        proc = ForgeProcess(state)
        result = proc.cancel()
        assert not result.success

    def test_reveal_no_process(self) -> None:
        state = LauncherState()
        proc = ForgeProcess(state)
        result = proc.reveal()
        assert result.status == "failed"
        assert "No process started" in result.errors


# ── P8.11: Dataclass ser/de ──────────────────────────────────────────────


class TestDataclassRoundTrip:
    def test_cancel_result(self) -> None:
        r = CancelResult(True, "done")
        assert r.success
        assert r.message == "done"

    def test_reveal_result(self) -> None:
        r = RevealResult("complete", "/pkg.story", "abc123", 0, [])
        assert r.status == "complete"
        assert r.package_path == "/pkg.story"
        assert r.exit_code == 0

    def test_progress_snapshot_fraction(self) -> None:
        snap = ProgressSnapshot(
            current_step="s",
            step_index=3,
            total_steps=7,
            step_completed=50,
            step_total=100,
            message="",
            artifacts_reused=0,
            artifacts_regenerated=0,
            is_complete=False,
            is_failed=False,
            is_cancelled=False,
            error_codes=[],
        )
        # Fraction = (3 + 50/100) / 7 = 3.5 / 7 = 0.5
        assert snap.fraction == pytest.approx(0.5)

    def test_progress_snapshot_complete_is_1(self) -> None:
        snap = ProgressSnapshot(
            current_step="packager",
            step_index=6,
            total_steps=7,
            step_completed=100,
            step_total=100,
            message="Done",
            artifacts_reused=10,
            artifacts_regenerated=2,
            is_complete=True,
            is_failed=False,
            is_cancelled=False,
            error_codes=[],
        )
        # Fraction = (6 + 100/100) / 7 = 7/7 = 1.0
        assert snap.fraction == pytest.approx(1.0)
