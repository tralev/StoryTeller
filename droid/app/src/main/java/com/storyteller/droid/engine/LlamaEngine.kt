package com.storyteller.droid.engine

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Thin Kotlin wrapper around the llama.cpp JNI bridge.
 *
 * Usage:
 *   val engine = LlamaEngine()
 *   engine.loadModel("/data/data/com.storyteller.droid/files/models/llama-3.2-3b.gguf")
 *   val response = engine.generate(prompt, maxTokens = 256)
 *   engine.unloadModel()
 *
 * Thread safety: generate() is synchronous on the native side.
 * Call from a coroutine with Dispatchers.IO.
 */
class LlamaEngine {
    companion object {
        private const val TAG = "LlamaEngine"
        private const val DEFAULT_CONTEXT_SIZE = 2048
    }

    private var contextPtr: Long = 0
    var isLoaded: Boolean = false
        private set

    // ── JNI declarations ─────────────────────────────────────────────

    private external fun nativeLoadModel(
        modelPath: String,
        contextSize: Int,
    ): Long

    private external fun nativeGenerate(
        contextPtr: Long,
        prompt: String,
        maxTokens: Int,
        temperature: Float,
        seed: Int,
    ): String

    private external fun nativeUnloadModel(contextPtr: Long)

    private external fun nativeGetModelInfo(contextPtr: Long): String

    // ── Public API ───────────────────────────────────────────────────

    /**
     * Load a GGUF model into memory.
     *
     * @param modelPath Absolute path to the .gguf file.
     * @param contextSize Context window size (default: 2048).
     * @throws IllegalStateException if a model is already loaded.
     * @throws RuntimeException if loading fails.
     */
    fun loadModel(modelPath: String, contextSize: Int = DEFAULT_CONTEXT_SIZE) {
        check(!isLoaded) { "Model already loaded. Unload first." }
        check(File(modelPath).exists()) { "Model file not found: $modelPath" }

        Log.d(TAG, "Loading model: $modelPath (ctx=$contextSize)")
        contextPtr = nativeLoadModel(modelPath, contextSize)
        check(contextPtr != 0L) { "Failed to load model: $modelPath" }
        isLoaded = true

        val info = nativeGetModelInfo(contextPtr)
        Log.d(TAG, "Model loaded: $info")
    }

    /**
     * Generate a response from a prompt.
     *
     * Runs on the calling thread — wrap in [withContext(Dispatchers.IO)].
     *
     * @param prompt The formatted prompt to send to the model.
     * @param maxTokens Maximum tokens to generate (default: 256).
     * @param temperature Sampling temperature (0.0 = greedy, default: 0.8).
     * @param seed RNG seed for reproducibility.
     * @return The model's text response.
     */
    suspend fun generate(
        prompt: String,
        maxTokens: Int = 256,
        temperature: Float = 0.8f,
        seed: Int = 0,
    ): String = withContext(Dispatchers.IO) {
        check(isLoaded) { "Model not loaded." }
        nativeGenerate(contextPtr, prompt, maxTokens, temperature, seed)
    }

    /**
     * Unload the model and free all memory.
     */
    fun unloadModel() {
        if (!isLoaded) return
        Log.d(TAG, "Unloading model...")
        nativeUnloadModel(contextPtr)
        contextPtr = 0
        isLoaded = false
        Log.d(TAG, "Model unloaded.")
    }

    protected fun finalize() {
        if (isLoaded) {
            Log.w(TAG, "Model not unloaded before GC — unloading now.")
            unloadModel()
        }
    }
}
