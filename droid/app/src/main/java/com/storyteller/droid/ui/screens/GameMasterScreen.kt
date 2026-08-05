package com.storyteller.droid.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.storyteller.droid.data.GmIndex
import com.storyteller.droid.data.StoryRepository
import com.storyteller.droid.engine.LlamaEngine
import com.storyteller.droid.model.SaveState
import kotlinx.coroutines.launch

data class ChatMessage(
    val text: String,
    val isUser: Boolean,
)

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

    var messages by remember { mutableStateOf(
        saveState.gmHistory.map { turn -> ChatMessage(turn.text, turn.role == "user") }
    ) }
    var question by remember { mutableStateOf("") }
    var isGenerating by remember { mutableStateOf(false) }

    // Auto-scroll to bottom
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) {
            listState.animateScrollToItem(messages.size - 1)
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Game Master") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "Back to story")
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
            // ── Chat history ─────────────────────────────────────────
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
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.primaryContainer,
                        ),
                    ) {
                        Text(
                            text = "I am the Game Master of this world. Ask me about the scene " +
                                   "you're in, the characters you've met, or the lore of this land. " +
                                   "I will answer in character — but I will not reveal what lies ahead.",
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.padding(12.dp),
                        )
                    }
                }

                items(messages) { message ->
                    ChatBubble(
                        text = message.text,
                        isUser = message.isUser,
                    )
                }

                // Loading indicator
                if (isGenerating) {
                    item {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(8.dp),
                        ) {
                            LinearProgressIndicator(
                                modifier = Modifier.fillMaxWidth(),
                            )
                        }
                    }
                }
            }

            // ── Input bar ────────────────────────────────────────────
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
                        modifier = Modifier.weight(1f),
                        placeholder = { Text("Ask the Game Master...") },
                        maxLines = 3,
                        enabled = !isGenerating,
                    )

                    Spacer(modifier = Modifier.width(8.dp))

                    IconButton(
                        onClick = {
                            val q = question.trim()
                            if (q.isEmpty() || isGenerating) return@IconButton

                            val userMsg = ChatMessage(q, true)
                            messages = messages + userMsg
                            question = ""
                            isGenerating = true

                            scope.launch {
                                try {
                                    // Build GM prompt with context
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

                                    val answer = llamaEngine.generate(
                                        prompt = prompt,
                                        maxTokens = 256,
                                        temperature = 0.8f,
                                    )

                                    val gmMsg = ChatMessage(answer.trim(), false)
                                    messages = messages + gmMsg
                                    saveState.addGmExchange(q, answer.trim())
                                    saveState.save(repository.story.saveDir)
                                } catch (e: Exception) {
                                    messages = messages + ChatMessage(
                                        "The Game Master's voice falters... (Error: ${e.message})",
                                        false,
                                    )
                                } finally {
                                    isGenerating = false
                                }
                            }
                        },
                        enabled = !isGenerating && question.isNotBlank(),
                    ) {
                        Icon(Icons.Default.Send, contentDescription = "Send")
                    }
                }
            }
        }
    }
}

@Composable
private fun ChatBubble(text: String, isUser: Boolean) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start,
    ) {
        Surface(
            modifier = Modifier.widthIn(max = 300.dp),
            shape = MaterialTheme.shapes.medium,
            color = if (isUser)
                MaterialTheme.colorScheme.primary
            else
                MaterialTheme.colorScheme.surfaceVariant,
        ) {
            Column(modifier = Modifier.padding(12.dp)) {
                Text(
                    text = if (isUser) "You" else "Game Master",
                    style = MaterialTheme.typography.labelSmall,
                    color = (if (isUser) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant)
                        .copy(alpha = 0.6f),
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = text,
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (isUser) MaterialTheme.colorScheme.onPrimary
                    else MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
