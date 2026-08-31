import Foundation

// MARK: - P8.6 Chunk Stream Events

/// Frozen stream event types — identical across Python, Kotlin, Swift.
///
/// One request owns one model lease and cancellation token.  Cancellation
/// emits ``cancelled`` — never ``failed``.
enum ChunkStreamEventType: String, Sendable {
    case started, text, completed, failed, cancelled
}

/// One emitted event from the chunk stream.
///
/// All fields are stable across platforms.  `requestId` ties events to their
/// originating request.  `sequence` is strictly increasing within a request
/// and starts at 0 for STARTED.
struct ChunkStreamEvent: Sendable {
    let requestId: String
    let eventType: ChunkStreamEventType
    let sequence: Int
    let text: String
    let usage: [String: Int]?
    let stableCode: String

    init(requestId: String, eventType: ChunkStreamEventType, sequence: Int,
         text: String = "", usage: [String: Int]? = nil, stableCode: String = "") {
        self.requestId = requestId
        self.eventType = eventType
        self.sequence = sequence
        self.text = text
        self.usage = usage
        self.stableCode = stableCode
    }

    var terminalCode: String? {
        switch eventType {
        case .failed, .cancelled: return stableCode.isEmpty ? nil : stableCode
        default: return nil
        }
    }
}

// MARK: - P8.C2 Stable Diagnostic Codes

enum StreamErrorCode {
    static let modelNotLoaded = "STREAM_MODEL_NOT_LOADED"
    static let cancelled = "STREAM_CANCELLED"
    static let nativeFailure = "STREAM_NATIVE_FAILURE"
    static let timeout = "STREAM_TIMEOUT"
    static let queueFull = "STREAM_QUEUE_FULL"
}

// MARK: - Bounded Async Channel

/// P8.6 bounded, lossless bridge from synchronous native callbacks to async UI.
///
/// `send` applies backpressure when 64 events are pending. No token text is
/// dropped, rewritten, or merged. One channel has one consumer and one terminal.
final class BoundedChunkChannel: AsyncSequence, @unchecked Sendable {
    typealias Element = ChunkStreamEvent

    struct AsyncIterator: AsyncIteratorProtocol {
        fileprivate let channel: BoundedChunkChannel
        mutating func next() async -> ChunkStreamEvent? { await channel.nextEvent() }
    }

    static let defaultCapacity = 64
    static let minCapacity = 4

    private let capacity: Int
    private let condition = NSCondition()
    private var buffer: [ChunkStreamEvent] = []
    private var waiter: CheckedContinuation<ChunkStreamEvent?, Never>?
    private var cancellationHandler: (@Sendable () -> Void)?
    private var finished = false

    init(capacity: Int = defaultCapacity) {
        precondition(capacity >= Self.minCapacity, "capacity must be at least \(Self.minCapacity)")
        self.capacity = capacity
    }

    func makeAsyncIterator() -> AsyncIterator { AsyncIterator(channel: self) }

    func onCancellation(_ handler: @escaping @Sendable () -> Void) {
        condition.lock()
        cancellationHandler = handler
        condition.unlock()
    }

    func send(_ event: ChunkStreamEvent) {
        condition.lock()
        while buffer.count >= capacity && waiter == nil && !finished {
            condition.wait()
        }
        guard !finished else { condition.unlock(); return }
        let waiting = waiter
        waiter = nil
        if waiting == nil { buffer.append(event) }
        if event.eventType == .completed || event.eventType == .failed || event.eventType == .cancelled {
            finished = true
        }
        condition.broadcast()
        condition.unlock()
        waiting?.resume(returning: event)
    }

    func finish() {
        condition.lock()
        finished = true
        let waiting = waiter
        waiter = nil
        condition.broadcast()
        condition.unlock()
        waiting?.resume(returning: nil)
    }

    private func nextEvent() async -> ChunkStreamEvent? {
        await withTaskCancellationHandler {
            await withCheckedContinuation { continuation in
                condition.lock()
                if !buffer.isEmpty {
                    let event = buffer.removeFirst()
                    condition.signal()
                    condition.unlock()
                    continuation.resume(returning: event)
                } else if finished {
                    condition.unlock()
                    continuation.resume(returning: nil)
                } else {
                    precondition(waiter == nil, "BoundedChunkChannel supports one consumer")
                    waiter = continuation
                    condition.unlock()
                }
            }
        } onCancel: {
            self.cancelConsumer()
        }
    }

    private func cancelConsumer() {
        condition.lock()
        let handler = cancellationHandler
        cancellationHandler = nil
        condition.unlock()
        handler?()
        finish()
    }
}

// MARK: - Stream Builder

/// P8.6 — Builds a correctly-ordered sequence of `ChunkStreamEvent`s.
struct StreamBuilder {
    let requestId: String
    private var seq = 0

    init(requestId: String) {
        self.requestId = requestId
    }

    func started() -> ChunkStreamEvent {
        ChunkStreamEvent(requestId: requestId, eventType: .started, sequence: 0)
    }

    mutating func text(_ text: String) -> ChunkStreamEvent {
        precondition(!text.isEmpty, "text chunk must be non-empty")
        seq += 1
        return ChunkStreamEvent(requestId: requestId, eventType: .text, sequence: seq, text: text)
    }

    mutating func completed(_ usage: [String: Int]) -> ChunkStreamEvent {
        seq += 1
        return ChunkStreamEvent(requestId: requestId, eventType: .completed, sequence: seq, usage: usage)
    }

    mutating func failed(_ code: String) -> ChunkStreamEvent {
        seq += 1
        return ChunkStreamEvent(requestId: requestId, eventType: .failed, sequence: seq, stableCode: code)
    }

    mutating func cancelled() -> ChunkStreamEvent {
        seq += 1
        return ChunkStreamEvent(requestId: requestId, eventType: .cancelled, sequence: seq, stableCode: StreamErrorCode.cancelled)
    }
}
