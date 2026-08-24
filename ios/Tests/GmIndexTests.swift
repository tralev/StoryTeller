import XCTest
@testable import StoryTellerLib

final class GmIndexTests: XCTestCase {
    private var root: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
    }

    func testSharedRetrievalScenariosProduceExactOrderedIDs() throws {
        let data = try Data(contentsOf: root.appendingPathComponent("tests/fixtures/gm_retrieval/catalog.json"))
        let catalog = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        let index = GmIndex(from: ["entries": catalog["entries"] as! [[String: Any]]])
        var outcomes: [String: Any] = [:]
        for scenario in catalog["scenarios"] as! [[String: Any]] {
            let ids = index.retrieve(
                query: scenario["query"] as! String,
                visitedNodes: Set(scenario["visited_nodes"] as! [String]),
                contextBudgetBytes: scenario["context_budget_bytes"] as! Int,
                maxResults: scenario["max_results"] as! Int,
                currentNodeId: scenario["current_node_id"] as? String,
                visitedRefs: Set(scenario["visited_refs"] as? [String] ?? [])
            ).map(\.entry.entryId)
            XCTAssertEqual(ids, scenario["expected_ids"] as! [String], scenario["id"] as! String)
            outcomes[scenario["id"] as! String] = ids
        }
        let output = root.appendingPathComponent("tmp/contracts/gm-ios.json")
        try FileManager.default.createDirectory(at: output.deletingLastPathComponent(), withIntermediateDirectories: true)
        try JSONSerialization.data(withJSONObject: ["format": "storyteller.gm-retrieval-results.v1", "scenarios": outcomes], options: [.sortedKeys]).write(to: output, options: .atomic)
    }

    func testNormalizationAndContextBytesAreBounded() {
        XCTAssertEqual(GmIndex.normalize("  Who—is ÉLENA?!  "), "who is élena")
        let entry = KnowledgeEntry(entryId: "entry", kind: "kind", normalizedText: "éastern gate", sourceIds: [], incomingRefs: [], outgoingRefs: [], revealAfterNodes: [])
        XCTAssertTrue(GmIndex(entries: [entry]).retrieve(query: "éastern", visitedNodes: [], contextBudgetBytes: 10).isEmpty)
    }

    func testRevealGateRemovesHiddenIdentifiersSourcesAndTextBeforePrompt() {
        let hidden = KnowledgeEntry(
            entryId: "SENTINEL_HIDDEN_ID", kind: "event", normalizedText: "SENTINEL HIDDEN TEXT",
            sourceIds: ["SENTINEL_HIDDEN_SOURCE"], incomingRefs: [], outgoingRefs: [],
            revealAfterNodes: ["node_reveal"]
        )
        let visible = KnowledgeEntry(
            entryId: "visible", kind: "event", normalizedText: "public event",
            sourceIds: [], incomingRefs: [], outgoingRefs: [], revealAfterNodes: []
        )
        let eligible = RevealGate.eligible([hidden, visible], visitedNodes: [])
        let index = GmIndex(entries: [hidden, visible])
        let prompt = index.formatForPrompt(index.lookup(query: "sentinel hidden", visitedNodes: []))

        XCTAssertEqual(eligible, [visible])
        for sentinel in [hidden.entryId, hidden.normalizedText] + hidden.sourceIds {
            XCTAssertFalse(String(describing: eligible).contains(sentinel))
            XCTAssertFalse(prompt.contains(sentinel))
        }
        XCTAssertEqual(RevealGate.eligible([hidden, visible], visitedNodes: ["node_reveal"]), [hidden, visible])
    }
}
