package com.storyteller.droid.model

/** Frozen v2 graph model. */
data class GraphNode(
    val nodeId: String,
    val text: String,
    val choices: List<Choice>,
    val chapter: Int = 1,
    val sceneType: String = "narrative",
    val mood: String = "",
    val sceneId: String = "",
    val locationId: String = "",
    val participantIds: List<String> = emptyList(),
    val authoritativeRefs: List<String> = emptyList(),
    val ending: String? = null,
    val isEnding: Boolean = ending != null,
) {
    val displayLines get() = text.split("\n").filter { it.isNotBlank() }
}

data class Choice(
    val choiceId: String,
    val choiceText: String,
    val targetNode: String,
    val setsFlags: List<String> = emptyList(),
    val requiresFlags: List<String> = emptyList(),
    val routeId: String = "",
) {
    fun isAvailable(activeFlags: Set<String>) = requiresFlags.all(activeFlags::contains)
    fun isAvailable(activeFlags: Map<String, Boolean>) =
        requiresFlags.all { activeFlags[it] == true }
}

/** Pure deterministic state transition shared by UI and tests. */
class StorySession(private val nodes: Map<String, GraphNode>, entryNode: String,
                   val state: SaveState) {
    init { require(entryNode in nodes); if (state.currentNode.isEmpty()) state.currentNode = entryNode }
    val current: GraphNode get() = nodes[state.currentNode] ?: error("Unknown current node")
    fun availableChoices() = current.choices.filter { it.isAvailable(state.flags.filterValues { v -> v }.keys) }
    fun choose(choiceId: String): GraphNode {
        val choice = availableChoices().singleOrNull { it.choiceId == choiceId }
            ?: throw IllegalArgumentException("CHOICE_UNAVAILABLE")
        require(choice.targetNode in nodes) { "CHOICE_TARGET_MISSING" }
        choice.setsFlags.forEach { state.flags[it] = true }
        state.currentNode = choice.targetNode
        if (choice.targetNode !in state.visitedNodes) state.visitedNodes.add(choice.targetNode)
        return current
    }
}
