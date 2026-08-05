package com.storyteller.droid.model

import com.google.gson.Gson
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.UUID

data class ChatTurn(val role: String, val text: String)

/** App-private state. Procedural/package facts are referenced, never copied. */
data class SaveState(
    val saveVersion: Int = 1,
    val storyId: String = "",
    val packageContentHash: String = "",
    val playthroughId: String = UUID.randomUUID().toString(),
    var currentNode: String = "",
    val visitedNodes: MutableList<String> = mutableListOf(),
    val flags: MutableMap<String, Boolean> = mutableMapOf(),
    val bookmarks: MutableList<String> = mutableListOf(),
    val gmHistory: MutableList<ChatTurn> = mutableListOf(),
    val choiceHistory: MutableList<String> = mutableListOf(),
) {
    var currentNodeId: String
        get() = currentNode
        set(value) { currentNode = value }

    fun visitNode(nodeId: String) { currentNode = nodeId; if (nodeId !in visitedNodes) visitedNodes += nodeId }
    fun makeChoice(choice: Choice) { choiceHistory += choice.choiceId; choice.setsFlags.forEach { flags[it] = true } }
    fun addGmExchange(question: String, answer: String) {
        gmHistory += ChatTurn("user", question); gmHistory += ChatTurn("assistant", answer)
    }
    fun toggleBookmark(): Boolean = if (bookmarks.remove(currentNode)) false else { bookmarks += currentNode; true }
    fun reset(entryNode: String = visitedNodes.firstOrNull() ?: currentNode) {
        currentNode = entryNode; visitedNodes.clear(); visitedNodes += entryNode
        flags.clear(); choiceHistory.clear(); gmHistory.clear(); bookmarks.clear()
    }
    fun save(saveDir: File) = SaveRepository(saveDir.parentFile ?: saveDir)
        .saveAt(this, File(saveDir, "save_state.json"))

    companion object {
        /** Compatibility adapter; new code uses [SaveRepository]. */
        fun load(saveDir: File): SaveState = SaveRepository(saveDir.parentFile ?: saveDir)
            .loadAny(saveDir) ?: SaveState()
    }
}

class SaveHashMismatch : IllegalStateException("SAVE_PACKAGE_HASH_MISMATCH")

class SaveRepository(private val root: File) {
    private val gson = Gson()
    private fun file(storyId: String, playthroughId: String) =
        File(root, "saves/$storyId/$playthroughId.json")

    fun load(story: StoryPackage, playthroughId: String): SaveState? {
        val path = file(story.storyId, playthroughId)
        if (!path.isFile) return null
        val state = gson.fromJson(path.readText(), SaveState::class.java)
        if (state.storyId != story.storyId || state.packageContentHash != story.contentHash) throw SaveHashMismatch()
        return state
    }

    fun save(state: SaveState) = saveAt(state, file(state.storyId, state.playthroughId))

    internal fun saveAt(state: SaveState, destination: File) {
        destination.parentFile?.mkdirs()
        val temp = File(destination.parentFile, ".${destination.name}.tmp")
        temp.outputStream().use { stream ->
            stream.write(gson.toJson(state).toByteArray(Charsets.UTF_8)); stream.fd.sync()
        }
        Files.move(temp.toPath(), destination.toPath(), StandardCopyOption.REPLACE_EXISTING,
                   StandardCopyOption.ATOMIC_MOVE)
    }

    internal fun loadAny(directory: File): SaveState? {
        val path = File(directory, "save_state.json")
        return if (path.isFile) runCatching { gson.fromJson(path.readText(), SaveState::class.java) }.getOrNull() else null
    }

    fun deleteStoryData(storyId: String) = File(root, "saves/$storyId").deleteRecursively()
}
