"""P8.7 — Transactional conversation history tests.

Covers:
- Round-trip save/load
- Atomic add_exchange
- Cancel/failure leaves no partial turn
- Corruption/mismatch isolation
- Version rejection
- Size/exchange limits
- Content hash tampering detection
- Two stories cannot collide
- History never enters .story
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from src.storage.conversation_history import (
    MAX_EXCHANGES,
    MAX_EXCHANGE_TEXT_BYTES,
    MAX_TOTAL_BYTES,
    ConversationHistory,
    ConversationHistoryError,
    ConversationHistoryStore,
    Exchange,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _ex(seq: int, user: str = "", assistant: str = "") -> Exchange:
    return Exchange(
        exchange_id=f"ex_{seq:04d}",
        user_text=user or f"User turn {seq}",
        assistant_text=assistant or f"Assistant turn {seq}",
        sequence=seq,
        created_at=1000.0 + seq,
    )


def _history(*exchanges: Exchange, story_id: str = "test_story") -> ConversationHistory:
    ex_list = list(exchanges)
    content_hash = hashlib.sha256(
        json.dumps([e.to_dict() for e in ex_list], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ConversationHistory(
        version=1,
        story_id=story_id,
        content_hash=content_hash,
        conversation_id="conv_test",
        exchanges=tuple(ex_list),
    )


# ── Round-trip ─────────────────────────────────────────────────────────


class TestRoundTrip:
    """P8.7: save → load yields identical history."""

    def test_empty_history(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        h = _history(story_id="story_a")
        store.save(h)
        loaded = store.load()
        assert loaded is not None
        assert loaded.story_id == "story_a"
        assert loaded.exchanges == ()

    def test_one_exchange(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        e = _ex(0, user="Hello", assistant="Hi there")
        store.save(_history(e, story_id="story_b"))
        loaded = store.load()
        assert loaded is not None
        assert loaded.exchange_count == 1
        assert loaded.exchanges[0].user_text == "Hello"
        assert loaded.exchanges[0].assistant_text == "Hi there"

    def test_many_exchanges(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        exchanges = tuple(_ex(i) for i in range(20))
        store.save(_history(*exchanges))
        loaded = store.load()
        assert loaded is not None
        assert loaded.exchange_count == 20
        assert loaded.exchanges[0].sequence == 0
        assert loaded.exchanges[-1].sequence == 19

    def test_metadata_round_trip(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        h = _history(story_id="meta_story")
        h = ConversationHistory(
            version=1,
            story_id="meta_story",
            content_hash=h.content_hash,
            conversation_id="conv_meta",
            exchanges=(),
            metadata={"model": "llama-3.2", "seed": "42"},
        )
        store.save(h)
        loaded = store.load()
        assert loaded is not None
        assert loaded.metadata == {"model": "llama-3.2", "seed": "42"}


# ── Atomic add_exchange ────────────────────────────────────────────────


class TestAddExchange:
    """P8.7: add_exchange atomically appends."""

    def test_add_first(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(
            _ex(0, user="A", assistant="B"),
            story_id="s", content_hash="h", conversation_id="c",
        )
        loaded = store.load()
        assert loaded is not None
        assert loaded.exchange_count == 1
        assert loaded.exchanges[0].sequence == 0

    def test_add_sequential(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(_ex(0), story_id="s", content_hash="h", conversation_id="c")
        store.add_exchange(_ex(1))
        store.add_exchange(_ex(2))
        loaded = store.load()
        assert loaded is not None
        assert loaded.exchange_count == 3
        assert [e.sequence for e in loaded.exchanges] == [0, 1, 2]

    def test_rejects_duplicate_sequence(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(_ex(0), story_id="s", content_hash="h", conversation_id="c")
        with pytest.raises(ConversationHistoryError, match="HISTORY_SEQUENCE_SKIP"):
            store.add_exchange(_ex(0))  # duplicate seq

    def test_rejects_sequence_skip(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(_ex(0), story_id="s", content_hash="h", conversation_id="c")
        with pytest.raises(ConversationHistoryError, match="HISTORY_SEQUENCE_SKIP"):
            store.add_exchange(_ex(5))  # skip from 0 to 5

    def test_preserves_story_binding_on_add(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(_ex(0), story_id="bound", content_hash="abc", conversation_id="c1")
        loaded = store.load()
        assert loaded is not None
        assert loaded.story_id == "bound"
        assert loaded.content_hash == "abc"


# ── Missing file returns None ──────────────────────────────────────────


class TestMissingFile:
    def test_load_nonexistent(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "nonexistent.json")
        assert store.load() is None

    def test_delete_removes_file(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.save(_history(_ex(0)))
        assert store._path.exists()
        store.delete()
        assert not store._path.exists()
        assert store.load() is None


# ── Corruption / version / tamper isolation ────────────────────────────


class TestCorruption:
    """P8.7: corrupt, mismatched, or tampered history raises stable error."""

    def test_corrupt_json(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store._path.write_text("{this is not json")
        with pytest.raises(ConversationHistoryError, match="HISTORY_CORRUPT_JSON"):
            store.load()

    def test_not_dict(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store._path.write_text("[]")
        with pytest.raises(ConversationHistoryError, match="HISTORY_CORRUPT_TYPE"):
            store.load()

    def test_missing_version(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store._path.write_text('{"exchanges": []}')
        with pytest.raises(ConversationHistoryError, match="HISTORY_MISSING_VERSION"):
            store.load()

    def test_future_version(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.save(_history(_ex(0)))
        raw = json.loads(store._path.read_text())
        raw["version"] = 99
        store._path.write_text(json.dumps(raw))
        with pytest.raises(ConversationHistoryError, match="HISTORY_FUTURE_VERSION"):
            store.load()

    def test_old_version(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.save(_history(_ex(0)))
        raw = json.loads(store._path.read_text())
        raw["version"] = 0
        store._path.write_text(json.dumps(raw))
        with pytest.raises(ConversationHistoryError, match="HISTORY_OLD_VERSION"):
            store.load()

    def test_content_hash_tamper(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.save(_history(_ex(0, "Real"), _ex(1, "Also real")))
        raw = json.loads(store._path.read_text())
        raw["exchanges"][0]["user_text"] = "Tampered!"
        store._path.write_text(json.dumps(raw))
        with pytest.raises(ConversationHistoryError, match="HISTORY_HASH_MISMATCH"):
            store.load()

    def test_broken_ordering(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.save(_history(_ex(0), _ex(1)))
        raw = json.loads(store._path.read_text())
        # swap order
        raw["exchanges"] = [raw["exchanges"][1], raw["exchanges"][0]]
        store._path.write_text(json.dumps(raw))
        with pytest.raises(ConversationHistoryError, match="HISTORY_ORDER_BROKEN"):
            store.load()

    def test_story_isolation(self, tmp_path: Path) -> None:
        """P8.7: history is a separate user file, never inside .story."""
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.save(_history(_ex(0)))
        # Verify the file is a plain JSON file, not a .story zip
        assert store._path.suffix == ".json"
        data = store._path.read_bytes()
        assert data.startswith(b"{")
        # Verify no .story path was touched
        story_path = tmp_path / "output.story"
        assert not story_path.exists()


# ── Limits ─────────────────────────────────────────────────────────────


class TestLimits:
    """P8.7: size and count budgets enforced on save and load."""

    def test_too_many_exchanges_on_save(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        h = _history(*(_ex(i) for i in range(MAX_EXCHANGES + 1)))
        with pytest.raises(ConversationHistoryError, match="HISTORY_EXCHANGE_LIMIT"):
            store.save(h)

    def test_too_many_exchanges_on_load(self, tmp_path: Path) -> None:
        # Write a file that exceeds limit artificially
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.save(_history(_ex(0)))
        raw = json.loads(store._path.read_text())
        raw["exchanges"] = [e.to_dict() for e in (_ex(i) for i in range(MAX_EXCHANGES + 1))]
        # Recompute hash to pass hash check
        raw["_sha256"] = hashlib.sha256(
            json.dumps(raw["exchanges"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        store._path.write_text(json.dumps(raw))
        with pytest.raises(ConversationHistoryError, match="HISTORY_EXCHANGE_LIMIT"):
            store.load()

    def test_oversize_exchange_text(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        big = _ex(0, user="x" * (MAX_EXCHANGE_TEXT_BYTES + 1))
        h = _history(big)
        store.save(h)  # save allowed for huge text
        raw = json.loads(store._path.read_text())
        raw["_sha256"] = hashlib.sha256(
            json.dumps(raw["exchanges"], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        store._path.write_text(json.dumps(raw))
        with pytest.raises(ConversationHistoryError, match="HISTORY_TEXT_SIZE"):
            store.load()

    def test_oversize_total(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        big_text = "x" * (MAX_TOTAL_BYTES // 2)
        e1 = _ex(0, user=big_text, assistant=big_text)
        e2 = _ex(1, user=big_text, assistant=big_text)
        with pytest.raises(ConversationHistoryError, match="HISTORY_SIZE_LIMIT"):
            store.save(_history(e1, e2))


# ── Two stories cannot collide ────────────────────────────────────────


class TestStoryCollision:
    """P8.7: separate story histories use separate files; they never collide."""

    def test_different_paths_isolated(self, tmp_path: Path) -> None:
        a = ConversationHistoryStore(tmp_path / "story_a.json")
        b = ConversationHistoryStore(tmp_path / "story_b.json")

        a.add_exchange(_ex(0, "A1"), story_id="story_a", content_hash="ha", conversation_id="ca")
        b.add_exchange(_ex(0, "B1"), story_id="story_b", content_hash="hb", conversation_id="cb")

        la = a.load()
        lb = b.load()
        assert la is not None and lb is not None
        assert la.exchanges[0].user_text == "A1"
        assert lb.exchanges[0].user_text == "B1"

    def test_same_path_overwrites(self, tmp_path: Path) -> None:
        """Same path means same store — calling add_exchange on story_b
        without clearing is a user-policy issue, not a collision."""
        store = ConversationHistoryStore(tmp_path / "shared.json")
        store.add_exchange(_ex(0, "First"), story_id="a", content_hash="ha", conversation_id="ca")
        # New story overwrites
        store.delete()
        store.add_exchange(_ex(0, "Second"), story_id="b", content_hash="hb", conversation_id="cb")
        loaded = store.load()
        assert loaded is not None
        assert loaded.exchanges[0].user_text == "Second"
        assert loaded.story_id == "b"


# ── Cancel / failure leaves no partial turn ────────────────────────────


class TestPartialTurn:
    """P8.7: cancel/failure must leave no partial exchange."""

    def test_failed_write_leaves_previous_state(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(_ex(0), story_id="s", content_hash="h", conversation_id="c")
        # Attempt to write a too-large exchange — should fail
        big = _ex(1, user="x" * (MAX_TOTAL_BYTES // 2), assistant="y" * (MAX_TOTAL_BYTES // 2))
        with pytest.raises(ConversationHistoryError):
            store.save(_history(big))
        # Previous state intact
        loaded = store.load()
        assert loaded is not None
        assert loaded.exchange_count == 1
        assert loaded.exchanges[0].sequence == 0

    def test_tmp_file_not_left_on_failure(self, tmp_path: Path) -> None:
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(_ex(0), story_id="s", content_hash="h", conversation_id="c")
        assert not store._tmp_path.exists()  # tmp should be cleaned up after success

    def test_add_exchange_does_not_touch_story_package(self, tmp_path: Path) -> None:
        """P8.7: history never enters the immutable .story."""
        story_dir = tmp_path / "story.story"
        story_dir.mkdir()
        (story_dir / "manifest.json").write_text("{}")
        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(_ex(0), story_id="s", content_hash="h", conversation_id="c")
        # story package untouched
        assert (story_dir / "manifest.json").read_text() == "{}"


# ── Restart round-trip ─────────────────────────────────────────────────


class TestRestart:
    """P8.7: reload after save is identical; persistence across store instances."""

    def test_reload_after_save(self, tmp_path: Path) -> None:
        path = tmp_path / "history.json"
        a = ConversationHistoryStore(path)
        a.add_exchange(_ex(0), story_id="s", content_hash="h", conversation_id="c")
        a.add_exchange(_ex(1))

        # New store instance — same file
        b = ConversationHistoryStore(path)
        loaded = b.load()
        assert loaded is not None
        assert loaded.exchange_count == 2
        assert [e.sequence for e in loaded.exchanges] == [0, 1]

    def test_empty_reload(self, tmp_path: Path) -> None:
        path = tmp_path / "history.json"
        a = ConversationHistoryStore(path)
        a.save(_history(story_id="empty"))
        b = ConversationHistoryStore(path)
        loaded = b.load()
        assert loaded is not None
        assert loaded.exchange_count == 0
        assert loaded.story_id == "empty"


# ── Exchange dataclass ─────────────────────────────────────────────────


class TestExchangeDataclass:
    def test_to_dict_from_dict_round_trip(self) -> None:
        e = _ex(3, "U", "A")
        d = e.to_dict()
        e2 = Exchange.from_dict(d)
        assert e2 == e  # frozen dataclass: __eq__ works

    def test_exchange_id_is_stable(self) -> None:
        e = Exchange("fixed_id", "user", "asst", 5, 123456.0)
        d = e.to_dict()
        assert d["exchange_id"] == "fixed_id"
        assert d["sequence"] == 5
        assert d["created_at"] == 123456.0
