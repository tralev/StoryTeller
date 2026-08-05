import SwiftUI

@main
struct StoryTellerApp: App {
    @StateObject private var appState = AppState()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(appState)
                .preferredColorScheme(.dark)
        }
    }
}

// MARK: - App-wide state

@MainActor
final class AppState: ObservableObject {
    let storyParser = StoryParser()
    let llamaEngine = LlamaEngine()
    let midiPlayer = MidiPlayer()
    
    let modelDownloadManager: ModelDownloadManager
    
    init() {
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("models")
        modelDownloadManager = ModelDownloadManager(modelsDirectory: directory)
        midiPlayer.setup()
    }
    
    var modelsDir: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("models")
    }
    
    var gmModelURL: URL {
        modelDownloadManager.installedURL
    }
}
