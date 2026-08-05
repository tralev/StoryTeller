package com.storyteller.droid.ui.screens

import android.graphics.BitmapFactory
import androidx.compose.animation.*
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Bookmark
import androidx.compose.material.icons.filled.BookmarkBorder
import androidx.compose.material.icons.filled.Chat
import androidx.compose.material.icons.filled.MusicNote
import androidx.compose.material.icons.filled.MusicOff
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.storyteller.droid.data.StoryRepository
import com.storyteller.droid.engine.MidiPlayer
import com.storyteller.droid.model.SaveState

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun ReaderScreen(
    repository: StoryRepository,
    saveState: SaveState,
    midiPlayer: MidiPlayer?,
    onBack: () -> Unit,
    onAskGameMaster: (nodeId: String) -> Unit,
) {
    var currentNodeId by remember { mutableStateOf(saveState.currentNodeId) }
    var isMidiPlaying by remember { mutableStateOf(false) }
    val context = LocalContext.current

    val currentNode = repository.nodes[currentNodeId]
    if (currentNode == null) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text("Error: Node '$currentNodeId' not found.")
        }
        return
    }

    // Auto-play MIDI on node change
    LaunchedEffect(currentNodeId) {
        saveState.visitNode(currentNodeId)
        saveState.save(repository.story.saveDir)

        val midiFile = repository.story.midiFor(currentNodeId)
        if (midiFile.exists() && midiPlayer != null) {
            midiPlayer.play(midiFile, loop = true)
            isMidiPlaying = true
        }
    }

    // Bookmark state
    val isBookmarked = currentNodeId in saveState.bookmarks

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(repository.story.title) },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    // Bookmark
                    IconButton(onClick = {
                        saveState.toggleBookmark()
                        saveState.save(repository.story.saveDir)
                    }) {
                        Icon(
                            if (isBookmarked) Icons.Default.Bookmark else Icons.Default.BookmarkBorder,
                            contentDescription = "Bookmark",
                        )
                    }
                    // MIDI toggle
                    IconButton(onClick = {
                        if (isMidiPlaying) {
                            midiPlayer?.stop()
                            isMidiPlaying = false
                        } else {
                            val midiFile = repository.story.midiFor(currentNodeId)
                            if (midiFile.exists()) {
                                midiPlayer?.play(midiFile, loop = true)
                                isMidiPlaying = true
                            }
                        }
                    }) {
                        Icon(
                            if (isMidiPlaying) Icons.Default.MusicNote else Icons.Default.MusicOff,
                            contentDescription = "Music",
                        )
                    }
                    // Game Master
                    IconButton(onClick = { onAskGameMaster(currentNodeId) }) {
                        Icon(Icons.Default.Chat, contentDescription = "Ask Game Master")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.background,
                ),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState()),
        ) {
            // ── Image ────────────────────────────────────────────────
            val imageFile = repository.story.imageFor(currentNodeId)
            if (imageFile.exists()) {
                val bitmap = remember(imageFile.absolutePath) {
                    try {
                        BitmapFactory.decodeFile(imageFile.absolutePath)
                    } catch (e: Exception) {
                        null
                    }
                }
                if (bitmap != null) {
                    Image(
                        bitmap = bitmap.asImageBitmap(),
                        contentDescription = "Scene illustration",
                        modifier = Modifier
                            .fillMaxWidth()
                            .heightIn(max = 384.dp),
                        contentScale = ContentScale.Crop,
                    )
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // ── Scene Text ───────────────────────────────────────────
            Column(
                modifier = Modifier.padding(horizontal = 24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                currentNode.displayLines.forEach { line ->
                    Text(
                        text = line,
                        style = MaterialTheme.typography.bodyLarge,
                        textAlign = TextAlign.Center,
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // ── Ending state ─────────────────────────────────────────
            if (currentNode.isEnding) {
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 24.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer,
                    ),
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            "The End",
                            style = MaterialTheme.typography.headlineMedium,
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                        )
                        Spacer(modifier = Modifier.height(12.dp))
                        OutlinedButton(
                            onClick = {
                                saveState.reset()
                                saveState.save(repository.story.saveDir)
                                currentNodeId = repository.story.entryNode
                            },
                        ) {
                            Text("Read Again")
                        }
                    }
                }
            }

            // ── Choices ──────────────────────────────────────────────
            if (!currentNode.isEnding && currentNode.choices.isNotEmpty()) {
                Column(
                    modifier = Modifier.padding(horizontal = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    currentNode.choices
                        .filter { it.isAvailable(saveState.flags) }
                        .forEach { choice ->
                            OutlinedCard(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clickable {
                                        saveState.makeChoice(choice)
                                        currentNodeId = choice.targetNode
                                    },
                                colors = CardDefaults.outlinedCardColors(
                                    containerColor = MaterialTheme.colorScheme.surface,
                                ),
                                border = CardDefaults.outlinedCardBorder().copy(
                                    width = 1.dp,
                                ),
                            ) {
                                Text(
                                    text = choice.choiceText,
                                    style = MaterialTheme.typography.labelLarge,
                                    modifier = Modifier.padding(16.dp),
                                    textAlign = TextAlign.Center,
                                )
                            }
                        }
                }

                Spacer(modifier = Modifier.height(32.dp))
            }

            // ── Mood indicator ───────────────────────────────────────
            if (currentNode.mood.isNotEmpty()) {
                Text(
                    text = "✦ ${currentNode.mood.replaceFirstChar { it.uppercase() }} ✦",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onBackground.copy(alpha = 0.4f),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(bottom = 16.dp),
                    textAlign = TextAlign.Center,
                )
            }
        }
    }
}
