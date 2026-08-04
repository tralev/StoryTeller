package com.storyteller.droid.model

/**
 * A single node in the CYOA branching graph.
 *
 * Parsed from content/graph.json.
 */
data class GraphNode(
    /** Unique node identifier (e.g., "node_01"). */
    val nodeId: String,

    /** Chapter number this node belongs to. */
    val chapter: Int,

    /** Type of scene (exploration, combat, dialog, etc.). */
    val sceneType: String,

    /** The 7-10 line narrative text, with \n line separators. */
    val text: String,

    /** Available choices from this node. */
    val choices: List<Choice>,

    /** Characters present in this scene (character IDs). */
    val presentCharacters: List<String> = emptyList(),

    /** Location where this scene takes place (location ID). */
    val presentLocation: String? = null,

    /** Creatures present in this scene (creature IDs). */
    val presentCreatures: List<String> = emptyList(),

    /** Emotional mood of the scene. */
    val mood: String = "",

    /** Whether this is an ending node. */
    val isEnding: Boolean = false,
) {
    /** Lines of text split by newline for display. */
    val displayLines: List<String>
        get() = text.split("\n").filter { it.isNotBlank() }
}

/**
 * A choice the reader can make at a node.
 */
data class Choice(
    /** Unique choice identifier (e.g., "ch_01_a"). */
    val choiceId: String,

    /** Display text for the choice button. */
    val choiceText: String,

    /** The node this choice leads to. */
    val targetNode: String,

    /** Consequences/flags set by this choice. */
    val setsFlags: List<String> = emptyList(),

    /** Whether this choice requires specific flags to be set. */
    val requiresFlags: List<String> = emptyList(),
) {
    /**
     * Check if this choice is available given the current flag set.
     */
    fun isAvailable(activeFlags: Set<String>): Boolean {
        return requiresFlags.all { it in activeFlags }
    }
}
