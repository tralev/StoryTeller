import Foundation

/// P8.7 — Transactional conversation history.
///
/// Durable conversation save — isolated from the immutable .story.
/// Writes temp file, fsyncs, then atomically replaces.
/// Only completed exchanges are saved; cancel/failure leaves no partial turn.

// MARK: - Data Types

/// One user/assistant turn. Only saved after `completed`.
public struct Exchange: Codable, Equatable {
    public let exchangeId: String
    public let userText: String
    public let assistantText: String
    public let sequence: Int
    public let createdAt: Double

    enum CodingKeys: String, CodingKey {
        case exchangeId = "exchange_id"
        case userText = "user_text"
        case assistantText = "assistant_text"
        case sequence
        case createdAt = "created_at"
    }

    public init(exchangeId: String, userText: String, assistantText: String, sequence: Int, createdAt: Double) {
        self.exchangeId = exchangeId
        self.userText = userText
        self.assistantText = assistantText
        self.sequence = sequence
        self.createdAt = createdAt
    }
}

/// Durable conversation save — isolated from the immutable .story.
public struct ConversationHistory: Codable {
    public let version: Int
    public let storyId: String
    public let contentHash: String
    public let conversationId: String
    public let exchanges: [Exchange]
    public let metadata: [String: String]
    public let sha256: String?

    public var exchangeCount: Int { exchanges.count }

    enum CodingKeys: String, CodingKey {
        case version
        case storyId = "story_id"
        case contentHash = "content_hash"
        case conversationId = "conversation_id"
        case exchanges
        case metadata
        case sha256 = "_sha256"
    }

    public init(
        version: Int = 1,
        storyId: String = "",
        contentHash: String = "",
        conversationId: String = "",
        exchanges: [Exchange] = [],
        metadata: [String: String] = [:]
    ) {
        self.version = version
        self.storyId = storyId
        self.contentHash = contentHash
        self.conversationId = conversationId
        self.exchanges = exchanges
        self.metadata = metadata
        self.sha256 = nil // computed on encode
    }

    fileprivate init(
        version: Int,
        storyId: String,
        contentHash: String,
        conversationId: String,
        exchanges: [Exchange],
        metadata: [String: String],
        sha256: String
    ) {
        self.version = version
        self.storyId = storyId
        self.contentHash = contentHash
        self.conversationId = conversationId
        self.exchanges = exchanges
        self.metadata = metadata
        self.sha256 = sha256
    }

    /// Encode with computed _sha256.
    public func encoded() throws -> Data {
        var dict: [String: Any] = [
            "version": version,
            "story_id": storyId,
            "content_hash": contentHash,
            "conversation_id": conversationId,
            "metadata": metadata
        ]
        dict["exchanges"] = exchanges.map { $0.toDict() }

        // Compute content hash
        let sortedExchanges = exchanges.sorted(by: { $0.sequence < $1.sequence })
        let hashInput = try JSONSerialization.data(
            withJSONObject: sortedExchanges.map { $0.toDict() },
            options: [.sortedKeys]
        )
        dict["_sha256"] = hashInput.sha256Hex()

        return try JSONSerialization.data(
            withJSONObject: dict,
            options: [.sortedKeys, .prettyPrinted]
        )
    }
}

extension Exchange {
    func toDict() -> [String: Any] {
        return [
            "exchange_id": exchangeId,
            "user_text": userText,
            "assistant_text": assistantText,
            "sequence": sequence,
            "created_at": createdAt
        ]
    }

    static func fromDict(_ dict: [String: Any]) -> Exchange? {
        guard let exchangeId = dict["exchange_id"] as? String,
              let userText = dict["user_text"] as? String,
              let assistantText = dict["assistant_text"] as? String,
              let sequence = dict["sequence"] as? Int,
              let createdAt = dict["created_at"] as? Double
        else { return nil }
        return Exchange(
            exchangeId: exchangeId,
            userText: userText,
            assistantText: assistantText,
            sequence: sequence,
            createdAt: createdAt
        )
    }
}

// MARK: - Errors

public enum ConversationHistoryError: LocalizedError {
    case exchangeLimit(String)
    case sizeLimit(String)
    case atomicFailed(String)
    case corruptJSON(String)
    case missingVersion
    case futureVersion(String)
    case oldVersion(String)
    case orderBroken(String)
    case textSize(String)
    case hashMismatch
    case sequenceSkip(String)
    case identityMismatch(String)

    public var code: String {
        switch self {
        case .exchangeLimit: return "HISTORY_EXCHANGE_LIMIT"
        case .sizeLimit: return "HISTORY_SIZE_LIMIT"
        case .atomicFailed: return "HISTORY_ATOMIC_FAILED"
        case .corruptJSON: return "HISTORY_CORRUPT_JSON"
        case .missingVersion: return "HISTORY_MISSING_VERSION"
        case .futureVersion: return "HISTORY_FUTURE_VERSION"
        case .oldVersion: return "HISTORY_OLD_VERSION"
        case .orderBroken: return "HISTORY_ORDER_BROKEN"
        case .textSize: return "HISTORY_TEXT_SIZE"
        case .hashMismatch: return "HISTORY_HASH_MISMATCH"
        case .sequenceSkip: return "HISTORY_SEQUENCE_SKIP"
        case .identityMismatch: return "HISTORY_IDENTITY_MISMATCH"
        }
    }

    public var errorDescription: String? {
        "\(code): \(message)"
    }

    private var message: String {
        switch self {
        case .exchangeLimit(let m): return m
        case .sizeLimit(let m): return m
        case .atomicFailed(let m): return m
        case .corruptJSON(let m): return m
        case .missingVersion: return "no version field"
        case .futureVersion(let m): return m
        case .oldVersion(let m): return m
        case .orderBroken(let m): return m
        case .textSize(let m): return m
        case .hashMismatch: return "content hash mismatch — history may be tampered"
        case .sequenceSkip(let m): return m
        case .identityMismatch(let m): return m
        }
    }
}

// MARK: - Store

/// Transactional conversation history save/load.
///
/// P8.7: Writes a temporary file, fsyncs, then atomically replaces.
/// Never stored inside the .story package — always a separate user file.
public enum ConversationHistoryStore {
    private static let version = 1
    private static let maxExchanges = 10_000
    private static let maxExchangeTextBytes = 64 * 1024
    private static let maxTotalBytes = 10 * 1024 * 1024

    public static func save(_ history: ConversationHistory, to url: URL) throws {
        if history.exchangeCount > maxExchanges {
            throw ConversationHistoryError.exchangeLimit(
                "\(history.exchangeCount) exchanges exceeds limit of \(maxExchanges)"
            )
        }
        var seenIds = Set<String>()
        for (expectedSequence, exchange) in history.exchanges.enumerated() {
            guard exchange.sequence == expectedSequence, !exchange.exchangeId.isEmpty,
                  seenIds.insert(exchange.exchangeId).inserted else {
                throw ConversationHistoryError.orderBroken(
                    "exchange order or identity is invalid"
                )
            }
            if exchange.userText.utf8.count > maxExchangeTextBytes ||
                exchange.assistantText.utf8.count > maxExchangeTextBytes {
                throw ConversationHistoryError.textSize(
                    "exchange \(exchange.exchangeId) text exceeds limit"
                )
            }
        }

        let data = try history.encoded()
        if data.count > maxTotalBytes {
            throw ConversationHistoryError.sizeLimit(
                "history exceeds \(maxTotalBytes / (1024 * 1024)) MB"
            )
        }

        let tmpURL = url.appendingPathExtension("tmp")
        let dir = url.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        // Temp write
        try data.write(to: tmpURL, options: .atomic)

        // Set restrictive permissions
        try FileManager.default.setAttributes(
            [.posixPermissions: 0o600],
            ofItemAtPath: tmpURL.path
        )

        // fsync via FileHandle
        let fh = try FileHandle(forWritingTo: tmpURL)
        try fh.synchronize()
        try fh.close()

        // Atomic replace
        if FileManager.default.fileExists(atPath: url.path) {
            _ = try FileManager.default.replaceItemAt(url, withItemAt: tmpURL)
        } else {
            try FileManager.default.moveItem(at: tmpURL, to: url)
        }
    }

    public static func load(from url: URL) throws -> ConversationHistory? {
        guard FileManager.default.fileExists(atPath: url.path) else {
            return nil
        }

        let data: Data
        do {
            data = try Data(contentsOf: url)
        } catch {
            return nil
        }

        if data.count > maxTotalBytes {
            throw ConversationHistoryError.sizeLimit("saved history exceeds size limit")
        }

        guard let raw = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw ConversationHistoryError.corruptJSON("cannot parse history")
        }

        guard let ver = raw["version"] as? Int else {
            throw ConversationHistoryError.missingVersion
        }
        if ver != version {
            if ver > version {
                throw ConversationHistoryError.futureVersion(
                    "cannot read version \(ver) — update the app"
                )
            }
            throw ConversationHistoryError.oldVersion("version \(ver) is not supported")
        }

        let storyId = raw["story_id"] as? String ?? ""
        let contentHash = raw["content_hash"] as? String ?? ""
        let conversationId = raw["conversation_id"] as? String ?? ""
        let metadata = raw["metadata"] as? [String: String] ?? [:]

        let exchanges: [Exchange] = (raw["exchanges"] as? [[String: Any]] ?? []).compactMap {
            Exchange.fromDict($0)
        }

        if exchanges.count > maxExchanges {
            throw ConversationHistoryError.exchangeLimit(
                "\(exchanges.count) exchanges exceeds limit of \(maxExchanges)"
            )
        }

        // Verify ordering
        var loadedIds = Set<String>()
        for (i, e) in exchanges.enumerated() {
            if e.sequence != i || e.exchangeId.isEmpty || !loadedIds.insert(e.exchangeId).inserted {
                throw ConversationHistoryError.orderBroken(
                    "exchange order or identity is invalid at index \(i)"
                )
            }
            if e.userText.utf8.count > maxExchangeTextBytes ||
                e.assistantText.utf8.count > maxExchangeTextBytes {
                throw ConversationHistoryError.textSize(
                    "exchange \(e.exchangeId) text exceeds limit"
                )
            }
        }

        // Verify content hash
        let sortedExchanges = exchanges.sorted(by: { $0.sequence < $1.sequence })
        let hashInput = try JSONSerialization.data(
            withJSONObject: sortedExchanges.map { $0.toDict() },
            options: [.sortedKeys]
        )
        let expectedHash = hashInput.sha256Hex()
        if let actualHash = raw["_sha256"] as? String, !actualHash.isEmpty, actualHash != expectedHash {
            throw ConversationHistoryError.hashMismatch
        }

        return ConversationHistory(
            version: ver,
            storyId: storyId,
            contentHash: contentHash,
            conversationId: conversationId,
            exchanges: exchanges,
            metadata: metadata,
            sha256: expectedHash
        )
    }

    public static func loadBound(
        from url: URL, storyId: String, contentHash: String
    ) throws -> ConversationHistory? {
        guard let history = try load(from: url) else { return nil }
        guard history.storyId == storyId, history.contentHash == contentHash else {
            throw ConversationHistoryError.identityMismatch(
                "history belongs to different immutable content"
            )
        }
        return history
    }

    public static func addExchange(
        _ exchange: Exchange,
        to url: URL,
        storyId: String = "",
        contentHash: String = "",
        conversationId: String = ""
    ) throws -> ConversationHistory {
        let current = try load(from: url)
        var existing = current?.exchanges ?? []

        let expectedSeq = existing.count
        if exchange.sequence != expectedSeq {
            throw ConversationHistoryError.sequenceSkip(
                "expected sequence \(expectedSeq), got \(exchange.sequence)"
            )
        }

        existing.append(exchange)
        let history = ConversationHistory(
            version: version,
            storyId: storyId.isEmpty ? (current?.storyId ?? "") : storyId,
            contentHash: contentHash.isEmpty ? (current?.contentHash ?? "") : contentHash,
            conversationId: conversationId.isEmpty ? (current?.conversationId ?? "") : conversationId,
            exchanges: existing,
            metadata: current?.metadata ?? [:]
        )
        try save(history, to: url)
        return history
    }

    public static func migrateLegacy(
        pairs: [(String, String)], to url: URL, storyId: String,
        contentHash: String, conversationId: String = "default"
    ) throws -> ConversationHistory? {
        if let existing = try loadBound(from: url, storyId: storyId, contentHash: contentHash) {
            return existing
        }
        guard !pairs.isEmpty else { return nil }
        let exchanges = pairs.enumerated().map { sequence, pair in
            Exchange(
                exchangeId: String(format: "legacy-%08d", sequence),
                userText: pair.0, assistantText: pair.1,
                sequence: sequence, createdAt: 0
            )
        }
        let history = ConversationHistory(
            storyId: storyId, contentHash: contentHash,
            conversationId: conversationId, exchanges: exchanges,
            metadata: ["migrated_from": "save_state_gm_history"]
        )
        try save(history, to: url)
        return history
    }

    public static func delete(_ url: URL) throws {
        if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
        let tmpURL = url.appendingPathExtension("tmp")
        if FileManager.default.fileExists(atPath: tmpURL.path) {
            try FileManager.default.removeItem(at: tmpURL)
        }
    }
}

/// Owns one stream-to-history transaction. Only `completed` commits.
final class ConversationTurnTransaction {
    private let url: URL
    private let storyId: String
    private let contentHash: String
    private let conversationId: String
    private let userText: String
    private let exchangeId: String
    private let createdAt: Double
    private var assistantText = ""
    private var terminal = false

    init(
        url: URL, storyId: String, contentHash: String, conversationId: String,
        userText: String, exchangeId: String, createdAt: Double
    ) {
        self.url = url; self.storyId = storyId; self.contentHash = contentHash
        self.conversationId = conversationId; self.userText = userText
        self.exchangeId = exchangeId; self.createdAt = createdAt
    }

    func accept(_ event: ChunkStreamEvent) throws -> String? {
        guard !terminal else { return nil }
        switch event.eventType {
        case .started:
            return nil
        case .text:
            assistantText += event.text
            return nil
        case .failed, .cancelled:
            terminal = true
            return nil
        case .completed:
            terminal = true
            let answer = assistantText.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !answer.isEmpty else { return nil }
            let sequence = try ConversationHistoryStore.loadBound(
                from: url, storyId: storyId, contentHash: contentHash
            )?.exchangeCount ?? 0
            _ = try ConversationHistoryStore.addExchange(
                Exchange(
                    exchangeId: exchangeId, userText: userText,
                    assistantText: answer, sequence: sequence, createdAt: createdAt
                ),
                to: url, storyId: storyId, contentHash: contentHash,
                conversationId: conversationId
            )
            return answer
        }
    }
}

// MARK: - Crypto helper

extension Data {
    func sha256Hex() -> String {
        var hasher = SHA256()
        hasher.update(data: self)
        let digest = hasher.finalize()
        return digest.compactMap { String(format: "%02x", $0) }.joined()
    }
}

// MARK: - CryptoSwift-compatible SHA256 (built-in)

#if canImport(CryptoKit)
import CryptoKit

private struct SHA256 {
    private var hasher = CryptoKit.SHA256()
    mutating func update(data: Data) { hasher.update(data: data) }
    func finalize() -> CryptoKit.SHA256.Digest { hasher.finalize() }
}
#else
import CommonCrypto

private struct SHA256 {
    private var ctx = CC_SHA256_CTX()
    init() { CC_SHA256_Init(&ctx) }
    mutating func update(data: Data) {
        data.withUnsafeBytes { ptr in
            _ = CC_SHA256_Update(&ctx, ptr.baseAddress, CC_LONG(data.count))
        }
    }
    func finalize() -> [UInt8] {
        var digest = [UInt8](repeating: 0, count: Int(CC_SHA256_DIGEST_LENGTH))
        var mutableCtx = ctx
        _ = digest.withUnsafeMutableBufferPointer { digestPtr in
            CC_SHA256_Final(digestPtr.baseAddress, &mutableCtx)
        }
        return digest
    }
}
#endif
