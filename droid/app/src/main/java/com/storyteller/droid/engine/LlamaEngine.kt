package com.storyteller.droid.engine

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.buffer
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.io.Closeable
import java.io.File

fun interface NativeTokenCallback {
    fun onText(text: String)
}

interface LlamaNativeRuntime {
    fun load(path: String, contextSize: Int): Long
    fun generate(context: Long, prompt: String, maxTokens: Int, temperature: Float, seed: Int): String
    fun generateStreaming(
        context: Long, prompt: String, maxTokens: Int, temperature: Float, seed: Int,
        callback: NativeTokenCallback,
    ): Int {
        val text = generate(context, prompt, maxTokens, temperature, seed)
        if (text.isNotEmpty()) callback.onText(text)
        return if (text.isEmpty()) 0 else 1
    }
    fun cancel(context: Long)
    fun unload(context: Long)
    fun info(context: Long): String
}

/** Serial, cancellable owner of exactly one native llama model/context pair. */
class LlamaEngine(
    runtimeOverride: LlamaNativeRuntime? = null,
    private val dispatcher: CoroutineDispatcher = Dispatchers.IO,
) : Closeable {
    companion object {
        const val DEFAULT_CONTEXT_SIZE = 2048
        const val MIN_CONTEXT_SIZE = 512
        const val MAX_CONTEXT_SIZE = 8192
        const val MAX_OUTPUT_TOKENS = 1024
        init {
            // JVM unit tests inject a fake runtime and do not package the .so.
            runCatching { System.loadLibrary("llama_jni") }
        }
    }

    private external fun nativeLoadModel(modelPath: String, contextSize: Int): Long
    private external fun nativeGenerate(contextPtr: Long, prompt: String, maxTokens: Int, temperature: Float, seed: Int): String
    private external fun nativeGenerateStreaming(
        contextPtr: Long, prompt: String, maxTokens: Int, temperature: Float, seed: Int,
        callback: NativeTokenCallback,
    ): Int
    private external fun nativeCancelGeneration(contextPtr: Long)
    private external fun nativeUnloadModel(contextPtr: Long)
    private external fun nativeGetModelInfo(contextPtr: Long): String

    private val runtime = runtimeOverride ?: object : LlamaNativeRuntime {
        override fun load(path: String, contextSize: Int) = nativeLoadModel(path, contextSize)
        override fun generate(context: Long, prompt: String, maxTokens: Int, temperature: Float, seed: Int) = nativeGenerate(context, prompt, maxTokens, temperature, seed)
        override fun generateStreaming(
            context: Long, prompt: String, maxTokens: Int, temperature: Float, seed: Int,
            callback: NativeTokenCallback,
        ) = nativeGenerateStreaming(context, prompt, maxTokens, temperature, seed, callback)
        override fun cancel(context: Long) = nativeCancelGeneration(context)
        override fun unload(context: Long) = nativeUnloadModel(context)
        override fun info(context: Long) = nativeGetModelInfo(context)
    }
    private val nativeMutex = Mutex()
    @Volatile private var contextPtr: Long = 0
    @Volatile var isLoaded: Boolean = false
        private set

    suspend fun loadModel(modelPath: String, contextSize: Int = DEFAULT_CONTEXT_SIZE) = withContext(dispatcher) {
        require(contextSize in MIN_CONTEXT_SIZE..MAX_CONTEXT_SIZE) { "Context size must be $MIN_CONTEXT_SIZE..$MAX_CONTEXT_SIZE" }
        require(File(modelPath).isFile) { "Model file not found: $modelPath" }
        nativeMutex.withLock {
            if (isLoaded) return@withLock
            val pointer = runtime.load(modelPath, contextSize)
            check(pointer != 0L) { "Failed to load model: $modelPath" }
            contextPtr = pointer
            isLoaded = true
            runtime.info(pointer) // Force native metadata access while the context is valid.
        }
    }

    suspend fun generate(
        prompt: String,
        maxTokens: Int = 256,
        temperature: Float = 0.8f,
        seed: Int = 0,
    ): String = withContext(dispatcher) {
        require(prompt.isNotBlank()) { "Prompt must not be blank" }
        require(maxTokens in 1..MAX_OUTPUT_TOKENS) { "maxTokens must be 1..$MAX_OUTPUT_TOKENS" }
        require(temperature in 0.0f..2.0f) { "temperature must be 0.0..2.0" }
        nativeMutex.withLock {
            val pointer = contextPtr
            check(isLoaded && pointer != 0L) { "Model not loaded." }
            try {
                runtime.generate(pointer, prompt, maxTokens, temperature, seed)
            } catch (cancelled: CancellationException) {
                runtime.cancel(pointer)
                throw cancelled
            }
        }
    }

    /** Invoke [onText] from the native token loop; no whole-answer rechunking. */
    suspend fun generateStreaming(
        prompt: String,
        maxTokens: Int = 256,
        temperature: Float = 0.8f,
        seed: Int = 0,
        onText: (String) -> Unit,
    ): Int = withContext(dispatcher) {
        require(prompt.isNotBlank()) { "Prompt must not be blank" }
        require(maxTokens in 1..MAX_OUTPUT_TOKENS) { "maxTokens must be 1..$MAX_OUTPUT_TOKENS" }
        require(temperature in 0.0f..2.0f) { "temperature must be 0.0..2.0" }
        nativeMutex.withLock {
            val pointer = contextPtr
            check(isLoaded && pointer != 0L) { "Model not loaded." }
            try {
                runtime.generateStreaming(
                    pointer, prompt, maxTokens, temperature, seed,
                    NativeTokenCallback { text -> if (text.isNotEmpty()) onText(text) },
                )
            } catch (cancelled: CancellationException) {
                runtime.cancel(pointer)
                throw cancelled
            }
        }
    }

    /** Frozen ordered stream around the native semantic callback boundary. */
    fun stream(
        requestId: String,
        prompt: String,
        maxTokens: Int = 256,
        temperature: Float = 0.8f,
        seed: Int = 0,
    ): Flow<ChunkStreamEvent> = callbackFlow {
        val builder = StreamBuilder(requestId)
        send(builder.started())
        val producer = launch(dispatcher) {
            try {
                val count = generateStreaming(prompt, maxTokens, temperature, seed) { text ->
                    runBlocking { send(builder.text(text)) }
                }
                if (count == -2) {
                    send(builder.cancelled())
                } else if (count < 0) {
                    send(builder.failed(StreamErrorCodes.NATIVE_FAILURE))
                } else {
                    send(builder.completed(mapOf("chunks" to count)))
                }
            } catch (_: CancellationException) {
                withContext(NonCancellable) { trySend(builder.cancelled()) }
            } catch (_: Exception) {
                trySend(builder.failed(StreamErrorCodes.NATIVE_FAILURE))
            } finally {
                close()
            }
        }
        awaitClose {
            cancelGeneration()
            producer.cancel()
        }
    }.buffer(BoundedChunkChannel.DEFAULT_CAPACITY)

    /** Interrupts the native token loop without waiting for the serialized call to return. */
    fun cancelGeneration() {
        val pointer = contextPtr
        if (pointer != 0L) runtime.cancel(pointer)
    }

    suspend fun unloadModel() = withContext(dispatcher) {
        cancelGeneration()
        nativeMutex.withLock { unloadLocked() }
    }

    fun onAppBackgrounded() = close()
    fun onMemoryPressure() = close()

    override fun close() {
        cancelGeneration()
        runBlocking(dispatcher) { nativeMutex.withLock { unloadLocked() } }
    }

    private fun unloadLocked() {
        val pointer = contextPtr
        contextPtr = 0
        isLoaded = false
        if (pointer != 0L) runtime.unload(pointer)
    }
}
