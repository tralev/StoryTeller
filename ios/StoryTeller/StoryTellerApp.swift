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

final class AppState: ObservableObject {
    let storyParser = StoryParser()
    let llamaEngine = LlamaEngine()
    let midiPlayer = MidiPlayer()
    
    @Published var isModelReady: Bool = false
    @Published var isDownloadingModel: Bool = false
    @Published var downloadProgress: Double = 0
    
    init() {
        midiPlayer.setup()
        checkModelAvailability()
    }
    
    var modelsDir: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("models")
    }
    
    var gmModelURL: URL {
        modelsDir.appendingPathComponent("Llama-3.2-3B-Instruct-Q4_K_M.gguf")
    }
    
    func checkModelAvailability() {
        let fileManager = FileManager.default
        let modelPath = gmModelURL.path
        if fileManager.fileExists(atPath: modelPath),
           let attrs = try? fileManager.attributesOfItem(atPath: modelPath),
           let size = attrs[.size] as? Int64,
           size > 100_000_000 {
            isModelReady = true
        }
    }
    
    func downloadModelIfNeeded() async {
        guard !isModelReady, !isDownloadingModel else { return }
        
        isDownloadingModel = true
        downloadProgress = 0
        
        let url = URL(string: "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf")!
        
        do {
            try FileManager.default.createDirectory(at: modelsDir, withIntermediateDirectories: true)
            let (bytes, response) = try await URLSession.shared.bytes(from: url)
            let totalBytes = Double(response.expectedContentLength)
            
            let outputURL = gmModelURL
            FileManager.default.createFile(atPath: outputURL.path, contents: nil)
            let handle = try FileHandle(forWritingTo: outputURL)
            defer { try? handle.close() }
            
            var downloaded: Double = 0
            for try await byte in bytes {
                // Accumulate chunks for efficiency
            }
            
            // Use a simpler streaming approach
            let (data, _) = try await URLSession.shared.data(from: url)
            try data.write(to: outputURL)
            
            isModelReady = true
        } catch {
            print("Model download failed: \(error)")
            try? FileManager.default.removeItem(at: gmModelURL)
        }
        
        isDownloadingModel = false
    }
}
