package com.storyteller.droid.data

import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

class GmIndexTest {
    private val gson = Gson()
    private val root: File by lazy {
        generateSequence(File(requireNotNull(System.getProperty("user.dir")))) { it.parentFile }
            .first { File(it, "tests/fixtures/gm_retrieval/catalog.json").isFile }
    }

    @Test
    fun `shared retrieval scenarios produce exact ordered IDs`() {
        @Suppress("UNCHECKED_CAST")
        val catalog = gson.fromJson(File(root, "tests/fixtures/gm_retrieval/catalog.json").readText(), Map::class.java) as Map<String, Any>
        @Suppress("UNCHECKED_CAST") val rawEntries = catalog["entries"] as List<Map<String, Any>>
        val index = GmIndex(mapOf("entries" to rawEntries))
        @Suppress("UNCHECKED_CAST") val scenarios = catalog["scenarios"] as List<Map<String, Any>>
        val outcomes = linkedMapOf<String, Any>()
        for (scenario in scenarios) {
            val ids = index.retrieve(
                scenario["query"] as String,
                (scenario["visited_nodes"] as List<String>).toSet(),
                (scenario["context_budget_bytes"] as Double).toInt(),
                (scenario["max_results"] as Double).toInt(),
            ).map { it.entry.entryId }
            assertEquals(scenario["id"] as String, scenario["expected_ids"] as List<String>, ids)
            outcomes[scenario["id"] as String] = ids
        }
        val output = File(root, "tmp/contracts/gm-android.json")
        output.parentFile?.mkdirs()
        output.writeText(gson.toJson(mapOf("format" to "storyteller.gm-retrieval-results.v1", "scenarios" to outcomes)))
    }

    @Test
    fun `normalization and context bytes are bounded`() {
        assertEquals("who is élena", GmIndex.normalize("  Who—is ÉLENA?!  "))
        val entry = KnowledgeEntry("entry", "kind", "éastern gate")
        val hit = GmIndex(listOf(entry)).retrieve("éastern", emptySet(), 10, 8)
        assertTrue(hit.isEmpty())
    }

    @Test
    fun `reveal gate removes hidden identifiers sources and text before prompt`() {
        val hidden = KnowledgeEntry(
            "SENTINEL_HIDDEN_ID", "event", "SENTINEL HIDDEN TEXT",
            sourceIds = listOf("SENTINEL_HIDDEN_SOURCE"), revealAfterNodes = listOf("node_reveal"),
        )
        val visible = KnowledgeEntry("visible", "event", "public event")
        val eligible = RevealGate.eligible(listOf(hidden, visible), emptySet())
        val prompt = GmIndex(listOf(hidden, visible)).formatForPrompt(
            GmIndex(listOf(hidden, visible)).lookup("sentinel hidden", emptySet())
        )

        assertEquals(listOf(visible), eligible)
        listOf(hidden.entryId, hidden.normalizedText, hidden.sourceIds.single()).forEach {
            assertTrue(it !in eligible.toString())
            assertTrue(it !in prompt)
        }
        assertEquals(listOf(hidden, visible), RevealGate.eligible(listOf(hidden, visible), setOf("node_reveal")))
    }
}
