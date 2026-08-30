"""P8.WG2 — Scoring controller unit tests.

Prove every integer scoring dimension is deterministic and platform-independent.
"""

from __future__ import annotations

from src.narrative.models import KnowledgeEntry
from src.narrative.scoring import SCORING, KindWeights


def _entry(
    entry_id: str = "test_001",
    kind: str = "person",
    text: str = "test entry",
    source_ids: tuple[str, ...] = (),
    incoming: tuple[str, ...] = (),
    outgoing: tuple[str, ...] = (),
    reveal: tuple[str, ...] = (),
) -> KnowledgeEntry:
    return KnowledgeEntry(entry_id, kind, text, source_ids, incoming, outgoing, reveal)


class TestKindWeights:
    def test_person_ranks_above_location(self) -> None:
        kw = KindWeights()
        assert kw.for_kind("person") > kw.for_kind("location")
        assert kw.for_kind("creature") > kw.for_kind("event")

    def test_unknown_kind_falls_back_to_default(self) -> None:
        assert KindWeights().for_kind("nonexistent_kind_xyz") == 50

    def test_all_kinds_have_positive_weights(self) -> None:
        kw = KindWeights()
        for kind in (
            "creature",
            "person",
            "event",
            "civilization",
            "settlement",
            "site",
            "location",
            "region",
            "route",
            "artifact",
            "opportunity",
            "local_map",
            "graph_node",
            "story_scene",
            "bible_local",
            "ecology",
            "registries",
            "identities",
            "cohort",
        ):
            assert kw.for_kind(kind) > 0, f"{kind} weight must be positive"


class TestScoringController:
    def test_zero_score_when_no_tokens_match(self) -> None:
        entry = _entry(kind="location", text="far away place")
        score = SCORING.score(entry, frozenset(("dragon",)), "dragon")
        assert score == 0

    def test_kind_weight_adds_base_score(self) -> None:
        entry = _entry(kind="creature", text="the ash dragon sleeps")
        score = SCORING.score(entry, frozenset(("dragon",)), "dragon")
        assert score >= 200  # creature base

    def test_person_ranks_higher_than_location_for_same_query(self) -> None:
        person = _entry("p1", "person", "guards the eastern gate")
        location = _entry("l1", "location", "the eastern gate")
        tokens = frozenset(("eastern", "gate"))
        sp = SCORING.score(person, tokens, "eastern gate")
        sl = SCORING.score(location, tokens, "eastern gate")
        assert sp > sl, f"person ({sp}) should outrank location ({sl})"

    def test_exact_phrase_bonus(self) -> None:
        entry = _entry(kind="artifact", text="the moon rune")
        exact = SCORING.score(entry, frozenset(("moon", "rune")), "moon rune")
        partial = SCORING.score(entry, frozenset(("moon",)), "moon")
        assert exact > partial

    def test_current_node_boost(self) -> None:
        entry = _entry(reveal=("node_x",))
        base = SCORING.score(entry, frozenset(("test",)), "test")
        boosted = SCORING.score(entry, frozenset(("test",)), "test", current_node_id="node_x")
        assert boosted > base, f"{boosted} should be > {base}"

    def test_current_node_no_boost_wrong_node(self) -> None:
        entry = _entry(reveal=("node_x",))
        base = SCORING.score(entry, frozenset(("test",)), "test")
        other = SCORING.score(entry, frozenset(("test",)), "test", current_node_id="node_y")
        assert other == base

    def test_visited_source_boost(self) -> None:
        entry = _entry(source_ids=("creature_dragon",), text="the dragon")
        base = SCORING.score(entry, frozenset(("dragon",)), "dragon")
        with_visited = SCORING.score(
            entry, frozenset(("dragon",)), "dragon", visited_refs=frozenset(("creature_dragon",))
        )
        assert with_visited > base

    def test_containment_boost(self) -> None:
        entry = _entry(outgoing=("site_gate",))
        base = SCORING.score(entry, frozenset(("test",)), "test")
        with_containment = SCORING.score(
            entry, frozenset(("test",)), "test", visited_refs=frozenset(("site_gate",))
        )
        assert with_containment > base

    def test_exact_source_boost(self) -> None:
        entry = _entry(source_ids=("creature_wyrm",), text="a wyrm")
        with_source = SCORING.score(entry, frozenset(("wyrm",)), "wyrm")
        # "wyrm" is substring of "creature_wyrm" → exact_source boost
        score_no_source = SCORING.score(entry, frozenset(("dragon",)), "dragon")
        assert with_source > score_no_source

    def test_recency_boost(self) -> None:
        entry = _entry(reveal=("node_a",))
        base = SCORING.score(entry, frozenset(("test",)), "test")
        recent = SCORING.score(entry, frozenset(("test",)), "test", recency_rank=0)
        old = SCORING.score(entry, frozenset(("test",)), "test", recency_rank=10)
        assert recent > old
        assert base < recent

    def test_recency_decays_to_zero(self) -> None:
        entry = _entry(reveal=("node_a",))
        far = SCORING.score(entry, frozenset(("test",)), "test", recency_rank=100)
        base = SCORING.score(entry, frozenset(("test",)), "test")
        assert far == base  # recency decayed to 0

    def test_rank_key_stable_tie_break(self) -> None:
        e1 = _entry("knowledge_guard")
        e2 = _entry("knowledge_gate")
        k1 = SCORING.rank_key(e1, 100)
        k2 = SCORING.rank_key(e2, 100)
        # Same score, sort by entry_id ascending
        assert sorted([k1, k2]) == [k2, k1]  # "gate" < "guard"

    def test_deterministic_same_input_same_output(self) -> None:
        entry = _entry("k1", "person", "captain elena", ("person_elena",))
        s1 = SCORING.score(
            entry,
            frozenset(("elena",)),
            "elena",
            current_node_id="n1",
            visited_refs=frozenset(("person_elena",)),
            recency_rank=1,
        )
        s2 = SCORING.score(
            entry,
            frozenset(("elena",)),
            "elena",
            current_node_id="n1",
            visited_refs=frozenset(("person_elena",)),
            recency_rank=1,
        )
        assert s1 == s2
        assert s1 > 0
