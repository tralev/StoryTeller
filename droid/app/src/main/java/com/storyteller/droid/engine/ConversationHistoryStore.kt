package com.storyteller.droid.engine

import java.io.File
import java.io.FileNotFoundException
import java.io.FileOutputStream
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import org.json.JSONArray
import org.json.JSONObject

/**
 * P8.7 — Transactional conversation history.
 *
 * Durable conversation save — isolated from the immutable .story.
 * Writes temp file, fsyncs, then atomically replaces.
 * Only completed exchanges are saved; cancel/failure leaves no partial turn.
 */
object ConversationHistoryStore {
    private const val VERSION = 1
    private const val MAX_EXCHANGES = 10_000
    private const val MAX_EXCHANGE_TEXT_BYTES = 64 * 1024
    private const val MAX_TOTAL_BYTES = 10 * 1024 * 1024

    // ── Data classes ──────────────────────────────────────────────

    data class Exchange(
        val exchangeId: String,
        val userText: String,
        val assistantText: String,
        val sequence: Int,
        val createdAt: Double
    ) {
        fun toJson(): JSONObject = JSONObject().apply {
            put("exchange_id", exchangeId)
            put("user_text", userText)
            put("assistant_text", assistantText)
            put("sequence", sequence)
            put("created_at", createdAt)
        }

        companion object {
            fun fromJson(json: JSONObject): Exchange = Exchange(
                exchangeId = json.getString("exchange_id"),
                userText = json.getString("user_text"),
                assistantText = json.getString("assistant_text"),
                sequence = json.getInt("sequence"),
                createdAt = json.getDouble("created_at")
            )
        }
    }

    data class ConversationHistory(
        val version: Int = VERSION,
        val storyId: String = "",
        val contentHash: String = "",
        val conversationId: String = "",
        val exchanges: List<Exchange> = emptyList(),
        val metadata: Map<String, String> = emptyMap()
    ) {
        val exchangeCount: Int get() = exchanges.size

        fun toJson(): JSONObject {
            val arr = JSONArray()
            exchanges.forEach { arr.put(it.toJson()) }
            val meta = JSONObject()
            metadata.forEach { (k, v) -> meta.put(k, v) }

            val exchangesForHash = JSONArray()
            exchanges.sortedBy { it.sequence }.forEach { exchangesForHash.put(it.toJson()) }

            return JSONObject().apply {
                put("version", version)
                put("story_id", storyId)
                put("content_hash", contentHash)
                put("conversation_id", conversationId)
                put("exchanges", arr)
                put("metadata", meta)
                put("_sha256", sha256(exchangesForHash.toString()))
            }
        }

        companion object {
            fun fromJson(json: JSONObject): ConversationHistory {
                val arr = json.optJSONArray("exchanges") ?: JSONArray()
                val exchanges = (0 until arr.length()).map { i ->
                    Exchange.fromJson(arr.getJSONObject(i))
                }
                val meta = mutableMapOf<String, String>()
                json.optJSONObject("metadata")?.let { metaObj ->
                    metaObj.keys().forEach { key ->
                        meta[key] = metaObj.optString(key, "")
                    }
                }
                return ConversationHistory(
                    version = json.optInt("version", VERSION),
                    storyId = json.optString("story_id", ""),
                    contentHash = json.optString("content_hash", ""),
                    conversationId = json.optString("conversation_id", ""),
                    exchanges = exchanges,
                    metadata = meta
                )
            }
        }
    }

    class ConversationHistoryException(val code: String, message: String) :
        RuntimeException("$code: $message")

    // ── Save / Load ───────────────────────────────────────────────

    fun save(path: File, history: ConversationHistory) {
        if (history.exchangeCount > MAX_EXCHANGES) {
            throw ConversationHistoryException(
                "HISTORY_EXCHANGE_LIMIT",
                "${history.exchangeCount} exchanges exceeds limit of $MAX_EXCHANGES"
            )
        }

        val data = history.toJson().toString(2).toByteArray(StandardCharsets.UTF_8)
        if (data.size > MAX_TOTAL_BYTES) {
            throw ConversationHistoryException(
                "HISTORY_SIZE_LIMIT",
                "history exceeds ${MAX_TOTAL_BYTES / (1024 * 1024)} MB"
            )
        }

        val tmp = File(path.parentFile, path.name + ".tmp")
        tmp.parentFile?.mkdirs()

        // Temp write
        FileOutputStream(tmp).use { fos ->
            fos.write(data)
            fos.fd.sync() // fsync
        }
        tmp.setReadable(true, true)
        tmp.setWritable(true, true)

        // Atomic replace
        if (!tmp.renameTo(path)) {
            path.delete()
            if (!tmp.renameTo(path)) {
                tmp.delete()
                throw ConversationHistoryException(
                    "HISTORY_ATOMIC_FAILED",
                    "failed to atomically replace history file"
                )
            }
        }
    }

    fun load(path: File): ConversationHistory? {
        if (!path.exists()) return null

        val data: ByteArray
        try {
            data = path.readBytes()
        } catch (e: FileNotFoundException) {
            return null
        }

        if (data.size > MAX_TOTAL_BYTES) {
            throw ConversationHistoryException(
                "HISTORY_SIZE_LIMIT",
                "saved history exceeds size limit"
            )
        }

        val raw: JSONObject
        try {
            raw = JSONObject(String(data, StandardCharsets.UTF_8))
        } catch (e: Exception) {
            throw ConversationHistoryException(
                "HISTORY_CORRUPT_JSON",
                "cannot parse history: ${e.message}"
            )
        }

        val version = raw.optInt("version", -1)
        if (!raw.has("version")) {
            throw ConversationHistoryException("HISTORY_MISSING_VERSION", "no version field")
        }
        if (version != VERSION) {
            if (version > VERSION) {
                throw ConversationHistoryException(
                    "HISTORY_FUTURE_VERSION",
                    "cannot read version $version — update the app"
                )
            }
            throw ConversationHistoryException(
                "HISTORY_OLD_VERSION",
                "version $version is not supported"
            )
        }

        val history = ConversationHistory.fromJson(raw)

        if (history.exchangeCount > MAX_EXCHANGES) {
            throw ConversationHistoryException(
                "HISTORY_EXCHANGE_LIMIT",
                "${history.exchangeCount} exchanges exceeds limit of $MAX_EXCHANGES"
            )
        }

        // Verify ordering
        for ((i, e) in history.exchanges.withIndex()) {
            if (e.sequence != i) {
                throw ConversationHistoryException(
                    "HISTORY_ORDER_BROKEN",
                    "exchange ${e.exchangeId} has sequence ${e.sequence}, expected $i"
                )
            }
            if (e.userText.toByteArray(StandardCharsets.UTF_8).size > MAX_EXCHANGE_TEXT_BYTES ||
                e.assistantText.toByteArray(StandardCharsets.UTF_8).size > MAX_EXCHANGE_TEXT_BYTES) {
                throw ConversationHistoryException(
                    "HISTORY_TEXT_SIZE",
                    "exchange ${e.exchangeId} text exceeds limit"
                )
            }
        }

        // Verify content hash
        val exchangesForHash = JSONArray()
        history.exchanges.sortedBy { it.sequence }.forEach { exchangesForHash.put(it.toJson()) }
        val expectedHash = sha256(exchangesForHash.toString())
        val actualHash = raw.optString("_sha256", "")
        if (actualHash.isNotEmpty() && actualHash != expectedHash) {
            throw ConversationHistoryException(
                "HISTORY_HASH_MISMATCH",
                "content hash mismatch — history may be tampered"
            )
        }

        return history
    }

    fun loadBound(path: File, storyId: String, contentHash: String): ConversationHistory? {
        val history = load(path) ?: return null
        if (history.storyId != storyId || history.contentHash != contentHash) {
            throw ConversationHistoryException(
                "HISTORY_IDENTITY_MISMATCH", "history belongs to different immutable content"
            )
        }
        return history
    }

    fun addExchange(
        path: File,
        exchange: Exchange,
        storyId: String = "",
        contentHash: String = "",
        conversationId: String = ""
    ): ConversationHistory {
        val current = load(path)
        val existing = current?.exchanges?.toMutableList() ?: mutableListOf()

        if (existing.isNotEmpty()) {
            val lastSeq = existing.last().sequence
            if (exchange.sequence != lastSeq + 1) {
                throw ConversationHistoryException(
                    "HISTORY_SEQUENCE_SKIP",
                    "expected sequence ${lastSeq + 1}, got ${exchange.sequence}"
                )
            }
        }

        existing.add(exchange)
        val history = ConversationHistory(
            version = VERSION,
            storyId = storyId.ifEmpty { current?.storyId ?: "" },
            contentHash = contentHash.ifEmpty { current?.contentHash ?: "" },
            conversationId = conversationId.ifEmpty { current?.conversationId ?: "" },
            exchanges = existing.toList(),
            metadata = current?.metadata ?: emptyMap()
        )
        save(path, history)
        return history
    }

    fun delete(path: File) {
        path.delete()
        File(path.parentFile, path.name + ".tmp").delete()
    }

    // ── Helpers ───────────────────────────────────────────────────

    private fun sha256(input: String): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val hashBytes = digest.digest(input.toByteArray(StandardCharsets.UTF_8))
        return hashBytes.joinToString("") { "%02x".format(it) }
    }
}
