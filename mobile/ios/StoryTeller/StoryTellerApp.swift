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
        let outputURL = gmModelURL
        
        do {
            try FileManager.default.createDirectory(at: modelsDir, withIntermediateDirectories: true)
            
            let (asyncBytes, response) = try await URLSession.shared.bytes(for: URLRequest(url: url))
            let totalBytes = Double(response.expectedContentLength)
            
            FileManager.default.createFile(atPath: outputURL.path, contents: nil)
            let handle = try FileHandle(forWritingTo: outputURL)
            defer { try? handle.close() }
            
            var downloaded: Double = 0
            var buffer = Data()
            for try await byte in asyncBytes {
                buffer.append(byte)
                downloaded += 1
                // Flush in 1 MB chunks
                if buffer.count >= 1_048_576 {
                    try handle.write(contentsOf: buffer)
                    buffer.removeAll(keepingCapacity: true)
                    downloadProgress = downloaded / totalBytes
                }
            }
            // Final flush
            if !buffer.isEmpty {
                try handle.write(contentsOf: buffer)
            }
            
            isModelReady = true
            downloadProgress = 1.0
            print("[AppState] Model downloaded: \(outputURL.path)")
        } catch {
            print("[AppState] Model download failed: \(error)")
            try? FileManager.default.removeItem(at: outputURL)
        }
        
        isDownloadingModel = false
    }
}
