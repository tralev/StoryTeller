import Foundation

/// Game Master keyword index for context-aware question answering.
///
/// Provides keyword lookup and spoiler-gated entity retrieval.
struct GmIndex {
    let keywords: [String: [String]]
    let entityCache: [String: EntitySummary]
    
    init(from raw: [String: Any] = [:]) {
        self.keywords = raw["keywords"] as? [String: [String]] ?? [:]
        
        var cache: [String: EntitySummary] = [:]
        if let entities = raw["entity_cache"] as? [String: [String: Any]] {
            for (id, data) in entities {
                let summary = EntitySummary(
                    entityId: id,
                    entityType: data["entity_type"] as? String ?? "unknown",
                    name: data["name"] as? String ?? id,
                    aliases: data["aliases"] as? [String] ?? [],
                    summary: data["summary"] as? String ?? "",
                    nodeIds: data["node_ids"] as? [String] ?? [],
                    revealAfterNode: data["reveal_after_node"] as? String
                )
                cache[id] = summary
            }
        }
        self.entityCache = cache
    }
    
    /// Look up entities relevant to a question, gated by visited nodes.
    func lookup(query: String, visitedNodes: Set<String>) -> [EntitySummary] {
        let q = query.lowercased()
        var matchedIds = Set<String>()
        
        // Match by keyword
        for (keyword, nodeIds) in keywords {
            if q.contains(keyword.lowercased()) {
                for nodeId in nodeIds {
                    entityCache.values
                        .filter { $0.nodeIds.contains(nodeId) }
                        .forEach { matchedIds.insert($0.entityId) }
                }
            }
        }
        
        // Match by name/alias directly
        for (id, entity) in entityCache {
            if q.contains(entity.name.lowercased()) ||
               entity.aliases.contains(where: { q.contains($0.lowercased()) }) {
                matchedIds.insert(id)
            }
        }
        
        // Spoiler gate + limit
        return Array(matchedIds
            .compactMap { entityCache[$0] }
            .filter { entity in
                entity.revealAfterNode == nil || visitedNodes.contains(entity.revealAfterNode!)
            }
            .prefix(5))
    }
    
    func formatForPrompt(_ entities: [EntitySummary]) -> String {
        entities.map { entity in
            "[\(entity.entityId)] \(entity.name) (\(entity.entityType)): \(entity.summary)"
        }.joined(separator: "\n")
    }
}

struct EntitySummary: Codable {
    let entityId: String
    let entityType: String
    let name: String
    let aliases: [String]
    let summary: String
    let nodeIds: [String]
    let revealAfterNode: String?
}
