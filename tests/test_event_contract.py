from __future__ import annotations

import json

from src.pipeline.events import InMemoryEventSink, JsonlEventSink, StepStarted


def test_in_memory_sequences_are_monotonic() -> None:
    sink = InMemoryEventSink()
    sink.emit(StepStarted(run_id="r", step_id="a"))
    sink.emit(StepStarted(run_id="r", step_id="b"))
    assert [event.sequence for event in sink.events] == [1, 2]


def test_jsonl_sequences_are_monotonic(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    sink = JsonlEventSink(str(path))
    sink.emit_many(
        [
            StepStarted(run_id="r", step_id="a"),
            StepStarted(run_id="r", step_id="b"),
        ]
    )
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row["sequence"] for row in rows] == [1, 2]
    assert sink.event_count == 2
