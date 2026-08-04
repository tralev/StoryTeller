package com.storyteller.droid.data

import org.junit.Assert.*
import org.junit.Test

class GmIndexTest {

    private val sampleRaw: Map<String, Any> = mapOf(
        "keywords" to mapOf(
            "Elena" to listOf("node_01", "node_02"),
            "crystal" to listOf("node_01", "node_05"),
            "spire" to listOf("node_01"),
        ),
        "entity_cache" to mapOf(
            "char_01" to mapOf(
                "entity_type" to "character",
                "name" to "Elena Brightblade",
                "aliases" to listOf("The Accord Bearer"),
                "summary" to "A young knight sworn to unite the fractured kingdoms.",
                "node_ids" to listOf("node_01", "node_02", "node_03"),
                "reveal_after_node" to null,
            ),
            "char_02" to mapOf(
                "entity_type" to "character",
                "name" to "Thorn Ironveil",
                "aliases" to listOf("The Warden"),
                "summary" to "An aging dwarf warden guarding the High Pass.",
                "node_ids" to listOf("node_03", "node_04"),
                "reveal_after_node" to "node_03",
            ),
            "loc_01" to mapOf(
                "entity_type" to "location",
                "name" to "High Pass",
                "aliases" to listOf("The Pass"),
                "summary" to "A narrow mountain pass leading to the Crystal Spire.",
                "node_ids" to listOf("node_01"),
                "reveal_after_node" to null,
            ),
        ),
    )

    private val index = GmIndex(sampleRaw)

    @Test
    fun `lookup by keyword finds entity`() {
        val results = index.lookup("Who is Elena?", setOf("node_01"))
        assertEquals(1, results.size)
        assertEquals("char_01", results[0].entityId)
    }

    @Test
    fun `lookup by entity name directly`() {
        val results = index.lookup("Tell me about Thorn Ironveil", setOf("node_01", "node_03"))
        assertEquals(1, results.size)
        assertEquals("char_02", results[0].entityId)
    }

    @Test
    fun `lookup by alias finds entity`() {
        val results = index.lookup("Who is the Accord Bearer?", setOf("node_01"))
        assertEquals(1, results.size)
        assertEquals("char_01", results[0].entityId)
    }

    @Test
    fun `spoiler gate hides entity when reveal_after_node not visited`() {
        val results = index.lookup("Tell me about Thorn", setOf("node_01"))
        assertTrue(results.none { it.entityId == "char_02" })
    }

    @Test
    fun `spoiler gate shows entity when reveal_after_node visited`() {
        val results = index.lookup("Tell me about Thorn", setOf("node_01", "node_03"))
        assertTrue(results.any { it.entityId == "char_02" })
    }

    @Test
    fun `empty query returns empty`() {
        val results = index.lookup("", setOf("node_01"))
        assertTrue(results.isEmpty())
    }

    @Test
    fun `unknown query returns empty`() {
        val results = index.lookup("zzzblarg", setOf("node_01"))
        assertTrue(results.isEmpty())
    }

    @Test
    fun `formatForPrompt produces expected string`() {
        val entities = listOf(
            EntitySummary("char_01", "character", "Elena", listOf(), "A knight.", listOf("node_01"), null),
            EntitySummary("loc_01", "location", "High Pass", listOf(), "A mountain pass.", listOf("node_01"), null),
        )
        val formatted = index.formatForPrompt(entities)
        assertTrue(formatted.contains("[char_01]"))
        assertTrue(formatted.contains("[loc_01]"))
        assertTrue(formatted.contains("A knight."))
    }

    @Test
    fun `empty index handles gracefully`() {
        val empty = GmIndex()
        assertTrue(empty.lookup("anything", setOf("node_01")).isEmpty())
        assertEquals("", empty.formatForPrompt(emptyList()))
    }

    @Test
    fun `case insensitive matching`() {
        val results = index.lookup("ELENA", setOf("node_01"))
        assertEquals(1, results.size)
        assertEquals("char_01", results[0].entityId)
    }
}
