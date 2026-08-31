import CryptoKit
import Foundation

struct KnowledgeReadCounters: Equatable {
    let bytesRead: Int
    let chunksOpened: Int
    let recordsDecoded: Int
}

struct KnowledgeRead {
    let excerpts: [KnowledgeEntry]
    let counters: KnowledgeReadCounters
}

private struct KnowledgeLocator {
    let entryId: String
    let tokens: Set<String>
    let revealAfterNodes: Set<String>
    let path: String
    let sha256: String
    let sizeBytes: Int
}

/// Bounded content-addressed reader for the v2 narrative/knowledge namespace.
struct DirectoryKnowledgeSource {
    private let root: URL
    private let locators: [KnowledgeLocator]

    init(root: URL) throws {
        self.root = root.standardizedFileURL
        let data = try Data(contentsOf: root.appendingPathComponent("index.json"))
        guard let raw = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let entries = raw["entries"] as? [[String: Any]] else {
            throw KnowledgeSourceError.invalid("KNOWLEDGE_INDEX_FORMAT")
        }
        var parsed: [KnowledgeLocator] = []
        for item in entries {
            guard let entryId = item["entry_id"] as? String,
                  let tokens = item["tokens"] as? [String],
                  let reveal = item["reveal_after_nodes"] as? [String],
                  let path = item["path"] as? String,
                  let sha256 = item["sha256"] as? String,
                  let sizeBytes = item["size_bytes"] as? Int,
                  tokens == Array(Set(tokens)).sorted(),
                  reveal == Array(Set(reveal)).sorted(),
                  !path.hasPrefix("/"), !path.contains("\\"),
                  path.split(separator: "/", omittingEmptySubsequences: false)
                    .allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }),
                  sha256.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil,
                  sizeBytes >= 0 else {
                throw KnowledgeSourceError.invalid("KNOWLEDGE_INDEX_ENTRY")
            }
            parsed.append(KnowledgeLocator(
                entryId: entryId, tokens: Set(tokens), revealAfterNodes: Set(reveal),
                path: path, sha256: sha256, sizeBytes: sizeBytes
            ))
        }
        parsed.sort { $0.entryId < $1.entryId }
        guard Set(parsed.map(\.entryId)).count == parsed.count else {
            throw KnowledgeSourceError.invalid("KNOWLEDGE_INDEX_DUPLICATE_ID")
        }
        locators = parsed
    }

    func read(
        entryIds: Set<String> = [],
        queryTokens: Set<String> = [],
        visitedNodes: Set<String> = [],
        maxRecords: Int,
        maxExcerptBytes: Int
    ) throws -> KnowledgeRead {
        guard maxRecords >= 0, maxExcerptBytes >= 0 else {
            throw KnowledgeSourceError.invalid("knowledge bounds must be non-negative")
        }
        var excerpts: [KnowledgeEntry] = []
        var bytesRead = 0
        var chunksOpened = 0
        var recordsDecoded = 0
        for locator in locators {
            if excerpts.count == maxRecords { break }
            if !entryIds.isEmpty, !entryIds.contains(locator.entryId) { continue }
            if !queryTokens.isEmpty, locator.tokens.isDisjoint(with: queryTokens) { continue }
            if !locator.revealAfterNodes.isSubset(of: visitedNodes) { continue }
            if bytesRead + locator.sizeBytes > maxExcerptBytes { continue }
            let file = root.appendingPathComponent(locator.path).standardizedFileURL
            guard file.path.hasPrefix(root.path + "/") else {
                throw KnowledgeSourceError.invalid("KNOWLEDGE_CHUNK_PATH")
            }
            let declaredSize = try file.resourceValues(forKeys: [.fileSizeKey]).fileSize
            guard declaredSize == locator.sizeBytes else {
                throw KnowledgeSourceError.invalid("KNOWLEDGE_CHUNK_SIZE")
            }
            let payload = try Data(contentsOf: file, options: .mappedIfSafe)
            chunksOpened += 1
            bytesRead += payload.count
            guard SHA256.hash(data: payload).map({ String(format: "%02x", $0) }).joined() == locator.sha256 else {
                throw KnowledgeSourceError.invalid("KNOWLEDGE_CHUNK_HASH")
            }
            guard let item = try JSONSerialization.jsonObject(with: payload) as? [String: Any],
                  let entry = Self.entry(item) else {
                throw KnowledgeSourceError.invalid("KNOWLEDGE_CHUNK_FORMAT")
            }
            recordsDecoded += 1
            guard entry.entryId == locator.entryId else {
                throw KnowledgeSourceError.invalid("KNOWLEDGE_CHUNK_ID")
            }
            guard Set(entry.revealAfterNodes) == locator.revealAfterNodes else {
                throw KnowledgeSourceError.invalid("KNOWLEDGE_CHUNK_REVEAL")
            }
            excerpts.append(entry)
        }
        return KnowledgeRead(
            excerpts: excerpts,
            counters: KnowledgeReadCounters(
                bytesRead: bytesRead, chunksOpened: chunksOpened, recordsDecoded: recordsDecoded
            )
        )
    }

    private static func entry(_ item: [String: Any]) -> KnowledgeEntry? {
        guard let entryId = item["entry_id"] as? String,
              let kind = item["kind"] as? String,
              let text = item["normalized_text"] as? String,
              let sources = item["source_ids"] as? [String],
              let incoming = item["incoming_refs"] as? [String],
              let outgoing = item["outgoing_refs"] as? [String],
              let reveal = item["reveal_after_nodes"] as? [String] else { return nil }
        return KnowledgeEntry(
            entryId: entryId, kind: kind, normalizedText: text, sourceIds: sources,
            incomingRefs: incoming, outgoingRefs: outgoing, revealAfterNodes: reveal
        )
    }
}

private enum KnowledgeSourceError: Error {
    case invalid(String)
}
