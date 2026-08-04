package com.storyteller.droid.model

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.io.File

/**
 * Mutable save state for a reader's progress through a story.
 *
 * Persisted as JSON in the save/ directory of the extracted .story.
 */
data class SaveState(
    /** Current node the reader is on. */
    var currentNodeId: String = "node_01",

    /** All nodes the reader has visited (in order). */
    val visitedNodes: MutableList<String> = mutableListOf("node_01"),

    /** Active consequence flags. */
    val flags: MutableSet<String> = mutableSetOf(),

    /** History of choices made (choice IDs in order). */
    val choiceHistory: MutableList<String> = mutableListOf(),

    /** Game Master conversation history (question → answer pairs). */
    val gmHistory: MutableList<Pair<String, String>> = mutableListOf(),

    /** Bookmarked node IDs. */
    val bookmarks: MutableSet<String> = mutableSetOf(),

    /** Timestamp of last save (epoch millis). */
    var lastSavedAt: Long = System.currentTimeMillis(),
) {
    companion object {
        private const val FILENAME = "save_state.json"
        private val gson = Gson()

        /**
         * Load save state from a story's save/ directory.
         */
        fun load(saveDir: File): SaveState {
            val file = File(saveDir, FILENAME)
            if (!file.exists()) return SaveState()

            return try {
                val type = object : TypeToken<SaveState>() {}.type
                gson.fromJson(file.readText(), type)
            } catch (e: Exception) {
                SaveState()
            }
        }

        /**
         * Persist save state to a story's save/ directory.
         */
        fun SaveState.save(saveDir: File) {
            lastSavedAt = System.currentTimeMillis()
            saveDir.mkdirs()
            File(saveDir, FILENAME).writeText(gson.toJson(this))
        }
    }

    /**
     * Record a visit to a new node.
     */
    fun visitNode(nodeId: String) {
        currentNodeId = nodeId
        if (nodeId !in visitedNodes) {
            visitedNodes.add(nodeId)
        }
    }

    /**
     * Record a choice made by the reader.
     */
    fun makeChoice(choice: Choice) {
        choiceHistory.add(choice.choiceId)
        flags.addAll(choice.setsFlags)
    }

    /**
     * Add a Game Master question/answer pair.
     */
    fun addGmExchange(question: String, answer: String) {
        gmHistory.add(question to answer)
    }

    /**
     * Toggle a bookmark on the current node.
     */
    fun toggleBookmark(): Boolean {
        return if (currentNodeId in bookmarks) {
            bookmarks.remove(currentNodeId)
            false
        } else {
            bookmarks.add(currentNodeId)
            true
        }
    }

    /**
     * Reset to beginning (new game).
     */
    fun reset() {
        currentNodeId = "node_01"
        visitedNodes.clear()
        visitedNodes.add("node_01")
        flags.clear()
        choiceHistory.clear()
        gmHistory.clear()
        bookmarks.clear()
        lastSavedAt = System.currentTimeMillis()
    }
}
