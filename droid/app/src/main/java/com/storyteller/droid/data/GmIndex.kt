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
        currentNodeId: String? = null,
        visitedRefs: Set<String> = emptySet(),
    ): List<KnowledgeHit> {
        require(contextBudgetBytes >= 0 && maxResults >= 0) { "retrieval budgets must be non-negative" }
        val normalized = normalize(query)
        val tokens = tokens(query)
        if (tokens.isEmpty() || normalized.isEmpty() || contextBudgetBytes == 0 || maxResults == 0) return emptyList()

        val recency = visitedNodes.sorted().asReversed().withIndex().associate { it.value to it.index }
        val ranked = RevealGate.eligible(entries, visitedNodes).mapNotNull { entry ->
            val searchable = normalize(listOf(entry.kind, entry.normalizedText).plus(entry.sourceIds).joinToString(" "))
            val searchableTokens = searchable.split(' ').filter(String::isNotEmpty).toSet()
            val matching = tokens.count(searchableTokens::contains)
            if (matching == 0) return@mapNotNull null
            var score = kindWeight(entry.kind) + 100 * matching
            if (searchable.contains(normalized)) score += 500
            if (tokens.any(entry.sourceIds::contains)) score += 400
            if (currentNodeId != null) {
                if (currentNodeId in entry.revealAfterNodes) score += 300
                if (currentNodeId in entry.outgoingRefs) score += 150
            }
            if (visitedRefs.isNotEmpty()) {
                if (entry.sourceIds.any(visitedRefs::contains)) score += 200
                if (entry.outgoingRefs.any(visitedRefs::contains)) score += 100
                if ((entry.outgoingRefs + entry.incomingRefs).any(visitedRefs::contains)) score += 250
            }
            entry.revealAfterNodes.mapNotNull(recency::get).minOrNull()?.let { rank ->
                score += maxOf(0, 50 - rank * 10)
            }
            score to entry
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

    fun promptContext(
        query: String,
        visitedNodes: Set<String>,
        currentNodeId: String? = null,
        visitedRefs: Set<String> = emptySet(),
    ): String = retrieve(query, visitedNodes, currentNodeId = currentNodeId, visitedRefs = visitedRefs)
        .joinToString("\n", transform = KnowledgeHit::promptLine)

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

        private fun kindWeight(kind: String): Int = mapOf(
            "creature" to 200, "person" to 180, "opportunity" to 160, "event" to 150,
            "civilization" to 140, "settlement" to 130, "site" to 120, "location" to 120,
            "region" to 110, "route" to 100, "artifact" to 100, "local_map" to 90,
            "graph_node" to 80, "story_scene" to 70, "bible_local" to 60, "ecology" to 50,
            "registries" to 40, "identities" to 40, "cohort" to 40,
        )[kind] ?: 50

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
