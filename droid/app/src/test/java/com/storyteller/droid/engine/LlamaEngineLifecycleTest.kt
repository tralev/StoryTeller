package com.storyteller.droid.engine

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.launch
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
        var streamingResult = 2
        override fun load(path: String, contextSize: Int): Long { loads++; return 42 }
        override fun generate(context: Long, prompt: String, maxTokens: Int, temperature: Float, seed: Int) = "answer"
        override fun generateStreaming(
            context: Long, prompt: String, maxTokens: Int, temperature: Float, seed: Int,
            callback: NativeTokenCallback,
        ): Int {
            callback.onText("ans")
            callback.onText("wer")
            return streamingResult
        }
        override fun cancel(context: Long) { cancels++ }
        override fun unload(context: Long) { unloads++ }
        override fun info(context: Long) = "{}"
    }

    @Test
    fun `streaming forwards native semantic chunks without rechunking`() = runBlocking {
        val native = FakeRuntime()
        val engine = LlamaEngine(native, Dispatchers.Unconfined)
        val model = Files.createTempFile("model", ".gguf").toFile()
        engine.loadModel(model.path)
        val chunks = mutableListOf<String>()

        val count = engine.generateStreaming("prompt", onText = chunks::add)

        assertEquals(2, count)
        assertEquals(listOf("ans", "wer"), chunks)
        engine.close()
    }

    @Test
    fun `typed stream has ordered native chunks and one terminal event`() = runBlocking {
        val engine = LlamaEngine(FakeRuntime(), Dispatchers.Unconfined)
        val model = Files.createTempFile("model", ".gguf").toFile()
        engine.loadModel(model.path)

        val events = engine.stream("req_01", "prompt").toList()

        assertEquals(
            listOf("started", "text", "text", "completed"),
            events.map(ChunkStreamEvent::eventType),
        )
        assertEquals(listOf("ans", "wer"), events.filterIsInstance<ChunkStreamEvent.Text>().map { it.text })
        assertEquals(1, events.count { it is ChunkStreamEvent.Completed })
        engine.close()
    }

    @Test
    fun `native cancellation has one cancelled terminal and no completion`() = runBlocking {
        val native = FakeRuntime().apply { streamingResult = -2 }
        val engine = LlamaEngine(native, Dispatchers.Unconfined)
        val model = Files.createTempFile("model", ".gguf").toFile()
        engine.loadModel(model.path)

        val events = engine.stream("req_cancel", "prompt").toList()

        assertEquals(1, events.count { it is ChunkStreamEvent.Cancelled })
        assertEquals(0, events.count { it is ChunkStreamEvent.Completed })
        assertEquals("cancelled", events.last().eventType)
        engine.close()
    }

    @Test
    fun `bounded channel preserves every event for a slow consumer`() = runBlocking {
        val channel = BoundedChunkChannel(capacity = 4)
        val builder = StreamBuilder("req_slow")
        val received = mutableListOf<ChunkStreamEvent>()
        val consumer = launch {
            channel.events().onEach { delay(1) }.collect(received::add)
        }
        val expected = (1..80).map { builder.text("chunk-$it") }
        expected.forEach { channel.send(it) }
        channel.close()
        consumer.join()

        assertEquals(expected, received)
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
