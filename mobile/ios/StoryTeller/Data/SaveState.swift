import Foundation

/// Mutable save state for reader progress through a story.
///
/// Persisted as JSON in save/save_state.json.
struct SaveState: Codable {
    var currentNodeId: String = "node_01"
    var visitedNodes: [String] = ["node_01"]
    var flags: Set<String> = []
    var choiceHistory: [String] = []
    var gmHistory: [(question: String, answer: String)] = []
    var bookmarks: Set<String> = []
    var lastSavedAt: Date = Date()
    
    enum CodingKeys: String, CodingKey {
        case currentNodeId, visitedNodes, flags, choiceHistory, gmHistory, bookmarks, lastSavedAt
    }
    
    // MARK: - Persistence
    
    static func load(from saveDir: URL) -> SaveState {
        let file = saveDir.appendingPathComponent("save_state.json")
        guard FileManager.default.fileExists(atPath: file.path),
              let data = try? Data(contentsOf: file)
        else { return SaveState() }
        
        return (try? JSONDecoder().decode(SaveState.self, from: data)) ?? SaveState()
    }
    
    func save(to saveDir: URL) {
        var state = self
        state.lastSavedAt = Date()
        
        try? FileManager.default.createDirectory(at: saveDir, withIntermediateDirectories: true)
        guard let data = try? JSONEncoder().encode(state) else { return }
        try? data.write(to: saveDir.appendingPathComponent("save_state.json"))
    }
    
    // MARK: - Mutations
    
    mutating func visitNode(_ nodeId: String) {
        currentNodeId = nodeId
        if !visitedNodes.contains(nodeId) {
            visitedNodes.append(nodeId)
        }
    }
    
    mutating func makeChoice(_ choice: Choice) {
        choiceHistory.append(choice.choiceId)
        flags.formUnion(choice.setsFlags)
    }
    
    mutating func addGMExchange(question: String, answer: String) {
        gmHistory.append((question, answer))
    }
    
    mutating func toggleBookmark() -> Bool {
        if bookmarks.contains(currentNodeId) {
            bookmarks.remove(currentNodeId)
            return false
        } else {
            bookmarks.insert(currentNodeId)
            return true
        }
    }
    
    mutating func reset() {
        self = SaveState()
    }
}

// MARK: - Codable support for tuples

extension SaveState {
    struct GMExchange: Codable {
        let question: String
        let answer: String
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        currentNodeId = try container.decode(String.self, forKey: .currentNodeId)
        visitedNodes = try container.decode([String].self, forKey: .visitedNodes)
        flags = try container.decode(Set<String>.self, forKey: .flags)
        choiceHistory = try container.decode([String].self, forKey: .choiceHistory)
        bookmarks = try container.decode(Set<String>.self, forKey: .bookmarks)
        lastSavedAt = try container.decode(Date.self, forKey: .lastSavedAt)
        
        let exchanges = try container.decode([GMExchange].self, forKey: .gmHistory)
        gmHistory = exchanges.map { ($0.question, $0.answer) }
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(currentNodeId, forKey: .currentNodeId)
        try container.encode(visitedNodes, forKey: .visitedNodes)
        try container.encode(flags, forKey: .flags)
        try container.encode(choiceHistory, forKey: .choiceHistory)
        try container.encode(bookmarks, forKey: .bookmarks)
        try container.encode(lastSavedAt, forKey: .lastSavedAt)
        try container.encode(gmHistory.map { GMExchange(question: $0.question, answer: $0.answer) }, forKey: .gmHistory)
    }
}
