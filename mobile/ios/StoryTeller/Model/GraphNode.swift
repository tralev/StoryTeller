import Foundation

/// A single node in the CYOA branching graph.
struct GraphNode: Codable, Identifiable {
    let nodeId: String
    let chapter: Int
    let sceneType: String
    let text: String
    let choices: [Choice]
    let presentCharacters: [String]
    let presentLocation: String?
    let presentCreatures: [String]
    let mood: String
    let isEnding: Bool
    
    var id: String { nodeId }
    
    var displayLines: [String] {
        text.components(separatedBy: "\n").filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty }
    }
    
    enum CodingKeys: String, CodingKey {
        case nodeId = "node_id"
        case chapter
        case sceneType = "scene_type"
        case text
        case choices
        case presentCharacters = "present_characters"
        case presentLocation = "present_location"
        case presentCreatures = "present_creatures"
        case mood
        case isEnding
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        nodeId = try container.decode(String.self, forKey: .nodeId)
        chapter = try container.decodeIfPresent(Int.self, forKey: .chapter) ?? 1
        sceneType = try container.decodeIfPresent(String.self, forKey: .sceneType) ?? "narrative"
        text = try container.decodeIfPresent(String.self, forKey: .text) ?? ""
        choices = try container.decodeIfPresent([Choice].self, forKey: .choices) ?? []
        presentCharacters = try container.decodeIfPresent([String].self, forKey: .presentCharacters) ?? []
        presentLocation = try container.decodeIfPresent(String.self, forKey: .presentLocation)
        presentCreatures = try container.decodeIfPresent([String].self, forKey: .presentCreatures) ?? []
        mood = try container.decodeIfPresent(String.self, forKey: .mood) ?? ""
        isEnding = { () -> Bool in
            if let raw = try? container.decode([String: Bool].self, forKey: .isEnding) {
                return raw["is_ending"] ?? false
            }
            return try container.decodeIfPresent(Bool.self, forKey: .isEnding) ?? false
        }()
    }
    
    init(nodeId: String, chapter: Int, sceneType: String, text: String, choices: [Choice],
         presentCharacters: [String], presentLocation: String?, presentCreatures: [String],
         mood: String, isEnding: Bool) {
        self.nodeId = nodeId
        self.chapter = chapter
        self.sceneType = sceneType
        self.text = text
        self.choices = choices
        self.presentCharacters = presentCharacters
        self.presentLocation = presentLocation
        self.presentCreatures = presentCreatures
        self.mood = mood
        self.isEnding = isEnding
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(nodeId, forKey: .nodeId)
        try container.encode(chapter, forKey: .chapter)
        try container.encode(sceneType, forKey: .sceneType)
        try container.encode(text, forKey: .text)
        try container.encode(choices, forKey: .choices)
        try container.encode(presentCharacters, forKey: .presentCharacters)
        try container.encode(presentLocation, forKey: .presentLocation)
        try container.encode(presentCreatures, forKey: .presentCreatures)
        try container.encode(mood, forKey: .mood)
        try container.encode(isEnding, forKey: .isEnding)
    }
}

/// A choice the reader can make at a node.
struct Choice: Codable, Identifiable {
    let choiceId: String
    let choiceText: String
    let targetNode: String
    let setsFlags: [String]
    let requiresFlags: [String]
    
    var id: String { choiceId }
    
    enum CodingKeys: String, CodingKey {
        case choiceId = "choice_id"
        case choiceText = "choice_text"
        case targetNode = "target_node"
        case setsFlags = "sets_flags"
        case requiresFlags = "requires_flags"
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        choiceId = try container.decode(String.self, forKey: .choiceId)
        choiceText = try container.decode(String.self, forKey: .choiceText)
        targetNode = try container.decode(String.self, forKey: .targetNode)
        setsFlags = try container.decodeIfPresent([String].self, forKey: .setsFlags) ?? []
        requiresFlags = try container.decodeIfPresent([String].self, forKey: .requiresFlags) ?? []
    }
    
    init(choiceId: String, choiceText: String, targetNode: String, setsFlags: [String], requiresFlags: [String]) {
        self.choiceId = choiceId
        self.choiceText = choiceText
        self.targetNode = targetNode
        self.setsFlags = setsFlags
        self.requiresFlags = requiresFlags
    }
    
    func isAvailable(activeFlags: Set<String>) -> Bool {
        requiresFlags.allSatisfy { activeFlags.contains($0) }
    }
}
