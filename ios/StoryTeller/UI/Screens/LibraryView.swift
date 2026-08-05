import SwiftUI
import UniformTypeIdentifiers

struct LibraryView: View {
    let storyParser: StoryParser
    let onSelect: (StoryPackage) -> Void
    
    @State private var stories: [StoryPackage] = []
    @State private var showFilePicker = false
    @State private var showDeleteAlert: StoryPackage? = nil
    @State private var importError: String?
    
    var body: some View {
        ZStack {
            AppTheme.midnight.ignoresSafeArea()
            
            if stories.isEmpty {
                emptyState
            } else {
                storyList
            }
        }
        .navigationTitle("StoryTeller")
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button(action: { showFilePicker = true }) {
                    Image(systemName: "plus")
                        .foregroundColor(AppTheme.gold)
                }
            }
        }
        .fileImporter(
            isPresented: $showFilePicker,
            allowedContentTypes: [.storyPackage, .archive],
            allowsMultipleSelection: false
        ) { result in
            handleImport(result)
        }
        .onAppear { stories = storyParser.listStories() }
        .alert("Import Error", isPresented: .constant(importError != nil)) {
            Button("OK") { importError = nil }
        } message: {
            Text(importError ?? "")
        }
    }
    
    // MARK: - Subviews
    
    private var emptyState: some View {
        VStack(spacing: 16) {
            Image(systemName: "book.closed")
                .font(.system(size: 64))
                .foregroundColor(AppTheme.gold.opacity(0.3))
            Text("No stories yet")
                .font(.storytellerHeading)
                .foregroundColor(AppTheme.parchment.opacity(0.5))
            Text("Tap + to import a .story file")
                .font(.storytellerCaption)
                .foregroundColor(AppTheme.parchment.opacity(0.3))
        }
    }
    
    private var storyList: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(stories) { story in
                    StoryCard(story: story) {
                        onSelect(story)
                    } onDelete: {
                        showDeleteAlert = story
                    }
                }
            }
            .padding(16)
        }
        .alert("Delete \"\(showDeleteAlert?.title ?? "")\"?",
               isPresented: .constant(showDeleteAlert != nil)) {
            Button("Delete, Keep Saves", role: .destructive) {
                if let story = showDeleteAlert {
                    try? storyParser.delete(storyId: story.storyId, deleteLocalData: false)
                    stories = storyParser.listStories()
                }
                showDeleteAlert = nil
            }
            Button("Delete Story and Saves", role: .destructive) {
                if let story = showDeleteAlert {
                    try? storyParser.delete(storyId: story.storyId, deleteLocalData: true)
                    stories = storyParser.listStories()
                }
                showDeleteAlert = nil
            }
            Button("Cancel", role: .cancel) { showDeleteAlert = nil }
        } message: {
            Text("Choose whether app-private saves and history should also be removed.")
        }
    }
    
    // MARK: - Actions
    
    private func handleImport(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            guard let url = urls.first else { return }
            guard url.startAccessingSecurityScopedResource() else {
                importError = "Cannot access this file."
                return
            }
            defer { url.stopAccessingSecurityScopedResource() }
            
            do {
                let story = try storyParser.importStory(from: url)
                stories = storyParser.listStories()
                onSelect(story)
            } catch {
                importError = error.localizedDescription
            }
        case .failure(let error):
            importError = error.localizedDescription
        }
    }
}

// MARK: - Story Card

struct StoryCard: View {
    let story: StoryPackage
    let onTap: () -> Void
    let onDelete: () -> Void
    
    var body: some View {
        HStack(spacing: 16) {
            // Book icon
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(AppTheme.gold.opacity(0.2))
                    .frame(width: 48, height: 48)
                Image(systemName: "book.closed")
                    .foregroundColor(AppTheme.gold)
            }
            
            VStack(alignment: .leading, spacing: 4) {
                Text(story.title)
                    .font(.storytellerHeading)
                    .foregroundColor(AppTheme.parchment)
                Text("Seed: \(story.seed)")
                    .font(.storytellerCaption)
                    .foregroundColor(AppTheme.parchment.opacity(0.5))
            }
            
            Spacer()
            
            Button(action: onDelete) {
                Image(systemName: "trash")
                    .foregroundColor(AppTheme.parchment.opacity(0.3))
            }
        }
        .padding(16)
        .background(AppTheme.charcoal)
        .cornerRadius(12)
        .onTapGesture(perform: onTap)
    }
}

// MARK: - UTType

extension UTType {
    static let storyPackage = UTType(filenameExtension: "story") ?? .archive
}
