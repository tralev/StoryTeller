import XCTest
@testable import StoryTellerLib

final class SaveStateTests: XCTestCase {

    func testDefaultState() {
        let state = SaveState()
        XCTAssertEqual(state.currentNodeId, "node_01")
        XCTAssertTrue(state.visitedNodes.contains("node_01"))
    }

    func testVisitNode() {
        var state = SaveState()
        state.visitNode("node_05")
        XCTAssertEqual(state.currentNodeId, "node_05")
        XCTAssertTrue(state.visitedNodes.contains("node_05"))
        XCTAssertEqual(state.visitedNodes.count, 2)
    }

    func testVisitNodeNoDuplicates() {
        var state = SaveState()
        state.visitNode("node_01")
        XCTAssertEqual(state.visitedNodes.count, 1)
    }

    func testMakeChoice() {
        var state = SaveState()
        let choice = Choice(choiceId: "ch_01_a", choiceText: "Go north", targetNode: "node_02", setsFlags: ["chose_north"], requiresFlags: [])
        state.makeChoice(choice)
        XCTAssertTrue(state.choiceHistory.contains("ch_01_a"))
        XCTAssertTrue(state.flags.contains("chose_north"))
    }

    func testAddGMExchange() {
        var state = SaveState()
        state.addGMExchange(question: "Who is Elena?", answer: "A brave knight.")
        XCTAssertEqual(state.gmHistory.count, 1)
        XCTAssertEqual(state.gmHistory[0].question, "Who is Elena?")
        XCTAssertEqual(state.gmHistory[0].answer, "A brave knight.")
    }

    func testToggleBookmark() {
        var state = SaveState()
        XCTAssertTrue(state.toggleBookmark()) // add
        XCTAssertTrue(state.bookmarks.contains("node_01"))
        XCTAssertFalse(state.toggleBookmark()) // remove
        XCTAssertFalse(state.bookmarks.contains("node_01"))
    }

    func testReset() {
        var state = SaveState()
        state.visitNode("node_05")
        state.makeChoice(Choice(choiceId: "c1", choiceText: "go", targetNode: "node_06", setsFlags: ["flag1"], requiresFlags: []))
        state.reset()
        XCTAssertEqual(state.currentNodeId, "node_01")
        XCTAssertEqual(state.visitedNodes.count, 1)
        XCTAssertTrue(state.flags.isEmpty)
    }

    func testCodableRoundTrip() throws {
        var state = SaveState()
        state.visitNode("node_03")
        state.makeChoice(Choice(choiceId: "c1", choiceText: "go", targetNode: "node_04", setsFlags: ["flag1"], requiresFlags: []))
        state.addGMExchange(question: "q?", answer: "a!")
        _ = state.toggleBookmark()

        let data = try JSONEncoder().encode(state)
        let restored = try JSONDecoder().decode(SaveState.self, from: data)

        XCTAssertEqual(state.currentNodeId, restored.currentNodeId)
        XCTAssertEqual(state.visitedNodes, restored.visitedNodes)
        XCTAssertEqual(state.flags, restored.flags)
        XCTAssertEqual(state.gmHistory.count, restored.gmHistory.count)
        XCTAssertTrue(restored.bookmarks.contains("node_01"))
    }

    func testSaveLoadDisk() throws {
        let tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("storyteller_test_\(UUID().uuidString)")
        let saveDir = tmpDir.appendingPathComponent("save")
        try FileManager.default.createDirectory(at: saveDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        var state = SaveState()
        state.visitNode("node_02")
        state.save(to: saveDir)

        let loaded = SaveState.load(from: saveDir)
        XCTAssertEqual(loaded.currentNodeId, "node_02")
        XCTAssertEqual(loaded.visitedNodes.count, 2)
    }

    func testLoadNonexistentReturnsDefault() {
        let loaded = SaveState.load(from: URL(fileURLWithPath: "/nonexistent/save"))
        XCTAssertEqual(loaded.currentNodeId, "node_01")
    }
}
