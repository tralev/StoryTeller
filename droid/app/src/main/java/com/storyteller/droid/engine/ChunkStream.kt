package com.storyteller.droid.engine

import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.receiveAsFlow

/**
 * P8.6 — Frozen stream event types, identical across Python, Kotlin, Swift.
 *
 * One request owns one model lease and cancellation token.  Cancellation
 * emits [CANCELLED] — never [FAILED].
 */
sealed class ChunkStreamEvent {
    abstract val requestId: String
    abstract val eventType: String

    data class Started(override val requestId: String) : ChunkStreamEvent() {
        override val eventType: String get() = "started"
    }

    data class Text(
        override val requestId: String,
        val sequence: Int,
        val text: String,
    ) : ChunkStreamEvent() {
        override val eventType: String get() = "text"
        init { require(text.isNotEmpty()) { "text chunk must be non-empty" } }
    }

    data class Completed(
        override val requestId: String,
        val sequence: Int,
        val usage: Map<String, Int>,
    ) : ChunkStreamEvent() {
        override val eventType: String get() = "completed"
    }

    data class Failed(
        override val requestId: String,
        val sequence: Int,
        val stableCode: String,
    ) : ChunkStreamEvent() {
        override val eventType: String get() = "failed"
    }

    data class Cancelled(
        override val requestId: String,
        val sequence: Int,
        val stableCode: String = "STREAM_CANCELLED",
    ) : ChunkStreamEvent() {
        override val eventType: String get() = "cancelled"
    }

    /** Every terminal event carries a stable diagnostic code. */
    val terminalCode: String?
        get() = when (this) {
            is Failed -> stableCode
            is Cancelled -> stableCode
            is Completed -> null
            else -> null
        }
}

/**
 * P8.6 — Bounded channel between native callbacks and UI consumer.
 *
 * Fixed capacity ([DEFAULT_CAPACITY] = 64). [send] suspends when the producer
 * outruns the consumer. Events are never dropped, rewritten, or merged.
 *
 * One [BoundedChunkChannel] per request.  Close it to signal the consumer.
 */
class BoundedChunkChannel(capacity: Int = DEFAULT_CAPACITY) {
    companion object {
        const val DEFAULT_CAPACITY = 64
        const val MIN_CAPACITY = 4
    }

    init { require(capacity >= MIN_CAPACITY) { "capacity must be at least $MIN_CAPACITY" } }

    private val channel = Channel<ChunkStreamEvent>(capacity)

    fun events(): Flow<ChunkStreamEvent> = channel.receiveAsFlow()

    suspend fun send(event: ChunkStreamEvent) {
        channel.send(event)
    }

    fun close() { channel.close() }
}

/** P8.C2 stable diagnostic codes for stream errors. */
object StreamErrorCodes {
    const val MODEL_NOT_LOADED = "STREAM_MODEL_NOT_LOADED"
    const val CANCELLED = "STREAM_CANCELLED"
    const val NATIVE_FAILURE = "STREAM_NATIVE_FAILURE"
    const val TIMEOUT = "STREAM_TIMEOUT"
    const val QUEUE_FULL = "STREAM_QUEUE_FULL"
}

/**
 * P8.6 — Builds a correctly-ordered sequence of [ChunkStreamEvent]s.
 *
 * Usage:
 * ```
 * val builder = StreamBuilder("req_01")
 * channel.send(builder.started())
 * channel.send(builder.text("Hello "))
 * channel.send(builder.completed(mapOf("tokens" to 2)))
 * ```
 */
class StreamBuilder(val requestId: String) {
    private var seq = 0

    fun started() = ChunkStreamEvent.Started(requestId)

    fun text(text: String): ChunkStreamEvent.Text {
        seq++
        return ChunkStreamEvent.Text(requestId, seq, text)
    }

    fun completed(usage: Map<String, Int>): ChunkStreamEvent.Completed {
        seq++
        return ChunkStreamEvent.Completed(requestId, seq, usage)
    }

    fun failed(code: String): ChunkStreamEvent.Failed {
        seq++
        return ChunkStreamEvent.Failed(requestId, seq, code)
    }

    fun cancelled(): ChunkStreamEvent.Cancelled {
        seq++
        return ChunkStreamEvent.Cancelled(requestId, seq)
    }
}
