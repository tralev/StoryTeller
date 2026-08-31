package com.storyteller.droid.data

import com.google.gson.Gson
import com.storyteller.droid.engine.ChunkStreamEvent
import com.storyteller.droid.engine.ConversationHistoryStore
import com.storyteller.droid.engine.ConversationTurnTransaction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files

class GmIndexTest {
    @Test
    fun malformedEntryIsRejectedWithoutCrashing() {
        assertEquals(emptyList<KnowledgeEntry>(), GmIndex(mapOf("entries" to listOf(mapOf("kind" to "event")))).entries)
    }
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
            @Suppress("UNCHECKED_CAST")
            val ids = index.retrieve(
                scenario["query"] as String,
                (scenario["visited_nodes"] as List<String>).toSet(),
                (scenario["context_budget_bytes"] as Double).toInt(),
                (scenario["max_results"] as Double).toInt(),
                scenario["current_node_id"] as? String,
                (scenario["visited_refs"] as? List<String>)?.toSet() ?: emptySet(),
            ).map { it.entry.entryId }
            assertEquals(scenario["id"] as String, scenario["expected_ids"] as List<String>, ids)
            outcomes[scenario["id"] as String] = ids
        }
        val output = File(root, "tmp/contracts/gm-android.json")
        output.parentFile?.mkdirs()
        output.writeText(gson.toJson(mapOf("format" to "storyteller.gm-retrieval-results.v1", "scenarios" to outcomes)))
    }

    @Test
    fun `shared cross-domain spoiler scenarios reveal only after visit`() {
        @Suppress("UNCHECKED_CAST")
        val catalog = gson.fromJson(
            File(root, "tests/fixtures/gm_retrieval/spoiler_catalog.json").readText(),
            Map::class.java,
        ) as Map<String, Any>
        @Suppress("UNCHECKED_CAST")
        val index = GmIndex(mapOf("entries" to (catalog["entries"] as List<Map<String, Any>>)))
        @Suppress("UNCHECKED_CAST")
        for (scenario in catalog["scenarios"] as List<Map<String, Any>>) {
            val ids = index.retrieve(
                scenario["query"] as String,
                (scenario["visited_nodes"] as List<String>).toSet(),
            ).map { it.entry.entryId }
            assertEquals(scenario["id"] as String, scenario["expected_ids"] as List<String>, ids)
        }
    }

    @Test
    fun `shared sentinels stay out of prompt diagnostics and saved history before reveal`() {
        @Suppress("UNCHECKED_CAST")
        val catalog = gson.fromJson(
            File(root, "tests/fixtures/gm_retrieval/spoiler_catalog.json").readText(),
            Map::class.java,
        ) as Map<String, Any>
        @Suppress("UNCHECKED_CAST")
        val entries = catalog["entries"] as List<Map<String, Any>>
        @Suppress("UNCHECKED_CAST")
        val sentinels = catalog["sentinels"] as List<String>
        val index = GmIndex(mapOf("entries" to entries))
        val beforeHits = index.lookup("sentinel marker", emptySet())
        val beforePrompt = index.formatForPrompt(beforeHits)
        val diagnostics = beforeHits.toString()
        val historyText = gson.toJson(
            mapOf(
                "story_id" to "spoiler_story",
                "exchanges" to listOf(
                    mapOf(
                        "user_text" to "sentinel marker",
                        "assistant_text" to beforePrompt.ifEmpty { "No revealed lore." },
                    ),
                ),
            ),
        )
        val surfaces = listOf(beforePrompt, diagnostics, "GM_RETRIEVAL_EMPTY", historyText)
        sentinels.forEach { sentinel ->
            assertTrue(sentinel, surfaces.none { sentinel in it })
        }

        val after = index.promptContext(
            "sentinelglobaltext7e15", setOf("node_global_reveal"),
        )
        assertTrue(after.contains("sentinel-global-id-7e15"))
        assertTrue(after.contains("sentinelglobaltext7e15"))
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

    @Test
    fun `hidden retrieval cancellation and persisted history stay isolated together`() {
        @Suppress("UNCHECKED_CAST")
        val catalog = gson.fromJson(
            File(root, "tests/fixtures/gm_retrieval/spoiler_catalog.json").readText(),
            Map::class.java,
        ) as Map<String, Any>
        @Suppress("UNCHECKED_CAST")
        val index = GmIndex(mapOf("entries" to (catalog["entries"] as List<Map<String, Any>>)))
        @Suppress("UNCHECKED_CAST") val sentinels = catalog["sentinels"] as List<String>
        val prompt = index.promptContext("sentinel marker", emptySet())
        assertTrue(prompt.isEmpty())

        val history = Files.createTempDirectory("isolation").resolve("history.json").toFile()
        val storyId = "story_" + "0".repeat(32)
        val contentHash = "a".repeat(64)
        val baseline = ConversationTurnTransaction(
            history, storyId, contentHash, "default", "Public question", "baseline", 1.0,
        )
        baseline.accept(ChunkStreamEvent.Text("baseline", 1, "Public answer"))
        baseline.accept(ChunkStreamEvent.Completed("baseline", 2, emptyMap()))
        val before = history.readBytes()

        val cancelled = ConversationTurnTransaction(
            history, storyId, contentHash, "default", "sentinel marker", "cancelled", 2.0,
        )
        cancelled.accept(ChunkStreamEvent.Text("cancelled", 1, prompt.ifEmpty { "No revealed lore." }))
        cancelled.accept(ChunkStreamEvent.Cancelled("cancelled", 2))
        assertEquals(before.toList(), history.readBytes().toList())
        val persisted = history.readText()
        sentinels.forEach { assertTrue(it, it !in persisted) }
        assertEquals(1, ConversationHistoryStore.loadBound(history, storyId, contentHash)?.exchangeCount)
    }
}
