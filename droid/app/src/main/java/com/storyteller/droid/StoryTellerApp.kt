package com.storyteller.droid

import android.app.Application
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit

/**
 * StoryTeller application — handles first-launch model download,
 * SoundFont download, and global initialization.
 */
class StoryTellerApp : Application() {
    companion object {
        private const val TAG = "StoryTellerApp"
        private const val GM_MODEL_FILENAME = "Llama-3.2-3B-Instruct-Q4_K_M.gguf"
        private const val GM_MODEL_URL =
            "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf"
        private const val SOUNDFONT_FILENAME = "general_user_gs.sf2"
        // SoundFont URL TBD — will be configured in Phase 7
    }

    private val appScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val okHttp = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    /** Directory where models are stored (app-private). */
    val modelsDir: File
        get() = File(filesDir, "models").also { it.mkdirs() }

    /** Path to the Game Master GGUF model. */
    val gmModelFile: File
        get() = File(modelsDir, GM_MODEL_FILENAME)

    /** Whether the Game Master model is downloaded. */
    val isGmModelReady: Boolean
        get() = gmModelFile.exists() && gmModelFile.length() > 100_000_000 // >100 MB

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "StoryTellerApp onCreate")

        // Check if first launch — if so, prompt for model download
        if (!isGmModelReady && isWifiConnected()) {
            Log.i(TAG, "First launch on Wi-Fi — starting model download")
            downloadGmModel()
        }
    }

    /**
     * Download the Game Master model (~2 GB) over Wi-Fi.
     */
    fun downloadGmModel() {
        if (isGmModelReady) return

        appScope.launch {
            try {
                Log.i(TAG, "Downloading GM model: $GM_MODEL_URL")
                val request = Request.Builder().url(GM_MODEL_URL).build()
                val response = okHttp.newCall(request).execute()

                if (!response.isSuccessful) {
                    Log.e(TAG, "Model download failed: HTTP ${response.code}")
                    return@launch
                }

                val body = response.body ?: return@launch
                val totalBytes = body.contentLength()
                Log.i(TAG, "Model size: ${totalBytes / 1_000_000} MB")

                gmModelFile.outputStream().use { output ->
                    body.byteStream().use { input ->
                        val buffer = ByteArray(8192)
                        var bytesRead: Int
                        var downloaded = 0L
                        while (input.read(buffer).also { bytesRead = it } != -1) {
                            output.write(buffer, 0, bytesRead)
                            downloaded += bytesRead
                            if (downloaded % (50_000_000) < 8192) {
                                val pct = (downloaded * 100 / totalBytes)
                                Log.d(TAG, "Download progress: ${pct}%")
                            }
                        }
                    }
                }

                Log.i(TAG, "GM model downloaded: ${gmModelFile.length() / 1_000_000} MB")
            } catch (e: Exception) {
                Log.e(TAG, "Model download failed", e)
                gmModelFile.delete() // Remove partial download
            }
        }
    }

    /**
     * Check if the device is connected to Wi-Fi.
     */
    fun isWifiConnected(): Boolean {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork ?: return false
        val capabilities = cm.getNetworkCapabilities(network) ?: return false
        return capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)
    }
}
