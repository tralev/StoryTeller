package com.storyteller.droid.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.nio.file.Files
import java.security.MessageDigest
import java.util.concurrent.atomic.AtomicInteger
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody

class ModelDownloadManagerTest {
    private fun spec(bytes: ByteArray, hash: String = sha(bytes)) = ReleaseModelRegistry.gameMaster.copy(
        filename = "test.gguf", byteSize = bytes.size.toLong(), sha256 = hash,
        minimumFreeStorageBytes = bytes.size.toLong(),
    )

    private fun sha(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(bytes).joinToString("") { "%02x".format(it) }

    private fun client(handler: (okhttp3.Request) -> Response): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor { chain -> handler(chain.request()) }
        .build()

    private fun response(request: okhttp3.Request, code: Int, bytes: ByteArray, contentRange: String? = null): Response {
        val builder = Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(code).message("test").body(bytes.toResponseBody())
        if (contentRange != null) builder.header("Content-Range", contentRange)
        return builder.build()
    }

    @Test
    fun sha256IsStreamingAndStable() {
        val directory = Files.createTempDirectory("model-hash").toFile()
        try {
            val file = File(directory, "model.part").apply { writeText("StoryTeller") }
            assertEquals("62aad81d5f84ea420ae5a9ac0b3a3b9e2bc230a37488f0737862da0af5597ad5", ModelDownloadManager.sha256(file))
        } finally {
            directory.deleteRecursively()
        }
    }

    @Test
    fun atomicPublicationRemovesPartialAndPublishesExactBytes() {
        val directory = Files.createTempDirectory("model-publish").toFile()
        try {
            val partial = File(directory, "model.gguf.part").apply { writeText("verified") }
            val installed = File(directory, "model.gguf")
            ModelDownloadManager.publishAtomically(partial, installed)
            assertFalse(partial.exists())
            assertTrue(installed.isFile)
            assertEquals("verified", installed.readText())
        } finally {
            directory.deleteRecursively()
        }
    }

    @Test
    fun fullDownloadVerifiesAndPublishes() {
        val bytes = "verified model".toByteArray()
        val directory = Files.createTempDirectory("model-full").toFile()
        try {
            val manager = ModelDownloadManager(directory, client { response(it, 200, bytes) }, spec(bytes), "https://example.invalid/model", { Long.MAX_VALUE })
            manager.downloadAfterConsent()
            assertEquals(ModelDownloadState.Installed, manager.state.value)
            assertEquals(bytes.toList(), manager.installedFile.readBytes().toList())
            assertFalse(manager.partialFile.exists())
        } finally { directory.deleteRecursively() }
    }

    @Test
    fun partialDownloadUsesRangeAndResumes() {
        val bytes = "resumable model".toByteArray()
        val prefix = bytes.copyOfRange(0, 5)
        val directory = Files.createTempDirectory("model-resume").toFile()
        try {
            val model = spec(bytes)
            File(directory, "${model.filename}.part").writeBytes(prefix)
            val manager = ModelDownloadManager(directory, client { request ->
                assertEquals("bytes=5-", request.header("Range"))
                response(request, 206, bytes.copyOfRange(5, bytes.size), "bytes 5-${bytes.lastIndex}/${bytes.size}")
            }, model, "https://example.invalid/model", { Long.MAX_VALUE })
            manager.downloadAfterConsent()
            assertEquals(ModelDownloadState.Installed, manager.state.value)
            assertEquals(bytes.toList(), manager.installedFile.readBytes().toList())
        } finally { directory.deleteRecursively() }
    }

    @Test
    fun checksumMismatchIsRejectedAndRemoved() {
        val bytes = "corrupt".toByteArray()
        val directory = Files.createTempDirectory("model-corrupt").toFile()
        try {
            val manager = ModelDownloadManager(directory, client { response(it, 200, bytes) }, spec(bytes, "0".repeat(64)), "https://example.invalid/model", { Long.MAX_VALUE })
            manager.downloadAfterConsent()
            assertTrue(manager.state.value is ModelDownloadState.Failed)
            assertFalse(manager.installedFile.exists())
            assertFalse(manager.partialFile.exists())
        } finally { directory.deleteRecursively() }
    }

    @Test
    fun insufficientStorageFailsBeforeNetworkAccess() {
        val bytes = "model".toByteArray()
        val calls = AtomicInteger()
        val directory = Files.createTempDirectory("model-storage").toFile()
        try {
            val manager = ModelDownloadManager(directory, client { calls.incrementAndGet(); response(it, 200, bytes) }, spec(bytes), "https://example.invalid/model", { 0 })
            manager.downloadAfterConsent()
            assertEquals(0, calls.get())
            assertEquals("MODEL_INSUFFICIENT_STORAGE", (manager.state.value as ModelDownloadState.Failed).code)
        } finally { directory.deleteRecursively() }
    }
}
