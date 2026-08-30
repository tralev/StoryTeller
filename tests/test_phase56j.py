"""Tests for Phase 5.6J: Event Integration.

Covers EventSink protocol, JsonlEventSink, InMemoryEventSink,
typed event emission through the pipeline, and event count verification.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from src.pipeline.events import (
    CheckpointSaved,
    EventSink,
    InMemoryEventSink,
    JsonlEventSink,
    NullEventSink,
    PipelineCompleted,
    PipelineStarted,
    StepCompleted,
    StepFailed,
    StepStarted,
)

# ── EventSink protocol ────────────────────────────────────────────────


class TestEventSinkProtocol:
    """EventSink subtypes satisfy the protocol."""

    def test_in_memory_satisfies_protocol(self) -> None:
        sink = InMemoryEventSink()
        assert isinstance(sink, EventSink)

    def test_jsonl_satisfies_protocol(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            sink = JsonlEventSink(path)
            assert isinstance(sink, EventSink)
        finally:
            Path(path).unlink(missing_ok=True)

    def test_null_satisfies_protocol(self) -> None:
        sink = NullEventSink()
        assert isinstance(sink, EventSink)


# ── InMemoryEventSink ────────────────────────────────────────────────


class TestInMemoryEventSink:
    """InMemoryEventSink captures events for assertions."""

    def test_capture_single_event(self) -> None:
        sink = InMemoryEventSink()
        sink.emit(StepStarted(run_id="run_01", step_id="world_builder"))
        assert len(sink.events) == 1
        assert sink.events[0].event_type == "step_started"

    def test_capture_multiple(self) -> None:
        sink = InMemoryEventSink()
        sink.emit_many(
            [
                StepStarted(run_id="r1", step_id="a"),
                StepCompleted(run_id="r1", step_id="a"),
                StepStarted(run_id="r1", step_id="b"),
            ]
        )
        assert len(sink.events) == 3

    def test_of_type_filter(self) -> None:
        sink = InMemoryEventSink()
        sink.emit(StepStarted(run_id="r1", step_id="a"))
        sink.emit(StepCompleted(run_id="r1", step_id="a"))
        sink.emit(StepStarted(run_id="r1", step_id="b"))

        started = sink.of_type("step_started")
        assert len(started) == 2
        completed = sink.of_type("step_completed")
        assert len(completed) == 1

    def test_clear(self) -> None:
        sink = InMemoryEventSink()
        sink.emit(StepStarted(run_id="r1", step_id="a"))
        assert len(sink.events) == 1
        sink.clear()
        assert len(sink.events) == 0

    def test_run_id_preserved(self) -> None:
        sink = InMemoryEventSink()
        sink.emit(StepStarted(run_id="run_abc123", step_id="test"))
        assert sink.events[0].run_id == "run_abc123"


# ── JsonlEventSink ────────────────────────────────────────────────────


class TestJsonlEventSink:
    """JsonlEventSink writes events to disk."""

    def test_writes_to_file(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            sink = JsonlEventSink(path)
            sink.emit(StepStarted(run_id="run_x", step_id="test"))
            sink.emit(StepCompleted(run_id="run_x", step_id="test"))

            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 2
            data = json.loads(lines[0])
            assert data["type"] == "step_started"
            assert data["run_id"] == "run_x"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_emit_many(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            sink = JsonlEventSink(path)
            sink.emit_many(
                [
                    StepStarted(run_id="r1", step_id="a"),
                    StepStarted(run_id="r1", step_id="b"),
                ]
            )

            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 2
        finally:
            Path(path).unlink(missing_ok=True)

    def test_event_count(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        try:
            sink = JsonlEventSink(path)
            assert sink.event_count == 0
            sink.emit(StepStarted(run_id="r", step_id="a"))
            assert sink.event_count == 1
            sink.emit_many([StepStarted(run_id="r", step_id="b") for _ in range(3)])
            assert sink.event_count == 4
        finally:
            Path(path).unlink(missing_ok=True)


# ── Event serialization ──────────────────────────────────────────────


class TestEventSerialization:
    """DomainEvents serialize to valid JSON."""

    def test_step_started_json(self) -> None:
        e = StepStarted(run_id="run_01", step_id="world_builder", attempt=1)
        js = e.to_json()
        d = json.loads(js)
        assert d["type"] == "step_started"
        assert d["run_id"] == "run_01"
        assert d["step_id"] == "world_builder"

    def test_pipeline_started_json(self) -> None:
        e = PipelineStarted(run_id="r1", seed=42, title="T", tone="dark")
        d = json.loads(e.to_json())
        assert d["seed"] == 42
        assert d["title"] == "T"

    def test_pipeline_completed_json(self) -> None:
        e = PipelineCompleted(run_id="r1", package_path="/out.story", content_hash="abc")
        d = json.loads(e.to_json())
        assert d["package_path"] == "/out.story"

    def test_checkpoint_saved_json(self) -> None:
        e = CheckpointSaved(run_id="r1", step_id="world_builder", phase=1)
        d = json.loads(e.to_json())
        assert d["step_id"] == "world_builder"
        assert d["phase"] == 1

    def test_step_failed_json(self) -> None:
        e = StepFailed(run_id="r1", step_id="bad", error_message="boom", retryable=True)
        d = json.loads(e.to_json())
        assert d["retryable"] is True


# ── Pipeline integration ──────────────────────────────────────────────


class TestPipelineEventIntegration:
    """Full pipeline emits expected events."""

    @pytest.mark.asyncio
    async def test_pipeline_emits_lifecycle_events(self, tmp_path: Path) -> None:
        from src.application.models import GenerationRequest
        from tests.test_production_wiring import (
            InstrumentedGenerateStory,
            TrackedImageGenerator,
            TrackedMusicGenerator,
            TrackedTextGenerator,
            _clear_fakes,
            _inject_fakes,
        )

        _clear_fakes()
        text = TrackedTextGenerator()
        image = TrackedImageGenerator()
        music = TrackedMusicGenerator()
        _inject_fakes(text, image, music)

        output_dir = str(tmp_path / "output")
        service = InstrumentedGenerateStory()
        request = GenerationRequest(
            seed=42,
            title="Event Test",
            tone="dark_fantasy",
            output_dir=output_dir,
            config_path="/nonexistent",
        )
        result = await service.execute(request)
        assert result.errors == [], f"Errors: {result.errors}"

        # Verify events.jsonl exists
        events_file = tmp_path / "output" / "pipeline_events.jsonl"
        assert events_file.exists(), "pipeline_events.jsonl was not created"

        # Read events
        events: list[dict[str, Any]] = []
        with open(events_file) as f:
            for line in f:
                events.append(json.loads(line))

        assert len(events) > 0, "No events emitted"

        # Verify key event types exist
        event_types = {e["type"] for e in events}
        assert "pipeline_started" in event_types
        assert "pipeline_completed" in event_types

        # All events have non-empty run_id
        for e in events:
            assert e.get("run_id", ""), f"Event missing run_id: {e['type']}"

    @pytest.mark.asyncio
    async def test_step_events_emitted(self, tmp_path: Path) -> None:
        from src.application.models import GenerationRequest
        from tests.test_production_wiring import (
            InstrumentedGenerateStory,
            TrackedImageGenerator,
            TrackedMusicGenerator,
            TrackedTextGenerator,
            _clear_fakes,
            _inject_fakes,
        )

        _clear_fakes()
        _inject_fakes(TrackedTextGenerator(), TrackedImageGenerator(), TrackedMusicGenerator())

        service = InstrumentedGenerateStory()
        result = await service.execute(
            GenerationRequest(
                seed=42,
                title="Step Events",
                tone="dark_fantasy",
                output_dir=str(tmp_path / "out"),
                config_path="/nonexistent",
            )
        )
        assert result.errors == []

        events_file = tmp_path / "out" / "pipeline_events.jsonl"
        with open(events_file) as f:
            events = [json.loads(line) for line in f]

        types = {e["type"] for e in events}
        assert "step_started" in types
        assert "step_completed" in types
        assert "checkpoint_saved" in types

    @pytest.mark.asyncio
    async def test_run_id_consistent_across_events(self, tmp_path: Path) -> None:
        from src.application.models import GenerationRequest
        from tests.test_production_wiring import (
            InstrumentedGenerateStory,
            TrackedImageGenerator,
            TrackedMusicGenerator,
            TrackedTextGenerator,
            _clear_fakes,
            _inject_fakes,
        )

        _clear_fakes()
        _inject_fakes(TrackedTextGenerator(), TrackedImageGenerator(), TrackedMusicGenerator())

        service = InstrumentedGenerateStory()
        result = await service.execute(
            GenerationRequest(
                seed=99,
                title="Consistent Run ID",
                tone="heroic_fantasy",
                output_dir=str(tmp_path / "out"),
                config_path="/nonexistent",
            )
        )
        assert result.errors == []

        events_file = tmp_path / "out" / "pipeline_events.jsonl"
        with open(events_file) as f:
            events = [json.loads(line) for line in f]

        # All run_ids should be the same
        run_ids = {e.get("run_id") for e in events}
        assert len(run_ids) == 1, f"Multiple run_ids found: {run_ids}"
