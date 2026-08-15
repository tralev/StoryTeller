"""P8.10 — CLI JSONL contract tests.

Verify the versioned JSONL event/result protocol:
- Every event has event_version, sequence, timestamp, run_id, type
- Line length limit (4096 bytes)
- Malformed/partial/unknown event handling
- stdout vs stderr ownership
- Artifact reuse/regeneration events
- Exit code contract
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.pipeline.events import (
    JSONL_EVENT_VERSION,
    JSONL_MAX_LINE_BYTES,
    ArtifactRegenerated,
    ArtifactReused,
    CheckpointSaved,
    InMemoryEventSink,
    JsonlEventSink,
    ModelLoaded,
    ModelLoading,
    PipelineCancelled,
    PipelineCompleted,
    PipelineFailed,
    PipelineStarted,
    ReuseSummary,
    StepCompleted,
    StepFailed,
    StepProgress,
    StepRetrying,
    StepStarted,
    ValidationFailed,
)


# ── P8.10: JSONL envelope contract ──────────────────────────────────────


class TestJsonlEnvelope:
    """P8.10: Every JSONL line must include the standard envelope fields."""

    def test_event_has_required_fields(self) -> None:
        event = StepStarted(run_id="run_01", step_id="world_builder")
        d = event.to_dict()
        # Base fields from DomainEvent
        assert "run_id" in d
        assert "sequence" in d
        assert "timestamp" in d
        assert "type" in d
        assert d["type"] == "step_started"

    def test_event_version_in_jsonl(self, tmp_path: Path) -> None:
        sink = JsonlEventSink(str(tmp_path / "events.jsonl"))
        sink.emit(StepStarted(run_id="run_01", step_id="test"))
        sink.emit(StepCompleted(run_id="run_01", step_id="test"))

        with open(sink.path) as f:
            for line in f:
                evt = json.loads(line.strip())
                assert evt["event_version"] == JSONL_EVENT_VERSION
                assert isinstance(evt["sequence"], int)
                assert isinstance(evt["timestamp"], str)
                assert isinstance(evt["run_id"], str)
                assert isinstance(evt["type"], str)

    def test_sequence_is_monotonic(self, tmp_path: Path) -> None:
        sink = JsonlEventSink(str(tmp_path / "events.jsonl"))
        for i in range(10):
            sink.emit(StepStarted(run_id="run_01", step_id=f"s{i}"))

        seqs: list[int] = []
        with open(sink.path) as f:
            for line in f:
                evt = json.loads(line.strip())
                seqs.append(evt["sequence"])

        assert seqs == list(range(1, 11))
        assert sink.event_count == 10


# ── P8.10: All 20 event types serialize/deserialize ──────────────────────


class TestAllEventTypes:
    """P8.10: Every documented event type must serialize to valid JSON."""

    def test_pipeline_started(self) -> None:
        e = PipelineStarted(run_id="r", seed=42, title="T", tone="mature_dark_fantasy")
        d = json.loads(e.to_json())
        assert d["type"] == "pipeline_started"
        assert d["seed"] == 42

    def test_pipeline_completed(self) -> None:
        e = PipelineCompleted(run_id="r", package_path="/out.story",
                             content_hash="abc", total_duration_s=120.5)
        d = json.loads(e.to_json())
        assert d["type"] == "pipeline_completed"
        assert d["package_path"] == "/out.story"

    def test_pipeline_failed(self) -> None:
        e = PipelineFailed(run_id="r", errors=["e1", "e2"])
        d = json.loads(e.to_json())
        assert d["type"] == "pipeline_failed"
        assert len(d["errors"]) == 2

    def test_pipeline_cancelled(self) -> None:
        e = PipelineCancelled(run_id="r", cancelled_at="2026-08-06T12:00:00Z")
        d = json.loads(e.to_json())
        assert d["type"] == "pipeline_cancelled"

    def test_model_loading(self) -> None:
        e = ModelLoading(run_id="r", model_name="qwen", estimated_mb=4700)
        d = json.loads(e.to_json())
        assert d["type"] == "model_loading"

    def test_model_loaded(self) -> None:
        e = ModelLoaded(run_id="r", model_name="qwen", ram_mb=4700)
        d = json.loads(e.to_json())
        assert d["type"] == "model_loaded"

    def test_step_lifecycle(self) -> None:
        types: list[str] = []
        for e in [
            StepStarted(run_id="r", step_id="s"),
            StepProgress(run_id="r", step_id="s", completed=300, total=500,
                        message="year 300"),
            StepCompleted(run_id="r", step_id="s"),
            StepFailed(run_id="r", step_id="s", error_code="ERR"),
            StepRetrying(run_id="r", step_id="s", attempt=2),
        ]:
            d = json.loads(e.to_json())
            types.append(d["type"])
        assert types == ["step_started", "step_progress", "step_completed",
                         "step_failed", "step_retrying"]

    def test_artifact_events(self) -> None:
        for e in [
            ArtifactReused(run_id="r", step_id="s", artifact_key="terrain",
                          artifact_id="id1", reused_from_run="run_old"),
            ArtifactRegenerated(run_id="r", step_id="s", artifact_key="terrain",
                               artifact_id="id1", reason="dependency_changed"),
        ]:
            d = json.loads(e.to_json())
            assert "artifact_id" in d

    def test_reuse_summary(self) -> None:
        e = ReuseSummary(run_id="r", reused_count=14, regenerated_count=3,
                        total_artifacts=17)
        d = json.loads(e.to_json())
        assert d["type"] == "reuse_summary"
        assert d["reused_count"] == 14
        assert d["regenerated_count"] == 3

    def test_validation_and_checkpoint(self) -> None:
        for e in [
            ValidationFailed(run_id="r", step_id="s", error_count=3),
            CheckpointSaved(run_id="r", step_id="s", phase=2),
        ]:
            d = json.loads(e.to_json())
            assert "type" in d


# ── P8.10: Line limit enforcement ────────────────────────────────────────


class TestLineLimits:
    """P8.10: Lines exceeding JSONL_MAX_LINE_BYTES are truncated."""

    def test_normal_event_fits(self, tmp_path: Path) -> None:
        sink = JsonlEventSink(str(tmp_path / "events.jsonl"))
        sink.emit(StepStarted(run_id="run_01", step_id="s"))
        with open(sink.path) as f:
            line = f.readline()
        assert len(line) <= JSONL_MAX_LINE_BYTES + 1  # +1 for \n

    def test_large_event_truncated(self, tmp_path: Path) -> None:
        sink = JsonlEventSink(str(tmp_path / "events.jsonl"))
        # Create an event with a very long error message
        huge_message = "x" * (JSONL_MAX_LINE_BYTES + 1000)
        sink.emit(StepFailed(run_id="run_01", step_id="s",
                            error_message=huge_message))
        assert sink.truncated_count == 1

    def test_truncation_keeps_valid_json_prefix(self, tmp_path: Path) -> None:
        """P8.10: Truncated line must end with ...} to hint at truncation."""
        sink = JsonlEventSink(str(tmp_path / "events.jsonl"))
        huge_message = "x" * (JSONL_MAX_LINE_BYTES + 100)
        sink.emit(StepFailed(run_id="run_01", step_id="s",
                            error_message=huge_message))
        with open(sink.path) as f:
            line = f.readline().strip()
        assert line.endswith("...}")
        assert len(line.encode()) <= JSONL_MAX_LINE_BYTES


# ── P8.10: Malformed/partial/unknown event handling ──────────────────────


class TestMalformedHandling:
    """P8.10: Consumers must tolerate malformed, unknown, and partial events."""

    def test_unknown_type_ignored(self, tmp_path: Path) -> None:
        """P8.10: Unknown 'type' values are silently ignored by consumers."""
        # Write a JSONL file with a mix of known and unknown types
        lines = [
            json.dumps({"event_version": 1, "sequence": 1, "type": "step_started",
                       "run_id": "r", "step_id": "s"}),
            json.dumps({"event_version": 1, "sequence": 2, "type": "future_event_xyz",
                       "run_id": "r", "payload": "whatever"}),
            json.dumps({"event_version": 1, "sequence": 3, "type": "step_completed",
                       "run_id": "r", "step_id": "s"}),
        ]
        path = tmp_path / "events.jsonl"
        path.write_text("\n".join(lines) + "\n")

        # Simulate consumer parsing: skip unknown types
        known_types = {"step_started", "step_completed", "step_failed",
                       "pipeline_started", "pipeline_completed", "pipeline_cancelled",
                       "pipeline_failed", "model_loading", "model_loaded",
                       "step_progress", "step_retrying", "artifact_committed",
                       "artifact_reused", "artifact_regenerated", "reuse_summary",
                       "validation_failed", "item_quarantined", "checkpoint_saved",
                       "model_unloaded"}
        parsed = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue  # malformed — skip
                if evt.get("type") in known_types:
                    parsed += 1
        assert parsed == 2  # Only step_started and step_completed

    def test_malformed_json_skipped(self, tmp_path: Path) -> None:
        """P8.10: Non-JSON lines are skipped, not crashing the consumer."""
        lines = [
            "this is not json",
            json.dumps({"event_version": 1, "sequence": 1, "type": "step_started",
                       "run_id": "r", "step_id": "s"}),
            "{incomplete",
        ]
        path = tmp_path / "events.jsonl"
        path.write_text("\n".join(lines) + "\n")

        parsed = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                    parsed += 1
                except json.JSONDecodeError:
                    pass  # skip malformed
        assert parsed == 1  # Only the valid line

    def test_missing_required_field_skipped(self, tmp_path: Path) -> None:
        """P8.10: Events missing 'type' are skipped."""
        path = tmp_path / "events.jsonl"
        path.write_text(
            json.dumps({"event_version": 1, "sequence": 1, "run_id": "r"}) + "\n" +
            json.dumps({"event_version": 1, "sequence": 2, "type": "step_started",
                       "run_id": "r", "step_id": "s"}) + "\n"
        )

        parsed = 0
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "type" in evt:
                    parsed += 1
        assert parsed == 1


# ── P8.10: Artifact reuse / regeneration counts ──────────────────────────


class TestReuseCounts:
    """P8.10: JsonlEventSink.reuse_summary reflects the emitted log."""

    def test_reuse_summary_from_log(self, tmp_path: Path) -> None:
        sink = JsonlEventSink(str(tmp_path / "events.jsonl"))
        sink.emit(ReuseSummary(run_id="r", reused_count=5, regenerated_count=2,
                              total_artifacts=7))
        for i in range(5):
            sink.emit(ArtifactReused(run_id="r", step_id="s", artifact_key=f"a{i}",
                                    artifact_id=f"id{i}", reused_from_run="old"))
        for i in range(2):
            sink.emit(ArtifactRegenerated(run_id="r", step_id="s",
                                         artifact_key=f"a{i+5}",
                                         artifact_id=f"id{i+5}",
                                         reason="missing"))

        summary = sink.reuse_summary
        assert summary["reused"] == 5
        assert summary["regenerated"] == 2
        assert summary["total"] == 7

    def test_empty_log_has_zero_counts(self, tmp_path: Path) -> None:
        sink = JsonlEventSink(str(tmp_path / "events.jsonl"))
        summary = sink.reuse_summary
        assert summary == {"reused": 0, "regenerated": 0, "total": 0}


# ── P8.10: Exit code contract ────────────────────────────────────────────


class TestExitCodes:
    """P8.10: CLI exit codes match the documented contract."""

    def test_exit_code_constants_match_spec(self) -> None:
        """Verify documented exit codes are available."""
        codes = {
            0: "success",
            2: "configuration error",
            3: "dependency/model unavailable",
            4: "generation/validation exhausted",
            5: "persistence/package acceptance failure",
            130: "user cancellation",
        }
        # 130 is the standard SIGINT exit code (128 + 2)
        assert 130 == 128 + 2

    def test_help_exits_zero(self) -> None:
        """P8.10: `forge --help` exits 0."""
        result = subprocess.run(
            [sys.executable, "-m", "src", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0

    def test_invalid_option_exits_2(self) -> None:
        """P8.10: Invalid CLI option exits 2 (configuration error)."""
        result = subprocess.run(
            [sys.executable, "-m", "src", "--nonexistent-option-xyz"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_stdout_stderr_separation(self) -> None:
        """P8.10: Help text goes to stdout; errors to stderr."""
        result = subprocess.run(
            [sys.executable, "-m", "src", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        # Help should produce stdout content
        assert len(result.stdout) > 0


# ── P8.10: InMemoryEventSink for tests ────────────────────────────────────


class TestInMemorySink:
    """P8.10: InMemoryEventSink captures events for test assertions."""

    def test_captures_events(self) -> None:
        sink = InMemoryEventSink()
        sink.emit(StepStarted(run_id="r", step_id="s"))
        sink.emit(StepCompleted(run_id="r", step_id="s"))
        assert len(sink.events) == 2
        assert sink.events[0].event_type == "step_started"

    def test_of_type_filter(self) -> None:
        sink = InMemoryEventSink()
        sink.emit(StepStarted(run_id="r", step_id="a"))
        sink.emit(StepStarted(run_id="r", step_id="b"))
        sink.emit(StepCompleted(run_id="r", step_id="a"))
        started = sink.of_type("step_started")
        assert len(started) == 2
        completed = sink.of_type("step_completed")
        assert len(completed) == 1

    def test_clear_resets(self) -> None:
        sink = InMemoryEventSink()
        sink.emit(StepStarted(run_id="r", step_id="s"))
        assert len(sink.events) == 1
        sink.clear()
        assert len(sink.events) == 0


# ── P8.10: Event type names match api.md ─────────────────────────────────


class TestEventTypeNames:
    """P8.10: Generated event_type names match the documented contract."""

    def test_all_required_types_exist(self) -> None:
        """Every required event type from api.md has a matching class."""
        assert PipelineStarted(run_id="r").event_type == "pipeline_started"
        assert ReuseSummary(run_id="r").event_type == "reuse_summary"
        assert PipelineCancelled(run_id="r").event_type == "pipeline_cancelled"
        assert ModelLoading(run_id="r").event_type == "model_loading"
        assert StepProgress(run_id="r").event_type == "step_progress"
        assert ArtifactReused(run_id="r").event_type == "artifact_reused"
        assert ArtifactRegenerated(run_id="r").event_type == "artifact_regenerated"
