import Foundation

struct GraphNode: Codable, Identifiable {
    let nodeId: String
    let text: String
    let choices: [Choice]
    let sceneId: String
    let locationId: String
    let participantIds: [String]
    let authoritativeRefs: [String]
    let ending: String?
    var id: String { nodeId }
    var isEnding: Bool { ending != nil }
    var displayLines: [String] { text.split(separator: "\n").map(String.init).filter { !$0.trimmingCharacters(in: .whitespaces).isEmpty } }
    enum CodingKeys: String, CodingKey {
        case nodeId = "node_id", text, choices, sceneId = "scene_id", locationId = "location_id"
        case participantIds = "participant_ids", authoritativeRefs = "authoritative_refs", ending
    }
    init(nodeId: String, text: String, choices: [Choice], sceneId: String = "",
         locationId: String = "", participantIds: [String] = [], authoritativeRefs: [String] = [],
         ending: String? = nil) {
        self.nodeId=nodeId; self.text=text; self.choices=choices; self.sceneId=sceneId
        self.locationId=locationId; self.participantIds=participantIds
        self.authoritativeRefs=authoritativeRefs; self.ending=ending
    }
}

struct Choice: Codable, Identifiable {
    let choiceId: String
    let text: String
    let targetNode: String
    let routeId: String
    let setsFlags, requiresFlags: [String]
    var id: String { choiceId }
    var choiceText: String { text }
    enum CodingKeys: String, CodingKey {
        case choiceId = "choice_id", text, targetNode = "target_node", routeId = "route_id"
        case setsFlags = "sets_flags", requiresFlags = "requires_flags"
    }
    init(choiceId: String, choiceText: String, targetNode: String, setsFlags: [String] = [],
         requiresFlags: [String] = [], routeId: String = "") {
        self.choiceId=choiceId; self.text=choiceText; self.targetNode=targetNode
        self.setsFlags=setsFlags; self.requiresFlags=requiresFlags; self.routeId=routeId
    }
    func isAvailable(activeFlags: Set<String>) -> Bool { requiresFlags.allSatisfy(activeFlags.contains) }
    func isAvailable(activeFlags: [String: Bool]) -> Bool { requiresFlags.allSatisfy { activeFlags[$0] == true } }
}

struct StorySession {
    let nodes: [String: GraphNode]
    var state: SaveState
    var current: GraphNode { nodes[state.currentNode] ?? { fatalError("Unknown node") }() }
    func availableChoices() -> [Choice] { current.choices.filter { $0.isAvailable(activeFlags: Set(state.flags.filter(\.value).map(\.key))) } }
    mutating func choose(_ id: String) throws {
        guard let choice = availableChoices().first(where: { $0.choiceId == id }) else { throw SessionError.unavailable }
        guard nodes[choice.targetNode] != nil else { throw SessionError.missingTarget }
        choice.setsFlags.forEach { state.flags[$0] = true }; state.currentNode = choice.targetNode
        if !state.visitedNodes.contains(choice.targetNode) { state.visitedNodes.append(choice.targetNode) }
    }
    enum SessionError: Error { case unavailable, missingTarget }
}
