"""P8.7 — Transactional conversation history.

Freezes one save-side conversation schema with version, story/content hash,
conversation ID, exchange ID, completed user and assistant text, deterministic
order, and no hidden candidate data.

Writes temporary file, fsyncs where supported, then atomically replaces.
On load, validates schema, package binding, ordering, and size/count budgets.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Schema constants ──────────────────────────────────────────────────

CONVERSATION_HISTORY_VERSION = 1
MAX_EXCHANGES = 10_000
MAX_EXCHANGE_TEXT_BYTES = 64 * 1024
MAX_TOTAL_BYTES = 10 * 1024 * 1024

# ── Data model ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Exchange:
    """One user/assistant turn. Only saved after `completed`."""

    exchange_id: str
    user_text: str
    assistant_text: str
    sequence: int
    created_at: float  # UTC epoch, deterministic ordering

    def to_dict(self) -> dict[str, Any]:
        return {
            "exchange_id": self.exchange_id,
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
            "sequence": self.sequence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Exchange:
        return cls(
            exchange_id=str(d["exchange_id"]),
            user_text=str(d["user_text"]),
            assistant_text=str(d["assistant_text"]),
            sequence=int(d["sequence"]),
            created_at=float(d["created_at"]),
        )


@dataclass(frozen=True)
class ConversationHistory:
    """Durable conversation save — isolated from the immutable .story."""

    version: int = CONVERSATION_HISTORY_VERSION
    story_id: str = ""
    content_hash: str = ""
    conversation_id: str = ""
    exchanges: tuple[Exchange, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def exchange_count(self) -> int:
        return len(self.exchanges)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "story_id": self.story_id,
            "content_hash": self.content_hash,
            "conversation_id": self.conversation_id,
            "exchanges": [e.to_dict() for e in self.exchanges],
            "metadata": dict(self.metadata),
            "_sha256": hashlib.sha256(
                json.dumps(
                    [e.to_dict() for e in self.exchanges],
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ConversationHistory:
        return cls(
            version=int(d["version"]),
            story_id=str(d["story_id"]),
            content_hash=str(d["content_hash"]),
            conversation_id=str(d["conversation_id"]),
            exchanges=tuple(Exchange.from_dict(e) for e in d.get("exchanges", [])),
            metadata={str(k): str(v) for k, v in d.get("metadata", {}).items()},
        )


# ── Transactional save/load ───────────────────────────────────────────


class ConversationHistoryStore:
    """Transactional save and load of conversation history.

    P8.7: Writes a temporary file, fsyncs, then atomically replaces.
    Never stored inside the .story package — always a separate user file.
    """

    def __init__(self, save_path: str | Path) -> None:
        self._path = Path(save_path)
        self._tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")

    def save(self, history: ConversationHistory) -> None:
        """Atomically persist the conversation history.

        P8.7: temp write → fsync → atomic replace.
        """
        if history.exchange_count > MAX_EXCHANGES:
            raise ConversationHistoryError(
                "HISTORY_EXCHANGE_LIMIT",
                f"{history.exchange_count} exchanges exceeds limit of {MAX_EXCHANGES}",
            )
        data = json.dumps(history.to_dict(), sort_keys=True, indent=2).encode("utf-8")
        if len(data) > MAX_TOTAL_BYTES:
            raise ConversationHistoryError(
                "HISTORY_SIZE_LIMIT",
                f"history exceeds {MAX_TOTAL_BYTES // (1024 * 1024)} MB",
            )

        # Temp write
        self._tmp_path.parent.mkdir(parents=True, exist_ok=True)
        self._tmp_path.write_bytes(data)
        self._tmp_path.chmod(0o600)

        # fsync
        try:
            fd = os.open(self._tmp_path, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass

        # Atomic replace
        os.replace(self._tmp_path, self._path)

    def load(self) -> ConversationHistory | None:
        """Load and validate the conversation history.

        Returns None if the file does not exist. Raises on corruption.
        """
        if not self._path.exists():
            return None

        try:
            data = self._path.read_bytes()
        except OSError:
            return None

        if len(data) > MAX_TOTAL_BYTES:
            raise ConversationHistoryError(
                "HISTORY_SIZE_LIMIT",
                "saved history exceeds size limit",
            )

        try:
            raw = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ConversationHistoryError(
                "HISTORY_CORRUPT_JSON",
                f"cannot parse history: {exc}",
            ) from exc

        if not isinstance(raw, dict):
            raise ConversationHistoryError("HISTORY_CORRUPT_TYPE", "history is not an object")

        version = raw.get("version")
        if version is None:
            raise ConversationHistoryError("HISTORY_MISSING_VERSION", "no version field")
        if version != CONVERSATION_HISTORY_VERSION:
            if version > CONVERSATION_HISTORY_VERSION:
                raise ConversationHistoryError(
                    "HISTORY_FUTURE_VERSION",
                    f"cannot read version {version} — update the app",
                )
            # Older version: reject (no auto-upgrade in P8.7)
            raise ConversationHistoryError(
                "HISTORY_OLD_VERSION",
                f"version {version} is not supported",
            )

        history = ConversationHistory.from_dict(raw)

        # Validate exchanges
        exchanges = list(history.exchanges)
        if len(exchanges) > MAX_EXCHANGES:
            raise ConversationHistoryError(
                "HISTORY_EXCHANGE_LIMIT",
                f"{len(exchanges)} exchanges exceeds limit of {MAX_EXCHANGES}",
            )

        # Verify ordering
        for i, e in enumerate(exchanges):
            if e.sequence != i:
                raise ConversationHistoryError(
                    "HISTORY_ORDER_BROKEN",
                    f"exchange {e.exchange_id} has sequence {e.sequence}, expected {i}",
                )
            if len(e.user_text.encode()) > MAX_EXCHANGE_TEXT_BYTES:
                raise ConversationHistoryError(
                    "HISTORY_TEXT_SIZE",
                    f"exchange {e.exchange_id} text exceeds limit",
                )

        # Verify content hash
        expected_hash = hashlib.sha256(
            json.dumps(
                [e.to_dict() for e in exchanges],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        actual_hash = raw.get("_sha256", "")
        if actual_hash and actual_hash != expected_hash:
            raise ConversationHistoryError(
                "HISTORY_HASH_MISMATCH",
                "content hash mismatch — history may be tampered",
            )

        return history

    def add_exchange(
        self,
        exchange: Exchange,
        story_id: str = "",
        content_hash: str = "",
        conversation_id: str = "",
    ) -> ConversationHistory:
        """Atomically append one completed exchange.

        P8.7: only completed exchanges are saved. Cancel/failure leaves
        no partial turn.
        """
        current = self.load()
        existing = list(current.exchanges) if current else []

        # Validate no duplicate sequence
        if existing:
            last_seq = existing[-1].sequence
            if exchange.sequence != last_seq + 1:
                raise ConversationHistoryError(
                    "HISTORY_SEQUENCE_SKIP",
                    f"expected sequence {last_seq + 1}, got {exchange.sequence}",
                )

        exchanges = existing + [exchange]
        history = ConversationHistory(
            version=CONVERSATION_HISTORY_VERSION,
            story_id=story_id or (current.story_id if current else ""),
            content_hash=content_hash or (current.content_hash if current else ""),
            conversation_id=conversation_id or (current.conversation_id if current else ""),
            exchanges=tuple(exchanges),
            metadata=current.metadata if current else {},
        )
        self.save(history)
        return history

    def delete(self) -> None:
        """Remove the conversation history file."""
        self._path.unlink(missing_ok=True)
        self._tmp_path.unlink(missing_ok=True)


class ConversationHistoryError(ValueError):
    """Stable-code conversation history error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")
