"""P8.6 — Native semantic chunk stream events and bounded async queue.

Defines the typed stream events (started, text, completed, failed) and a
bounded async channel that sits between the native generation callback and
the UI consumer. Cancellation has a typed outcome and must not masquerade
as failure.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator


class ChunkStreamEventType(str, Enum):
    """Frozen event types — identical across Python, Kotlin, Swift."""

    STARTED = "started"
    TEXT = "text"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"  # P8.6: cancellation is typed, never FAILED


@dataclass(frozen=True)
class ChunkStreamEvent:
    """One emitted event from the chunk stream.

    All fields are stable across platforms. ``request_id`` ties events
    to their originating request. ``sequence`` is strictly increasing
    within a request and starts at 0 for STARTED.
    """

    request_id: str
    event_type: ChunkStreamEventType
    sequence: int
    text: str = ""
    usage: dict[str, int] | None = None
    stable_code: str = ""


# ── P8.C2 stable diagnostic codes for stream errors ─────────────────

STREAM_ERR_MODEL_NOT_LOADED = "STREAM_MODEL_NOT_LOADED"
STREAM_ERR_CANCELLED = "STREAM_CANCELLED"
STREAM_ERR_NATIVE_FAILURE = "STREAM_NATIVE_FAILURE"
STREAM_ERR_TIMEOUT = "STREAM_TIMEOUT"
STREAM_ERR_QUEUE_FULL = "STREAM_QUEUE_FULL"


# ── Bounded async channel ────────────────────────────────────────────

class BoundedChunkChannel:
    """Bounded async queue between native callbacks and UI.

    P8.6: The queue has a fixed capacity. When full, the producer (native
    callback) is throttled — we never block the callback indefinitely.
    Coalescing: when at capacity, drop the oldest unconsumed TEXT event
    and insert a TEXT(text="…") continuation marker.
    """

    def __init__(self, capacity: int = 64) -> None:
        if capacity < 4:
            raise ValueError("capacity must be at least 4 (one per event type)")
        self._capacity = capacity
        self._queue: asyncio.Queue[ChunkStreamEvent | None] = asyncio.Queue(maxsize=capacity)
        self._closed = False

    @property
    def capacity(self) -> int:
        return self._capacity

    async def send(self, event: ChunkStreamEvent) -> None:
        """Send an event to the channel. Non-blocking for native callbacks."""
        if self._closed:
            return
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # Coalesce: drop oldest unconsumed TEXT, insert continuation marker
            try:
                dropped = self._queue.get_nowait()
                if dropped is not None and dropped.event_type == ChunkStreamEventType.TEXT:
                    self._queue.put_nowait(ChunkStreamEvent(
                        request_id=event.request_id,
                        event_type=ChunkStreamEventType.TEXT,
                        sequence=dropped.sequence,
                        text="…",
                    ))
            except asyncio.QueueEmpty:
                pass
            # Retry sending the new event
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                pass  # Drop silently — consumer too slow

    async def receive(self) -> AsyncIterator[ChunkStreamEvent]:
        """Async iterator over events until terminal event or close."""
        while not self._closed:
            event = await self._queue.get()
            if event is None:
                break
            yield event
            if event.event_type in (
                ChunkStreamEventType.COMPLETED,
                ChunkStreamEventType.FAILED,
                ChunkStreamEventType.CANCELLED,
            ):
                break

    def close(self) -> None:
        """Signal the consumer to stop. Thread-safe."""
        self._closed = True
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass


# ── Stream builder ────────────────────────────────────────────────────

@dataclass
class StreamBuilder:
    """Builds a correctly-ordered sequence of ChunkStreamEvents.

    Usage:
        builder = StreamBuilder("req_01")
        await channel.send(builder.started())
        await channel.send(builder.text(0, "Hello "))
        await channel.send(builder.text(1, "world"))
        await channel.send(builder.completed(2, {"prompt_tokens": 10, "completion_tokens": 2}))
    """

    request_id: str
    _seq: int = 0

    def started(self) -> ChunkStreamEvent:
        return ChunkStreamEvent(
            request_id=self.request_id,
            event_type=ChunkStreamEventType.STARTED,
            sequence=0,
        )

    def text(self, text: str) -> ChunkStreamEvent:
        if not text:
            raise ValueError("text chunk must be non-empty")
        self._seq += 1
        return ChunkStreamEvent(
            request_id=self.request_id,
            event_type=ChunkStreamEventType.TEXT,
            sequence=self._seq,
            text=text,
        )

    def completed(self, usage: dict[str, int]) -> ChunkStreamEvent:
        self._seq += 1
        return ChunkStreamEvent(
            request_id=self.request_id,
            event_type=ChunkStreamEventType.COMPLETED,
            sequence=self._seq,
            usage=usage,
        )

    def failed(self, code: str) -> ChunkStreamEvent:
        self._seq += 1
        return ChunkStreamEvent(
            request_id=self.request_id,
            event_type=ChunkStreamEventType.FAILED,
            sequence=self._seq,
            stable_code=code,
        )

    def cancelled(self) -> ChunkStreamEvent:
        self._seq += 1
        return ChunkStreamEvent(
            request_id=self.request_id,
            event_type=ChunkStreamEventType.CANCELLED,
            sequence=self._seq,
            stable_code=STREAM_ERR_CANCELLED,
        )
