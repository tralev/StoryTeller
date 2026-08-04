import XCTest
@testable import StoryTellerLib

final class GmIndexTests: XCTestCase {

    let sampleRaw: [String: Any] = [
        "keywords": [
            "Elena": ["node_01", "node_02"],
            "crystal": ["node_01", "node_05"],
            "spire": ["node_01"],
        ],
        "entity_cache": [
            "char_01": [
                "entity_type": "character",
                "name": "Elena Brightblade",
                "aliases": ["The Accord Bearer"],
                "summary": "A young knight sworn to unite the fractured kingdoms.",
                "node_ids": ["node_01", "node_02", "node_03"],
            ] as [String: Any],
            "char_02": [
                "entity_type": "character",
                "name": "Thorn Ironveil",
                "aliases": ["The Warden"],
                "summary": "An aging dwarf warden guarding the High Pass.",
                "node_ids": ["node_03", "node_04"],
                "reveal_after_node": "node_03",
            ] as [String: Any],
            "loc_01": [
                "entity_type": "location",
                "name": "High Pass",
                "aliases": ["The Pass"],
                "summary": "A narrow mountain pass leading to the Crystal Spire.",
                "node_ids": ["node_01"],
            ] as [String: Any],
        ],
    ]

    func testLookupByKeyword() {
        let index = GmIndex(from: sampleRaw)
        let results = index.lookup(query: "Who is Elena?", visitedNodes: ["node_01"])
        XCTAssertEqual(results.count, 1)
        XCTAssertEqual(results.first?.entityId, "char_01")
    }

    func testLookupByName() {
        let index = GmIndex(from: sampleRaw)
        let results = index.lookup(query: "Tell me about Thorn Ironveil", visitedNodes: ["node_01", "node_03"])
        XCTAssertEqual(results.count, 1)
        XCTAssertEqual(results.first?.entityId, "char_02")
    }

    func testLookupByAlias() {
        let index = GmIndex(from: sampleRaw)
        let results = index.lookup(query: "Who is the Accord Bearer?", visitedNodes: ["node_01"])
        XCTAssertEqual(results.count, 1)
        XCTAssertEqual(results.first?.entityId, "char_01")
    }

    func testSpoilerGateHidesBeforeReveal() {
        let index = GmIndex(from: sampleRaw)
        let results = index.lookup(query: "Tell me about Thorn", visitedNodes: ["node_01"])
        XCTAssertFalse(results.contains { $0.entityId == "char_02" })
    }

    func testSpoilerGateShowsAfterReveal() {
        let index = GmIndex(from: sampleRaw)
        let results = index.lookup(query: "Tell me about Thorn", visitedNodes: ["node_01", "node_03"])
        XCTAssertTrue(results.contains { $0.entityId == "char_02" })
    }

    func testEmptyQuery() {
        let index = GmIndex(from: sampleRaw)
        XCTAssertTrue(index.lookup(query: "", visitedNodes: ["node_01"]).isEmpty)
    }

    func testUnknownQuery() {
        let index = GmIndex(from: sampleRaw)
        XCTAssertTrue(index.lookup(query: "zzzblarg", visitedNodes: ["node_01"]).isEmpty)
    }

    func testCaseInsensitive() {
        let index = GmIndex(from: sampleRaw)
        let results = index.lookup(query: "ELENA", visitedNodes: ["node_01"])
        XCTAssertEqual(results.count, 1)
    }

    func testFormatForPrompt() {
        let index = GmIndex(from: sampleRaw)
        let entities = [
            EntitySummary(entityId: "char_01", entityType: "character", name: "Elena", aliases: [], summary: "A knight.", nodeIds: ["node_01"], revealAfterNode: nil),
            EntitySummary(entityId: "loc_01", entityType: "location", name: "High Pass", aliases: [], summary: "A pass.", nodeIds: ["node_01"], revealAfterNode: nil),
        ]
        let formatted = index.formatForPrompt(entities)
        XCTAssertTrue(formatted.contains("[char_01]"))
        XCTAssertTrue(formatted.contains("A knight."))
    }

    func testEmptyIndex() {
        let empty = GmIndex()
        XCTAssertTrue(empty.lookup(query: "anything", visitedNodes: ["node_01"]).isEmpty)
        XCTAssertEqual(empty.formatForPrompt([]), "")
    }
}
