import Foundation

struct KnowledgeEntry: Codable, Equatable {
    let entryId: String
    let kind: String
    let normalizedText: String
    let sourceIds: [String]
    let incomingRefs: [String]
    let outgoingRefs: [String]
    let revealAfterNodes: [String]
}

struct KnowledgeHit: Equatable {
    let entry: KnowledgeEntry
    let score: Int
    let promptLine: String
}

/// Spoiler-security boundary. Rejected entries must not be logged or diagnosed.
enum RevealGate {
    static func eligible(_ entries: [KnowledgeEntry], visitedNodes: Set<String>) -> [KnowledgeEntry] {
        entries.filter { entry in
            entry.revealAfterNodes.isEmpty || Set(entry.revealAfterNodes).isSubset(of: visitedNodes)
        }
    }
}

/// Deterministic v2 GM retrieval; algorithm is mirrored in Python and Kotlin.
struct GmIndex {
    static let defaultContextBudgetBytes = 4096
    static let defaultMaxResults = 8
    let entries: [KnowledgeEntry]

    init(entries: [KnowledgeEntry] = []) { self.entries = entries }

    init(from raw: [String: Any] = [:]) {
        if let values = raw["entries"] as? [[String: Any]] {
            entries = values.compactMap(Self.parseEntry)
            return
        }
        // Temporary parser compatibility for pre-v2 unit data; all matching
        // still goes through the canonical entry algorithm.
        let cache = raw["entity_cache"] as? [String: [String: Any]] ?? [:]
        entries = cache.map { id, data in
            let pieces = [data["name"] as? String ?? id]
                + (data["aliases"] as? [String] ?? []) + [data["summary"] as? String ?? ""]
            return KnowledgeEntry(
                entryId: id, kind: data["entity_type"] as? String ?? "unknown",
                normalizedText: pieces.joined(separator: " "), sourceIds: [], incomingRefs: [], outgoingRefs: [],
                revealAfterNodes: (data["reveal_after_node"] as? String).map { [$0] } ?? []
            )
        }
    }

    func retrieve(
        query: String,
        visitedNodes: Set<String>,
        contextBudgetBytes: Int = Self.defaultContextBudgetBytes,
        maxResults: Int = Self.defaultMaxResults
    ) -> [KnowledgeHit] {
        precondition(contextBudgetBytes >= 0 && maxResults >= 0, "retrieval budgets must be non-negative")
        let normalized = Self.normalize(query)
        let queryTokens = Self.tokens(query)
        guard !normalized.isEmpty, !queryTokens.isEmpty, contextBudgetBytes > 0, maxResults > 0 else { return [] }

        let ranked: [(Int, KnowledgeEntry)] = RevealGate.eligible(entries, visitedNodes: visitedNodes).compactMap { entry in
            let searchable = Self.normalize(([entry.kind, entry.normalizedText] + entry.sourceIds).joined(separator: " "))
            let searchableTokens = Set(searchable.split(separator: " ").map(String.init))
            var score = 100 * queryTokens.filter(searchableTokens.contains).count
            if searchable.contains(normalized) { score += 500 }
            return score == 0 ? nil : (score, entry)
        }.sorted { lhs, rhs in lhs.0 != rhs.0 ? lhs.0 > rhs.0 : lhs.1.entryId < rhs.1.entryId }

        var remaining = contextBudgetBytes
        var selected: [KnowledgeHit] = []
        for (score, entry) in ranked {
            let line = "[\(entry.entryId)] (\(entry.kind)) \(entry.normalizedText)"
            let cost = line.lengthOfBytes(using: .utf8) + (selected.isEmpty ? 0 : 1)
            guard cost <= remaining else { continue }
            selected.append(KnowledgeHit(entry: entry, score: score, promptLine: line))
            remaining -= cost
            if selected.count == maxResults { break }
        }
        return selected
    }

    func lookup(query: String, visitedNodes: Set<String>) -> [KnowledgeEntry] {
        retrieve(query: query, visitedNodes: visitedNodes).map(\.entry)
    }

    func promptContext(query: String, visitedNodes: Set<String>) -> String {
        retrieve(query: query, visitedNodes: visitedNodes).map(\.promptLine).joined(separator: "\n")
    }

    func formatForPrompt(_ entries: [KnowledgeEntry]) -> String {
        entries.map { "[\($0.entryId)] (\($0.kind)) \($0.normalizedText)" }.joined(separator: "\n")
    }

    static func normalize(_ value: String) -> String {
        value.precomposedStringWithCompatibilityMapping
            .lowercased(with: Locale(identifier: "en_US_POSIX"))
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    static func tokens(_ value: String) -> [String] { Array(Set(normalize(value).split(separator: " ").map(String.init))).sorted() }

    private static func parseEntry(_ data: [String: Any]) -> KnowledgeEntry? {
        guard let id = data["entry_id"] as? String ?? data["knowledge_id"] as? String else { return nil }
        return KnowledgeEntry(
            entryId: id, kind: data["kind"] as? String ?? "unknown",
            normalizedText: data["normalized_text"] as? String ?? "",
            sourceIds: data["source_ids"] as? [String] ?? [], incomingRefs: data["incoming_refs"] as? [String] ?? [],
            outgoingRefs: data["outgoing_refs"] as? [String] ?? [], revealAfterNodes: data["reveal_after_nodes"] as? [String] ?? []
        )
    }
}
