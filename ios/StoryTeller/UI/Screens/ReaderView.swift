import SwiftUI

struct ReaderView: View {
    let story: StoryPackage
    let onBack: () -> Void
    let onAskGM: () -> Void
    
    @StateObject private var viewModel: ReaderViewModel
    
    init(story: StoryPackage, onBack: @escaping () -> Void, onAskGM: @escaping () -> Void) {
        self.story = story
        self.onBack = onBack
        self.onAskGM = onAskGM
        _viewModel = StateObject(wrappedValue: ReaderViewModel(story: story))
    }
    
    var body: some View {
        ZStack {
            AppTheme.midnight.ignoresSafeArea()
            
            if let node = viewModel.currentNode {
                ScrollView {
                    VStack(spacing: 0) {
                        // Scene image
                        AsyncImage(url: story.imageFor(nodeId: node.nodeId)) { phase in
                            switch phase {
                            case .success(let image):
                                image
                                    .resizable()
                                    .aspectRatio(contentMode: .fill)
                                    .frame(height: 320)
                                    .clipped()
                            case .failure:
                                Rectangle()
                                    .fill(AppTheme.charcoal)
                                    .frame(height: 200)
                            default:
                                Rectangle()
                                    .fill(AppTheme.charcoal)
                                    .frame(height: 200)
                                    .overlay(ProgressView().tint(AppTheme.gold))
                            }
                        }
                        
                        // Scene text
                        VStack(spacing: 6) {
                            ForEach(node.displayLines, id: \.self) { line in
                                Text(line)
                                    .font(.storytellerBody)
                                    .foregroundColor(AppTheme.parchment)
                                    .multilineTextAlignment(.center)
                                    .frame(maxWidth: .infinity)
                            }
                        }
                        .padding(.horizontal, 24)
                        .padding(.vertical, 20)
                        
                        // Ending state
                        if node.isEnding {
                            VStack(spacing: 16) {
                                Text("The End")
                                    .font(.storytellerTitle)
                                    .foregroundColor(AppTheme.gold)
                                Button("Read Again") {
                                    viewModel.reset()
                                }
                                .buttonStyle(.bordered)
                                .tint(AppTheme.gold)
                            }
                            .padding(24)
                            .background(AppTheme.gold.opacity(0.1))
                            .cornerRadius(12)
                            .padding(.horizontal, 24)
                        }
                        
                        // Choices
                        if !node.isEnding {
                            VStack(spacing: 12) {
                                ForEach(node.choices.filter {
                                    $0.isAvailable(activeFlags: viewModel.saveState.flags)
                                }) { choice in
                                    Button(action: { viewModel.makeChoice(choice) }) {
                                        Text(choice.choiceText)
                                            .font(.storytellerChoice)
                                            .foregroundColor(AppTheme.parchment)
                                            .frame(maxWidth: .infinity)
                                            .padding(16)
                                            .background(AppTheme.charcoal)
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 12)
                                                    .stroke(AppTheme.gold.opacity(0.3), lineWidth: 1)
                                            )
                                            .cornerRadius(12)
                                    }
                                }
                            }
                            .padding(.horizontal, 24)
                        }
                        
                    }
                }
            } else {
                ProgressView("Loading...")
                    .tint(AppTheme.gold)
            }
        }
        .navigationTitle(story.title)
        .navigationBarTitleDisplayMode(.inline)
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button(action: onBack) {
                    Image(systemName: "chevron.left")
                        .foregroundColor(AppTheme.gold)
                }
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                HStack(spacing: 16) {
                    // Bookmark
                    Button(action: { viewModel.toggleBookmark() }) {
                        Image(systemName: viewModel.isBookmarked ? "bookmark.fill" : "bookmark")
                            .foregroundColor(AppTheme.gold)
                    }
                    // Music toggle
                    Button(action: { viewModel.toggleMusic() }) {
                        Image(systemName: viewModel.isMusicPlaying ? "music.note" : "music.note.slash")
                            .foregroundColor(AppTheme.gold)
                    }
                    // Game Master
                    Button(action: onAskGM) {
                        Image(systemName: "message")
                            .foregroundColor(AppTheme.gold)
                    }
                }
            }
        }
        .onAppear { viewModel.onAppear() }
    }
}

// MARK: - ViewModel

@MainActor
final class ReaderViewModel: ObservableObject {
    @Published var currentNode: GraphNode?
    @Published var isBookmarked = false
    @Published var isMusicPlaying = false
    
    let story: StoryPackage
    let repository: StoryRepository
    var saveState: SaveState
    
    private let midiPlayer: MidiPlayer
    
    init(story: StoryPackage) {
        self.story = story
        self.repository = StoryRepository(story: story)
        let loaded = SaveState.load(from: story.saveDir)
        self.saveState = loaded.currentNode.isEmpty
            ? SaveState(storyId: story.storyId, packageContentHash: story.contentHash,
                        currentNode: story.entryNode, visitedNodes: [story.entryNode])
            : loaded
        self.midiPlayer = MidiPlayer()
        midiPlayer.setup()
    }
    
    func onAppear() {
        loadNode(saveState.currentNodeId)
    }
    
    func loadNode(_ nodeId: String) {
        currentNode = repository.nodes[nodeId]
        saveState.visitNode(nodeId)
        saveState.save(to: story.saveDir)
        isBookmarked = saveState.bookmarks.contains(nodeId)
        
        // Auto-play MIDI
        let midiURL = story.midiFor(nodeId: nodeId)
        if FileManager.default.fileExists(atPath: midiURL.path) {
            midiPlayer.play(midiURL, loop: true)
            isMusicPlaying = true
        }
    }
    
    func makeChoice(_ choice: Choice) {
        saveState.makeChoice(choice)
        saveState.save(to: story.saveDir)
        loadNode(choice.targetNode)
    }
    
    func toggleBookmark() {
        isBookmarked = saveState.toggleBookmark()
        saveState.save(to: story.saveDir)
    }
    
    func toggleMusic() {
        if isMusicPlaying {
            midiPlayer.stop()
        } else if let node = currentNode {
            let midiURL = story.midiFor(nodeId: node.nodeId)
            if FileManager.default.fileExists(atPath: midiURL.path) {
                midiPlayer.play(midiURL, loop: true)
            }
        }
        isMusicPlaying.toggle()
    }
    
    func reset() {
        saveState.reset()
        saveState.save(to: story.saveDir)
        loadNode(story.entryNode)
    }
}
