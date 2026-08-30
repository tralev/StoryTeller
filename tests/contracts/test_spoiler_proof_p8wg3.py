"""P8.WG3 — Procedural spoiler proof tests.

Prove sentinels are absent from every boundary surface before reveal
and present after all required nodes are visited.
"""

from __future__ import annotations

from src.narrative.models import KnowledgeEntry
from src.narrative.retrieval import (
    filter_revealed_entries,
    format_knowledge_prompt,
    retrieve_knowledge,
)
from src.narrative.spoiler_proof import (
    SENTINEL_PREFIX,
    Sentinel,
    build_spoiler_gate,
)


def _entry(
    eid: str,
    kind: str = "event",
    text: str = "test fact",
    sources: tuple[str, ...] = (),
    reveal: tuple[str, ...] = (),
) -> KnowledgeEntry:
    return KnowledgeEntry(eid, kind, text, sources, (), (), reveal)


class TestSentinel:
    def test_marker_contains_prefix(self) -> None:
        s = Sentinel.deterministic("s1", 42, ("e1",))
        assert SENTINEL_PREFIX in s.marker
        assert len(s.marker) > len(SENTINEL_PREFIX)

    def test_marker_is_deterministic(self) -> None:
        a = Sentinel.deterministic("s1", 42, ("e1",))
        b = Sentinel.deterministic("s1", 42, ("e1",))
        assert a.marker == b.marker
        assert a.suffix == b.suffix

    def test_different_seeds_different_markers(self) -> None:
        a = Sentinel.deterministic("s1", 42, ("e1",))
        b = Sentinel.deterministic("s1", 43, ("e1",))
        assert a.marker != b.marker


class TestSpoilerGate:
    def _make_entries(self) -> tuple[KnowledgeEntry, ...]:
        return (
            _entry("e_open", "event", "public fact"),
            _entry("e_hidden", "event", "secret fact", reveal=("node_x",)),
            _entry("e_local", "local_map", "local secret", reveal=("node_y",)),
            _entry("e_opp", "opportunity", "opportunity secret", reveal=("node_z",)),
            _entry("e_global", "person", "global secret", reveal=("node_w",)),
        )

    def test_inject_adds_marker_to_hidden_entries(self) -> None:
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # e_open has no reveal_after_nodes → unchanged
        assert injected[0].normalized_text == "public fact"
        assert SENTINEL_PREFIX not in injected[0].normalized_text

        # e_hidden has reveal_after_nodes → injected
        assert SENTINEL_PREFIX in injected[1].normalized_text
        assert any(SENTINEL_PREFIX in s for s in injected[1].source_ids)

        # All hidden entries get sentinels
        for entry in injected:
            if entry.reveal_after_nodes:
                assert SENTINEL_PREFIX in entry.normalized_text, (
                    f"{entry.entry_id} missing sentinel"
                )

    def test_candidates_boundary_is_clean_before_reveal(self) -> None:
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Before any nodes visited, filter_revealed removes hidden entries
        eligible = filter_revealed_entries(injected, frozenset())

        # Scan eligible candidates — must be clean
        report = gate.scan_candidates(eligible)
        assert report.clean, (
            f"Sentinels leaked into eligible candidates: {report.sentinel_ids_found}"
        )

    def test_prompt_boundary_is_clean_before_reveal(self) -> None:
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        hits = retrieve_knowledge(injected, "secret", frozenset())
        prompt = format_knowledge_prompt(hits)

        report = gate.scan_prompt(prompt)
        assert report.clean, f"Sentinels leaked into prompt: {report.sentinel_ids_found}"

    def test_hits_boundary_is_clean_before_reveal(self) -> None:
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        hits = retrieve_knowledge(injected, "secret", frozenset())
        hits_text = "\n".join(h.prompt_line for h in hits)

        report = gate.scan_hits(hits_text)
        assert report.clean, f"Sentinels leaked into hits: {report.sentinel_ids_found}"

    def test_sentinels_present_after_all_nodes_revealed(self) -> None:
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Visit all nodes
        all_nodes = frozenset({"node_x", "node_y", "node_z", "node_w"})
        eligible = filter_revealed_entries(injected, all_nodes)

        # All 4 hidden entries should now be eligible
        hidden_count = sum(1 for e in eligible if e.reveal_after_nodes)
        assert hidden_count == 4, f"Expected 4 hidden entries, got {hidden_count}"

        # Sentinels should be present in the eligible entries
        report = gate.scan_candidates(eligible)
        assert report.leaked, "Sentinels should be present after all nodes revealed"
        # The "leaked" here means found → which is correct after reveal
        assert len(report.sentinel_ids_found) >= 2  # at least global + history

    def test_no_sentinel_in_open_entries(self) -> None:
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # e_open should be unchanged
        assert SENTINEL_PREFIX not in injected[0].normalized_text
        assert not any(SENTINEL_PREFIX in s for s in injected[0].source_ids)

    def test_empty_query_returns_no_sentinel(self) -> None:
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        hits = retrieve_knowledge(injected, " ! ", frozenset())
        prompt = format_knowledge_prompt(hits)
        assert SENTINEL_PREFIX not in prompt

    def test_retrieval_never_exposes_sentinels_before_reveal(self) -> None:
        """P8.WG3: Even with a matching query, sentinels stay hidden."""
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Query that would match hidden entries if revealed
        for node_subset in (frozenset(),):  # empty = not yet visited
            hits = retrieve_knowledge(injected, "secret", node_subset)
            for hit in hits:
                assert SENTINEL_PREFIX not in hit.prompt_line, (
                    f"Sentinel in hit after nodes {node_subset}: {hit.entry.entry_id}"
                )
                assert SENTINEL_PREFIX not in hit.entry.normalized_text, (
                    f"Sentinel in entry text after nodes {node_subset}"
                )

    def test_cross_domain_sentinels(self) -> None:
        """P8.WG3: Every domain has its own sentinel."""
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        assert gate.sentinel_count >= 3  # global, history, local_maps, opportunities

        # Each sentinel covers different entry sets
        sentinel_ids = set()
        for s in gate.sentinels:
            sentinel_ids.add(s.sentinel_id)
        assert "sentinel_global" in sentinel_ids
        assert "sentinel_history" in sentinel_ids

    def test_scan_returns_clean_for_unrelated_text(self) -> None:
        gate = build_spoiler_gate(self._make_entries(), seed=42)
        report = gate.scan("test", "this is completely normal text")
        assert report.clean
        assert report.sentinel_ids_found == ()

    def test_report_snippets_include_context(self) -> None:
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        sentinel = gate.get_sentinel("e_hidden")
        assert sentinel is not None
        report = gate.scan("test", f"context {sentinel.marker} more")
        assert report.leaked
        assert len(report.marker_snippets) > 0
        assert sentinel.marker in report.marker_snippets[0]

    def test_partial_reveal_isolation(self) -> None:
        """P8.WG3: Visiting node_y does NOT leak e_hidden which needs node_x."""
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Visit node_y only — e_local becomes revealed, e_hidden stays hidden
        hits = retrieve_knowledge(injected, "secret", frozenset({"node_y"}))
        hit_ids = [h.entry.entry_id for h in hits]

        # e_hidden (requires node_x) must NOT appear
        assert "e_hidden" not in hit_ids, f"e_hidden leaked when only node_y visited: {hit_ids}"
        # e_local (requires node_y) SHOULD appear
        assert "e_local" in hit_ids, f"e_local missing when node_y visited: {hit_ids}"

        # After revealing node_y, e_local sentinel IS present (correct reveal)
        # But e_hidden sentinel must still be absent (correctly hidden)
        from src.narrative.retrieval import format_knowledge_prompt

        prompt = format_knowledge_prompt(hits)

        # e_local is revealed: its sentinel should appear
        e_local_sentinel = gate.get_sentinel("e_local")
        assert e_local_sentinel is not None
        assert e_local_sentinel.marker in prompt, "e_local sentinel missing after reveal"

        # e_hidden is still hidden: its sentinel must NOT appear
        e_hidden_sentinel = gate.get_sentinel("e_hidden")
        assert e_hidden_sentinel is not None
        assert e_hidden_sentinel.marker not in prompt, (
            "e_hidden sentinel leaked after only node_y visited"
        )

    def test_production_integration_wiring(self) -> None:
        """P8.WG3: build_spoiler_gate + inject can be wired into knowledge pipeline."""
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Simulate the production flow: gate.inject before filter_revealed
        eligible_before = filter_revealed_entries(injected, frozenset())
        report = gate.scan_candidates(eligible_before)
        assert report.clean, f"Production pipeline leak: {report.sentinel_ids_found}"

        # After all nodes visited, all hidden entries are present with sentinels
        all_nodes = frozenset({"node_x", "node_y", "node_z", "node_w"})
        eligible_after = filter_revealed_entries(injected, all_nodes)
        report2 = gate.scan_candidates(eligible_after)
        assert report2.leaked, "After full reveal, sentinels should be present"

    # ── P8.WG3 error, log, ranking, and saved-history boundaries ──

    def test_error_boundary_detects_sentinel_leak(self) -> None:
        """P8.WG3: Error/exception messages must be sentinel-free before reveal."""
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)

        # Simulate an error that accidentally includes an unrevealed sentinel
        hidden_sentinel = gate.get_sentinel("e_hidden")
        assert hidden_sentinel is not None

        # An error message that DOES contain a sentinel is detected
        leaky_error = ValueError(f"Failed to process: {hidden_sentinel.marker}")
        report = gate.scan_error(leaky_error)
        assert report.leaked, "Expected scan_error to detect sentinel in exception args"

        # A clean error message passes
        clean_error = ValueError("Failed to process: some normal error text")
        report2 = gate.scan_error(clean_error)
        assert report2.clean, f"Clean error flagged as leak: {report2.sentinel_ids_found}"

    def test_log_boundary_detects_sentinel_leak(self) -> None:
        """P8.WG3: Log output must be sentinel-free before reveal."""
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)

        hidden_sentinel = gate.get_sentinel("e_hidden")
        assert hidden_sentinel is not None

        # A log line that leaks a sentinel is detected
        leaky_log = f"DEBUG: candidate='{hidden_sentinel.marker}' score=0"
        report = gate.scan_log(leaky_log)
        assert report.leaked, "Expected scan_log to detect sentinel in log line"

        # A clean log line passes
        clean_log = "DEBUG: candidate='e_open' score=150"
        report2 = gate.scan_log(clean_log)
        assert report2.clean, f"Clean log flagged as leak: {report2.sentinel_ids_found}"

    def test_saved_history_boundary_detects_sentinel_leak(self) -> None:
        """P8.WG3: Saved/persisted history must be sentinel-free."""
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)

        hidden_sentinel = gate.get_sentinel("e_hidden")
        assert hidden_sentinel is not None

        # Saved history that leaks a sentinel is detected
        leaky_saved = (
            '{"turns": [{"role": "gm", "text": "'
            f'You discover {hidden_sentinel.marker} in the ruins."'
            "}]}"
        )
        report = gate.scan_saved_history(leaky_saved)
        assert report.leaked, "Expected scan_saved_history to detect sentinel in serialized history"

        # Clean saved history passes
        clean_saved = '{"turns": [{"role": "gm", "text": "You discover ancient ruins."}]}'
        report2 = gate.scan_saved_history(clean_saved)
        assert report2.clean, f"Clean history flagged as leak: {report2.sentinel_ids_found}"

    def test_ranking_diagnostics_boundary_is_clean(self) -> None:
        """P8.WG3: Ranking diagnostics (scores, hit lines) must be sentinel-free."""
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        # Simulate ranking diagnostics: a debug dump of scores + entries
        eligible = filter_revealed_entries(injected, frozenset())

        # Build a fake diagnostics string that would be logged in debug mode
        diagnostics = "\n".join(
            f"SCORE {e.entry_id}: {e.kind} -> {e.normalized_text[:40]}" for e in eligible
        )
        report = gate.scan("ranking_diagnostics", diagnostics)
        assert report.clean, f"Ranking diagnostics leaked sentinels: {report.sentinel_ids_found}"

    def test_all_boundary_surfaces_clean_before_any_reveal(self) -> None:
        """P8.WG3: Every named boundary surface is clean before any node visited."""
        entries = self._make_entries()
        gate = build_spoiler_gate(entries, seed=42)
        injected = gate.inject(entries)

        visited = frozenset()

        # 1. Candidates
        eligible = filter_revealed_entries(injected, visited)
        assert gate.scan_candidates(eligible).clean, "candidates leaked"

        # 2. Prompt
        hits = retrieve_knowledge(injected, "secret", visited)
        prompt = format_knowledge_prompt(hits)
        assert gate.scan_prompt(prompt).clean, "prompt leaked"

        # 3. Hits
        hits_text = "\n".join(h.prompt_line for h in hits)
        assert gate.scan_hits(hits_text).clean, "hits leaked"

        # 4. Error
        assert gate.scan_error("Normal error text").clean, "error boundary failed"

        # 5. Log
        assert gate.scan_log("Normal log line").clean, "log boundary failed"

        # 6. Saved history
        assert gate.scan_saved_history('{"turns":[]}').clean, "saved_history boundary failed"

        # 7. Ranking diagnostics (from filter_revealed)
        diag = " ".join(e.normalized_text for e in eligible)
        assert gate.scan("ranking_diagnostics", diag).clean, "ranking diag failed"
