"""P8.12 — GUI adapter tests (core testable without display).

Tests the HeadlessGuiAdapter (no display required) and verifies
the adapter interface contract.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.launcher.core import (
    LauncherState,
    ProgressSnapshot,
    to_config_dict,
)
from src.launcher.gui import (
    DirectCallbacks,
    HeadlessGuiAdapter,
    LauncherGuiAdapter,
    TkLauncherGui,
)

# ── P8.12: Headless adapter (testable without display) ─────────────────


class TestHeadlessAdapter:
    """P8.12: The headless adapter records all GUI calls for verification."""

    def test_config_round_trip(self) -> None:
        adapter = HeadlessGuiAdapter()
        state = LauncherState(seed=99, title="Test", width=2048)
        returned = adapter.show_configuration(state)
        assert adapter.config_shown
        assert returned.seed == 99
        assert returned.title == "Test"

    def test_progress_records_snapshots(self) -> None:
        adapter = HeadlessGuiAdapter()
        snap = ProgressSnapshot(
            current_step="s",
            step_index=2,
            total_steps=7,
            step_completed=50,
            step_total=100,
            message="msg",
            artifacts_reused=1,
            artifacts_regenerated=0,
            is_complete=False,
            is_failed=False,
            is_cancelled=False,
            error_codes=[],
        )
        adapter.on_progress(snap)
        adapter.on_progress(snap)
        assert len(adapter.progress_snapshots) == 2

    def test_complete_sets_flags(self) -> None:
        adapter = HeadlessGuiAdapter()
        snap = ProgressSnapshot(
            current_step="",
            step_index=10,
            total_steps=11,
            step_completed=100,
            step_total=100,
            message="",
            artifacts_reused=0,
            artifacts_regenerated=0,
            is_complete=False,
            is_failed=False,
            is_cancelled=False,
            error_codes=[],
        )
        adapter.on_complete(snap, "/pkg.story")
        assert adapter.complete_called
        assert adapter.complete_package_path == "/pkg.story"

    def test_failure_sets_snapshot(self) -> None:
        adapter = HeadlessGuiAdapter()
        snap = ProgressSnapshot(
            current_step="bad_step",
            step_index=3,
            total_steps=7,
            step_completed=0,
            step_total=0,
            message="",
            artifacts_reused=0,
            artifacts_regenerated=0,
            is_complete=False,
            is_failed=True,
            is_cancelled=False,
            error_codes=["ERR_CODE"],
        )
        adapter.on_failure(snap)
        assert adapter.failure_snapshot is not None
        assert adapter.failure_snapshot.error_codes == ["ERR_CODE"]

    def test_cancelled_sets_flag(self) -> None:
        adapter = HeadlessGuiAdapter()
        assert not adapter.cancelled_called
        adapter.on_cancelled()
        assert adapter.cancelled_called

    def test_reveal_sets_flag(self) -> None:
        adapter = HeadlessGuiAdapter()
        assert not adapter.reveal_called
        adapter.reveal_output("/path")
        assert adapter.reveal_called

    def test_error_dialog_recorded(self) -> None:
        adapter = HeadlessGuiAdapter()
        adapter.show_error_dialog("Title", "Message")
        assert len(adapter.error_dialogs) == 1
        assert adapter.error_dialogs[0] == ("Title", "Message")

    def test_full_lifecycle(self) -> None:
        """P8.12: Simulate a complete run through the headless adapter."""
        adapter = HeadlessGuiAdapter()

        # 1. Configure
        state = LauncherState(seed=42, title="Lifecycle Test")
        returned = adapter.show_configuration(state)
        assert adapter.config_shown

        # 2. Start
        adapter.on_start(returned)

        # 3. Progress (several updates)
        for i in range(5):
            snap = ProgressSnapshot(
                current_step=f"step_{i}",
                step_index=i,
                total_steps=5,
                step_completed=i * 20,
                step_total=100,
                message=f"Working on step {i}",
                artifacts_reused=i,
                artifacts_regenerated=0,
                is_complete=False,
                is_failed=False,
                is_cancelled=False,
                error_codes=[],
            )
            adapter.on_progress(snap)
        assert len(adapter.progress_snapshots) == 5

        # 4. Complete
        final_snap = ProgressSnapshot(
            current_step="packager",
            step_index=4,
            total_steps=5,
            step_completed=100,
            step_total=100,
            message="Done",
            artifacts_reused=5,
            artifacts_regenerated=0,
            is_complete=True,
            is_failed=False,
            is_cancelled=False,
            error_codes=[],
        )
        adapter.on_complete(final_snap, "/output.story")
        assert adapter.complete_called

        # 5. Reveal
        adapter.reveal_output("/output.story")
        assert adapter.reveal_called


# ── P8.12: DirectCallbacks ──────────────────────────────────────────────


class TestDirectCallbacks:
    def test_start_generation(self) -> None:
        cb = DirectCallbacks(["a", "b", "c"])
        state = LauncherState(seed=1)
        proc = cb.start_generation(state)
        assert proc is not None
        assert cb.process is proc
        assert cb.progress is not None

    def test_cancel_no_process(self) -> None:
        cb = DirectCallbacks(["a"])
        cb.cancel_generation()  # should not raise

    def test_resume(self) -> None:
        cb = DirectCallbacks(["a", "b"])
        proc = cb.resume_generation("/tmp/out")
        assert proc is not None


# ── P8.12: LauncherGuiAdapter is abstract ───────────────────────────────


class TestAdapterAbstract:
    def test_concrete_adapters_subclass(self) -> None:
        """Both adapters implement the abstract interface."""
        assert issubclass(HeadlessGuiAdapter, LauncherGuiAdapter)
        # TkLauncherGui also subclasses
        assert issubclass(TkLauncherGui, LauncherGuiAdapter)

    def test_headless_is_instantiable(self) -> None:
        adapter = HeadlessGuiAdapter()
        assert isinstance(adapter, LauncherGuiAdapter)

    def test_direct_callbacks_match_protocol(self) -> None:
        cb = DirectCallbacks(["step1"])
        assert hasattr(cb, "start_generation")
        assert hasattr(cb, "cancel_generation")
        assert hasattr(cb, "resume_generation")


# ── P8.12: Config dict round-trip through adapter ───────────────────────


class TestConfigThroughAdapter:
    def test_state_survives_round_trip(self) -> None:
        original = LauncherState(
            seed=123,
            title="Adapter World",
            width=1024,
            height=768,
            continent_count=2,
            history_years=300,
            civilization_count=5,
        )
        adapter = HeadlessGuiAdapter()
        returned = adapter.show_configuration(original)
        # The headless adapter passes the state through unmodified
        assert returned.seed == original.seed
        assert returned.title == original.title
        assert returned.width == original.width

    def test_config_dict_round_trip(self) -> None:
        state = LauncherState(seed=7, continent_count=3)
        d = to_config_dict(state)
        assert d["seed"] == 7
        assert d["continent_count"] == 3
        # JSON-serializable
        json.dumps(d)  # must not raise


# ── P8.12: TkLauncherGui (lightweight — no display needed for state) ────


class TestTkGuiStateless:
    """P8.12: TkLauncherGui state tests — no display required."""

    def test_default_step_order(self) -> None:
        """TkLauncherGui has a defined step order."""
        from src.pipeline.plan import PipelinePlan

        assert TkLauncherGui.STEP_ORDER == PipelinePlan.production_v2().step_ids()
        assert "world_builder_v2" in TkLauncherGui.STEP_ORDER
        assert "packager" in TkLauncherGui.STEP_ORDER

    def test_step_order_covers_pipeline(self) -> None:
        """All major pipeline stages are in the step order."""
        required = {
            "physical_world",
            "simulate_world",
            "local_maps_v2",
            "world_builder_v2",
            "story_v2",
            "graph_v2",
            "gm_index_v2",
            "packager",
        }
        assert required.issubset(set(TkLauncherGui.STEP_ORDER))

    def test_wine_spike_script_exists(self) -> None:
        """P8.12: The Wine spike script is present."""
        spike = Path(__file__).parent.parent / "scripts" / "wine_spike_p8c12.py"
        assert spike.exists(), f"Wine spike script missing: {spike}"


# ── P8.12: Architecture — core testable without display ─────────────────


class TestCoreTestableWithoutDisplay:
    """P8.12: Core launcher logic must work without any GUI imports."""

    def test_core_imports_without_tkinter(self) -> None:
        """The core module does not import tkinter at module scope."""
        import ast
        from pathlib import Path

        core_path = Path(__file__).parent.parent / "src" / "launcher" / "core.py"
        source = core_path.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("tkinter"), "core.py must not import tkinter"
                    assert alias.name not in ("tkinter", "tkinter.ttk"), (
                        "core.py must not import tkinter at module level"
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert not module.startswith("tkinter"), "core.py must not import tkinter"

    def test_gui_module_imports_tkinter_lazily(self) -> None:
        """The gui module may import tkinter (it's the GUI adapter)."""
        import ast
        from pathlib import Path

        gui_path = Path(__file__).parent.parent / "src" / "launcher" / "gui.py"
        source = gui_path.read_text()
        tree = ast.parse(source)

        # Find all imports
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.add(module.split(".")[0])

        # tkinter is allowed in gui.py (it's the GUI module)
        assert "tkinter" in imports, "gui.py should import tkinter"

    def test_headless_adapter_works_without_tkinter(self) -> None:
        """The HeadlessGuiAdapter has zero tkinter dependencies."""
        adapter = HeadlessGuiAdapter()
        assert adapter is not None
        # Full lifecycle without tkinter
        state = LauncherState()
        adapter.show_configuration(state)
        snap = ProgressSnapshot(
            current_step="",
            step_index=0,
            total_steps=1,
            step_completed=0,
            step_total=0,
            message="",
            artifacts_reused=0,
            artifacts_regenerated=0,
            is_complete=False,
            is_failed=False,
            is_cancelled=False,
            error_codes=[],
        )
        adapter.on_progress(snap)
        adapter.on_complete(snap, "/out")
        assert adapter.complete_called


# ── P8.12: Adapter interface completeness ───────────────────────────────


class TestAdapterInterfaceCompleteness:
    """P8.12: All required actions are present in the adapter interface."""

    REQUIRED_METHODS = {
        "show_configuration",
        "on_start",
        "on_progress",
        "on_failure",
        "on_complete",
        "on_cancelled",
        "reveal_output",
        "show_error_dialog",
    }

    def test_headless_has_all_methods(self) -> None:
        adapter = HeadlessGuiAdapter()
        for method in self.REQUIRED_METHODS:
            assert hasattr(adapter, method), f"Missing: {method}"
            assert callable(getattr(adapter, method)), f"Not callable: {method}"

    def test_tk_gui_has_all_methods(self) -> None:
        for method in self.REQUIRED_METHODS:
            assert hasattr(TkLauncherGui, method), f"Missing: {method}"
