package com.storyteller.droid.model

import android.os.StatFs
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.Call
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.security.MessageDigest

sealed interface ModelDownloadState {
    data object NotInstalled : ModelDownloadState
    data class Downloading(val downloadedBytes: Long, val totalBytes: Long) : ModelDownloadState
    data object Verifying : ModelDownloadState
    data object Installed : ModelDownloadState
    data object Cancelled : ModelDownloadState
    data class Failed(val code: String, val detail: String) : ModelDownloadState
}

/** Resumable, verified and atomically publishing model downloader. */
class ModelDownloadManager(
    private val modelsDir: File,
    private val client: OkHttpClient,
    private val spec: ReleaseModelSpec = ReleaseModelRegistry.gameMaster,
    private val downloadUrl: String = spec.downloadUrl,
    private val availableBytesProvider: (File) -> Long = ::availableBytes,
) {
    private val mutableState = MutableStateFlow<ModelDownloadState>(initialState())
    val state: StateFlow<ModelDownloadState> = mutableState.asStateFlow()
    @Volatile private var activeCall: Call? = null
    @Volatile private var cancelled = false

    val installedFile: File get() = File(modelsDir, spec.filename)
    val partialFile: File get() = File(modelsDir, "${spec.filename}.part")
    val isInstalled: Boolean get() = installedFile.isFile && installedFile.length() == spec.byteSize

    /** Must only be called after the user explicitly accepts the displayed model terms. */
    @Synchronized
    fun downloadAfterConsent() {
        if (state.value is ModelDownloadState.Downloading || state.value is ModelDownloadState.Verifying) return
        if (isInstalled) {
            mutableState.value = ModelDownloadState.Installed
            return
        }
        cancelled = false
        modelsDir.mkdirs()
        val existing = partialFile.takeIf { it.isFile }?.length() ?: 0L
        val remaining = spec.byteSize - existing
        if (remaining <= 0L || availableBytesProvider(modelsDir) < remaining) {
            mutableState.value = ModelDownloadState.Failed("MODEL_INSUFFICIENT_STORAGE", "At least $remaining additional bytes are required")
            return
        }

        val requestBuilder = Request.Builder().url(downloadUrl)
        if (existing > 0L) requestBuilder.header("Range", "bytes=$existing-")
        val call = client.newCall(requestBuilder.build())
        activeCall = call
        try {
            call.execute().use { response ->
                val validStatus = response.code == 200 && existing == 0L || response.code == 206 && existing > 0L
                if (!validStatus) throw DownloadFailure("MODEL_RESUME_REJECTED", "Unexpected HTTP ${response.code} for offset $existing")
                if (existing > 0L && response.header("Content-Range")?.startsWith("bytes $existing-") != true) {
                    throw DownloadFailure("MODEL_RESUME_REJECTED", "Invalid Content-Range for offset $existing")
                }
                val body = response.body ?: throw DownloadFailure("MODEL_EMPTY_RESPONSE", "Response has no body")
                var downloaded = existing
                FileOutputStream(partialFile, existing > 0L).buffered().use { output ->
                    body.byteStream().use { input ->
                        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                        while (true) {
                            if (cancelled) throw DownloadCancelled()
                            val count = input.read(buffer)
                            if (count < 0) break
                            output.write(buffer, 0, count)
                            downloaded += count
                            mutableState.value = ModelDownloadState.Downloading(downloaded, spec.byteSize)
                        }
                    }
                }
            }
            if (partialFile.length() != spec.byteSize) throw DownloadFailure("MODEL_SIZE_MISMATCH", "Expected ${spec.byteSize}, got ${partialFile.length()}")
            mutableState.value = ModelDownloadState.Verifying
            if (sha256(partialFile) != spec.sha256) {
                partialFile.delete()
                throw DownloadFailure("MODEL_CHECKSUM_MISMATCH", "Downloaded model failed SHA-256 verification")
            }
            publishAtomically(partialFile, installedFile)
            mutableState.value = ModelDownloadState.Installed
        } catch (_: DownloadCancelled) {
            mutableState.value = ModelDownloadState.Cancelled
        } catch (error: DownloadFailure) {
            mutableState.value = ModelDownloadState.Failed(error.code, error.message ?: error.code)
        } catch (error: IOException) {
            mutableState.value = if (cancelled) ModelDownloadState.Cancelled else ModelDownloadState.Failed("MODEL_NETWORK_ERROR", error.message ?: "Network error")
        } finally {
            activeCall = null
        }
    }

    fun cancel() {
        cancelled = true
        activeCall?.cancel()
    }

    @Synchronized
    fun deleteInstalledAndPartial() {
        cancel()
        installedFile.delete()
        partialFile.delete()
        mutableState.value = ModelDownloadState.NotInstalled
    }

    private fun initialState(): ModelDownloadState = if (isInstalled) ModelDownloadState.Installed else ModelDownloadState.NotInstalled

    private class DownloadFailure(val code: String, message: String) : IOException(message)
    private class DownloadCancelled : IOException()

    companion object {
        fun availableBytes(directory: File): Long = StatFs(directory.absolutePath).availableBytes

        fun sha256(file: File): String {
            val digest = MessageDigest.getInstance("SHA-256")
            file.inputStream().buffered().use { input ->
                val buffer = ByteArray(1024 * 1024)
                while (true) {
                    val count = input.read(buffer)
                    if (count < 0) break
                    digest.update(buffer, 0, count)
                }
            }
            return digest.digest().joinToString("") { "%02x".format(it) }
        }

        fun publishAtomically(partial: File, destination: File) {
            try {
                Files.move(partial.toPath(), destination.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
            } catch (_: java.nio.file.AtomicMoveNotSupportedException) {
                Files.move(partial.toPath(), destination.toPath(), StandardCopyOption.REPLACE_EXISTING)
            }
        }
    }
}
