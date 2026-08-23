"""P8.12 — GUI adapter layer for the launcher core.

Widgets live behind an adapter so the core logic is testable without a
display.  The ``TkLauncherGui`` uses tkinter — the smallest toolkit that
ships with Python and runs on native Windows and Wine.

Actions exposed: configuration, start, progress, cancel, resume,
failure detail, and reveal-output.
"""

from __future__ import annotations

import threading
import tkinter as tk
from abc import ABC, abstractmethod
from tkinter import messagebox, ttk
from typing import Any, Protocol

from ..pipeline.plan import PipelinePlan
from .core import (
    ForgeProcess,
    JsonlProgress,
    LauncherState,
    ProgressSnapshot,
    build_argv,
    parse_jsonl_line,
)
from .world_controls import (
    FieldMeta,
    advanced_fields,
    all_fields,
    basic_fields,
    get_field,
)

# ── Abstract adapter ────────────────────────────────────────────────────


class LauncherGuiAdapter(ABC):
    """P8.12: Abstract GUI adapter — the core is testable without a display.

    Subclasses wire these callbacks to a concrete toolkit (tkinter, Qt, etc.).
    """

    @abstractmethod
    def show_configuration(self, state: LauncherState) -> LauncherState:
        """Show the configuration panel and return the (possibly modified) state.

        The adapter may mutate the state in-place and return it, or return
        a new state.  The caller uses the return value.
        """
        ...

    @abstractmethod
    def on_start(self, state: LauncherState) -> None:
        """Called when the user clicks Start.

        The adapter should begin polling the ForgeProcess for events and
        updating the progress display.
        """
        ...

    @abstractmethod
    def on_progress(self, snapshot: ProgressSnapshot) -> None:
        """Update the progress display with the latest snapshot."""
        ...

    @abstractmethod
    def on_failure(self, snapshot: ProgressSnapshot) -> None:
        """Show failure detail: error codes, last step, message."""
        ...

    @abstractmethod
    def on_complete(self, snapshot: ProgressSnapshot, package_path: str) -> None:
        """Show completion: package path, content hash."""
        ...

    @abstractmethod
    def on_cancelled(self) -> None:
        """Show that the run was cancelled."""
        ...

    @abstractmethod
    def reveal_output(self, package_path: str) -> None:
        """Reveal the output package in the OS file manager."""
        ...

    @abstractmethod
    def show_error_dialog(self, title: str, message: str) -> None:
        """Show an error dialog to the user."""
        ...


# ── Callback protocol (testable without display) ────────────────────────


class GuiCallbacks(Protocol):
    """P8.12: Callbacks from the GUI to the launcher core.

    Implementations can be in-process (direct) or subprocess-based.
    """

    def start_generation(self, state: LauncherState) -> ForgeProcess: ...
    def cancel_generation(self) -> None: ...
    def resume_generation(self, output_dir: str) -> ForgeProcess: ...


class DirectCallbacks:
    """P8.12: In-process callbacks — for testing without a real subprocess."""

    def __init__(self, step_order: list[str]) -> None:
        self.step_order = step_order
        self.process: ForgeProcess | None = None
        self.progress: JsonlProgress | None = None
        self._on_progress: Any = None
        self._on_complete: Any = None
        self._on_failure: Any = None
        self._on_cancelled: Any = None

    def start_generation(self, state: LauncherState) -> ForgeProcess:
        self.process = ForgeProcess(state)
        self.progress = JsonlProgress(self.step_order)
        return self.process

    def cancel_generation(self) -> None:
        if self.process:
            self.process.cancel()

    def resume_generation(self, output_dir: str) -> ForgeProcess:
        state = LauncherState(output_dir=output_dir)
        self.process = ForgeProcess(state, resume=True)
        self.progress = JsonlProgress(self.step_order)
        return self.process


# ── Tkinter implementation ──────────────────────────────────────────────


class TkLauncherGui(LauncherGuiAdapter):
    """P8.12: Minimal tkinter launcher GUI.

    Single window with configuration panel, start/cancel buttons,
    progress bar, status label, and output area.  Works on Windows,
    macOS, Linux, and Wine with no additional dependencies.
    """

    # The product plan is the single source of truth for progress ordering.
    STEP_ORDER = PipelinePlan.production_v2().step_ids()

    def __init__(self, state: LauncherState | None = None) -> None:
        self._state = state or LauncherState()
        self._process: ForgeProcess | None = None
        self._progress: JsonlProgress = JsonlProgress(self.STEP_ORDER)
        self._polling = False
        self._callbacks = DirectCallbacks(self.STEP_ORDER)

        # ── Build the window ─────────────────────────────────────────
        self._root = tk.Tk()
        self._root.title("StoryTeller Forge")
        self._root.geometry("680x620")
        self._root.resizable(True, True)

        # P8.WG4: Preset selector at the top
        preset_frame = ttk.Frame(self._root)
        preset_frame.pack(fill=tk.X, padx=8, pady=4)
        ttk.Label(preset_frame, text="Preset:", width=8).pack(side=tk.LEFT)
        self._preset_var = tk.StringVar(value=self._state.preset_name or "(custom)")
        preset_combo = ttk.Combobox(
            preset_frame,
            textvariable=self._preset_var,
            values=["(custom)", "tiny", "conformance", "default"],
            state="readonly",
            width=14,
        )
        preset_combo.pack(side=tk.LEFT, padx=4)
        preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        # ── Configuration frame (basic fields) ───────────────────────
        config_frame = ttk.LabelFrame(self._root, text="Configuration", padding=8)
        config_frame.pack(fill=tk.X, padx=8, pady=4)

        # P8.WG4: Build widgets from world_controls metadata
        self._config_widgets: dict[str, tk.StringVar] = {}
        for field_meta in basic_fields():
            self._build_config_row(config_frame, field_meta, 99)

        # Output dir
        row_out = ttk.Frame(config_frame)
        row_out.pack(fill=tk.X, pady=2)
        ttk.Label(row_out, text="Output:", width=19).pack(side=tk.LEFT)
        self._output_var = tk.StringVar(value=self._state.output_dir or "tmp/output")
        ttk.Entry(row_out, textvariable=self._output_var, width=40).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(row_out, text="Browse...", command=self._browse_output).pack(
            side=tk.LEFT, padx=4
        )

        # ── P8.WG4: Advanced fields (collapsible) ────────────────────
        self._advanced_frame = ttk.LabelFrame(self._root, text="Advanced", padding=8)
        self._advanced_visible = False
        self._advanced_widgets: dict[str, tk.StringVar] = {}

        toggle_btn = ttk.Button(config_frame, text="Show Advanced ▸", command=self._toggle_advanced)
        toggle_btn.pack(anchor=tk.W, pady=2)
        self._advanced_toggle_btn = toggle_btn

        # Pre-build advanced widgets (hidden initially)
        for field_meta in advanced_fields():
            self._build_config_row(
                self._advanced_frame, field_meta, 99, widget_dict=self._advanced_widgets
            )

        # ── Control buttons ──────────────────────────────────────────
        btn_frame = ttk.Frame(self._root)
        btn_frame.pack(fill=tk.X, padx=8, pady=4)

        self._start_btn = ttk.Button(btn_frame, text="Start", command=self._on_start_clicked)
        self._start_btn.pack(side=tk.LEFT, padx=4)

        self._cancel_btn = ttk.Button(
            btn_frame, text="Cancel", command=self._on_cancel_clicked, state=tk.DISABLED
        )
        self._cancel_btn.pack(side=tk.LEFT, padx=4)

        self._resume_btn = ttk.Button(btn_frame, text="Resume", command=self._on_resume_clicked)
        self._resume_btn.pack(side=tk.LEFT, padx=4)

        # ── Progress bar ─────────────────────────────────────────────
        self._progress_var = tk.DoubleVar(value=0.0)
        self._progress_bar = ttk.Progressbar(
            self._root,
            variable=self._progress_var,
            maximum=1.0,
        )
        self._progress_bar.pack(fill=tk.X, padx=8, pady=4)

        # ── Status label ─────────────────────────────────────────────
        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(self._root, textvariable=self._status_var).pack(anchor=tk.W, padx=8)

        # ── Reuse summary label ──────────────────────────────────────
        self._reuse_var = tk.StringVar(value="")
        ttk.Label(self._root, textvariable=self._reuse_var, foreground="gray").pack(
            anchor=tk.W, padx=8
        )

        # ── Output text area ─────────────────────────────────────────
        output_frame = ttk.LabelFrame(self._root, text="Output", padding=4)
        output_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._output_text = tk.Text(output_frame, height=6, wrap=tk.WORD, state=tk.DISABLED)
        self._output_text.pack(fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(self._output_text, command=self._output_text.yview)
        self._output_text.configure(yscrollcommand=scrollbar.set)

        # ── Reveal button ────────────────────────────────────────────
        self._reveal_btn = ttk.Button(
            self._root,
            text="Reveal Output",
            command=self._on_reveal_clicked,
            state=tk.DISABLED,
        )
        self._reveal_btn.pack(pady=4)

        self._package_path: str = ""

        # Populate initial config values
        self._populate_config()

    # ── Config helpers ─────────────────────────────────────────────────

    def _build_config_row(
        self,
        parent: ttk.Frame | ttk.LabelFrame,
        meta: FieldMeta,
        row: int,
        *,
        widget_dict: dict[str, tk.StringVar] | None = None,
    ) -> None:
        """P8.WG4: Build a labelled entry row from FieldMeta."""
        field_meta = get_field(meta.name)
        f = ttk.Frame(parent)
        f.pack(fill=tk.X, pady=2)
        lbl = field_meta.label + ":"
        ttk.Label(f, text=lbl, width=19).pack(side=tk.LEFT)
        var = tk.StringVar(value=str(getattr(self._state, field_meta.name, field_meta.default)))
        ttk.Entry(f, textvariable=var, width=20).pack(side=tk.LEFT)
        (widget_dict if widget_dict is not None else self._config_widgets)[field_meta.name] = var

    def _read_config(self) -> LauncherState:
        """P8.WG4: Read widget values into LauncherState using world_controls coercion."""
        kwargs: dict[str, Any] = {
            "output_dir": self._output_var.get(),
            "preset_name": self._preset_var.get() if self._preset_var.get() != "(custom)" else "",
        }
        # Basic fields
        for field_meta in basic_fields():
            var = self._config_widgets.get(field_meta.name)
            if var is not None:
                try:
                    kwargs[field_meta.name] = field_meta.coerce(var.get())
                except (ValueError, tk.TclError):
                    kwargs[field_meta.name] = field_meta.default
        # Advanced fields (if widget exists)
        for field_meta in advanced_fields():
            var = self._advanced_widgets.get(field_meta.name)
            if var is not None:
                try:
                    kwargs[field_meta.name] = field_meta.coerce(var.get())
                except (ValueError, tk.TclError):
                    kwargs[field_meta.name] = field_meta.default
            else:
                kwargs[field_meta.name] = getattr(self._state, field_meta.name, field_meta.default)
        kwargs.setdefault("seed", self._state.seed)
        kwargs.setdefault("title", self._state.title)
        kwargs.setdefault("tone", self._state.tone)
        kwargs.setdefault("temperature", self._state.temperature)
        return LauncherState(**kwargs)

    def _populate_config(self) -> None:
        """P8.WG4: Set widget values from current state for all fields."""
        for field_meta in basic_fields():
            var = self._config_widgets.get(field_meta.name)
            if var is not None:
                var.set(str(getattr(self._state, field_meta.name, field_meta.default)))
        for field_meta in advanced_fields():
            var = self._advanced_widgets.get(field_meta.name)
            if var is not None:
                var.set(str(getattr(self._state, field_meta.name, field_meta.default)))
        self._output_var.set(self._state.output_dir or "tmp/output")
        self._preset_var.set(self._state.preset_name or "(custom)")

    def _toggle_advanced(self) -> None:
        """P8.WG4: Show/hide the advanced fields panel."""
        if self._advanced_visible:
            self._advanced_frame.pack_forget()
            self._advanced_toggle_btn.configure(text="Show Advanced ▸")
            self._advanced_visible = False
        else:
            # Find a widget to pack after (the config frame)
            after_widget = None
            for child_name, child in self._root.children.items():
                if "labelframe" in child_name.lower():
                    after_widget = child
                    break
            if after_widget is not None:
                self._advanced_frame.pack(fill=tk.X, padx=8, pady=4, after=after_widget)
            else:
                self._advanced_frame.pack(fill=tk.X, padx=8, pady=4)
            self._advanced_toggle_btn.configure(text="Hide Advanced ▾")
            self._advanced_visible = True
            # Populate advanced widgets from current state
            for field_meta in advanced_fields():
                var = self._advanced_widgets.get(field_meta.name)
                if var is not None:
                    var.set(str(getattr(self._state, field_meta.name, field_meta.default)))

    def _on_preset_selected(self, event: object) -> None:
        """P8.WG4: Expand a named preset into the form fields."""
        name = self._preset_var.get()
        if name == "(custom)":
            return
        try:
            from ..worldgen.conformance.profiles import expand_profile

            spec = expand_profile(name)
            # Map WorldSpec fields back to LauncherState
            for field_meta in all_fields():
                ws_val = getattr(spec, field_meta.name, None)
                if ws_val is not None:
                    setattr(self._state, field_meta.name, ws_val)
            self._state.preset_name = name
            self._populate_config()
        except (ImportError, ValueError) as exc:
            self.show_error_dialog("Preset Error", str(exc))

    def _browse_output(self) -> None:
        from tkinter import filedialog

        d = filedialog.askdirectory(title="Select output directory")
        if d:
            self._output_var.set(d)

    # ── Action handlers ─────────────────────────────────────────────────

    def _on_start_clicked(self) -> None:
        state = self._read_config()
        errors = state.validate()
        if errors:
            self.show_error_dialog("Validation Error", "\n".join(errors))
            return
        self._state = state
        self._set_running(True)
        self._clear_output()
        self._log("Starting generation...")
        self._log(f"  {build_argv(state)}")
        self.on_start(state)

    def _on_cancel_clicked(self) -> None:
        if self._process:
            result = self._process.cancel()
            self._log(f"Cancelled: {result.message}")
            self.on_cancelled()
        self._set_running(False)

    def _on_resume_clicked(self) -> None:
        state = self._read_config()
        if not state.output_dir:
            self.show_error_dialog("Error", "Output directory is required for resume")
            return
        self._state = state
        self._set_running(True)
        self._clear_output()
        self._log("Resuming generation...")
        self.on_start(state)

    def _on_reveal_clicked(self) -> None:
        if self._package_path:
            self.reveal_output(self._package_path)

    def _set_running(self, running: bool) -> None:
        self._start_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self._cancel_btn.configure(state=tk.NORMAL if running else tk.DISABLED)
        self._resume_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        if not running:
            self._progress_var.set(0.0)

    def _set_reveal_enabled(self, enabled: bool) -> None:
        self._reveal_btn.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def _log(self, text: str) -> None:
        self._output_text.configure(state=tk.NORMAL)
        self._output_text.insert(tk.END, text + "\n")
        self._output_text.see(tk.END)
        self._output_text.configure(state=tk.DISABLED)

    def _clear_output(self) -> None:
        self._output_text.configure(state=tk.NORMAL)
        self._output_text.delete("1.0", tk.END)
        self._output_text.configure(state=tk.DISABLED)
        self._package_path = ""
        self._set_reveal_enabled(False)

    # ── LauncherGuiAdapter implementation ──────────────────────────────

    def show_configuration(self, state: LauncherState) -> LauncherState:
        self._state = state
        self._populate_config()
        return self._read_config()

    def on_start(self, state: LauncherState) -> None:
        """Start generation in a background thread."""
        self._process = self._callbacks.start_generation(state)
        self._progress = JsonlProgress(self.STEP_ORDER)
        self._polling = True
        self._status_var.set("Running...")

        def _poll() -> None:
            """Poll process stdout for JSONL events."""
            while self._polling and self._process is not None:
                lines = self._process.read_events(timeout=0.1)
                for line in lines:
                    event = parse_jsonl_line(line)
                    if event:
                        updated_snap = self._progress.feed(event)
                        self._root.after(0, self._on_progress_deferred(updated_snap))

                if self._process.is_running:
                    continue

                # Process finished — read remaining output
                exit_result = self._process.reveal()
                self._root.after(0, self._on_exit_deferred(exit_result))
                self._polling = False
                return

        thread = threading.Thread(target=_poll, daemon=True)
        thread.start()

        # Simulate some progress events for testing without a real forge
        if self._process.run_id == "":
            self._simulate_progress()

    def _simulate_progress(self) -> None:
        """P8.12: Simulate progress for testing without a real Forge subprocess."""
        import time

        def _sim() -> None:
            from .core import ParsedEvent

            steps = self.STEP_ORDER
            for i, step in enumerate(steps):
                if not self._polling:
                    break
                self._progress.feed(
                    ParsedEvent(
                        "step_started",
                        i + 1,
                        "sim",
                        {
                            "type": "step_started",
                            "step_id": step,
                        },
                    )
                )
                self._root.after(0, self._on_progress_deferred(self._progress.snapshot))

                for pct in range(0, 101, 25):
                    if not self._polling:
                        break
                    self._progress.feed(
                        ParsedEvent(
                            "step_progress",
                            i + 1,
                            "sim",
                            {
                                "type": "step_progress",
                                "completed": pct,
                                "total": 100,
                                "message": f"{step}: {pct}%",
                            },
                        )
                    )
                    self._root.after(0, self._on_progress_deferred(self._progress.snapshot))
                    time.sleep(0.05)

                self._progress.feed(
                    ParsedEvent(
                        "artifact_committed",
                        i + 1,
                        "sim",
                        {
                            "type": "artifact_committed",
                            "step_id": step,
                        },
                    )
                )
                self._root.after(0, self._on_progress_deferred(self._progress.snapshot))

            if self._polling:
                self._progress.feed(
                    ParsedEvent(
                        "pipeline_completed",
                        len(steps) + 1,
                        "sim",
                        {
                            "type": "pipeline_completed",
                            "package_path": "/tmp/simulated_output.story",
                            "content_hash": "sim_hash_42",
                        },
                    )
                )
                self._root.after(0, self._on_sim_complete)

        threading.Thread(target=_sim, daemon=True).start()

    def _on_sim_complete(self) -> None:
        snap = self._progress.snapshot
        snap = ProgressSnapshot(
            current_step=snap.current_step,
            step_index=snap.step_index,
            total_steps=snap.total_steps,
            step_completed=snap.step_completed,
            step_total=snap.step_total,
            message=snap.message,
            artifacts_reused=snap.artifacts_reused,
            artifacts_regenerated=snap.artifacts_regenerated,
            is_complete=True,
            is_failed=False,
            is_cancelled=False,
            error_codes=[],
        )
        self.on_complete(snap, "/tmp/simulated_output.story")
        self._set_running(False)

    def _on_progress_deferred(self, snapshot: ProgressSnapshot) -> Any:
        """Return a callable for tkinter .after() that updates progress."""

        def _call() -> None:
            self.on_progress(snapshot)

        return _call

    def _on_exit_deferred(self, result: Any) -> Any:
        """Return a callable for tkinter .after() that handles exit."""

        def _call() -> None:
            self._on_process_exited(result)

        return _call

    def _on_process_exited(self, result: Any) -> None:
        """Handle subprocess exit."""
        self._set_running(False)
        snap = self._progress.snapshot
        if result.status == "complete":
            self.on_complete(snap, result.package_path)
        elif result.status == "cancelled":
            self.on_cancelled()
        else:
            err_snap = ProgressSnapshot(
                current_step=snap.current_step,
                step_index=snap.step_index,
                total_steps=snap.total_steps,
                step_completed=snap.step_completed,
                step_total=snap.step_total,
                message=snap.message,
                artifacts_reused=snap.artifacts_reused,
                artifacts_regenerated=snap.artifacts_regenerated,
                is_complete=False,
                is_failed=True,
                is_cancelled=False,
                error_codes=result.errors,
            )
            self.on_failure(err_snap)

    def on_progress(self, snapshot: ProgressSnapshot) -> None:
        self._progress_var.set(snapshot.fraction)
        status = f"{snapshot.current_step or '...'}"
        if snapshot.message:
            status += f" — {snapshot.message}"
        if snapshot.artifacts_reused or snapshot.artifacts_regenerated:
            self._reuse_var.set(
                f"Reused: {snapshot.artifacts_reused}  "
                f"Regenerated: {snapshot.artifacts_regenerated}"
            )
        self._status_var.set(status)

    def on_failure(self, snapshot: ProgressSnapshot) -> None:
        self._set_running(False)
        self._status_var.set("FAILED")
        self._log("GENERATION FAILED")
        for code in snapshot.error_codes:
            self._log(f"  Error: {code}")

    def on_complete(self, snapshot: ProgressSnapshot, package_path: str) -> None:
        self._set_running(False)
        self._package_path = package_path
        self._progress_var.set(1.0)
        self._status_var.set("Complete")
        self._set_reveal_enabled(True)
        self._log(f"Package: {package_path}")

    def on_cancelled(self) -> None:
        self._set_running(False)
        self._status_var.set("Cancelled")
        self._log("Generation cancelled by user")

    def reveal_output(self, package_path: str) -> None:
        import platform
        import subprocess
        from pathlib import Path as _Path

        system = platform.system()
        try:
            if system == "Darwin":
                subprocess.run(["open", "-R", package_path], check=False)
            elif system == "Windows":
                subprocess.run(["explorer", "/select,", package_path], check=False)
            else:
                subprocess.run(["xdg-open", str(_Path(package_path).parent)], check=False)
        except Exception as e:
            self.show_error_dialog("Error", f"Could not reveal output: {e}")

    def show_error_dialog(self, title: str, message: str) -> None:
        messagebox.showerror(title, message)

    # ── Public API ─────────────────────────────────────────────────────

    def run(self) -> None:
        """Enter the tkinter main loop."""
        self._root.mainloop()

    def close(self) -> None:
        """Close the GUI window."""
        self._polling = False
        try:
            self._root.destroy()
        except tk.TclError:
            pass


# ── P8.12: Headless adapter for testing ─────────────────────────────────


class HeadlessGuiAdapter(LauncherGuiAdapter):
    """P8.12: GUI adapter that records calls for testing.

    Runs without a display — all state is captured in attributes.
    Used to verify that the core logic drives the GUI correctly.
    """

    def __init__(self) -> None:
        self.config_shown = False
        self.last_state: LauncherState | None = None
        self.progress_snapshots: list[ProgressSnapshot] = []
        self.failure_snapshot: ProgressSnapshot | None = None
        self.complete_called = False
        self.complete_package_path = ""
        self.cancelled_called = False
        self.reveal_called = False
        self.error_dialogs: list[tuple[str, str]] = []

    def show_configuration(self, state: LauncherState) -> LauncherState:
        self.config_shown = True
        self.last_state = state
        return state

    def on_start(self, state: LauncherState) -> None:
        self.last_state = state

    def on_progress(self, snapshot: ProgressSnapshot) -> None:
        self.progress_snapshots.append(snapshot)

    def on_failure(self, snapshot: ProgressSnapshot) -> None:
        self.failure_snapshot = snapshot

    def on_complete(self, snapshot: ProgressSnapshot, package_path: str) -> None:
        self.complete_called = True
        self.complete_package_path = package_path

    def on_cancelled(self) -> None:
        self.cancelled_called = True

    def reveal_output(self, package_path: str) -> None:
        self.reveal_called = True

    def show_error_dialog(self, title: str, message: str) -> None:
        self.error_dialogs.append((title, message))
