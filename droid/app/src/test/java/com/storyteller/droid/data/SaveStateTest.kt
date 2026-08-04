package com.storyteller.droid.data

import com.google.gson.Gson
import com.storyteller.droid.model.Choice
import com.storyteller.droid.model.SaveState
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class SaveStateTest {
    private val gson = Gson()

    @Test
    fun `default state starts at node_01`() {
        val state = SaveState()
        assertEquals("node_01", state.currentNodeId)
        assertTrue(state.visitedNodes.contains("node_01"))
    }

    @Test
    fun `visitNode updates current and adds to visited`() {
        val state = SaveState()
        state.visitNode("node_05")
        assertEquals("node_05", state.currentNodeId)
        assertTrue(state.visitedNodes.contains("node_05"))
        assertEquals(2, state.visitedNodes.size)
    }

    @Test
    fun `visitNode does not duplicate visited`() {
        val state = SaveState()
        state.visitNode("node_01")
        assertEquals(1, state.visitedNodes.size)
    }

    @Test
    fun `makeChoice records choice and sets flags`() {
        val state = SaveState()
        val choice = Choice("ch_01_a", "Go north", "node_02", listOf("chose_north"), emptyList())
        state.makeChoice(choice)
        assertTrue(state.choiceHistory.contains("ch_01_a"))
        assertTrue(state.flags.contains("chose_north"))
    }

    @Test
    fun `addGmExchange accumulates history`() {
        val state = SaveState()
        state.addGmExchange("Who is Elena?", "A brave knight.")
        assertEquals(1, state.gmHistory.size)
        assertEquals("Who is Elena?", state.gmHistory[0].first)
        assertEquals("A brave knight.", state.gmHistory[0].second)
    }

    @Test
    fun `toggleBookmark adds and removes`() {
        val state = SaveState()
        assertTrue(state.toggleBookmark()) // add
        assertTrue(state.bookmarks.contains("node_01"))
        assertFalse(state.toggleBookmark()) // remove
        assertFalse(state.bookmarks.contains("node_01"))
    }

    @Test
    fun `reset clears all state`() {
        val state = SaveState()
        state.visitNode("node_05")
        state.makeChoice(Choice("c1", "go", "node_06", listOf("flag1"), emptyList()))
        state.reset()
        assertEquals("node_01", state.currentNodeId)
        assertEquals(1, state.visitedNodes.size)
        assertTrue(state.flags.isEmpty())
        assertTrue(state.choiceHistory.isEmpty())
    }

    @Test
    fun `serialize round-trip preserves state`() {
        val state = SaveState()
        state.visitNode("node_03")
        state.makeChoice(Choice("c1", "go", "node_04", listOf("flag1"), emptyList()))
        state.addGmExchange("q?", "a!")
        state.toggleBookmark()

        val json = gson.toJson(state)
        val restored = gson.fromJson(json, SaveState::class.java)

        assertEquals(state.currentNodeId, restored.currentNodeId)
        assertEquals(state.visitedNodes, restored.visitedNodes)
        assertEquals(state.flags, restored.flags)
        assertEquals(state.gmHistory.size, restored.gmHistory.size)
        assertTrue(restored.bookmarks.contains("node_01"))
    }

    @Test
    fun `save and load from disk`() {
        val tmpDir = File(System.getProperty("java.io.tmpdir"), "storyteller_test_${System.nanoTime()}")
        val saveDir = File(tmpDir, "save")
        saveDir.mkdirs()

        try {
            val state = SaveState()
            state.visitNode("node_02")
            state.save(saveDir)

            val loaded = SaveState.load(saveDir)
            assertEquals("node_02", loaded.currentNodeId)
            assertEquals(2, loaded.visitedNodes.size)
        } finally {
            tmpDir.deleteRecursively()
        }
    }

    @Test
    fun `load from nonexistent dir returns default`() {
        val loaded = SaveState.load(File("/nonexistent/save"))
        assertEquals("node_01", loaded.currentNodeId)
    }
}
