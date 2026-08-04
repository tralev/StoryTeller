package com.storyteller.droid.model

import org.junit.Assert.*
import org.junit.Test

class GraphNodeTest {

    @Test
    fun `displayLines splits text by newline`() {
        val node = GraphNode(
            nodeId = "node_01",
            chapter = 1,
            sceneType = "narrative",
            text = "Line one.\nLine two.\n  \nLine three.",
            choices = emptyList(),
        )
        assertEquals(listOf("Line one.", "Line two.", "Line three."), node.displayLines)
    }

    @Test
    fun `choice isAvailable without requires returns true`() {
        val choice = Choice("ch", "Go", "node_02")
        assertTrue(choice.isAvailable(emptySet()))
    }

    @Test
    fun `choice isAvailable with satisfied requires returns true`() {
        val choice = Choice("ch", "Go", "node_02", requiresFlags = listOf("flag1"))
        assertTrue(choice.isAvailable(setOf("flag1", "flag2")))
    }

    @Test
    fun `choice isAvailable with unsatisfied requires returns false`() {
        val choice = Choice("ch", "Go", "node_02", requiresFlags = listOf("flag1"))
        assertFalse(choice.isAvailable(setOf("flag2")))
    }

    @Test
    fun `isEnding defaults to false`() {
        val node = GraphNode(
            nodeId = "end",
            chapter = 1,
            sceneType = "ending",
            text = "The end.",
            choices = emptyList(),
        )
        assertFalse(node.isEnding)
    }

    @Test
    fun `isEnding true when set`() {
        val node = GraphNode(
            nodeId = "end",
            chapter = 1,
            sceneType = "ending",
            text = "The end.",
            choices = emptyList(),
            isEnding = true,
        )
        assertTrue(node.isEnding)
    }
}
