package com.storyteller.droid.data

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import java.io.File
import java.security.MessageDigest

data class KnowledgeReadCounters(val bytesRead: Long = 0, val chunksOpened: Int = 0, val recordsDecoded: Int = 0)
data class KnowledgeRead(val excerpts: List<KnowledgeEntry>, val counters: KnowledgeReadCounters)

private data class KnowledgeLocator(
    val entryId: String,
    val tokens: Set<String>,
    val revealAfterNodes: Set<String>,
    val path: String,
    val sha256: String,
    val sizeBytes: Long,
)

/** Bounded content-addressed reader for the v2 narrative/knowledge namespace. */
class DirectoryKnowledgeSource(private val root: File) {
    private val gson = Gson()
    private val canonicalRoot = root.canonicalFile
    private val locators: List<KnowledgeLocator> = parseIndex(File(root, "index.json"))

    fun read(
        entryIds: Set<String> = emptySet(),
        queryTokens: Set<String> = emptySet(),
        visitedNodes: Set<String> = emptySet(),
        maxRecords: Int,
        maxExcerptBytes: Long,
    ): KnowledgeRead {
        require(maxRecords >= 0 && maxExcerptBytes >= 0) { "knowledge bounds must be non-negative" }
        if (maxRecords == 0 || maxExcerptBytes == 0L) return KnowledgeRead(emptyList(), KnowledgeReadCounters())
        val excerpts = mutableListOf<KnowledgeEntry>()
        var bytesRead = 0L
        var chunksOpened = 0
        var recordsDecoded = 0
        for (locator in locators) {
            if (excerpts.size == maxRecords) break
            if (entryIds.isNotEmpty() && locator.entryId !in entryIds) continue
            if (queryTokens.isNotEmpty() && locator.tokens.intersect(queryTokens).isEmpty()) continue
            if (!visitedNodes.containsAll(locator.revealAfterNodes)) continue
            if (bytesRead + locator.sizeBytes > maxExcerptBytes) continue
            val file = File(canonicalRoot, locator.path).canonicalFile
            require(file.parentFile?.toPath()?.startsWith(canonicalRoot.toPath()) == true) { "KNOWLEDGE_CHUNK_PATH" }
            require(file.length() == locator.sizeBytes) { "KNOWLEDGE_CHUNK_SIZE" }
            val payload = file.readBytes()
            chunksOpened += 1
            bytesRead += payload.size
            require(sha256(payload) == locator.sha256) { "KNOWLEDGE_CHUNK_HASH" }
            val entry = parseEntry(payload)
            recordsDecoded += 1
            require(entry.entryId == locator.entryId) { "KNOWLEDGE_CHUNK_ID" }
            require(entry.revealAfterNodes.toSet() == locator.revealAfterNodes) { "KNOWLEDGE_CHUNK_REVEAL" }
            excerpts += entry
        }
        return KnowledgeRead(excerpts, KnowledgeReadCounters(bytesRead, chunksOpened, recordsDecoded))
    }

    private fun parseIndex(file: File): List<KnowledgeLocator> {
        val type = object : TypeToken<Map<String, Any>>() {}.type
        val raw: Map<String, Any> = gson.fromJson(file.readText(Charsets.UTF_8), type)
        val entries = raw["entries"] as? List<*> ?: error("KNOWLEDGE_INDEX_FORMAT")
        val parsed = entries.map { value ->
            val item = value as? Map<*, *> ?: error("KNOWLEDGE_INDEX_ENTRY")
            val tokens = strings(item["tokens"])
            val reveal = strings(item["reveal_after_nodes"])
            val path = item["path"] as? String ?: error("KNOWLEDGE_INDEX_ENTRY")
            val hash = item["sha256"] as? String ?: error("KNOWLEDGE_INDEX_ENTRY")
            val size = (item["size_bytes"] as? Number)?.toLong() ?: error("KNOWLEDGE_INDEX_ENTRY")
            require(tokens == tokens.distinct().sorted() && reveal == reveal.distinct().sorted() &&
                !path.startsWith('/') && '\\' !in path && path.split('/').none { it.isEmpty() || it == "." || it == ".." } &&
                hash.matches(Regex("[0-9a-f]{64}")) && size >= 0
            ) { "KNOWLEDGE_INDEX_ENTRY" }
            KnowledgeLocator(
                item["entry_id"] as? String ?: error("KNOWLEDGE_INDEX_ENTRY"),
                tokens.toSet(), reveal.toSet(), path, hash, size,
            )
        }.sortedBy(KnowledgeLocator::entryId)
        require(parsed.map(KnowledgeLocator::entryId).distinct().size == parsed.size) { "KNOWLEDGE_INDEX_DUPLICATE_ID" }
        return parsed
    }

    private fun parseEntry(payload: ByteArray): KnowledgeEntry {
        val type = object : TypeToken<Map<String, Any>>() {}.type
        val item: Map<String, Any> = gson.fromJson(String(payload, Charsets.UTF_8), type)
        return KnowledgeEntry(
            item["entry_id"] as? String ?: error("KNOWLEDGE_CHUNK_FORMAT"),
            item["kind"] as? String ?: error("KNOWLEDGE_CHUNK_FORMAT"),
            item["normalized_text"] as? String ?: error("KNOWLEDGE_CHUNK_FORMAT"),
            strings(item["source_ids"]), strings(item["incoming_refs"]),
            strings(item["outgoing_refs"]), strings(item["reveal_after_nodes"]),
        )
    }

    private fun strings(value: Any?): List<String> =
        (value as? List<*>)?.map { it as? String ?: error("KNOWLEDGE_INDEX_ENTRY") }.orEmpty()

    private fun sha256(payload: ByteArray): String =
        MessageDigest.getInstance("SHA-256").digest(payload).joinToString("") { "%02x".format(it) }
}
