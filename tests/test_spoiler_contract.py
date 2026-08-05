from src.narrative.knowledge import normalize_knowledge, revealed
from src.narrative.models import KnowledgeEntry


def test_normalization_is_shared_and_platform_neutral():
    assert normalize_knowledge("  ＡSHEN\nRoad  ") == "ashen road"


def test_reveal_requires_all_visited_nodes_with_empty_sentinel():
    open_entry = KnowledgeEntry("a", "fact", "x", (), (), (), ())
    gated = KnowledgeEntry("b", "fact", "x", (), (), (), ("node_001", "node_003"))
    assert revealed(open_entry, frozenset())
    assert not revealed(gated, frozenset({"node_001"}))
    assert revealed(gated, frozenset({"node_001", "node_003", "node_999"}))
