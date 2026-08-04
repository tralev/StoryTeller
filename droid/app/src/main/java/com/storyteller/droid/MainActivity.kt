package com.storyteller.droid

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.storyteller.droid.data.StoryRepository
import com.storyteller.droid.engine.LlamaEngine
import com.storyteller.droid.engine.MidiPlayer
import com.storyteller.droid.engine.StoryParser
import com.storyteller.droid.model.SaveState
import com.storyteller.droid.ui.screens.GameMasterScreen
import com.storyteller.droid.ui.screens.LibraryScreen
import com.storyteller.droid.ui.screens.ReaderScreen
import com.storyteller.droid.ui.theme.StoryTellerTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()

        val storyParser = StoryParser(this)
        val llamaEngine = LlamaEngine()
        val midiPlayer = MidiPlayer(this)

        // Initialize MIDI player
        midiPlayer.init()

        // Check for shared .story file intent
        handleShareIntent(intent, storyParser)

        setContent {
            StoryTellerTheme {
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
                            val saveState = remember(storyId) { SaveState.load(story.saveDir) }

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
            }
        }
    }

    override fun onNewIntent(intent: android.content.Intent) {
        super.onNewIntent(intent)
        handleShareIntent(intent, StoryParser(this))
    }

    override fun onDestroy() {
        midiPlayer.release()
        llamaEngine.unloadModel()
        super.onDestroy()
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
