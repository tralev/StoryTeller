import json
from pathlib import Path

import pytest

from src.narrative.models import KnowledgeEntry
from src.narrative.retrieval import (
    filter_revealed_entries,
    format_knowledge_prompt,
    normalize_query,
    retrieve_knowledge,
)
from src.storage.conversation_history import ConversationHistoryStore, Exchange

ROOT = Path(__file__).resolve().parents[2]


def _catalog():
    return json.loads((ROOT / "tests/fixtures/gm_retrieval/catalog.json").read_text())


def _spoiler_catalog():
    return json.loads((ROOT / "tests/fixtures/gm_retrieval/spoiler_catalog.json").read_text())


def test_normalization_contract() -> None:
    assert normalize_query("  Who—is ÉLENA?!  ") == "who is élena"


def test_shared_retrieval_catalog() -> None:
    catalog = _catalog()
    entries = tuple(KnowledgeEntry(**entry) for entry in catalog["entries"])
    outcomes = {}
    for scenario in catalog["scenarios"]:
        hits = retrieve_knowledge(
            entries,
            scenario["query"],
            frozenset(scenario["visited_nodes"]),
            context_budget_bytes=scenario["context_budget_bytes"],
            max_results=scenario["max_results"],
            current_node_id=scenario.get("current_node_id"),
            visited_refs=frozenset(scenario.get("visited_refs", ())),
        )
        ids = [hit.entry.entry_id for hit in hits]
        assert ids == scenario["expected_ids"], scenario["id"]
        outcomes[scenario["id"]] = ids
        assert (
            len("\n".join(hit.prompt_line for hit in hits).encode("utf-8"))
            <= scenario["context_budget_bytes"]
        )
    output = ROOT / "tmp/contracts/gm-python.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"format": "storyteller.gm-retrieval-results.v1", "scenarios": outcomes}, sort_keys=True
        )
    )


def test_reveal_gate_removes_every_hidden_field_before_ranking_and_prompt() -> None:
    entries = tuple(KnowledgeEntry(**entry) for entry in _catalog()["entries"])
    hidden = next(entry for entry in entries if entry.entry_id == "knowledge_hidden")

    eligible = filter_revealed_entries(entries, frozenset())
    candidate_debug = json.dumps([entry.__dict__ for entry in eligible], sort_keys=True)
    # Query that would match hidden if it were revealed
    hits = retrieve_knowledge(entries, "silver regent event betrayal", frozenset())
    prompt = format_knowledge_prompt(hits)

    # Hidden entry must not appear anywhere
    for sentinel in (hidden.entry_id, hidden.normalized_text, *hidden.source_ids):
        assert sentinel not in candidate_debug, (
            f"hidden sentinel {sentinel!r} leaked into candidates"
        )
        assert sentinel not in prompt, f"hidden sentinel {sentinel!r} leaked into prompt"
    # knowledge_hidden must not be in results
    result_ids = [h.entry.entry_id for h in hits]
    assert "knowledge_hidden" not in result_ids, f"hidden entry appeared in results: {result_ids}"
    # After reveal, hidden must appear
    revealed_after = filter_revealed_entries(entries, frozenset({"node_reveal"}))
    assert hidden in revealed_after, "hidden entry not revealed after node_reveal"


def test_shared_cross_domain_spoiler_catalog() -> None:
    catalog = _spoiler_catalog()
    entries = tuple(KnowledgeEntry(**entry) for entry in catalog["entries"])
    for scenario in catalog["scenarios"]:
        hits = retrieve_knowledge(
            entries,
            scenario["query"],
            frozenset(scenario["visited_nodes"]),
        )
        assert [hit.entry.entry_id for hit in hits] == scenario["expected_ids"], scenario["id"]

        serialized = json.dumps(
            [
                {
                    "entry_id": hit.entry.entry_id,
                    "source_ids": hit.entry.source_ids,
                    "text": hit.entry.normalized_text,
                    "prompt": hit.prompt_line,
                }
                for hit in hits
            ],
            sort_keys=True,
        )
        if scenario["id"].endswith("before-reveal"):
            domain = scenario["id"].removesuffix("-before-reveal")
            hidden = next(entry for entry in entries if entry.kind == _DOMAIN_KIND[domain])
            for sentinel in (hidden.entry_id, hidden.normalized_text, *hidden.source_ids):
                assert sentinel not in serialized, scenario["id"]


_DOMAIN_KIND = {
    "global": "person",
    "history": "event",
    "belief": "belief",
    "local": "local_map",
    "opportunity": "opportunity",
}


def test_shared_sentinels_do_not_reach_runtime_boundaries_before_reveal(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    catalog = _spoiler_catalog()
    entries = tuple(KnowledgeEntry(**entry) for entry in catalog["entries"])
    sentinels = tuple(catalog["sentinels"])

    hits = retrieve_knowledge(entries, "sentinel marker", frozenset())
    candidates = filter_revealed_entries(entries, frozenset())
    prompt = format_knowledge_prompt(hits)
    ranking_diagnostics = repr(hits)
    error_text = "GM_RETRIEVAL_EMPTY"
    log_text = caplog.text
    store = ConversationHistoryStore(tmp_path / "history.json")
    store.add_exchange(
        Exchange("ex_0000", "sentinel marker", prompt or "No revealed lore.", 0, 1.0),
        story_id="spoiler_story",
        content_hash="package_hash",
        conversation_id="spoiler_conversation",
    )
    history_text = (tmp_path / "history.json").read_text()

    surfaces = (repr(candidates), prompt, ranking_diagnostics, error_text, log_text, history_text)
    for sentinel in sentinels:
        assert all(sentinel not in surface for surface in surfaces), sentinel

    revealed = retrieve_knowledge(
        entries,
        "sentinelglobaltext7e15",
        frozenset({"node_global_reveal"}),
    )
    revealed_text = format_knowledge_prompt(revealed)
    assert "sentinel-global-id-7e15" in revealed_text
    assert "sentinelglobaltext7e15" in revealed_text
    assert "sentinel-global-source-7e15" in repr(revealed)
