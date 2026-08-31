package com.storyteller.droid.data

import com.google.gson.Gson
import com.storyteller.droid.model.StoryPackage
import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import java.util.zip.ZipFile
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertThrows
import org.junit.Test

class KnowledgeSourceTest {
    @Test
    fun revealGateRunsBeforeBoundedChunkOpen() {
        val root = Files.createTempDirectory("knowledge-source").toFile()
        val chunks = File(root, "chunks").apply { mkdirs() }
        val known = record("known", "known eastern gate", emptyList())
        val hidden = record("hidden", "UNOPENED_SENTINEL eastern gate", listOf("node_2"))
        val locators = listOf(write(chunks, known), write(chunks, hidden))
        File(root, "index.json").writeText(Gson().toJson(mapOf("entries" to locators)))

        val read = DirectoryKnowledgeSource(root).read(
            queryTokens = setOf("eastern"), maxRecords = 8, maxExcerptBytes = 4096,
        )

        assertEquals(listOf("known"), read.excerpts.map(KnowledgeEntry::entryId))
        assertEquals(1, read.counters.chunksOpened)
        assertEquals(1, read.counters.recordsDecoded)
        assertFalse(read.toString().contains("UNOPENED_SENTINEL"))
    }

    @Test
    fun repositorySelectsBoundedSourceAndExposesCounters() {
        val storyRoot = Files.createTempDirectory("knowledge-repository").toFile()
        val narrative = File(storyRoot, "narrative").apply { mkdirs() }
        val knowledge = File(narrative, "knowledge")
        val chunks = File(knowledge, "chunks").apply { mkdirs() }
        val known = record("known", "known eastern gate", emptyList())
        val locator = write(chunks, known)
        File(knowledge, "index.json").writeText(Gson().toJson(mapOf("entries" to listOf(locator))))
        File(narrative, "gm_index.json").writeText("{\"entries\":[]}")
        val story = StoryPackage("story", "Story", 1, "hash", "node", storyRoot)

        val lookup = StoryRepository(story).gmLookup("eastern", emptySet())

        assertEquals(true, lookup.usedBoundedSource)
        assertEquals(1, lookup.counters?.chunksOpened)
        assertEquals("known", lookup.promptContext.substringAfter("[").substringBefore("]"))
    }

    @Test
    fun repositoryFallsBackForPreSliceV2Package() {
        val storyRoot = Files.createTempDirectory("knowledge-fallback").toFile()
        val narrative = File(storyRoot, "narrative").apply { mkdirs() }
        val record = record("legacy", "legacy eastern gate", emptyList())
        File(narrative, "gm_index.json").writeText(Gson().toJson(mapOf("entries" to listOf(record))))
        val story = StoryPackage("story", "Story", 1, "hash", "node", storyRoot)

        val lookup = StoryRepository(story).gmLookup("eastern", emptySet())

        assertFalse(lookup.usedBoundedSource)
        assertEquals(null, lookup.counters)
        assertEquals("legacy", lookup.promptContext.substringAfter("[").substringBefore("]"))
    }

    @Test
    fun hostileLocatorIsRejectedBeforeChunkIo() {
        val root = Files.createTempDirectory("knowledge-hostile").toFile()
        val locator = mapOf(
            "entry_id" to "hostile", "tokens" to listOf("eastern"),
            "reveal_after_nodes" to emptyList<String>(), "path" to "../escape.json",
            "sha256" to "0".repeat(64), "size_bytes" to 1,
        )
        File(root, "index.json").writeText(Gson().toJson(mapOf("entries" to listOf(locator))))

        assertThrows(IllegalArgumentException::class.java) { DirectoryKnowledgeSource(root) }
    }

    @Test
    fun duplicateLocatorIdentityIsRejected() {
        val root = Files.createTempDirectory("knowledge-duplicate").toFile()
        val locator = mapOf(
            "entry_id" to "duplicate", "tokens" to listOf("eastern"),
            "reveal_after_nodes" to emptyList<String>(), "path" to "chunks/duplicate.json",
            "sha256" to "0".repeat(64), "size_bytes" to 1,
        )
        File(root, "index.json").writeText(
            Gson().toJson(mapOf("entries" to listOf(locator, locator))),
        )

        assertThrows(IllegalArgumentException::class.java) { DirectoryKnowledgeSource(root) }
    }

    @Test
    fun sharedV2PackageOpensOneBoundedChunk() {
        val projectRoot = generateSequence(File(requireNotNull(System.getProperty("user.dir")))) { it.parentFile }
            .first { File(it, "tests/fixtures/v2/complete.story").isFile }
        val extracted = Files.createTempDirectory("knowledge-shared").toFile()
        ZipFile(File(projectRoot, "tests/fixtures/v2/complete.story")).use { archive ->
            archive.entries().asSequence().filter { it.name.startsWith("narrative/knowledge/") }
                .forEach { entry ->
                    val target = File(extracted, entry.name.removePrefix("narrative/knowledge/"))
                    target.parentFile?.mkdirs()
                    target.writeBytes(archive.getInputStream(entry).use { it.readBytes() })
                }
        }

        val read = DirectoryKnowledgeSource(extracted).read(
            queryTokens = setOf("eastern"),
            visitedNodes = setOf("node_00000000000000000000000000000001"),
            maxRecords = 1,
            maxExcerptBytes = 8192,
        )

        assertEquals(listOf("knowledge_00000000000000000000000000000001"), read.excerpts.map { it.entryId })
        assertEquals(KnowledgeReadCounters(read.counters.bytesRead, 1, 1), read.counters)
    }

    @Test
    fun sharedLocalSpoilerChunkStaysPhysicallyUnopenedUntilReveal() {
        val projectRoot = generateSequence(File(requireNotNull(System.getProperty("user.dir")))) { it.parentFile }
            .first { File(it, "tests/fixtures/gm_retrieval/spoiler_catalog.json").isFile }
        @Suppress("UNCHECKED_CAST")
        val catalog = Gson().fromJson(
            File(projectRoot, "tests/fixtures/gm_retrieval/spoiler_catalog.json").readText(),
            Map::class.java,
        ) as Map<String, Any>
        @Suppress("UNCHECKED_CAST")
        val record = (catalog["entries"] as List<Map<String, Any>>)
            .first { it["kind"] == "local_map" }
        val root = Files.createTempDirectory("knowledge-spoiler-shared").toFile()
        val chunks = File(root, "chunks").apply { mkdirs() }
        val payload = Gson().toJson(record).toByteArray()
        val id = record.getValue("entry_id") as String
        File(chunks, "$id.json").writeBytes(payload)
        val locator = mapOf(
            "entry_id" to id, "tokens" to listOf("sentinellocaltext31d8"),
            "reveal_after_nodes" to record.getValue("reveal_after_nodes"),
            "path" to "chunks/$id.json", "sha256" to sha256(payload),
            "size_bytes" to payload.size,
        )
        File(root, "index.json").writeText(Gson().toJson(mapOf("entries" to listOf(locator))))
        val source = DirectoryKnowledgeSource(root)

        val before = source.read(
            queryTokens = setOf("sentinellocaltext31d8"), maxRecords = 8,
            maxExcerptBytes = 8192,
        )
        assertEquals(KnowledgeRead(emptyList(), KnowledgeReadCounters()), before)

        val after = source.read(
            queryTokens = setOf("sentinellocaltext31d8"),
            visitedNodes = setOf("node_local_reveal"), maxRecords = 8,
            maxExcerptBytes = 8192,
        )
        assertEquals(listOf(id), after.excerpts.map(KnowledgeEntry::entryId))
        assertEquals(KnowledgeReadCounters(payload.size.toLong(), 1, 1), after.counters)
    }

    private fun record(id: String, text: String, reveal: List<String>) = linkedMapOf<String, Any>(
        "entry_id" to id, "kind" to "event", "normalized_text" to text,
        "source_ids" to listOf("source"), "incoming_refs" to emptyList<String>(),
        "outgoing_refs" to emptyList<String>(), "reveal_after_nodes" to reveal,
    )

    private fun write(root: File, record: Map<String, Any>): Map<String, Any> {
        val payload = Gson().toJson(record).toByteArray()
        val id = record.getValue("entry_id") as String
        File(root, "$id.json").writeBytes(payload)
        return mapOf(
            "entry_id" to id, "tokens" to listOf("eastern", "gate"),
            "reveal_after_nodes" to record.getValue("reveal_after_nodes"),
            "path" to "chunks/$id.json", "sha256" to sha256(payload), "size_bytes" to payload.size,
        )
    }

    private fun sha256(payload: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(payload).joinToString("") { "%02x".format(it) }
}
