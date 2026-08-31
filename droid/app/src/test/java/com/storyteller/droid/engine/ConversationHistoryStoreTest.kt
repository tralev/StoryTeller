package com.storyteller.droid.engine

import java.nio.file.Files
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class ConversationHistoryStoreTest {
    private val storyId = "story_" + "0".repeat(32)
    private val contentHash = "a".repeat(64)

    private fun transaction(path: java.io.File, id: String = "exchange-1") =
        ConversationTurnTransaction(
            path, storyId, contentHash, "default", "Question?", id, 1.0,
        )

    @Test
    fun `completed stream commits exactly one paired exchange and restores`() {
        val path = Files.createTempDirectory("history").resolve("history.json").toFile()
        val tx = transaction(path)
        tx.accept(ChunkStreamEvent.Started("request"))
        tx.accept(ChunkStreamEvent.Text("request", 1, "Answer "))
        tx.accept(ChunkStreamEvent.Text("request", 2, "here."))

        assertEquals("Answer here.", tx.accept(ChunkStreamEvent.Completed("request", 3, emptyMap())))
        tx.accept(ChunkStreamEvent.Completed("request", 4, emptyMap()))

        val restored = ConversationHistoryStore.loadBound(path, storyId, contentHash)!!
        assertEquals(1, restored.exchangeCount)
        assertEquals("Question?", restored.exchanges.single().userText)
        assertEquals("Answer here.", restored.exchanges.single().assistantText)
    }

    @Test
    fun `failure and cancellation leave existing history byte identical`() {
        val path = Files.createTempDirectory("history").resolve("history.json").toFile()
        val initial = transaction(path, "initial")
        initial.accept(ChunkStreamEvent.Text("initial", 1, "Kept"))
        initial.accept(ChunkStreamEvent.Completed("initial", 2, emptyMap()))
        val before = path.readBytes()

        val failed = transaction(path, "failed")
        failed.accept(ChunkStreamEvent.Text("failed", 1, "partial-secret"))
        failed.accept(ChunkStreamEvent.Failed("failed", 2, "STREAM_NATIVE_FAILURE"))
        assertArrayEquals(before, path.readBytes())

        val cancelled = transaction(path, "cancelled")
        cancelled.accept(ChunkStreamEvent.Text("cancelled", 1, "partial-secret"))
        cancelled.accept(ChunkStreamEvent.Cancelled("cancelled", 2))
        assertArrayEquals(before, path.readBytes())
    }

    @Test
    fun `identity mismatch corrupt json and oversized assistant are rejected`() {
        val root = Files.createTempDirectory("history")
        val path = root.resolve("history.json").toFile()
        val tx = transaction(path)
        tx.accept(ChunkStreamEvent.Text("request", 1, "Answer"))
        tx.accept(ChunkStreamEvent.Completed("request", 2, emptyMap()))
        assertThrows(ConversationHistoryStore.ConversationHistoryException::class.java) {
            ConversationHistoryStore.loadBound(path, storyId, "b".repeat(64))
        }

        path.writeText("{truncated")
        assertThrows(ConversationHistoryStore.ConversationHistoryException::class.java) {
            ConversationHistoryStore.load(path)
        }

        ConversationHistoryStore.delete(path)
        val oversized = transaction(path, "oversized")
        oversized.accept(ChunkStreamEvent.Text("oversized", 1, "x".repeat(64 * 1024 + 1)))
        assertThrows(ConversationHistoryStore.ConversationHistoryException::class.java) {
            oversized.accept(ChunkStreamEvent.Completed("oversized", 2, emptyMap()))
        }
    }

    @Test
    fun `legacy pairs migrate once without overwriting durable history`() {
        val path = Files.createTempDirectory("history").resolve("history.json").toFile()
        val migrated = ConversationHistoryStore.migrateLegacy(
            path, listOf("Old question" to "Old answer"), storyId, contentHash,
        )!!
        val firstBytes = path.readBytes()
        assertEquals("legacy-00000000", migrated.exchanges.single().exchangeId)

        val reopened = ConversationHistoryStore.migrateLegacy(
            path, listOf("Replacement" to "Must not win"), storyId, contentHash,
        )!!
        assertEquals("Old question", reopened.exchanges.single().userText)
        assertArrayEquals(firstBytes, path.readBytes())
    }
}
