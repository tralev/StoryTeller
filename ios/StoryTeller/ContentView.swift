import SwiftUI

struct ContentView: View {
    @EnvironmentObject var appState: AppState
    @State private var selectedStory: StoryPackage?
    @State private var showGM = false
    
    var body: some View {
        NavigationStack {
            Group {
                if let story = selectedStory, !showGM {
                    ReaderView(
                        story: story,
                        onBack: { selectedStory = nil },
                        onAskGM: { showGM = true }
                    )
                } else if let story = selectedStory, showGM {
                    GameMasterView(
                        story: story,
                        onBack: { showGM = false }
                    )
                } else {
                    LibraryView(
                        storyParser: appState.storyParser,
                        onSelect: { story in
                            selectedStory = story
                            showGM = false
                        }
                    )
                }
            }
        }
        .tint(AppTheme.gold)
        .task {
            await appState.downloadModelIfNeeded()
        }
    }
}
