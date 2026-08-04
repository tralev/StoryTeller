package com.storyteller.droid.data

import android.util.Log
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.storyteller.droid.model.Choice
import com.storyteller.droid.model.GraphNode
import com.storyteller.droid.model.StoryPackage
import java.io.File

/**
 * Loads and caches parsed content from an extracted .story package.
 *
 * Provides access to the graph, bible, and GM index without
 * re-parsing JSON on every access.
 */
class StoryRepository(private val story: StoryPackage) {
    companion object {
        private const val TAG = "StoryRepository"
    }

    private val gson = Gson()

    /** Cached graph nodes, keyed by node_id. */
    val nodes: Map<String, GraphNode> by lazy { loadGraph() }

    /** Cached World Bible. */
    val bible: Map<String, Any> by lazy {
        loadJson(story.bibleFile) ?: emptyMap()
    }

    /** Cached Game Master index. */
    val gmIndex: GmIndex by lazy { loadGmIndex() }

    /** Cached style bible. */
    val styleBible: Map<String, Any> by lazy {
        loadJson(story.styleBibleFile) ?: emptyMap()
    }

    /** Number of nodes in the graph. */
    val nodeCount: Int get() = nodes.size

    /** Starting node (always node_01). */
    val startNode: GraphNode
        get() = nodes["node_01"] ?: throw IllegalStateException("Story has no node_01")

    // ── Graph loading ────────────────────────────────────────────────

    private fun loadGraph(): Map<String, GraphNode> {
        val raw = loadJson(story.graphFile) ?: return emptyMap()
        val rawNodes = raw["nodes"] as? List<Map<String, Any>> ?: return emptyMap()

        return rawNodes.mapNotNull { nodeMap ->
            try {
                val nodeId = nodeMap["node_id"] as? String ?: return@mapNotNull null
                val text = nodeMap["text"] as? String ?: ""
                val chapter = (nodeMap["chapter"] as? Double)?.toInt() ?: 1
                val sceneType = nodeMap["scene_type"] as? String ?: "narrative"
                val mood = nodeMap["mood"] as? String ?: ""
                val presentCharacters = (nodeMap["present_characters"] as? List<*>)
                    ?.mapNotNull { it as? String } ?: emptyList()
                val presentLocation = nodeMap["present_location"] as? String
                val presentCreatures = (nodeMap["present_creatures"] as? List<*>)
                    ?.mapNotNull { it as? String } ?: emptyList()
                val endings = nodeMap["endings"] as? Map<String, Any>
                val isEnding = endings?.get("is_ending") as? Boolean ?: false

                val rawChoices = nodeMap["choices"] as? List<Map<String, Any>> ?: emptyList()
                val choices = rawChoices.mapNotNull { choiceMap ->
                    Choice(
                        choiceId = choiceMap["choice_id"] as? String ?: "",
                        choiceText = choiceMap["choice_text"] as? String ?: "",
                        targetNode = choiceMap["target_node"] as? String ?: "",
                        setsFlags = (choiceMap["sets_flags"] as? List<*>)
                            ?.mapNotNull { it as? String } ?: emptyList(),
                        requiresFlags = (choiceMap["requires_flags"] as? List<*>
                            ?: choiceMap["required_flags"] as? List<*>)
                            ?.mapNotNull { it as? String } ?: emptyList(),
                    )
                }.filter { it.choiceId.isNotEmpty() }

                nodeId to GraphNode(
                    nodeId = nodeId,
                    chapter = chapter,
                    sceneType = sceneType,
                    text = text,
                    choices = choices,
                    presentCharacters = presentCharacters,
                    presentLocation = presentLocation,
                    presentCreatures = presentCreatures,
                    mood = mood,
                    isEnding = isEnding,
                )
            } catch (e: Exception) {
                Log.e(TAG, "Failed to parse node", e)
                null
            }
        }.toMap()
    }

    // ── GM Index loading ─────────────────────────────────────────────

    private fun loadGmIndex(): GmIndex {
        val raw = loadJson(story.gmIndexFile) ?: return GmIndex()
        return GmIndex(raw)
    }

    // ── Helpers ──────────────────────────────────────────────────────

    private fun loadJson(file: File): Map<String, Any>? {
        if (!file.exists()) {
            Log.w(TAG, "File not found: ${file.name}")
            return null
        }
        return try {
            val type = object : TypeToken<Map<String, Any>>() {}.type
            gson.fromJson(file.readText(), type)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse: ${file.name}", e)
            null
        }
    }
}
