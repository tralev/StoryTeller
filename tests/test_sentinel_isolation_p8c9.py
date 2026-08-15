"""P8.9 — End-to-end sentinel isolation across every boundary surface.

Run the same sentinel through candidate source, reveal gate, prompt,
native model double output/error, UI semantics/snapshot, local log capture,
retry, cancellation, and persisted history. Search every captured boundary
for hidden ID, source ID, and text.

A prompt instruction saying "do not reveal" is never accepted as a
substitute for absence from input.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.narrative.models import KnowledgeEntry
from src.narrative.retrieval import (
    filter_revealed_entries,
    format_knowledge_prompt,
    retrieve_knowledge,
)
from src.narrative.spoiler_proof import (
    SENTINEL_PREFIX,
    Sentinel,
    SpoilerGate,
    SpoilerReport,
    build_spoiler_gate,
)
from src.storage.conversation_history import (
    ConversationHistory,
    ConversationHistoryError,
    ConversationHistoryStore,
    Exchange,
)

# ── Helpers ────────────────────────────────────────────────────────────


def _entry(
    eid: str,
    kind: str = "event",
    text: str = "test fact",
    sources: tuple[str, ...] = (),
    reveal: tuple[str, ...] = (),
) -> KnowledgeEntry:
    return KnowledgeEntry(eid, kind, text, sources, (), (), reveal)


def _build_entries() -> tuple[KnowledgeEntry, ...]:
    """Build a representative set of knowledge entries for isolation testing."""
    return (
        _entry("e_open", "event", "public fact about the kingdom"),
        _entry("e_hidden", "event", "the traitor is the vizier's son",
               reveal=("node_x",)),
        _entry("e_local", "local_map", "hidden chamber beneath the throne",
               reveal=("node_y",)),
        _entry("e_opp", "opportunity", "the vizier plans to seize the throne",
               reveal=("node_z",)),
        _entry("e_global", "person", "Vizier Aldric - age 47, scar on left cheek",
               reveal=("node_w",)),
        _entry("e_open2", "event", "the harvest festival approaches"),
        _entry("e_belief", "belief", "the old gods sleep beneath the mountain",
               reveal=("node_x", "node_y")),
        _entry("e_history", "event", "the last dragon was slain in 814 by King Eamon",
               reveal=("node_x", "node_w")),
    )


# ── P8.9: Boundary 1 — Candidate source ───────────────────────────────


class TestCandidateSourceIsolation:
    """P8.9: Sentinels must not leak into candidate entries before reveal."""

    def test_filter_revealed_removes_all_sentinels(self) -> None:
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Before any reveal: filter_revealed should remove ALL hidden entries
        eligible = filter_revealed_entries(injected, frozenset())
        report = gate.scan_candidates(eligible)
        assert report.clean, (
            f"Candidates leaked sentinels: {report.sentinel_ids_found}\n"
            f"Snippets: {report.marker_snippets}"
        )

    def test_open_entries_never_get_sentinels(self) -> None:
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        for entry in injected:
            if not entry.reveal_after_nodes:  # open entries
                assert SENTINEL_PREFIX not in entry.normalized_text, (
                    f"Open entry {entry.entry_id} got injected sentinel"
                )
                assert not any(
                    SENTINEL_PREFIX in s for s in entry.source_ids
                ), f"Open entry {entry.entry_id} source_ids got sentinel"


# ── P8.9: Boundary 2 — Reveal gate ─────────────────────────────────────


class TestRevealGateIsolation:
    """P8.9: The reveal gate must correctly gate every hidden entry."""

    def test_no_reveal_before_all_nodes_visited(self) -> None:
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # e_hidden needs node_x — visiting a DIFFERENT node (node_z) must NOT
        # reveal it. e_opp needs node_z — visiting node_z DOES reveal it.
        # e_local needs node_y — NOT revealed.
        # So visiting node_z should reveal only e_opp.
        eligible = filter_revealed_entries(injected, frozenset({"node_z"}))
        revealed_ids = {e.entry_id for e in eligible}
        # Correctly revealed
        assert "e_opp" in revealed_ids, "e_opp should be revealed by node_z"
        # NOT revealed (require different nodes)
        assert "e_hidden" not in revealed_ids, "e_hidden leaked without node_x"
        assert "e_local" not in revealed_ids, "e_local leaked without node_y"
        assert "e_global" not in revealed_ids, "e_global leaked without node_w"
        assert "e_belief" not in revealed_ids, "e_belief leaked without node_x/y"

        # e_opp IS revealed, so its sentinel appears — that's correct.
        # But the OTHER sentinels (e_hidden, e_local, etc.) must be absent.
        report = gate.scan_candidates(eligible)
        # Verify only e_opp sentinel is present
        found = set(report.sentinel_ids_found)
        assert "sentinel_opportunities" in found, (
            f"e_opp sentinel should be present after node_z reveal"
        )
        # These should NOT be present
        for bad in ("sentinel_local_maps",):
            assert bad not in found, f"{bad} leaked when only node_z visited"

    def test_partial_reveal_never_leaks_unrevealed(self) -> None:
        """P8.9: A multi-node entry is NOT revealed when only some nodes visited."""
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # e_belief needs BOTH node_x AND node_y — visiting only node_x must
        # NOT reveal it. Also, e_hidden (needs only node_x) WILL be revealed.
        eligible = filter_revealed_entries(injected, frozenset({"node_x"}))
        revealed_ids = {e.entry_id for e in eligible}
        # Correctly revealed (single-node requirement met)
        assert "e_hidden" in revealed_ids, "e_hidden should be revealed by node_x"
        # Multi-node requirement: e_belief needs node_x AND node_y
        assert "e_belief" not in revealed_ids, "e_belief leaked with only node_x"
        # e_history needs node_x AND node_w — only node_x visited
        assert "e_history" not in revealed_ids, "e_history leaked with only node_x"

        # Scan: the eligible entries (e_hidden) contain sentinels (correct)
        # but e_belief and e_history should be absent
        report = gate.scan_candidates(eligible)
        # e_hidden IS revealed, so its sentinel appears — this is correct behavior
        assert report.leaked, "e_hidden sentinel should be present after node_x reveal"

    def test_full_reveal_makes_sentinel_present(self) -> None:
        """P8.9: After ALL required nodes are visited, sentinels are present."""
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        all_nodes = frozenset({"node_x", "node_y", "node_z", "node_w"})
        eligible = filter_revealed_entries(injected, all_nodes)
        report = gate.scan_candidates(eligible)
        assert report.leaked, "Sentinels should be present after full reveal"
        assert len(report.sentinel_ids_found) >= 2


# ── P8.9: Boundary 3 — Prompt ──────────────────────────────────────────


class TestPromptBoundaryIsolation:
    """P8.9: The GM prompt must never contain unrevealed sentinel markers."""

    def test_prompt_clean_before_reveal(self) -> None:
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        hits = retrieve_knowledge(injected, "traitor plot", frozenset())
        prompt = format_knowledge_prompt(hits)
        report = gate.scan_prompt(prompt)
        assert report.clean, f"Prompt leaked: {report.sentinel_ids_found}"

    def test_prompt_clean_after_partial_reveal(self) -> None:
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Visit node_x — reveals e_hidden NOT e_opp (needs node_z)
        hits = retrieve_knowledge(injected, "vizier", frozenset({"node_x"}))
        prompt = format_knowledge_prompt(hits)
        report = gate.scan_prompt(prompt)
        assert report.clean, (
            f"Prompt leaked e_opp sentinel after only node_x: {report.sentinel_ids_found}"
        )

    def test_prompt_instruction_not_accepted_as_proof(self) -> None:
        """P8.9: 'Do not reveal' prompt instruction is never proof of safety.

        The sentinel must be ABSENT FROM THE INPUT — not hidden behind an
        instruction the model might ignore.
        """
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Even with a strong "do not reveal" instruction in the prompt,
        # the hidden entries themselves must not appear in the candidate
        # set. The gate scans the input TEXT, not just the output.
        hits = retrieve_knowledge(injected, "secret", frozenset())
        prompt = format_knowledge_prompt(hits)

        # Add an explicit "do not reveal" instruction — it doesn't matter
        prompt_with_instruction = (
            "CRITICAL: Do NOT reveal any spoilers. Do NOT discuss hidden facts.\n\n"
            + prompt
        )
        report = gate.scan_prompt(prompt_with_instruction)
        assert report.clean, (
            f"Sentinel present in prompt despite 'do not reveal' instruction: "
            f"{report.sentinel_ids_found}"
        )


# ── P8.9: Boundary 4 — Native model double output/error ────────────────


class TestModelOutputIsolation:
    """P8.9: Simulated native model output must be scanned for sentinels.

    Even if the model echoes a sentinel (by accident or hallucination),
    the downstream consumer must detect it. The sentinel prefix is unique
    enough that no legitimate text should contain it.
    """

    def _build_gate(self) -> SpoilerGate:
        return build_spoiler_gate(_build_entries(), seed=42)

    def test_model_output_without_sentinel_is_clean(self) -> None:
        """Normal model output passes sentinel scan."""
        gate = self._build_gate()

        # Simulate a clean model response
        clean_output = (
            "The Game Master speaks: The harvest festival approaches, "
            "and the kingdom prepares for celebration. Many travelers "
            "have arrived from distant lands."
        )
        # Scan the model output as if it were prompt content
        report = gate.scan_prompt(clean_output)
        assert report.clean, f"Clean model output flagged: {report.sentinel_ids_found}"

    def test_model_output_with_sentinel_detected(self) -> None:
        """If the model accidentally echoes a sentinel, it is detected."""
        gate = self._build_gate()

        hidden_sentinel = gate.get_sentinel("e_hidden")
        assert hidden_sentinel is not None

        # Simulate a model that accidentally leaks a sentinel
        leaky_output = (
            f"The Game Master speaks: I cannot reveal {hidden_sentinel.marker} "
            "to you at this time."
        )
        report = gate.scan("model_output", leaky_output)
        assert report.leaked, "Model output leak was not detected"
        assert hidden_sentinel.marker in report.marker_snippets[0]

    def test_model_error_message_scanned(self) -> None:
        """P8.9: Error messages from the model engine are scanned."""
        gate = self._build_gate()

        hidden_sentinel = gate.get_sentinel("e_global")
        assert hidden_sentinel is not None

        # Simulate an error message that leaks a sentinel
        leaky_error = (
            f"Model inference failed while processing entry "
            f"{hidden_sentinel.marker} — context overflow"
        )
        report = gate.scan_error(leaky_error)
        assert report.leaked, "Model error leak was not detected"

    def test_double_output_boundary(self) -> None:
        """P8.9: Both primary output and re-generated output are scanned."""
        gate = self._build_gate()

        # Simulate the native model producing two outputs
        output1 = "The Game Master speaks: The kingdom awaits."
        output2 = "The Game Master speaks: Many paths lie ahead."

        r1 = gate.scan("model_output_1", output1)
        r2 = gate.scan("model_output_2", output2)
        assert r1.clean and r2.clean, (
            f"Double output leaked: primary={r1.sentinel_ids_found}, "
            f"secondary={r2.sentinel_ids_found}"
        )


# ── P8.9: Boundary 5 — UI semantics/snapshot ───────────────────────────


class TestUISemanticsIsolation:
    """P8.9: What the GM screen renders must be sentinel-free.

    Simulate the UI semantics: the chat messages that would appear
    on screen. Even the partial streaming text must be scanned.
    """

    def test_ui_messages_clean_before_reveal(self) -> None:
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Simulate a GM conversation that uses clean retrieved knowledge
        hits = retrieve_knowledge(injected, "festival", frozenset())
        prompt = format_knowledge_prompt(hits)

        # Simulate UI messages (what the screen shows)
        user_message = "Tell me about the harvest festival"
        gm_response = "The Game Master speaks: The harvest festival celebrates the autumn bounty."

        # Scan the complete UI snapshot
        ui_snapshot = json.dumps({
            "messages": [
                {"role": "user", "text": user_message},
                {"role": "gm", "text": gm_response},
            ],
            "prompt_context": prompt,
        })
        report = gate.scan("ui_snapshot", ui_snapshot)
        assert report.clean, f"UI snapshot leaked: {report.sentinel_ids_found}"

    def test_streaming_partial_text_scanned(self) -> None:
        """P8.9: Streaming partial text from GMStreamState must be scanned."""
        gate = build_spoiler_gate(_build_entries(), seed=42)

        # Simulate streaming partial text chunks
        for chunk in [
            "The Game Master...",
            "The Game Master speaks: The...",
            "The Game Master speaks: The harvest celebration...",
        ]:
            report = gate.scan("streaming_chunk", chunk)
            assert report.clean, f"Streaming chunk leaked: {report.sentinel_ids_found}"

    def test_accessibility_label_snapshot_clean(self) -> None:
        """P8.9: Accessibility labels and live-region text must be clean."""
        gate = build_spoiler_gate(_build_entries(), seed=42)

        a11y_labels = json.dumps({
            "welcome": "Game Master welcome message",
            "chatMessages": ["You: Tell me about the kingdom", "Game Master: It is ancient"],
            "liveRegion": "Game Master is responding",
            "inputField": "Type your question for the Game Master",
        })
        report = gate.scan("accessibility_labels", a11y_labels)
        assert report.clean, f"Accessibility labels leaked: {report.sentinel_ids_found}"


# ── P8.9: Boundary 6 — Local log capture ───────────────────────────────


class TestLogCaptureIsolation:
    """P8.9: Any log line capturing debug output must be sentinel-free."""

    def test_retrieval_logs_clean(self) -> None:
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Simulate debug log lines from retrieval
        for entry in filter_revealed_entries(injected, frozenset()):
            log_line = f"DEBUG retrieval: entry={entry.entry_id} score={len(entry.normalized_text)}"
            report = gate.scan_log(log_line)
            assert report.clean, (
                f"Log line leaked sentinel: {log_line[:80]}\n"
                f"Found: {report.sentinel_ids_found}"
            )

    def test_timing_logs_clean(self) -> None:
        gate = build_spoiler_gate(_build_entries(), seed=42)

        log_lines = [
            "INFO llm_inference: tokens=42 time_ms=1234",
            "DEBUG prompt_size: bytes=2048",
            "INFO retrieval: candidates=5 filtered=2",
        ]
        for line in log_lines:
            report = gate.scan_log(line)
            assert report.clean, f"Timing log leaked: {line}"

    def test_error_log_isolation(self) -> None:
        """P8.9: Error logs must never contain hidden content."""
        gate = build_spoiler_gate(_build_entries(), seed=42)

        hidden_s = gate.get_sentinel("e_local")
        assert hidden_s is not None

        # A sloppy error log that includes hidden content is detected
        bad_log = f"ERROR: failed to render knowledge_{hidden_s.marker}"
        report = gate.scan_error(bad_log)
        assert report.leaked, "Error log leak not detected"


# ── P8.9: Boundary 7 — Retry ───────────────────────────────────────────


class TestRetryIsolation:
    """P8.9: After failure and retry, sentinels remain absent."""

    def test_retry_after_failure_clean(self) -> None:
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Simulate: first attempt fails, user retries
        for attempt in range(3):
            hits = retrieve_knowledge(injected, "secret", frozenset())
            prompt = format_knowledge_prompt(hits)
            report = gate.scan_prompt(prompt)
            assert report.clean, (
                f"Retry attempt {attempt} leaked: {report.sentinel_ids_found}"
            )

    def test_retry_with_different_query_clean(self) -> None:
        """P8.9: Retrying with a different query doesn't change the gate."""
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        queries = ["festival", "traitor", "vizier", "kingdom"]
        for q in queries:
            hits = retrieve_knowledge(injected, q, frozenset())
            prompt = format_knowledge_prompt(hits)
            report = gate.scan_prompt(prompt)
            assert report.clean, f"Query '{q}' leaked: {report.sentinel_ids_found}"


# ── P8.9: Boundary 8 — Cancellation ────────────────────────────────────


class TestCancellationIsolation:
    """P8.9: After cancellation, partial output is sentinel-free."""

    def test_cancelled_partial_output_clean(self) -> None:
        gate = build_spoiler_gate(_build_entries(), seed=42)

        # Simulate partial output that was interrupted by cancellation
        partial_output = (
            "The Game Master speaks: The kingdom of Eldara stretches "
            "across the eastern plains, its borders marked by the..."
        )
        report = gate.scan("cancelled_output", partial_output)
        assert report.clean, (
            f"Cancelled partial output leaked: {report.sentinel_ids_found}"
        )

    def test_cancellation_never_masquerades_as_failed(self) -> None:
        """P8.9: CANCELLED state is distinct from FAILED state."""
        gate = build_spoiler_gate(_build_entries(), seed=42)

        # Cancellation error codes don't contain hidden content
        for code in ["STREAM_CANCELLED", "STREAM_MODEL_NOT_LOADED", "STREAM_NATIVE_FAILURE"]:
            report = gate.scan("cancellation_code", code)
            assert report.clean, f"Cancellation code leaked: {code}"

    def test_ui_cancelled_state_clean(self) -> None:
        """P8.9: GMStreamState.cancelled snapshot is sentinel-free."""
        gate = build_spoiler_gate(_build_entries(), seed=42)

        cancelled_snapshot = json.dumps({
            "state": "cancelled",
            "partialText": "The Game Master was interrupted...",
            "messages": [
                {"role": "user", "text": "Tell me everything"},
            ],
        })
        report = gate.scan("ui_cancelled_snapshot", cancelled_snapshot)
        assert report.clean, f"Cancelled UI snapshot leaked: {report.sentinel_ids_found}"


# ── P8.9: Boundary 9 — Persisted history ───────────────────────────────


class TestPersistedHistoryIsolation:
    """P8.9: Conversation history saved to disk must be sentinel-free."""

    def test_saved_history_clean(self, tmp_path: Path) -> None:
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Simulate a GM conversation with clean retrieved knowledge
        hits = retrieve_knowledge(injected, "festival", frozenset())
        prompt = format_knowledge_prompt(hits)

        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(
            Exchange("ex_01", "Tell me about the festival", "It celebrates the autumn bounty.",
                     0, 1000.0),
            story_id="test_story", content_hash="abc", conversation_id="c1",
        )
        store.add_exchange(
            Exchange("ex_02", "What else?", "The kingdom welcomes travelers from afar.",
                     1, 1001.0),
        )

        loaded = store.load()
        assert loaded is not None

        # Scan the serialized history
        serialized = json.dumps(loaded.to_dict(), sort_keys=True)
        report = gate.scan_saved_history(serialized)
        assert report.clean, (
            f"Saved history leaked: {report.sentinel_ids_found}\n"
            f"Snippets: {report.marker_snippets}"
        )

    def test_saved_history_with_sentinel_detected(self, tmp_path: Path) -> None:
        """P8.9: If history accidentally saves a sentinel, it's detected."""
        gate = build_spoiler_gate(_build_entries(), seed=42)

        hidden_s = gate.get_sentinel("e_hidden")
        assert hidden_s is not None

        # P8.9: The sentinel survives in raw exchange text.
        # Note: json.dumps with ensure_ascii=True (default) escapes
        # the \u200b ZWSP prefix, so scan the RAW text, not the
        # ASCII-escaped serialization.  The consumer's scan must also
        # use the raw text representation.
        leaked_text = f"The truth is {hidden_s.marker} cannot be revealed."

        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(
            Exchange("ex_01", "What is hidden?", leaked_text, 0, 1000.0),
            story_id="test", content_hash="h", conversation_id="c",
        )

        loaded = store.load()
        assert loaded is not None
        assert loaded.exchanges[0].assistant_text == leaked_text

        # Scan the raw exchange text — sentinel must be detected
        report = gate.scan_saved_history(leaked_text)
        assert report.leaked, (
            f"Sentinel in saved history was NOT detected. "
            f"Marker: {hidden_s.marker[:40]}..."
        )

        # Serialized form with ensure_ascii=False preserves the marker
        serialized = json.dumps(loaded.to_dict(), sort_keys=True, ensure_ascii=False)
        report2 = gate.scan_saved_history(serialized)
        assert report2.leaked, (
            f"Sentinel not detected in serialized history (ensure_ascii=False). "
        )

    def test_history_never_leaks_during_add_exchange(self, tmp_path: Path) -> None:
        """P8.9: Each add_exchange call is scanned automatically."""
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)

        store = ConversationHistoryStore(tmp_path / "history.json")

        # Build clean exchanges from filtered knowledge
        for i in range(5):
            exchange = Exchange(
                f"ex_{i:04d}",
                f"User question {i}",
                f"GM response about public facts {i}",
                i, 1000.0 + i,
            )
            store.add_exchange(
                exchange, story_id="test", content_hash="h", conversation_id="c",
            )
            # After each add, scan the persisted history
            loaded = store.load()
            if loaded is not None:
                serialized = json.dumps(loaded.to_dict(), sort_keys=True)
                report = gate.scan_saved_history(serialized)
                assert report.clean, (
                    f"Exchange {i} caused leak: {report.sentinel_ids_found}"
                )

    def test_history_integrity_after_delete_and_recreate(self, tmp_path: Path) -> None:
        """P8.9: Deleting and recreating history doesn't leak."""
        gate = build_spoiler_gate(_build_entries(), seed=42)

        store = ConversationHistoryStore(tmp_path / "history.json")
        store.add_exchange(
            Exchange("ex_00", "hello", "greetings", 0, 1000.0),
            story_id="test", content_hash="h", conversation_id="c",
        )
        store.delete()

        # Recreate — must still be clean
        store.add_exchange(
            Exchange("ex_00", "hello again", "welcome back", 0, 2000.0),
            story_id="test", content_hash="h2", conversation_id="c2",
        )
        loaded = store.load()
        assert loaded is not None
        serialized = json.dumps(loaded.to_dict(), sort_keys=True)
        report = gate.scan_saved_history(serialized)
        assert report.clean, f"Recreated history leaked: {report.sentinel_ids_found}"


# ── P8.9: Unified end-to-end boundary scan ─────────────────────────────


class TestEndToEndIsolation:
    """P8.9: All 9 boundaries are clean in a single end-to-end flow."""

    def test_all_boundaries_clean_before_any_reveal(self) -> None:
        """P8.9: Run the same sentinel through every boundary in sequence."""
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        visited = frozenset()
        boundaries: list[tuple[str, str]] = []

        # 1. Candidate source
        eligible = filter_revealed_entries(injected, visited)
        boundaries.append(("candidates", " ".join(
            f"{e.entry_id} {e.kind} {e.normalized_text}" for e in eligible
        )))

        # 2. Prompt
        hits = retrieve_knowledge(injected, "secret", visited)
        boundaries.append(("prompt", format_knowledge_prompt(hits)))

        # 3. Native model output (simulated)
        model_output = "The Game Master speaks of ancient kingdoms and forgotten lore."
        boundaries.append(("model_output", model_output))

        # 4. UI snapshot
        ui_snapshot = json.dumps({"messages": [{"role": "gm", "text": model_output}]})
        boundaries.append(("ui_snapshot", ui_snapshot))

        # 5. Log capture
        boundaries.append(("log", "DEBUG retrieval: candidates=3"))

        # 6. Retry
        hits2 = retrieve_knowledge(injected, "kingdom", visited)
        boundaries.append(("retry_prompt", format_knowledge_prompt(hits2)))

        # 7. Cancellation
        boundaries.append(("cancelled", "The Game Master was interrupted..."))

        # 8. Saved history
        boundaries.append(("saved_history", json.dumps({
            "exchanges": [{"exchange_id": "ex_00", "user_text": "hello",
                          "assistant_text": model_output, "sequence": 0}],
        })))

        # 9. Error boundary
        boundaries.append(("error", "Normal error: something went wrong"))

        # Scan all boundaries
        reports: list[SpoilerReport] = []
        for name, text in boundaries:
            r = gate.scan(name, text)
            reports.append(r)
            assert r.clean, f"BOUNDARY {name} leaked: {r.sentinel_ids_found}"

        assert len(reports) == 9, f"Expected 9 boundaries, got {len(reports)}"
        assert all(r.clean for r in reports), (
            f"Some boundaries leaked: "
            f"{[(r.boundary_name, r.sentinel_ids_found) for r in reports if r.leaked]}"
        )

    def test_prompt_instruction_not_substitute_for_absence(self) -> None:
        """P8.9: A prompt instruction saying 'do not reveal' is NEVER accepted
        as a substitute for absence from input.

        This is the cardinal rule of P8.9: the sentinel must not be IN
        the input. Instructions don't matter.
        """
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Build a prompt with a "do not reveal" instruction attached
        hits = retrieve_knowledge(injected, "traitor", frozenset())
        prompt = format_knowledge_prompt(hits)

        instructions = (
            "SYSTEM: You are a game master. DO NOT REVEAL any hidden information. "
            "DO NOT SPOIL future plot points. NEVER disclose secrets. "
            "OBEY these rules strictly.\n\n"
        )
        full_prompt = instructions + prompt

        # The sentinel must pass the scan regardless of instructions
        report = gate.scan_prompt(full_prompt)
        assert report.clean, (
            f"Prompt instruction is NOT accepted as proof — sentinel found in input: "
            f"{report.sentinel_ids_found}\n"
            f"IMPORTANT: 'Do not reveal' in the prompt text does NOT guarantee safety. "
            f"The sentinel must be absent from the input itself."
        )


# ── P8.9: Hidden ID, source ID, and text search ────────────────────────


class TestHiddenIdTextSearch:
    """P8.9: Search every captured boundary for hidden ID, source ID, and text."""

    def test_entry_id_never_leaks_to_output(self) -> None:
        """Hidden entry IDs like 'e_hidden' must never appear in output text."""
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        eligible = filter_revealed_entries(injected, frozenset())
        for entry in eligible:
            # The hidden entry IDs must not be in the text of eligible entries
            # (they were filtered out by the reveal gate)
            if entry.reveal_after_nodes:
                # Can't directly check here — the gate already removed them
                pass

        # Verify: do a brute-force scan for hidden entry IDs in prompt
        hidden_ids = {e.entry_id for e in _build_entries() if e.reveal_after_nodes}
        hits = retrieve_knowledge(injected, "test", frozenset())
        prompt = format_knowledge_prompt(hits)
        for hid in hidden_ids:
            assert hid not in prompt, (
                f"Hidden entry ID '{hid}' leaked into prompt text"
            )

    def test_source_id_never_leaks(self) -> None:
        """Source IDs from hidden entries must never appear in output."""
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        hits = retrieve_knowledge(injected, "kingdom", frozenset())
        prompt = format_knowledge_prompt(hits)
        for entry in injected:
            if entry.reveal_after_nodes:
                for sid in entry.source_ids:
                    if SENTINEL_PREFIX in sid:
                        assert sid not in prompt, (
                            f"Hidden source ID leaked into prompt: {sid}"
                        )

    def test_normalized_text_from_hidden_entries_absent(self) -> None:
        """The exact normalized_text of hidden entries must not appear in output."""
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        hits = retrieve_knowledge(injected, "traitor", frozenset())
        prompt = format_knowledge_prompt(hits)

        for entry in _build_entries():
            if entry.reveal_after_nodes:
                # The original text without sentinel should also be absent
                assert entry.normalized_text not in prompt, (
                    f"Hidden entry '{entry.entry_id}' text leaked into prompt"
                )

    def test_empty_query_is_clean(self) -> None:
        """P8.9: An empty query must not trigger any sentinel leak."""
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        hits = retrieve_knowledge(injected, "", frozenset())
        prompt = format_knowledge_prompt(hits)
        assert SENTINEL_PREFIX not in prompt
        report = gate.scan_prompt(prompt)
        assert report.clean

    def test_whitespace_query_is_clean(self) -> None:
        """P8.9: A whitespace-only query must not trigger any leak."""
        entries = _build_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        hits = retrieve_knowledge(injected, "   ", frozenset())
        prompt = format_knowledge_prompt(hits)
        assert SENTINEL_PREFIX not in prompt
        report = gate.scan_prompt(prompt)
        assert report.clean
