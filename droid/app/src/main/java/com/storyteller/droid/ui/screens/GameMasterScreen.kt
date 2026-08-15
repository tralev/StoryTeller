package com.storyteller.droid.ui.screens

import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.storyteller.droid.data.GmIndex
import com.storyteller.droid.data.StoryRepository
import com.storyteller.droid.engine.ChunkStreamEvent
import com.storyteller.droid.engine.LlamaEngine
import com.storyteller.droid.engine.StreamBuilder
import com.storyteller.droid.engine.StreamErrorCodes
import com.storyteller.droid.model.SaveState
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

// ── P8.8 Stream State ─────────────────────────────────────────────

/** P8.8: Observable GM stream state replacing boolean isGenerating. */
sealed class GMStreamState {
    /** No active request; input is enabled. */
    data object Idle : GMStreamState()

    /** Model is loading or prompt is being prepared. */
    data object Loading : GMStreamState()

    /** Streaming chunks arriving. P8.8: live-region announces coalesced text. */
    data class Streaming(
        val partialText: String,
        val chunkCount: Int,
    ) : GMStreamState()

    /** Generation completed successfully. */
    data class Completed(val fullAnswer: String) : GMStreamState()

    /** Generation was cancelled by the user. */
    data class Cancelled(val partialText: String) : GMStreamState()

    /** Generation failed with a stable diagnostic code. */
    data class Failed(val errorCode: String, val message: String) : GMStreamState()
}

// ── Messages ──────────────────────────────────────────────────────

data class ChatMessage(
    val text: String,
    val isUser: Boolean,
    val isError: Boolean = false,
)

// ── Screen ────────────────────────────────────────────────────────

@Composable
@OptIn(ExperimentalMaterial3Api::class)
fun GameMasterScreen(
    repository: StoryRepository,
    saveState: SaveState,
    currentNodeId: String,
    llamaEngine: LlamaEngine,
    onBack: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    val currentNode = repository.nodes[currentNodeId]
    val listState = rememberLazyListState()

    // ── P8.8: stream state replaces isGenerating ──────────────────
    var streamState by remember { mutableStateOf<GMStreamState>(GMStreamState.Idle) }
    var messages by remember {
        mutableStateOf(
            saveState.gmHistory.map { turn ->
                ChatMessage(turn.text, turn.role == "user")
            }
        )
    }
    var question by remember { mutableStateOf("") }
    var showClearConfirmation by remember { mutableStateOf(false) }

    // P8.8: coalesced live-region announcement text
    var liveRegionText by remember { mutableStateOf("") }
    var lastAnnouncedChunk by remember { mutableIntStateOf(0) }

    // Active generation job for cancellation
    var generationJob by remember { mutableStateOf<Job?>(null) }

    // Auto-scroll to bottom
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }

    // ── P8.8: Clear-history confirmation dialog ───────────────────
    if (showClearConfirmation) {
        AlertDialog(
            onDismissRequest = { showClearConfirmation = false },
            title = { Text("Clear conversation history?") },
            text = {
                Text("This will permanently delete all messages with the Game Master " +
                     "for this story. This action cannot be undone.")
            },
            confirmButton = {
                TextButton(
                    onClick = {
                        messages = emptyList()
                        saveState.gmHistory.clear()
                        saveState.save(repository.story.saveDir)
                        showClearConfirmation = false
                    },
                ) {
                    Text("Clear", color = MaterialTheme.colorScheme.error)
                }
            },
            dismissButton = {
                TextButton(onClick = { showClearConfirmation = false }) {
                    Text("Cancel")
                }
            },
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Game Master") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(
                            Icons.Default.ArrowBack,
                            contentDescription = "Back to story",
                        )
                    }
                },
                actions = {
                    // P8.8: Clear history button
                    IconButton(
                        onClick = { showClearConfirmation = true },
                        enabled = messages.isNotEmpty(),
                    ) {
                        Icon(
                            Icons.Default.Delete,
                            contentDescription = "Clear conversation history",
                            tint = if (messages.isNotEmpty())
                                MaterialTheme.colorScheme.onSurface
                            else
                                MaterialTheme.colorScheme.onSurface.copy(alpha = 0.3f),
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            // ── Chat history ──────────────────────────────────────
            LazyColumn(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth(),
                state = listState,
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                // Welcome message
                item {
                    Card(
                        modifier = Modifier
                            .fillMaxWidth()
                            .semantics { heading() },
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.primaryContainer,
                        ),
                    ) {
                        Text(
                            text = "I am the Game Master of this world. Ask me about the " +
                                   "scene you're in, the characters you've met, or the lore " +
                                   "of this land. I will answer in character — but I will " +
                                   "not reveal what lies ahead.",
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(12.dp),
                        )
                    }
                }

                items(messages) { message ->
                    ChatBubble(
                        text = message.text,
                        isUser = message.isUser,
                        isError = message.isError,
                    )
                }

                // ── P8.8: Live-region for streaming text ──────────
                // Announces coalesced chunks to screen readers
                if (streamState is GMStreamState.Streaming) {
                    val state = streamState as GMStreamState.Streaming
                    if (state.chunkCount > lastAnnouncedChunk) {
                        LaunchedEffect(state.chunkCount) {
                            // Coalesce: announce every ~5 chunks to avoid spam
                            if (state.chunkCount - lastAnnouncedChunk >= 5 ||
                                state.chunkCount % 10 == 0) {
                                liveRegionText = "Game Master is responding..."
                                delay(50)
                                liveRegionText = ""
                                lastAnnouncedChunk = state.chunkCount
                            }
                        }
                    }
                    item {
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .semantics {
                                    liveRegion = LiveRegionMode.Assertive
                                    contentDescription = liveRegionText.ifEmpty {
                                        "Game Master is responding"
                                    }
                                },
                        ) {
                            GMStreamingBubble(
                                partialText = state.partialText,
                                chunkCount = state.chunkCount,
                            )
                        }
                    }
                }
            }

            // ── P8.8: Stream state indicators ─────────────────────
            AnimatedVisibility(visible = streamState is GMStreamState.Loading) {
                LinearProgressIndicator(
                    modifier = Modifier
                        .fillMaxWidth()
                        .semantics { contentDescription = "Game Master is thinking" },
                )
            }

            // P8.8: Failed state with retry
            AnimatedVisibility(visible = streamState is GMStreamState.Failed) {
                val failed = (streamState as? GMStreamState.Failed)
                Surface(
                    modifier = Modifier.fillMaxWidth(),
                    color = MaterialTheme.colorScheme.errorContainer,
                ) {
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            text = failed?.message ?: "Generation failed",
                            modifier = Modifier.weight(1f),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onErrorContainer,
                        )
                        IconButton(
                            onClick = {
                                val q = question.ifEmpty { messages.lastOrNull { it.isUser }?.text ?: "" }
                                if (q.isNotEmpty()) {
                                    question = q
                                    messages = messages.dropLastWhile { !it.isUser }
                                    sendQuestion(
                                        q, messages, llamaEngine, repository, saveState,
                                        scope, generationJob,
                                        { messages = it; streamState = GMStreamState.Idle },
                                        { streamState = it },
                                        { generationJob = it },
                                    )
                                } else {
                                    streamState = GMStreamState.Idle
                                }
                            },
                            modifier = Modifier.semantics { contentDescription = "Retry generation" },
                        ) {
                            Icon(Icons.Default.Refresh, contentDescription = "Retry")
                        }
                    }
                }
            }

            // ── Input bar ────────────────────────────────────────
            Surface(
                modifier = Modifier.fillMaxWidth(),
                tonalElevation = 4.dp,
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    OutlinedTextField(
                        value = question,
                        onValueChange = { question = it },
                        modifier = Modifier
                            .weight(1f)
                            .semantics {
                                contentDescription = "Type your question for the Game Master"
                            },
                        placeholder = { Text("Ask the Game Master...") },
                        maxLines = 3,
                        enabled = streamState is GMStreamState.Idle,
                    )

                    Spacer(modifier = Modifier.width(8.dp))

                    // ── P8.8: Cancel button during streaming ──────
                    if (streamState is GMStreamState.Streaming || streamState is GMStreamState.Loading) {
                        FilledIconButton(
                            onClick = {
                                generationJob?.cancel()
                                llamaEngine.cancelGeneration()
                                streamState = GMStreamState.Cancelled("")
                            },
                            modifier = Modifier.semantics {
                                contentDescription = "Stop Game Master response"
                            },
                            colors = IconButtonDefaults.filledIconButtonColors(
                                containerColor = MaterialTheme.colorScheme.error,
                            ),
                        ) {
                            Icon(
                                Icons.Default.Stop,
                                contentDescription = "Stop generating",
                            )
                        }
                    } else {
                        IconButton(
                            onClick = {
                                val q = question.trim()
                                if (q.isEmpty()) return@IconButton

                                sendQuestion(
                                    q, messages, llamaEngine, repository, saveState,
                                    scope, generationJob,
                                    { messages = it; streamState = GMStreamState.Idle },
                                    { streamState = it },
                                    { generationJob = it },
                                )
                            },
                            enabled = question.isNotBlank() && streamState is GMStreamState.Idle,
                            modifier = Modifier.semantics {
                                contentDescription = "Send question to Game Master"
                            },
                        ) {
                            Icon(
                                Icons.Default.Send,
                                contentDescription = "Send",
                            )
                        }
                    }
                }
            }
        }
    }
}

// ── P8.8: Send with streaming ─────────────────────────────────────

private fun sendQuestion(
    q: String,
    currentMessages: List<ChatMessage>,
    llamaEngine: LlamaEngine,
    repository: StoryRepository,
    saveState: SaveState,
    scope: kotlinx.coroutines.CoroutineScope,
    existingJob: Job?,
    onMessagesChanged: (List<ChatMessage>) -> Unit,
    onStateChanged: (GMStreamState) -> Unit,
    onJobChanged: (Job) -> Unit,
) {
    val userMsg = ChatMessage(q, true)
    val updatedMessages = currentMessages + userMsg
    onMessagesChanged(updatedMessages)
    onStateChanged(GMStreamState.Loading)

    val job = scope.launch {
        try {
            // Build GM prompt with context
            val currentNode = repository.nodes[saveState.currentNodeId]
            val sceneText = currentNode?.text ?: ""
            val sceneContext = currentNode?.let {
                "The reader is at: \"${it.text}\""
            } ?: ""

            // Look up relevant lore (spoiler-gated)
            val loreContext = repository.gmIndex.promptContext(
                q,
                saveState.visitedNodes.toSet(),
            )

            // World rules from bible
            val worldRules = repository.styleBible["art_style"]?.toString() ?: ""

            val prompt = buildString {
                append("You are the Game Master of a fantasy book. ")
                append(sceneContext)
                append("\n\nThe rules of this world are: $worldRules")
                if (loreContext.isNotEmpty()) {
                    append("\n\nRelevant lore:\n$loreContext")
                }
                append("\n\nCRITICAL RULES:")
                append("\n1. Answer in character as a wise, mysterious Game Master.")
                append("\n2. NEVER break the rules of the World Bible.")
                append("\n3. NEVER disclose future plot points or tell the reader which choice is correct.")
                append("\n4. Keep your answer under 4 sentences.")
                append("\n\nReader's question: $q")
                append("\n\nGame Master's answer:")
            }

            // P8.8: Stream events from the model
            val builder = StreamBuilder("gm_${System.currentTimeMillis()}")
            onStateChanged(GMStreamState.Streaming("", 0))

            val answer = llamaEngine.generate(
                prompt = prompt,
                maxTokens = 256,
                temperature = 0.8f,
            )

            // Simulate chunk streaming from the full answer
            // (Native stream callbacks would emit per-token; we chunk the result)
            val words = answer.split(" ")
            var accumulated = ""
            var chunkCount = 0
            for (word in words) {
                accumulated += if (accumulated.isEmpty()) word else " $word"
                chunkCount++
                // Emit every 3 words as a chunk
                if (chunkCount % 3 == 0 || chunkCount == words.size) {
                    onStateChanged(GMStreamState.Streaming(accumulated, chunkCount))
                    kotlinx.coroutines.delay(30) // Gentle pacing for UI
                }
            }

            val finalAnswer = accumulated.trim()
            val gmMsg = ChatMessage(finalAnswer, false)
            onMessagesChanged(updatedMessages + gmMsg)
            saveState.addGmExchange(q, finalAnswer)
            saveState.save(repository.story.saveDir)
            onStateChanged(GMStreamState.Completed(finalAnswer))

        } catch (e: kotlinx.coroutines.CancellationException) {
            onStateChanged(GMStreamState.Cancelled(""))
        } catch (e: Exception) {
            val code = when {
                e.message?.contains("not loaded") == true -> StreamErrorCodes.MODEL_NOT_LOADED
                else -> StreamErrorCodes.NATIVE_FAILURE
            }
            val errorMsg = ChatMessage(
                "The Game Master's voice falters... (${e.message ?: code})",
                false,
                isError = true,
            )
            onMessagesChanged(updatedMessages + errorMsg)
            onStateChanged(GMStreamState.Failed(code, e.message ?: "Unknown error"))
        }
    }
    onJobChanged(job)
}

// ── P8.8: Streaming text bubble ───────────────────────────────────

@Composable
private fun GMStreamingBubble(partialText: String, chunkCount: Int) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.Start,
    ) {
        Surface(
            modifier = Modifier
                .widthIn(max = 300.dp)
                .semantics {
                    contentDescription = "Game Master responding: $partialText"
                    liveRegion = LiveRegionMode.Polite
                },
            shape = MaterialTheme.shapes.medium,
            color = MaterialTheme.colorScheme.surfaceVariant,
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = "Game Master",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.6f),
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = partialText.ifEmpty { "…" },
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(modifier = Modifier.height(4.dp))
                // P8.8: subtle typing indicator
                Text(
                    text = "●".repeat((chunkCount % 3) + 1),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.4f),
                )
            }
        }
    }
}

// ── Chat bubble ───────────────────────────────────────────────────

@Composable
private fun ChatBubble(text: String, isUser: Boolean, isError: Boolean = false) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Surface(
            modifier = Modifier
                .widthIn(max = 300.dp)
                .semantics {
                    contentDescription = if (isUser) "You: $text" else "Game Master: $text"
                },
            shape = MaterialTheme.shapes.medium,
            color = when {
                isError -> MaterialTheme.colorScheme.errorContainer
                isUser -> MaterialTheme.colorScheme.primary
                else -> MaterialTheme.colorScheme.surfaceVariant
            },
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = if (isError) "Error" else if (isUser) "You" else "Game Master",
                    style = MaterialTheme.typography.labelSmall,
                    color = when {
                        isError -> MaterialTheme.colorScheme.onErrorContainer
                        isUser -> MaterialTheme.colorScheme.onPrimary
                        else -> MaterialTheme.colorScheme.onSurfaceVariant
                    }.copy(alpha = 0.6f),
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = when {
                        isError -> MaterialTheme.colorScheme.onErrorContainer
                        isUser -> MaterialTheme.colorScheme.onPrimary
                        else -> MaterialTheme.colorScheme.onSurfaceVariant
                    },
                )
            }
        }
    }
}
