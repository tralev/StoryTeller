import SwiftUI

// MARK: - P8.8 GM Stream State

/// P8.8: Observable GM stream state replacing boolean isGenerating.
enum GMStreamState: Equatable {
    case idle
    case loading
    case streaming(partialText: String, chunkCount: Int)
    case completed(answer: String)
    case cancelled(partialText: String)
    case failed(code: String, message: String)
}

// MARK: - Messages

struct ChatMessage: Identifiable, Equatable {
    let id = UUID()
    let text: String
    let isUser: Bool
    let isError: Bool

    init(text: String, isUser: Bool, isError: Bool = false) {
        self.text = text
        self.isUser = isUser
        self.isError = isError
    }
}

// MARK: - Game Master View

struct GameMasterView: View {
    let story: StoryPackage
    let llamaEngine: LlamaEngine
    let modelURL: URL
    let onBack: () -> Void

    // P8.8: ViewModel owns the stream state lifecycle
    @StateObject private var viewModel: GMViewModel

    init(story: StoryPackage, llamaEngine: LlamaEngine, modelURL: URL, onBack: @escaping () -> Void) {
        self.story = story
        self.llamaEngine = llamaEngine
        self.modelURL = modelURL
        self.onBack = onBack
        _viewModel = StateObject(wrappedValue: GMViewModel(
            story: story,
            llamaEngine: llamaEngine,
            modelURL: modelURL
        ))
    }

    var body: some View {
        ZStack {
            AppTheme.midnight.ignoresSafeArea()

            VStack(spacing: 0) {
                // Chat history
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 8) {
                            // Welcome
                            ChatBubbleView(
                                text: "I am the Game Master of this world. Ask me about the scene you're in, the characters you've met, or the lore of this land. I will answer in character — but I will not reveal what lies ahead.",
                                isUser: false,
                                isError: false
                            )
                            .accessibilityAddTraits(.isHeader)
                            .accessibilityLabel("Game Master welcome message")

                            ForEach(viewModel.messages) { message in
                                ChatBubbleView(
                                    text: message.text,
                                    isUser: message.isUser,
                                    isError: message.isError
                                )
                                .id(message.id)
                                .accessibilityLabel(message.isUser
                                    ? "You: \(message.text)"
                                    : "Game Master: \(message.text)")
                            }

                            // P8.8: Streaming indicator with live-region
                            if case .streaming(let partial, let count) = viewModel.streamState {
                                GMStreamingBubble(partialText: partial, chunkCount: count)
                                    .accessibilityLabel("Game Master is responding")
                                    .accessibilityAddTraits(.updatesFrequently)
                            }
                        }
                        .padding(12)
                    }
                    .onChange(of: viewModel.messages.count) { _ in
                        if let last = viewModel.messages.last {
                            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
                        }
                    }
                }

                // P8.8: Loading indicator
                if viewModel.streamState == .loading {
                    ProgressView("Game Master is thinking…")
                        .tint(AppTheme.gold)
                        .padding(.vertical, 4)
                        .accessibilityLabel("Game Master is thinking")
                }

                // P8.8: Failed state with retry
                if case .failed(let code, let message) = viewModel.streamState {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.red)
                        Text(message)
                            .font(.caption)
                            .foregroundColor(.red)
                            .lineLimit(2)
                        Spacer()
                        Button("Retry") {
                            viewModel.retryLastQuestion()
                        }
                        .font(.caption.bold())
                        .foregroundColor(AppTheme.gold)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.red.opacity(0.1))
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel("Generation failed. \(message). Retry available.")
                }

                // Input bar
                HStack(spacing: 8) {
                    TextField(
                        "Ask the Game Master...",
                        text: $viewModel.question,
                        axis: .vertical
                    )
                    .textFieldStyle(.plain)
                    .padding(12)
                    .background(AppTheme.charcoal)
                    .cornerRadius(12)
                    .foregroundColor(AppTheme.parchment)
                    .lineLimit(3)
                    .disabled(viewModel.isInputDisabled)
                    .accessibilityLabel("Type your question for the Game Master")

                    // P8.8: Cancel button during streaming
                    if viewModel.isStreaming {
                        Button(action: viewModel.cancelGeneration) {
                            Image(systemName: "stop.circle.fill")
                                .font(.system(size: 28))
                                .foregroundColor(.red)
                        }
                        .accessibilityLabel("Stop Game Master response")
                    } else {
                        Button(action: viewModel.sendQuestion) {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.system(size: 28))
                                .foregroundColor(
                                    viewModel.question.trimmingCharacters(in: .whitespaces).isEmpty
                                        ? AppTheme.gold.opacity(0.3)
                                        : AppTheme.gold
                                )
                        }
                        .disabled(viewModel.question.trimmingCharacters(in: .whitespaces).isEmpty
                                  || !viewModel.isInputEnabled)
                        .accessibilityLabel("Send question to Game Master")
                    }
                }
                .padding(12)
                .background(AppTheme.charcoal.opacity(0.5))
            }
        }
        .navigationTitle("Game Master")
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button(action: onBack) {
                    Image(systemName: "chevron.left")
                        .foregroundColor(AppTheme.gold)
                }
                .accessibilityLabel("Back to story")
            }

            // P8.8: Clear history button with confirmation
            ToolbarItem(placement: .navigationBarTrailing) {
                Button(action: { viewModel.showClearConfirmation = true }) {
                    Image(systemName: "trash")
                        .foregroundColor(viewModel.messages.isEmpty
                            ? AppTheme.parchment.opacity(0.3)
                            : AppTheme.parchment)
                }
                .disabled(viewModel.messages.isEmpty)
                .accessibilityLabel("Clear conversation history")
            }
        }
        .alert("Clear conversation history?", isPresented: $viewModel.showClearConfirmation) {
            Button("Cancel", role: .cancel) {}
            Button("Clear", role: .destructive) { viewModel.clearHistory() }
        } message: {
            Text("This will permanently delete all messages with the Game Master for this story. This action cannot be undone.")
        }
        .task { await viewModel.ensureModelLoaded() }
    }
}

// MARK: - P8.8 Streaming Bubble

struct GMStreamingBubble: View {
    let partialText: String
    let chunkCount: Int

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                Text("Game Master")
                    .font(.caption)
                    .foregroundColor(AppTheme.parchment.opacity(0.6))
                Text(partialText.isEmpty ? "…" : partialText)
                    .font(.storytellerBody)
                    .foregroundColor(AppTheme.parchment)
                // Subtle typing indicator
                Text(String(repeating: "●", count: (chunkCount % 3) + 1))
                    .font(.caption2)
                    .foregroundColor(AppTheme.parchment.opacity(0.4))
            }
            .padding(12)
            .background(AppTheme.charcoal)
            .cornerRadius(12)
            .frame(maxWidth: 280, alignment: .leading)
            Spacer()
        }
    }
}

// MARK: - Chat Bubble View

struct ChatBubbleView: View {
    let text: String
    let isUser: Bool
    let isError: Bool

    var body: some View {
        HStack {
            if isUser { Spacer() }

            VStack(alignment: .leading, spacing: 4) {
                Text(isError ? "Error" : isUser ? "You" : "Game Master")
                    .font(.caption)
                    .foregroundColor(isError
                        ? Color.red.opacity(0.6)
                        : isUser
                            ? AppTheme.gold.opacity(0.6)
                            : AppTheme.parchment.opacity(0.6))
                Text(text)
                    .font(.storytellerBody)
                    .foregroundColor(isError
                        ? .red
                        : isUser
                            ? AppTheme.midnight
                            : AppTheme.parchment)
            }
            .padding(12)
            .background(isError
                ? Color.red.opacity(0.15)
                : isUser
                    ? AppTheme.gold
                    : AppTheme.charcoal)
            .cornerRadius(12)
            .frame(maxWidth: 280, alignment: isUser ? .trailing : .leading)

            if !isUser { Spacer() }
        }
    }
}

// MARK: - P8.8 ViewModel

@MainActor
final class GMViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var question: String = ""
    @Published var streamState: GMStreamState = .idle
    @Published var showClearConfirmation = false

    let story: StoryPackage
    private let repository: StoryRepository
    private var saveState: SaveState
    private let llamaEngine: LlamaEngine
    private let modelURL: URL
    private var generationTask: Task<Void, Never>?

    /// P8.8: Last user question for retry
    private var lastUserQuestion: String = ""
    private var historyURL: URL { story.saveDir.appendingPathComponent("gm_history.json") }

    var isStreaming: Bool {
        if case .streaming = streamState { return true }
        if case .loading = streamState { return true }
        return false
    }

    var isInputEnabled: Bool { streamState == .idle }
    var isInputDisabled: Bool { !isInputEnabled }

    init(story: StoryPackage, llamaEngine: LlamaEngine, modelURL: URL) {
        self.story = story
        self.repository = StoryRepository(story: story)
        self.llamaEngine = llamaEngine
        self.modelURL = modelURL
        let loaded = SaveState.load(from: story.saveDir)
        self.saveState = loaded.currentNode.isEmpty
            ? SaveState(storyId: story.storyId, packageContentHash: story.contentHash,
                        currentNode: story.entryNode, visitedNodes: [story.entryNode])
            : loaded

        if let history = try? ConversationHistoryStore.loadBound(
            from: story.saveDir.appendingPathComponent("gm_history.json"),
            storyId: story.storyId,
            contentHash: story.contentHash
        ) {
            self.messages = history.exchanges.flatMap { exchange in
                [ChatMessage(text: exchange.userText, isUser: true),
                 ChatMessage(text: exchange.assistantText, isUser: false)]
            }
        } else {
            self.messages = saveState.gmHistory.map { turn in
                ChatMessage(text: turn.text, isUser: turn.role == "user")
            }
        }
    }

    func ensureModelLoaded() async {
        guard !llamaEngine.isLoaded else { return }
        do { try await llamaEngine.loadModel(path: modelURL.path) }
        catch {
            messages.append(ChatMessage(
                text: "Local Game Master unavailable: \(error.localizedDescription)",
                isUser: false
            ))
        }
    }

    // MARK: - P8.8: Send with streaming

    func sendQuestion() {
        let q = question.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty, streamState == .idle else { return }

        lastUserQuestion = q
        let userMsg = ChatMessage(text: q, isUser: true)
        messages.append(userMsg)
        question = ""
        streamState = .loading

        generationTask = Task { [weak self] in
            guard let self else { return }
            do {
                try await self.generateStreamingAnswer(for: q)
            } catch is CancellationError {
                self.streamState = .cancelled(partialText: "")
            } catch {
                let code = error.localizedDescription.contains("not loaded")
                    ? "STREAM_MODEL_NOT_LOADED"
                    : "STREAM_NATIVE_FAILURE"
                let errorMsg = ChatMessage(
                    text: "The Game Master's voice falters... (\(error.localizedDescription))",
                    isUser: false,
                    isError: true
                )
                self.messages.append(errorMsg)
                self.streamState = .failed(code: code, message: error.localizedDescription)
            }
        }
    }

    /// P8.8: Retry the last failed question
    func retryLastQuestion() {
        guard !lastUserQuestion.isEmpty, streamState != .loading,
              case .streaming = streamState, false else {
            streamState = .idle
            return
        }
        // Remove failed error message
        if messages.last?.isError == true {
            messages.removeLast()
        }
        // Also remove the last user message (will re-add)
        if messages.last?.isUser == true {
            messages.removeLast()
        }
        question = lastUserQuestion
        streamState = .idle
        sendQuestion()
    }

    /// P8.8: Cancel the active generation
    func cancelGeneration() {
        generationTask?.cancel()
        llamaEngine.cancelGeneration()
        streamState = .cancelled(partialText: "")
    }

    /// P8.8: Clear history with confirmation (called after alert dismisses)
    func clearHistory() {
        messages.removeAll()
        saveState.gmHistory.removeAll()
        saveState.save(to: story.saveDir)
        try? ConversationHistoryStore.delete(historyURL)
    }

    // MARK: - Streaming generation

    private func generateStreamingAnswer(for q: String) async throws {
        let node = repository.nodes[saveState.currentNodeId]
        let sceneText = node?.text ?? ""

        let visitedRefs = Set(saveState.visitedNodes.flatMap { repository.nodes[$0]?.authoritativeRefs ?? [] })
        let loreContext = repository.gmPromptContext(
            query: q,
            visitedNodes: Set(saveState.visitedNodes),
            currentNodeId: saveState.currentNodeId,
            visitedRefs: visitedRefs
        )

        let prompt = """
        You are the Game Master of a fantasy book. The reader is at: "\(sceneText)"

        Relevant lore:
        \(loreContext)

        CRITICAL RULES:
        1. Answer in character as a wise, mysterious Game Master.
        2. NEVER disclose future plot points or tell the reader which choice is correct.
        3. Keep your answer under 4 sentences.

        Reader's question: \(q)

        Game Master's answer:
        """

        var accumulated = ""
        var chunkCount = 0
        for await event in llamaEngine.stream(
            requestId: "gm_\(UUID().uuidString)", prompt: prompt,
            maxTokens: 256, temperature: 0.8
        ) {
            try Task.checkCancellation()
            switch event.eventType {
            case .started:
                streamState = .streaming(partialText: "", chunkCount: 0)
            case .text:
                accumulated += event.text
                chunkCount += 1
                self.streamState = .streaming(partialText: accumulated, chunkCount: chunkCount)
            case .completed:
                break
            case .cancelled:
                throw CancellationError()
            case .failed:
                throw LlamaError.generationFailed
            }
        }

        let finalAnswer = accumulated.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !finalAnswer.isEmpty else { throw LlamaError.generationFailed }
        let nextSequence = (try ConversationHistoryStore.loadBound(
            from: historyURL, storyId: story.storyId, contentHash: story.contentHash
        ))?.exchangeCount ?? 0
        _ = try ConversationHistoryStore.addExchange(
            Exchange(
                exchangeId: UUID().uuidString,
                userText: q,
                assistantText: finalAnswer,
                sequence: nextSequence,
                createdAt: Date().timeIntervalSince1970
            ),
            to: historyURL,
            storyId: story.storyId,
            contentHash: story.contentHash,
            conversationId: "default"
        )
        let gmMsg = ChatMessage(text: finalAnswer, isUser: false)
        messages.append(gmMsg)

        var state = self.saveState
        state.addGMExchange(question: q, answer: finalAnswer)
        state.save(to: story.saveDir)

        streamState = .completed(answer: finalAnswer)
    }
}
