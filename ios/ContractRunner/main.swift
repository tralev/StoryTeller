import Foundation

struct Scenario: Decodable {
    let id: String
    let path: String
    let accepted: Bool
    let issueCode: String?
    let currentNodeId: String?
    enum CodingKeys: String, CodingKey {
        case id, path, accepted, issueCode = "issue_code", currentNodeId = "current_node_id"
    }
}
struct Catalog: Decodable { let scenarios: [Scenario] }

let arguments = CommandLine.arguments
guard arguments.count == 3 else {
    fatalError("usage: storyteller-contract-runner PROJECT_ROOT OUTPUT_JSON")
}
let root = URL(fileURLWithPath: arguments[1], isDirectory: true)
let fixtures = root.appendingPathComponent("tests/fixtures/v2")
let catalog = try JSONDecoder().decode(
    Catalog.self,
    from: Data(contentsOf: fixtures.appendingPathComponent("catalog.json"))
)
var outcomes: [String: Any] = [:]
for scenario in catalog.scenarios {
    let result = V2PackageValidator.validate(fixtures.appendingPathComponent(scenario.path))
    precondition(result.accepted == scenario.accepted, "\(scenario.id): acceptance mismatch")
    let expectedCodes = scenario.issueCode.map { [$0] } ?? []
    precondition(result.issueCodes == expectedCodes, "\(scenario.id): issue-code mismatch")
    outcomes[scenario.id] = [
        "outcome": result.accepted ? "accepted" : "invalid",
        "issue_codes": result.issueCodes,
    ]
    if scenario.id == "complete", let manifest = result.manifest {
        precondition(manifest.storyId.range(of: #"^story_[0-9a-f]{32}$"#, options: .regularExpression) != nil)
        precondition(manifest.entryNode.range(of: #"^node_[0-9a-f]{32}$"#, options: .regularExpression) != nil)
        let ids = Set(manifest.artifacts.map(\.artifactId))
        precondition(ids.count == manifest.artifacts.count)
        precondition(manifest.artifacts.contains { $0.path == "world/index.json" })
        precondition(manifest.artifacts.contains { $0.path.contains("/chunks/") })
        precondition(manifest.artifacts.allSatisfy { $0.dependsOn.allSatisfy(ids.contains) })
    }
}
let document: [String: Any] = [
    "format": "storyteller.contract-results.v2",
    "scenarios": outcomes,
]
let output = URL(fileURLWithPath: arguments[2])
try FileManager.default.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
try JSONSerialization.data(withJSONObject: document, options: [.sortedKeys]).write(to: output, options: .atomic)
print("validated \(catalog.scenarios.count) iOS player scenarios")

let gmCatalogURL = root.appendingPathComponent("tests/fixtures/gm_retrieval/catalog.json")
let gmRaw = try JSONSerialization.jsonObject(with: Data(contentsOf: gmCatalogURL)) as! [String: Any]
let gmIndex = GmIndex(from: ["entries": gmRaw["entries"] as! [[String: Any]]])
var gmOutcomes: [String: Any] = [:]
for scenario in gmRaw["scenarios"] as! [[String: Any]] {
    let ids = gmIndex.retrieve(
        query: scenario["query"] as! String,
        visitedNodes: Set(scenario["visited_nodes"] as! [String]),
        contextBudgetBytes: scenario["context_budget_bytes"] as! Int,
        maxResults: scenario["max_results"] as! Int,
        currentNodeId: scenario["current_node_id"] as? String,
        visitedRefs: Set(scenario["visited_refs"] as? [String] ?? [])
    ).map(\.entry.entryId)
    precondition(ids == scenario["expected_ids"] as! [String], "\(scenario["id"]!): GM retrieval mismatch")
    gmOutcomes[scenario["id"] as! String] = ids
}
let gmDocument: [String: Any] = [
    "format": "storyteller.gm-retrieval-results.v1",
    "scenarios": gmOutcomes,
]
let gmOutput = output.deletingLastPathComponent().appendingPathComponent("gm-ios.json")
try JSONSerialization.data(withJSONObject: gmDocument, options: [.sortedKeys]).write(to: gmOutput, options: .atomic)
print("validated \((gmRaw["scenarios"] as! [[String: Any]]).count) iOS GM retrieval scenarios")

let hidden = KnowledgeEntry(
    entryId: "SENTINEL_HIDDEN_ID", kind: "event", normalizedText: "SENTINEL HIDDEN TEXT",
    sourceIds: ["SENTINEL_HIDDEN_SOURCE"], incomingRefs: [], outgoingRefs: [],
    revealAfterNodes: ["node_reveal"]
)
let visible = KnowledgeEntry(
    entryId: "visible", kind: "event", normalizedText: "public event",
    sourceIds: [], incomingRefs: [], outgoingRefs: [], revealAfterNodes: []
)
let gated = RevealGate.eligible([hidden, visible], visitedNodes: [])
let hiddenPrompt = GmIndex(entries: [hidden, visible]).promptContext(
    query: "sentinel hidden", visitedNodes: []
)
precondition(gated == [visible], "reveal gate admitted a hidden candidate")
for sentinel in [hidden.entryId, hidden.normalizedText] + hidden.sourceIds {
    precondition(!String(describing: gated).contains(sentinel), "reveal gate leaked hidden candidate data")
    precondition(!hiddenPrompt.contains(sentinel), "prompt leaked hidden candidate data")
}
print("validated iOS pre-prompt reveal boundary")
