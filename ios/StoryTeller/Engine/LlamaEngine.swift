import Foundation

enum LlamaLifecycleState: Equatable {
    case unloaded
    case loading
    case loaded
    case generating
    case unloading
}

/// Serial, cancellable owner of exactly one native llama model/context pair.
final class LlamaEngine: @unchecked Sendable {
    static let defaultContextSize: Int32 = 2048
    static let minimumContextSize: Int32 = 512
    static let maximumContextSize: Int32 = 8192
    static let maximumOutputTokens: Int32 = 1024

    private let queue = DispatchQueue(label: "com.storyteller.llama", qos: .userInitiated)
    private let lock = NSLock()
    private var contextPtr: UnsafeMutableRawPointer?
    private var internalState: LlamaLifecycleState = .unloaded

    var state: LlamaLifecycleState { lock.withLock { internalState } }
    var isLoaded: Bool { state == .loaded || state == .generating }

    deinit {
        cancelGeneration()
        queue.sync { unloadOnQueue() }
    }

    func loadModel(path: String, contextSize: Int32 = defaultContextSize) async throws {
        guard Self.minimumContextSize...Self.maximumContextSize ~= contextSize else { throw LlamaError.invalidContextSize }
        guard FileManager.default.fileExists(atPath: path) else { throw LlamaError.fileNotFound(path) }
        if isLoaded { return }
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
            queue.async { [self] in
                guard transition(from: [.unloaded], to: .loading) else {
                    continuation.resume(throwing: LlamaError.invalidLifecycle)
                    return
                }
                guard let pointer = native_load_model(path, contextSize) else {
                    setState(.unloaded)
                    continuation.resume(throwing: LlamaError.loadFailed(path))
                    return
                }
                lock.withLock { contextPtr = pointer; internalState = .loaded }
                continuation.resume(returning: ())
            }
        }
    }

    func generate(
        prompt: String,
        maxTokens: Int32 = 256,
        temperature: Float = 0.8,
        seed: Int32 = 0
    ) async throws -> String {
        guard !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { throw LlamaError.emptyPrompt }
        guard 1...Self.maximumOutputTokens ~= maxTokens else { throw LlamaError.invalidTokenLimit }
        guard (0...2).contains(temperature) else { throw LlamaError.invalidTemperature }
        let cancellation = CancellationFlag()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                queue.async { [self] in
                    guard transition(from: [.loaded], to: .generating), let pointer = pointer() else {
                        continuation.resume(throwing: LlamaError.notLoaded)
                        return
                    }
                    let result = native_generate(pointer, prompt, maxTokens, temperature, seed)
                    setState(.loaded)
                    if cancellation.isCancelled {
                        if let result { free(result) }
                        continuation.resume(throwing: CancellationError())
                    } else if let result {
                        let text = String(cString: result)
                        free(result)
                        continuation.resume(returning: text)
                    } else {
                        continuation.resume(throwing: LlamaError.generationFailed)
                    }
                }
            }
        } onCancel: { [weak self] in
            cancellation.cancel()
            self?.cancelGeneration()
        }
    }

    func generateStreaming(
        prompt: String,
        maxTokens: Int32 = 256,
        temperature: Float = 0.8,
        seed: Int32 = 0,
        onText: @escaping @Sendable (String) -> Void
    ) async throws -> Int {
        guard !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw LlamaError.emptyPrompt
        }
        guard 1...Self.maximumOutputTokens ~= maxTokens else { throw LlamaError.invalidTokenLimit }
        guard (0...2).contains(temperature) else { throw LlamaError.invalidTemperature }
        let cancellation = CancellationFlag()
        return try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { continuation in
                queue.async { [self] in
                    guard transition(from: [.loaded], to: .generating), let pointer = pointer() else {
                        continuation.resume(throwing: LlamaError.notLoaded)
                        return
                    }
                    let box = Unmanaged.passRetained(NativeTextCallbackBox(onText))
                    let result = native_generate_streaming(
                        pointer, prompt, maxTokens, temperature, seed,
                        storytellerNativeTextCallback, box.toOpaque()
                    )
                    box.release()
                    setState(.loaded)
                    if cancellation.isCancelled || result == -2 {
                        continuation.resume(throwing: CancellationError())
                    } else if result < 0 {
                        continuation.resume(throwing: LlamaError.generationFailed)
                    } else {
                        continuation.resume(returning: Int(result))
                    }
                }
            }
        } onCancel: { [weak self] in
            cancellation.cancel()
            self?.cancelGeneration()
        }
    }

    func stream(
        requestId: String,
        prompt: String,
        maxTokens: Int32 = 256,
        temperature: Float = 0.8,
        seed: Int32 = 0
    ) -> BoundedChunkChannel {
        let channel = BoundedChunkChannel()
        let task = Task {
            let builder = LockedStreamBuilder(requestId: requestId)
            channel.send(builder.started())
            do {
                let count = try await generateStreaming(
                    prompt: prompt, maxTokens: maxTokens, temperature: temperature, seed: seed
                ) { text in
                    channel.send(builder.text(text))
                }
                channel.send(builder.completed(["chunks": count]))
            } catch is CancellationError {
                channel.send(builder.cancelled())
            } catch {
                channel.send(builder.failed(StreamErrorCode.nativeFailure))
            }
            channel.finish()
        }
        channel.onCancellation { [weak self] in
            self?.cancelGeneration()
            task.cancel()
        }
        return channel
    }

    func cancelGeneration() {
        if let pointer = pointer() { native_cancel_generation(pointer) }
    }

    func unloadModel() async {
        cancelGeneration()
        await withCheckedContinuation { continuation in
            queue.async { [self] in unloadOnQueue(); continuation.resume() }
        }
    }

    /// Background and memory-pressure callbacks cannot await; cancellation makes
    /// the token loop return, then this serial queue releases all native memory.
    func suspendForBackground() {
        cancelGeneration()
        queue.async { [self] in unloadOnQueue() }
    }

    func releaseForMemoryPressure() { suspendForBackground() }

    private func unloadOnQueue() {
        guard let pointer = pointer() else { setState(.unloaded); return }
        setState(.unloading)
        native_unload_model(pointer)
        lock.withLock { contextPtr = nil; internalState = .unloaded }
    }

    private func pointer() -> UnsafeMutableRawPointer? { lock.withLock { contextPtr } }
    private func setState(_ value: LlamaLifecycleState) { lock.withLock { internalState = value } }
    private func transition(from allowed: Set<LlamaLifecycleState>, to next: LlamaLifecycleState) -> Bool {
        lock.withLock {
            guard allowed.contains(internalState) else { return false }
            internalState = next
            return true
        }
    }
}

private final class NativeTextCallbackBox: @unchecked Sendable {
    let callback: @Sendable (String) -> Void
    init(_ callback: @escaping @Sendable (String) -> Void) { self.callback = callback }
}

private final class LockedStreamBuilder: @unchecked Sendable {
    private let lock = NSLock()
    private var builder: StreamBuilder

    init(requestId: String) { builder = StreamBuilder(requestId: requestId) }
    func started() -> ChunkStreamEvent { lock.withLock { builder.started() } }
    func text(_ value: String) -> ChunkStreamEvent { lock.withLock { builder.text(value) } }
    func completed(_ usage: [String: Int]) -> ChunkStreamEvent {
        lock.withLock { builder.completed(usage) }
    }
    func failed(_ code: String) -> ChunkStreamEvent { lock.withLock { builder.failed(code) } }
    func cancelled() -> ChunkStreamEvent { lock.withLock { builder.cancelled() } }
}

private func storytellerNativeTextCallback(
    _ text: UnsafePointer<CChar>?, _ length: Int32, _ userData: UnsafeMutableRawPointer?
) {
    guard let text, let userData, length > 0 else { return }
    let bytes = UnsafeRawBufferPointer(start: text, count: Int(length))
    let value = String(decoding: bytes, as: UTF8.self)
    if !value.isEmpty {
        Unmanaged<NativeTextCallbackBox>.fromOpaque(userData).takeUnretainedValue().callback(value)
    }
}

private final class CancellationFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var value = false
    var isCancelled: Bool { lock.withLock { value } }
    func cancel() { lock.withLock { value = true } }
}

private extension NSLock {
    func withLock<T>(_ body: () throws -> T) rethrows -> T {
        lock(); defer { unlock() }
        return try body()
    }
}

enum LlamaError: LocalizedError {
    case notLoaded, invalidLifecycle, invalidContextSize, invalidTokenLimit, invalidTemperature, emptyPrompt
    case fileNotFound(String), loadFailed(String), generationFailed

    var errorDescription: String? {
        switch self {
        case .notLoaded: return "No model is loaded."
        case .invalidLifecycle: return "The model is changing lifecycle state."
        case .invalidContextSize: return "Context size is outside the supported mobile range."
        case .invalidTokenLimit: return "Output token limit is outside the supported range."
        case .invalidTemperature: return "Temperature must be between 0 and 2."
        case .emptyPrompt: return "Prompt must not be empty."
        case .fileNotFound(let path): return "Model file not found: \(path)"
        case .loadFailed(let path): return "Failed to load model: \(path)"
        case .generationFailed: return "Text generation failed."
        }
    }
}
