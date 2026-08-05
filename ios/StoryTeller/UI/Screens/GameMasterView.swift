import SwiftUI

struct GameMasterView: View {
    let story: StoryPackage
    let llamaEngine: LlamaEngine
    let modelURL: URL
    let onBack: () -> Void
    
    @StateObject private var viewModel: GMViewModel
    
    init(story: StoryPackage, llamaEngine: LlamaEngine, modelURL: URL, onBack: @escaping () -> Void) {
        self.story = story
        self.llamaEngine = llamaEngine
        self.modelURL = modelURL
        self.onBack = onBack
        _viewModel = StateObject(wrappedValue: GMViewModel(story: story, llamaEngine: llamaEngine, modelURL: modelURL))
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
                            ChatBubble(
                                text: "I am the Game Master of this world. Ask me about the scene you're in, the characters you've met, or the lore of this land. I will answer in character — but I will not reveal what lies ahead.",
                                isUser: false
                            )
                            
                            ForEach(viewModel.messages) { message in
                                ChatBubble(text: message.text, isUser: message.isUser)
                                    .id(message.id)
                            }
                            
                            if viewModel.isGenerating {
                                HStack {
                                    ProgressView()
                                        .tint(AppTheme.gold)
                                        .padding(.leading, 12)
                                    Spacer()
                                }
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
                
                // Input bar
                HStack(spacing: 8) {
                    TextField("Ask the Game Master...", text: $viewModel.question, axis: .vertical)
                        .textFieldStyle(.plain)
                        .padding(12)
                        .background(AppTheme.charcoal)
                        .cornerRadius(12)
                        .foregroundColor(AppTheme.parchment)
                        .lineLimit(3)
                        .disabled(viewModel.isGenerating)
                    
                    Button(action: viewModel.sendQuestion) {
                        Image(systemName: "arrow.up.circle.fill")
                            .font(.system(size: 28))
                            .foregroundColor(
                                viewModel.question.trimmingCharacters(in: .whitespaces).isEmpty
                                    ? AppTheme.gold.opacity(0.3)
                                    : AppTheme.gold
                            )
                    }
                    .disabled(viewModel.question.trimmingCharacters(in: .whitespaces).isEmpty || viewModel.isGenerating)
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
            }
        }
        .task { await viewModel.ensureModelLoaded() }
    }
}

// MARK: - Chat Bubble

struct ChatBubble: View {
    let text: String
    let isUser: Bool
    
    var body: some View {
        HStack {
            if isUser { Spacer() }
            
            VStack(alignment: .leading, spacing: 4) {
                Text(isUser ? "You" : "Game Master")
                    .font(.caption)
                    .foregroundColor(isUser
                        ? AppTheme.gold.opacity(0.6)
                        : AppTheme.parchment.opacity(0.6))
                Text(text)
                    .font(.storytellerBody)
                    .foregroundColor(isUser ? AppTheme.midnight : AppTheme.parchment)
            }
            .padding(12)
            .background(isUser ? AppTheme.gold : AppTheme.charcoal)
            .cornerRadius(12)
            .frame(maxWidth: 280, alignment: isUser ? .trailing : .leading)
            
            if !isUser { Spacer() }
        }
    }
}

// MARK: - Message Model

struct ChatMessage: Identifiable {
    let id = UUID()
    let text: String
    let isUser: Bool
}

// MARK: - ViewModel

@MainActor
final class GMViewModel: ObservableObject {
    @Published var messages: [ChatMessage] = []
    @Published var question: String = ""
    @Published var isGenerating = false
    
    let story: StoryPackage
    private let repository: StoryRepository
    private let saveState: SaveState
    private let llamaEngine: LlamaEngine
    private let modelURL: URL
    
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
        
        // Load history
        self.messages = saveState.gmHistory.map { turn in
            ChatMessage(text: turn.text, isUser: turn.role == "user")
        }
    }

    func ensureModelLoaded() async {
        guard !llamaEngine.isLoaded else { return }
        do { try await llamaEngine.loadModel(path: modelURL.path) }
        catch { messages.append(ChatMessage(text: "Local Game Master unavailable: \(error.localizedDescription)", isUser: false)) }
    }
    
    func sendQuestion() {
        let q = question.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty, !isGenerating else { return }
        
        let userMsg = ChatMessage(text: q, isUser: true)
        messages.append(userMsg)
        question = ""
        isGenerating = true
        
        Task {
            do {
                // Build GM prompt with context
                let node = repository.nodes[saveState.currentNodeId]
                let sceneText = node?.text ?? ""
                
                let loreContext = repository.gmIndex.promptContext(
                    query: q,
                    visitedNodes: Set(saveState.visitedNodes)
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
                
                let answer = try await llamaEngine.generate(
                    prompt: prompt,
                    maxTokens: 256,
                    temperature: 0.8
                )
                
                let trimmed = answer.trimmingCharacters(in: .whitespacesAndNewlines)
                let gmMsg = ChatMessage(text: trimmed, isUser: false)
                messages.append(gmMsg)
                
                var state = self.saveState
                state.addGMExchange(question: q, answer: trimmed)
                state.save(to: story.saveDir)
            } catch {
                messages.append(ChatMessage(
                    text: "The Game Master's voice falters... (\(error.localizedDescription))",
                    isUser: false
                ))
            }
            
            isGenerating = false
        }
    }
}
