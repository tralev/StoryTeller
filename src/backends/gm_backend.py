"""P8.6 — Game Master backend with native semantic chunk streaming.

Implements the GameMaster Protocol using llama-cpp-python with real
token-by-token streaming via ChunkStreamEvent. One request owns one model
lease and cancellation token.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from ..config import ModelConfig
from ..interfaces import GameMasterContext
from .chunk_stream import (
    STREAM_ERR_MODEL_NOT_LOADED,
    STREAM_ERR_NATIVE_FAILURE,
    BoundedChunkChannel,
    ChunkStreamEvent,
    ChunkStreamEventType,
    StreamBuilder,
)


class LlamaCppGameMaster:
    """Game Master for mobile via llama.cpp with chunk streaming.

    P8.6: Uses BoundedChunkChannel for backpressure-safe streaming from
    native callbacks to UI. One request owns one model lease and
    cancellation token. Cancellation emits typed CANCELLED, never FAILED.
    """

    provider: str
    model_name: str
    quantization: str

    def __init__(self, config: ModelConfig) -> None:
        self.provider = config.provider
        self.model_name = config.model
        self.quantization = config.quantization
        self._config = config
        self._loaded = False
        self._model: Any = None
        self._current_channel: BoundedChunkChannel | None = None

    async def answer(
        self,
        question: str,
        context: GameMasterContext,
    ) -> AsyncIterator[str]:
        """Answer a reader's question, streaming tokens via ChunkStreamEvent.

        P8.6: Emits STARTED → TEXT* → COMPLETED/FAILED/CANCELLED.
        The consumer receives plain text tokens; the full event stream
        is exposed via ``answer_events()`` for UI-level consumers.
        """
        async for event in self.answer_events(question, context):
            if event.event_type == ChunkStreamEventType.TEXT:
                yield event.text

    async def answer_events(
        self,
        question: str,
        context: GameMasterContext,
    ) -> AsyncIterator[ChunkStreamEvent]:
        """Stream GM answer as typed ChunkStreamEvent sequence."""
        if self._model is None:
            builder = StreamBuilder("gm_stub")
            yield builder.failed(STREAM_ERR_MODEL_NOT_LOADED)
            return

        request_id = f"gm_{hash(question) & 0xFFFFFFFF:08x}"
        builder = StreamBuilder(request_id)
        channel = BoundedChunkChannel()
        self._current_channel = channel

        try:
            prompt = self._build_prompt(question, context)
            yield builder.started()

            # Run token generation in a thread; pump tokens into channel
            task = asyncio.create_task(self._generate_tokens(prompt, builder, channel))

            async for event in channel.receive():
                yield event
                if event.event_type in (
                    ChunkStreamEventType.COMPLETED,
                    ChunkStreamEventType.FAILED,
                    ChunkStreamEventType.CANCELLED,
                ):
                    break

            await task
        except asyncio.CancelledError:
            channel.close()
            yield builder.cancelled()
        finally:
            self._current_channel = None

    def cancel(self) -> None:
        """Cancel the current generation, if any."""
        if self._current_channel is not None:
            self._current_channel.close()

    async def load(self) -> None:
        """Load the Llama 3.2 3B model into memory."""
        try:
            import llama_cpp
        except ImportError:
            self._loaded = False
            return

        path = self._resolve_model_path()
        if path is None or not path.exists():
            self._loaded = False
            return

        self._model = llama_cpp.Llama(
            model_path=str(path),
            n_ctx=2048,
            n_threads=min(4, os.cpu_count() or 4),
            verbose=False,
        )
        self._loaded = True

    async def unload(self) -> None:
        self.cancel()
        self._model = None
        self._loaded = False

    @property
    def ram_usage_mb(self) -> int:
        return 2020

    def assert_implements(self, interface: type) -> None:
        """Fail fast when this backend no longer satisfies its protocol."""
        if not isinstance(self, interface):
            raise TypeError(f"{type(self).__name__} does not implement {interface.__name__}")

    # ── internal ──────────────────────────────────────────────────────

    async def _generate_tokens(
        self,
        prompt: str,
        builder: StreamBuilder,
        channel: BoundedChunkChannel,
    ) -> None:
        """Generate tokens in a thread, pushing events into the channel."""
        try:
            assert self._model is not None
            raw = await asyncio.to_thread(
                self._model.create_completion,
                prompt=prompt,
                max_tokens=256,
                temperature=0.8,
                stream=True,
                stop=["</s>", "<|im_end|>"],
            )
            total_tokens = 0
            for chunk in raw:
                choices = chunk.get("choices", [])
                if choices:
                    text = choices[0].get("text", "")
                    if text:
                        total_tokens += 1
                        await channel.send(builder.text(text))
            await channel.send(
                builder.completed(
                    {
                        "prompt_tokens": len(prompt.split()),
                        "completion_tokens": total_tokens,
                    }
                )
            )
        except asyncio.CancelledError:
            await channel.send(builder.cancelled())
        except Exception:
            await channel.send(builder.failed(STREAM_ERR_NATIVE_FAILURE))

    def _build_prompt(self, question: str, context: GameMasterContext) -> str:
        parts = [
            "You are a Game Master for a dark fantasy interactive story.",
            "Answer the player's question using only the provided world context.",
            "",
            f"=== CURRENT SCENE ===\n{context.current_scene}\n",
            f"=== WORLD RULES ===\n{context.world_rules}\n",
        ]
        for entry in context.relevant_lore:
            parts.append(f"{entry['name']}: {entry['summary']}")
        parts.extend(
            [
                "",
                f"=== PLAYER QUESTION ===\n{question}",
                "",
                "Answer concisely and stay in-universe.",
            ]
        )
        return "\n".join(parts)

    def _resolve_model_path(self) -> Path | None:
        env_dir = os.environ.get("STORYTELLER_MODELS_DIR", "")
        project_root = Path(__file__).resolve().parent.parent.parent
        for p in (
            Path(env_dir) / self._config.file if env_dir else None,
            project_root / "ai_models" / self._config.file,
            Path.home() / ".storyteller" / "models" / self._config.file,
        ):
            if p is not None and p.is_file():
                return p
        return None
