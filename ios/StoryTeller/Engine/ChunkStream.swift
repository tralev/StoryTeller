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

/// P8.6 — Bounded async stream between native callbacks and UI.
///
/// Fixed capacity (default 64).  When the producer outruns the consumer, the
/// oldest unconsumed `.text` event is dropped and a continuation-marker `"…"`
/// is inserted.  This guarantees the native callback is never blocked
/// indefinitely.
///
/// One `BoundedChunkChannel` per request.  Call `finish()` to signal the
/// consumer.
final class BoundedChunkChannel: @unchecked Sendable {
    static let defaultCapacity = 64
    static let minCapacity = 4

    private let capacity: Int
    private let lock = NSLock()
    private var buffer: [ChunkStreamEvent] = []
    private var continuation: AsyncStream<ChunkStreamEvent>.Continuation?
    private var finished = false

    init(capacity: Int = defaultCapacity) {
        precondition(capacity >= Self.minCapacity, "capacity must be at least \(Self.minCapacity)")
        self.capacity = capacity
    }

    /// Returns an `AsyncStream` that yields events until a terminal event or finish.
    func events() -> AsyncStream<ChunkStreamEvent> {
        AsyncStream { continuation in
            lock.withLock {
                self.continuation = continuation
                // Drain any buffered events
                for event in buffer {
                    continuation.yield(event)
                    if event.eventType == .completed || event.eventType == .failed || event.eventType == .cancelled {
                        self.finished = true
                        continuation.finish()
                        return
                    }
                }
                buffer.removeAll()
                if finished {
                    continuation.finish()
                }
            }
        }
    }

    func send(_ event: ChunkStreamEvent) {
        lock.withLock {
            guard !finished else { return }
            if let cont = continuation {
                cont.yield(event)
                if event.eventType == .completed || event.eventType == .failed || event.eventType == .cancelled {
                    finished = true
                    cont.finish()
                }
            } else {
                // Coalesce: drop oldest TEXT if at capacity
                while buffer.count >= capacity {
                    if let idx = buffer.firstIndex(where: { $0.eventType == .text }) {
                        buffer[idx] = ChunkStreamEvent(
                            requestId: event.requestId, eventType: .text,
                            sequence: buffer[idx].sequence, text: "…"
                        )
                        break
                    } else {
                        buffer.removeFirst()
                    }
                }
                buffer.append(event)
            }
        }
    }

    func finish() {
        lock.withLock {
            guard !finished else { return }
            finished = true
            continuation?.finish()
        }
    }
}

// MARK: - Stream Builder

/// P8.6 — Builds a correctly-ordered sequence of `ChunkStreamEvent`s.
struct StreamBuilder {
    let requestId: String
    private var seq = 0

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
