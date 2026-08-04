package com.storyteller.droid.data

/**
 * Game Master keyword index for context-aware question answering.
 *
 * Parsed from content/gm_index.json. Provides keyword lookup
 * and entity context retrieval for the Game Master prompt.
 *
 * Spoiler prevention: entity summaries are gated by
 * [revealAfterNode] — the GM won't disclose entities
 * the reader hasn't encountered yet.
 */
data class GmIndex(
    /** Keyword → node references map. */
    val keywords: Map<String, List<String>> = emptyMap(),

    /** Entity summaries, keyed by entity ID. */
    val entityCache: Map<String, EntitySummary> = emptyMap(),
) {
    constructor(raw: Map<String, Any>) : this(
        keywords = (raw["keywords"] as? Map<String, List<String>>) ?: emptyMap(),
        entityCache = (raw["entity_cache"] as? Map<String, Map<String, Any>>)
            ?.mapNotNull { (id, data) ->
                try {
                    id to EntitySummary(
                        entityId = id,
                        entityType = data["entity_type"] as? String ?: "unknown",
                        name = data["name"] as? String ?: id,
                        aliases = (data["aliases"] as? List<*>)?.mapNotNull { it as? String } ?: emptyList(),
                        summary = data["summary"] as? String ?: "",
                        nodeIds = (data["node_ids"] as? List<*>)?.mapNotNull { it as? String } ?: emptyList(),
                        revealAfterNode = data["reveal_after_node"] as? String,
                    )
                } catch (e: Exception) {
                    null
                }
            }?.toMap() ?: emptyMap(),
    )

    /**
     * Look up entities relevant to a reader's question.
     *
     * @param query The reader's question text.
     * @param visitedNodes Nodes the reader has visited (for spoiler gating).
     * @return List of entity summaries the reader is allowed to know about.
     */
    fun lookup(query: String, visitedNodes: Set<String>): List<EntitySummary> {
        val queryLower = query.lowercase()
        val matchedIds = mutableSetOf<String>()

        // Match by keyword
        for ((keyword, nodeIds) in keywords) {
            if (keyword.lowercase() in queryLower) {
                // Find entity IDs referenced in these nodes
                for (nodeId in nodeIds) {
                    entityCache.values
                        .filter { nodeId in it.nodeIds }
                        .forEach { matchedIds.add(it.entityId) }
                }
            }
        }

        // Match by entity name or alias directly
        for ((id, entity) in entityCache) {
            if (entity.name.lowercase() in queryLower ||
                entity.aliases.any { it.lowercase() in queryLower }
            ) {
                matchedIds.add(id)
            }
        }

        // Spoiler gate: only return entities the reader has encountered
        return matchedIds
            .mapNotNull { entityCache[it] }
            .filter { entity ->
                entity.revealAfterNode == null ||
                entity.revealAfterNode in visitedNodes
            }
            .take(5)  // Limit context to keep prompt short
    }

    /**
     * Format entity summaries as a compact string for the GM prompt.
     */
    fun formatForPrompt(entities: List<EntitySummary>): String {
        if (entities.isEmpty()) return ""
        return entities.joinToString("\n") { entity ->
            "[${entity.entityId}] ${entity.name} (${entity.entityType}): ${entity.summary}"
        }
    }
}

/**
 * A cached entity summary from the GM index.
 */
data class EntitySummary(
    /** Entity ID (e.g., "char_01", "loc_02"). */
    val entityId: String,

    /** Type of entity (character, location, faction, creature, artifact, event). */
    val entityType: String,

    /** Display name. */
    val name: String,

    /** Alternative names. */
    val aliases: List<String> = emptyList(),

    /** One-line description for the GM prompt. */
    val summary: String,

    /** Nodes where this entity appears. */
    val nodeIds: List<String> = emptyList(),

    /** If set, the GM should not disclose this entity until the reader reaches this node. */
    val revealAfterNode: String? = null,
)
