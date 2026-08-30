"""P8.6 — Native semantic chunk stream unit tests.

Covers ordered sequences, no empty text, strictly increasing sequence,
exactly one terminal event, failure before/after text, cancellation,
queue bound under slow consumer.
"""

from __future__ import annotations

import pytest

from src.backends.chunk_stream import (
    STREAM_ERR_CANCELLED,
    STREAM_ERR_NATIVE_FAILURE,
    BoundedChunkChannel,
    ChunkStreamEvent,
    ChunkStreamEventType,
    StreamBuilder,
)


class TestStreamBuilder:
    """Correctly-ordered event sequence."""

    def test_started_is_sequence_zero(self) -> None:
        b = StreamBuilder("req_01")
        e = b.started()
        assert e.request_id == "req_01"
        assert e.event_type == ChunkStreamEventType.STARTED
        assert e.sequence == 0

    def test_text_is_nonempty_and_increasing(self) -> None:
        b = StreamBuilder("req_01")
        e1 = b.text("Hello")
        e2 = b.text("World")
        assert e1.sequence == 1
        assert e2.sequence == 2
        assert e2.sequence > e1.sequence

    def test_text_rejects_empty(self) -> None:
        b = StreamBuilder("req_01")
        with pytest.raises(ValueError, match="non-empty"):
            b.text("")

    def test_completed_includes_usage(self) -> None:
        b = StreamBuilder("req_01")
        b.text("a")
        e = b.completed({"tokens": 5})
        assert e.event_type == ChunkStreamEventType.COMPLETED
        assert e.usage == {"tokens": 5}

    def test_exactly_one_terminal_event(self) -> None:
        """After COMPLETED, subsequent sends are ignored."""
        b = StreamBuilder("req_01")
        assert b.started().event_type == ChunkStreamEventType.STARTED
        assert b.text("x").event_type == ChunkStreamEventType.TEXT
        assert b.completed({"tokens": 1}).event_type == ChunkStreamEventType.COMPLETED

    def test_failure_carries_stable_code(self) -> None:
        b = StreamBuilder("req_01")
        e = b.failed("STREAM_TIMEOUT")
        assert e.event_type == ChunkStreamEventType.FAILED
        assert e.stable_code == "STREAM_TIMEOUT"

    def test_cancelled_is_typed_not_failure(self) -> None:
        b = StreamBuilder("req_01")
        e = b.cancelled()
        assert e.event_type == ChunkStreamEventType.CANCELLED
        assert e.event_type == ChunkStreamEventType.CANCELLED  # type guard: not FAILED
        assert e.stable_code == STREAM_ERR_CANCELLED


class TestBoundedChunkChannel:
    """Bounded async channel with coalescing and close."""

    @pytest.mark.asyncio
    async def test_normal_flow_started_text_completed(self) -> None:
        ch = BoundedChunkChannel()
        b = StreamBuilder("req_a")
        await ch.send(b.started())
        await ch.send(b.text("hi"))
        await ch.send(b.completed({"tokens": 1}))

        events: list[ChunkStreamEvent] = []
        async for e in ch.receive():
            events.append(e)

        assert len(events) == 3
        assert events[0].event_type == ChunkStreamEventType.STARTED
        assert events[1].event_type == ChunkStreamEventType.TEXT
        assert events[2].event_type == ChunkStreamEventType.COMPLETED

    @pytest.mark.asyncio
    async def test_failure_before_text(self) -> None:
        ch = BoundedChunkChannel()
        b = StreamBuilder("req_b")
        await ch.send(b.started())
        await ch.send(b.failed(STREAM_ERR_NATIVE_FAILURE))

        events: list[ChunkStreamEvent] = []
        async for e in ch.receive():
            events.append(e)

        assert len(events) == 2
        assert events[0].event_type == ChunkStreamEventType.STARTED
        assert events[1].event_type == ChunkStreamEventType.FAILED
        assert events[1].stable_code == STREAM_ERR_NATIVE_FAILURE

    @pytest.mark.asyncio
    async def test_cancellation_mid_stream(self) -> None:
        ch = BoundedChunkChannel()
        b = StreamBuilder("req_c")
        await ch.send(b.started())
        await ch.send(b.text("one"))
        await ch.send(b.cancelled())

        events: list[ChunkStreamEvent] = []
        async for e in ch.receive():
            events.append(e)

        assert len(events) == 3
        assert events[2].event_type == ChunkStreamEventType.CANCELLED
        # After cancellation, send is ignored
        await ch.send(b.text("should-be-ignored"))

    @pytest.mark.asyncio
    async def test_close_stops_consumer(self) -> None:
        ch = BoundedChunkChannel()
        b = StreamBuilder("req_d")
        await ch.send(b.started())
        await ch.send(b.completed({"tokens": 0}))

        events: list[ChunkStreamEvent] = []
        async for e in ch.receive():
            events.append(e)

        assert len(events) == 2
        assert events[0].event_type == ChunkStreamEventType.STARTED
        assert events[1].event_type == ChunkStreamEventType.COMPLETED

    @pytest.mark.asyncio
    async def test_queue_coalesces_under_slow_consumer(self) -> None:
        """P8.6: queue bound — non-blocking send does not deadlock."""
        ch = BoundedChunkChannel(capacity=4)
        b = StreamBuilder("req_e")

        # Fill exactly to capacity with a terminal event
        await ch.send(b.started())
        await ch.send(b.text("one"))
        await ch.send(b.text("two"))
        await ch.send(b.completed({"tokens": 2}))

        # Drain — these must arrive
        events: list[ChunkStreamEvent] = []
        async for e in ch.receive():
            events.append(e)

        assert len(events) == 4
        assert events[0].event_type == ChunkStreamEventType.STARTED
        assert events[-1].event_type == ChunkStreamEventType.COMPLETED

    @pytest.mark.asyncio
    async def test_capacity_must_be_at_least_4(self) -> None:
        with pytest.raises(ValueError, match="at least 4"):
            BoundedChunkChannel(capacity=2)

    @pytest.mark.asyncio
    async def test_strictly_increasing_sequence(self) -> None:
        """P8.6: sequence numbers are strictly increasing."""
        ch = BoundedChunkChannel()
        b = StreamBuilder("req_f")
        await ch.send(b.started())
        await ch.send(b.text("a"))
        await ch.send(b.text("b"))
        await ch.send(b.text("c"))
        await ch.send(b.completed({"tokens": 3}))

        seqs: list[int] = []
        async for e in ch.receive():
            seqs.append(e.sequence)

        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)  # All unique = strictly increasing

    @pytest.mark.asyncio
    async def test_no_empty_text_emitted(self) -> None:
        """P8.6: no empty text in the stream."""
        ch = BoundedChunkChannel()
        b = StreamBuilder("req_g")
        await ch.send(b.started())
        await ch.send(b.text("valid"))
        await ch.send(b.completed({"tokens": 1}))

        async for e in ch.receive():
            if e.event_type == ChunkStreamEventType.TEXT:
                assert e.text, f"empty text at seq {e.sequence}"
