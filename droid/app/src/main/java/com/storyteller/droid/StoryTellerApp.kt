package com.storyteller.droid

import android.app.Application
import android.util.Log
import com.storyteller.droid.model.ModelDownloadManager
import com.storyteller.droid.model.ReleaseModelRegistry
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch
import okhttp3.OkHttpClient
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * StoryTeller application — handles first-launch model download,
 * SoundFont download, and global initialization.
 */
class StoryTellerApp : Application() {
    companion object {
        private const val TAG = "StoryTellerApp"
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

    val modelDownloadManager: ModelDownloadManager by lazy {
        ModelDownloadManager(modelsDir, okHttp)
    }

    /** Path to the Game Master GGUF model. */
    val gmModelFile: File
        get() = File(modelsDir, ReleaseModelRegistry.gameMaster.filename)

    /** Whether the Game Master model is downloaded. */
    val isGmModelReady: Boolean
        get() = modelDownloadManager.isInstalled

    override fun onCreate() {
        super.onCreate()
        Log.d(TAG, "StoryTellerApp onCreate")

        // Network access is never started here. The UI must obtain explicit consent.
    }

    /**
     * Download the Game Master model after the UI has recorded explicit consent.
     */
    fun downloadGmModelAfterConsent() {
        appScope.launch { modelDownloadManager.downloadAfterConsent() }
    }

    fun cancelGmModelDownload() = modelDownloadManager.cancel()

    fun deleteGmModel() = modelDownloadManager.deleteInstalledAndPartial()
}
