package com.storyteller.droid

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.lifecycle.lifecycleScope
import com.storyteller.droid.data.StoryRepository
import com.storyteller.droid.engine.LlamaEngine
import com.storyteller.droid.engine.MidiPlayer
import com.storyteller.droid.engine.StoryParser
import com.storyteller.droid.model.SaveState
import com.storyteller.droid.model.ModelDownloadState
import com.storyteller.droid.model.ReleaseModelRegistry
import com.storyteller.droid.ui.screens.GameMasterScreen
import com.storyteller.droid.ui.screens.LibraryScreen
import com.storyteller.droid.ui.screens.ReaderScreen
import com.storyteller.droid.ui.theme.StoryTellerTheme
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private lateinit var llamaEngine: LlamaEngine
    private lateinit var midiPlayer: MidiPlayer
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val storyParser = StoryParser(this)
        llamaEngine = LlamaEngine()
        midiPlayer = MidiPlayer(this)

        // Initialize MIDI player
        midiPlayer.init()

        // Check for shared .story file intent
        handleShareIntent(intent, storyParser)

        setContent {
            StoryTellerTheme {
                val app = application as StoryTellerApp
                val modelState by app.modelDownloadManager.state.collectAsState()
                LaunchedEffect(modelState) {
                    if (modelState is ModelDownloadState.Installed && !llamaEngine.isLoaded) {
                        llamaEngine.loadModel(app.gmModelFile.absolutePath)
                    }
                }
                var showModelConsent by rememberSaveable { mutableStateOf(!app.isGmModelReady) }
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background,
                ) {
                    val navController = rememberNavController()

                    NavHost(
                        navController = navController,
                        startDestination = "library",
                    ) {
                        composable("library") {
                            LibraryScreen(
                                storyParser = storyParser,
                                onStorySelected = { story ->
                                    navController.navigate("reader/${story.storyId}")
                                },
                            )
                        }

                        composable("reader/{storyId}") { backStackEntry ->
                            val storyId = backStackEntry.arguments?.getString("storyId") ?: return@composable
                            val story = storyParser.load(storyId) ?: return@composable
                            val repository = remember(storyId) { StoryRepository(story) }
                            val saveState = remember(storyId) {
                                SaveState.load(story.saveDir).takeIf { it.currentNode.isNotEmpty() }
                                    ?: SaveState(storyId = story.storyId,
                                        packageContentHash = story.contentHash,
                                        currentNode = story.entryNode,
                                        visitedNodes = mutableListOf(story.entryNode))
                            }

                            var showGm by remember { mutableStateOf(false) }

                            if (showGm) {
                                GameMasterScreen(
                                    repository = repository,
                                    saveState = saveState,
                                    currentNodeId = saveState.currentNodeId,
                                    llamaEngine = llamaEngine,
                                    onBack = { showGm = false },
                                )
                            } else {
                                ReaderScreen(
                                    repository = repository,
                                    saveState = saveState,
                                    midiPlayer = midiPlayer,
                                    onBack = { navController.popBackStack() },
                                    onAskGameMaster = { showGm = true },
                                )
                            }
                        }
                    }
                }

                if (showModelConsent || modelState is ModelDownloadState.Downloading || modelState is ModelDownloadState.Verifying) {
                    val spec = ReleaseModelRegistry.gameMaster
                    AlertDialog(
                        onDismissRequest = {
                            if (modelState !is ModelDownloadState.Downloading && modelState !is ModelDownloadState.Verifying) showModelConsent = false
                        },
                        title = { Text("Install local Game Master?") },
                        text = {
                            Column(verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(8.dp)) {
                                Text("${spec.displayName} by ${spec.publisher} • ${"%.2f".format(spec.byteSize / 1_000_000_000.0)} GB")
                                Text(spec.licenseNotice)
                                Text("Source and license: ${spec.licenseUrl}", style = MaterialTheme.typography.bodySmall)
                                when (val state = modelState) {
                                    is ModelDownloadState.Downloading -> {
                                        LinearProgressIndicator(progress = { state.downloadedBytes.toFloat() / state.totalBytes.toFloat() })
                                        Text("${state.downloadedBytes / 1_000_000} / ${state.totalBytes / 1_000_000} MB")
                                    }
                                    ModelDownloadState.Verifying -> Text("Verifying download…")
                                    is ModelDownloadState.Failed -> Text(state.detail, color = MaterialTheme.colorScheme.error)
                                    ModelDownloadState.Cancelled -> Text("Download paused. Continue to resume it.")
                                    else -> Text("The model is downloaded once, verified, and used completely offline.")
                                }
                            }
                        },
                        confirmButton = {
                            if (modelState !is ModelDownloadState.Downloading && modelState !is ModelDownloadState.Verifying) {
                                TextButton(onClick = { app.downloadGmModelAfterConsent() }) {
                                    Text(if (modelState is ModelDownloadState.Cancelled) "Continue" else "Accept and download")
                                }
                            }
                        },
                        dismissButton = {
                            TextButton(onClick = {
                                if (modelState is ModelDownloadState.Downloading || modelState is ModelDownloadState.Verifying) app.cancelGmModelDownload()
                                else showModelConsent = false
                            }) { Text(if (modelState is ModelDownloadState.Downloading || modelState is ModelDownloadState.Verifying) "Cancel" else "Not now") }
                        },
                    )
                }
            }
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        handleShareIntent(intent, StoryParser(this))
    }

    override fun onDestroy() {
        midiPlayer.release()
        llamaEngine.close()
        super.onDestroy()
    }

    override fun onStart() {
        super.onStart()
        val app = application as StoryTellerApp
        if (app.isGmModelReady && !llamaEngine.isLoaded) {
            lifecycleScope.launch { llamaEngine.loadModel(app.gmModelFile.absolutePath) }
        }
    }

    override fun onStop() {
        llamaEngine.onAppBackgrounded()
        super.onStop()
    }

    override fun onTrimMemory(level: Int) {
        if (level >= TRIM_MEMORY_RUNNING_LOW) llamaEngine.onMemoryPressure()
        super.onTrimMemory(level)
    }

    /**
     * Handle .story file shared from another app.
     */
    private fun handleShareIntent(intent: android.content.Intent, parser: StoryParser) {
        val uri = intent.data ?: return
        try {
            val cacheFile = java.io.File(cacheDir, "shared_${System.currentTimeMillis()}.story")
            contentResolver.openInputStream(uri)?.use { input ->
                cacheFile.outputStream().use { output ->
                    input.copyTo(output)
                }
            }
            parser.import(cacheFile.absolutePath)
            cacheFile.delete()
        } catch (e: Exception) {
            android.util.Log.e("MainActivity", "Share import failed", e)
        }
    }
}
