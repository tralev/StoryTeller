import Foundation

/// Swift wrapper around llama.cpp's C API.
///
/// The C functions are declared in llama.h and linked via a bridging header.
/// This class manages model lifecycle and provides an async Swift interface.
///
/// Thread safety: All llama calls run on a serial background queue.
final class LlamaEngine {
    private let queue = DispatchQueue(label: "com.storyteller.llama", qos: .userInitiated)
    private var contextPtr: UnsafeMutableRawPointer?
    private(set) var isLoaded = false
    
    deinit {
        unloadModel()
    }
    
    // MARK: - Public API
    
    /// Load a GGUF model from disk.
    func loadModel(path: String, contextSize: Int32 = 2048) throws {
        guard !isLoaded else { throw LlamaError.alreadyLoaded }
        guard FileManager.default.fileExists(atPath: path) else {
            throw LlamaError.fileNotFound(path)
        }
        
        var error: Error?
        queue.sync {
            guard let ptr = native_load_model(path, contextSize) else {
                error = LlamaError.loadFailed(path)
                return
            }
            contextPtr = ptr
            isLoaded = true
        }
        
        if let error { throw error }
        print("[LlamaEngine] Model loaded: \(path)")
    }
    
    /// Generate a response from a prompt.
    func generate(
        prompt: String,
        maxTokens: Int32 = 256,
        temperature: Float = 0.8,
        seed: Int32 = 0
    ) async throws -> String {
        guard isLoaded, let ptr = contextPtr else {
            throw LlamaError.notLoaded
        }
        
        return try await withCheckedThrowingContinuation { continuation in
            queue.async {
                let result = native_generate(ptr, prompt, maxTokens, temperature, seed)
                if let output = result {
                    continuation.resume(returning: output as String)
                } else {
                    continuation.resume(throwing: LlamaError.generationFailed)
                }
            }
        }
    }
    
    /// Unload the model and free memory.
    func unloadModel() {
        guard isLoaded, let ptr = contextPtr else { return }
        
        queue.sync {
            native_unload_model(ptr)
            contextPtr = nil
            isLoaded = false
        }
        print("[LlamaEngine] Model unloaded.")
    }
}

// MARK: - Errors

enum LlamaError: LocalizedError {
    case alreadyLoaded
    case notLoaded
    case fileNotFound(String)
    case loadFailed(String)
    case generationFailed
    
    var errorDescription: String? {
        switch self {
        case .alreadyLoaded: return "Model is already loaded."
        case .notLoaded: return "No model loaded. Call loadModel() first."
        case .fileNotFound(let path): return "Model file not found: \(path)"
        case .loadFailed(let path): return "Failed to load model: \(path)"
        case .generationFailed: return "Text generation failed."
        }
    }
}
