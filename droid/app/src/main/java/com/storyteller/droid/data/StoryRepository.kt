package com.storyteller.droid.data

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.storyteller.droid.model.Choice
import com.storyteller.droid.model.GraphNode
import com.storyteller.droid.model.StoryPackage
import java.io.File

/** Read-only and lazy access to an accepted v2 package. */
class StoryRepository(val story: StoryPackage) {
    private val gson = Gson()
    val nodes: Map<String, GraphNode> by lazy { loadGraph() }
    val bible by lazy { json(story.bibleFile) }
    val gmIndex by lazy { GmIndex(json(story.gmIndexFile)) }
    val styleBible by lazy { json(story.styleBibleFile) }
    val worldIndex by lazy { json(story.worldIndexFile) }
    val nodeCount get() = nodes.size
    val startNode get() = nodes[story.entryNode] ?: error("PACKAGE_ENTRY_NODE")

    /** Large ledgers and chunks stay file-backed until explicitly requested. */
    fun historyEvent(relativePath: String) = json(story.confined(relativePath))
    fun localMapIndex(siteId: String) = json(story.localMapIndex(siteId))
    fun chunk(relativePath: String): ByteArray = story.confined(relativePath).inputStream().use { it.readBytes() }

    private fun loadGraph(): Map<String, GraphNode> {
        val raw = json(story.graphFile)
        val rawNodes = raw["nodes"] as? List<Map<String, Any>> ?: error("PACKAGE_GRAPH")
        return rawNodes.associate { item ->
            val id = item["node_id"] as String
            val choices = (item["choices"] as? List<Map<String, Any>>).orEmpty().map { choice ->
                Choice(choice["choice_id"] as String,
                       (choice["text"] ?: choice["choice_text"] ?: "") as String,
                       choice["target_node"] as String,
                       strings(choice["sets_flags"]), strings(choice["requires_flags"]),
                       choice["route_id"] as? String ?: "")
            }
            id to GraphNode(nodeId = id, text = item["text"] as? String ?: "", choices = choices,
                sceneId = item["scene_id"] as? String ?: "",
                locationId = item["location_id"] as? String ?: "",
                participantIds = strings(item["participant_ids"]),
                authoritativeRefs = strings(item["authoritative_refs"]),
                ending = item["ending"] as? String, isEnding = item["ending"] != null)
        }
    }

    private fun strings(value: Any?) = (value as? List<*>)?.mapNotNull { it as? String }.orEmpty()
    private fun json(file: File): Map<String, Any> {
        require(file.isFile) { "PACKAGE_MISSING_ARTIFACT: ${file.path}" }
        val type = object : TypeToken<Map<String, Any>>() {}.type
        return gson.fromJson(file.readText(Charsets.UTF_8), type)
    }
}
