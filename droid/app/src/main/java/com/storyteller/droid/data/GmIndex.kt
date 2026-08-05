package com.storyteller.droid.data

import java.text.Normalizer
import java.util.Locale

data class KnowledgeEntry(
    val entryId: String,
    val kind: String,
    val normalizedText: String,
    val sourceIds: List<String> = emptyList(),
    val incomingRefs: List<String> = emptyList(),
    val outgoingRefs: List<String> = emptyList(),
    val revealAfterNodes: List<String> = emptyList(),
)

data class KnowledgeHit(val entry: KnowledgeEntry, val score: Int, val promptLine: String)

/** Spoiler-security boundary. Rejected entries must not be logged or diagnosed. */
internal object RevealGate {
    fun eligible(entries: List<KnowledgeEntry>, visitedNodes: Set<String>): List<KnowledgeEntry> =
        entries.filter { entry ->
            entry.revealAfterNodes.isEmpty() || visitedNodes.containsAll(entry.revealAfterNodes)
        }
}

/** Deterministic v2 GM retrieval; algorithm is mirrored in Python and Swift. */
data class GmIndex(val entries: List<KnowledgeEntry> = emptyList()) {
    constructor(raw: Map<String, Any>) : this(parseEntries(raw))

    fun retrieve(
        query: String,
        visitedNodes: Set<String>,
        contextBudgetBytes: Int = DEFAULT_CONTEXT_BUDGET_BYTES,
        maxResults: Int = DEFAULT_MAX_RESULTS,
    ): List<KnowledgeHit> {
        require(contextBudgetBytes >= 0 && maxResults >= 0) { "retrieval budgets must be non-negative" }
        val normalized = normalize(query)
        val tokens = tokens(query)
        if (tokens.isEmpty() || normalized.isEmpty() || contextBudgetBytes == 0 || maxResults == 0) return emptyList()

        val ranked = RevealGate.eligible(entries, visitedNodes).mapNotNull { entry ->
            val searchable = normalize(listOf(entry.kind, entry.normalizedText).plus(entry.sourceIds).joinToString(" "))
            val searchableTokens = searchable.split(' ').filter(String::isNotEmpty).toSet()
            var score = 100 * tokens.count(searchableTokens::contains)
            if (searchable.contains(normalized)) score += 500
            if (score == 0) null else score to entry
        }.sortedWith(compareByDescending<Pair<Int, KnowledgeEntry>> { it.first }.thenBy { it.second.entryId })

        var remaining = contextBudgetBytes
        val selected = mutableListOf<KnowledgeHit>()
        for ((score, entry) in ranked) {
            val line = "[${entry.entryId}] (${entry.kind}) ${entry.normalizedText}"
            val cost = line.toByteArray(Charsets.UTF_8).size + if (selected.isEmpty()) 0 else 1
            if (cost > remaining) continue
            selected += KnowledgeHit(entry, score, line)
            remaining -= cost
            if (selected.size == maxResults) break
        }
        return selected
    }

    /** Compatibility call used by the current GM screen. */
    fun lookup(query: String, visitedNodes: Set<String>): List<KnowledgeEntry> =
        retrieve(query, visitedNodes).map(KnowledgeHit::entry)

    fun promptContext(query: String, visitedNodes: Set<String>): String =
        retrieve(query, visitedNodes).joinToString("\n", transform = KnowledgeHit::promptLine)

    internal fun formatForPrompt(entries: List<KnowledgeEntry>): String = entries.joinToString("\n") {
        "[${it.entryId}] (${it.kind}) ${it.normalizedText}"
    }

    companion object {
        const val DEFAULT_CONTEXT_BUDGET_BYTES = 4096
        const val DEFAULT_MAX_RESULTS = 8
        private val separator = Regex("[^\\p{L}\\p{N}]+")

        fun normalize(value: String): String = Normalizer.normalize(value, Normalizer.Form.NFKC)
            .lowercase(Locale.ROOT).split(separator).filter(String::isNotEmpty).joinToString(" ")

        fun tokens(value: String): List<String> = normalize(value).split(' ')
            .filter(String::isNotEmpty).toSortedSet().toList()

        private fun strings(value: Any?): List<String> = (value as? List<*>)?.mapNotNull { it as? String }.orEmpty()

        @Suppress("UNCHECKED_CAST")
        private fun parseEntries(raw: Map<String, Any>): List<KnowledgeEntry> {
            val v2 = raw["entries"] as? List<Map<String, Any>>
            if (v2 != null) return v2.map { data ->
                KnowledgeEntry(
                    entryId = data["entry_id"] as? String ?: data["knowledge_id"] as? String ?: error("GM_INDEX_ENTRY_ID"),
                    kind = data["kind"] as? String ?: "unknown",
                    normalizedText = data["normalized_text"] as? String ?: "",
                    sourceIds = strings(data["source_ids"]), incomingRefs = strings(data["incoming_refs"]),
                    outgoingRefs = strings(data["outgoing_refs"]), revealAfterNodes = strings(data["reveal_after_nodes"]),
                )
            }
            // Temporary reader compatibility for pre-v2 unit data. Retrieval is
            // still performed by the canonical entry algorithm above.
            val cache = raw["entity_cache"] as? Map<String, Map<String, Any>> ?: return emptyList()
            return cache.map { (id, data) ->
                KnowledgeEntry(
                    id, data["entity_type"] as? String ?: "unknown",
                    listOf(data["name"] as? String ?: id)
                        .plus(strings(data["aliases"])).plus(data["summary"] as? String ?: "").joinToString(" "),
                    revealAfterNodes = (data["reveal_after_node"] as? String)?.let(::listOf).orEmpty(),
                )
            }
        }
    }
}
