package com.storyteller.droid.engine

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.nio.file.Files

class LlamaEngineLifecycleTest {
    private class FakeRuntime : LlamaNativeRuntime {
        var loads = 0
        var cancels = 0
        var unloads = 0
        override fun load(path: String, contextSize: Int): Long { loads++; return 42 }
        override fun generate(context: Long, prompt: String, maxTokens: Int, temperature: Float, seed: Int) = "answer"
        override fun cancel(context: Long) { cancels++ }
        override fun unload(context: Long) { unloads++ }
        override fun info(context: Long) = "{}"
    }

    @Test
    fun loadGenerateBackgroundUnloadOwnsOneContext() = runBlocking {
        val model = Files.createTempFile("model", ".gguf").toFile()
        val native = FakeRuntime()
        val engine = LlamaEngine(native, Dispatchers.Unconfined)
        try {
            engine.loadModel(model.absolutePath)
            engine.loadModel(model.absolutePath)
            assertTrue(engine.isLoaded)
            assertEquals("answer", engine.generate("prompt"))
            assertEquals(1, native.loads)
            engine.onAppBackgrounded()
            assertFalse(engine.isLoaded)
            assertEquals(1, native.unloads)
            assertTrue(native.cancels >= 1)
        } finally { model.delete() }
    }

    @Test
    fun invalidBudgetsAreRejectedBeforeNativeCalls() = runBlocking {
        val model = Files.createTempFile("model", ".gguf").toFile()
        val native = FakeRuntime()
        val engine = LlamaEngine(native, Dispatchers.Unconfined)
        try {
            val error = runCatching { engine.loadModel(model.absolutePath, 128) }.exceptionOrNull()
            assertTrue(error is IllegalArgumentException)
            assertEquals(0, native.loads)
        } finally { model.delete() }
    }

    @Test
    fun closeIsIdempotent() = runBlocking {
        val model = Files.createTempFile("model", ".gguf").toFile()
        val native = FakeRuntime()
        val engine = LlamaEngine(native, Dispatchers.Unconfined)
        try {
            engine.loadModel(model.absolutePath)
            engine.close(); engine.close()
            assertEquals(1, native.unloads)
        } finally { model.delete() }
    }
}
