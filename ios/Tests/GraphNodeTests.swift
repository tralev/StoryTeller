import XCTest
@testable import StoryTellerLib

final class GraphNodeTests: XCTestCase {

    func testDisplayLines() {
        let node = GraphNode(
            nodeId: "node_01", chapter: 1, sceneType: "narrative",
            text: "Line one.\nLine two.\n  \nLine three.",
            choices: [],
            presentCharacters: [], presentLocation: nil, presentCreatures: [],
            mood: "", isEnding: false
        )
        XCTAssertEqual(node.displayLines, ["Line one.", "Line two.", "Line three."])
    }

    func testChoiceAvailableWithoutRequires() {
        let choice = Choice(choiceId: "ch", choiceText: "Go", targetNode: "node_02")
        XCTAssertTrue(choice.isAvailable(activeFlags: []))
    }

    func testChoiceAvailableSatisfied() {
        let choice = Choice(choiceId: "ch", choiceText: "Go", targetNode: "node_02",
                            setsFlags: [], requiresFlags: ["flag1"])
        XCTAssertTrue(choice.isAvailable(activeFlags: ["flag1", "flag2"]))
    }

    func testChoiceAvailableUnsatisfied() {
        let choice = Choice(choiceId: "ch", choiceText: "Go", targetNode: "node_02",
                            setsFlags: [], requiresFlags: ["flag1"])
        XCTAssertFalse(choice.isAvailable(activeFlags: ["flag2"]))
    }

    func testIsEnding() {
        let normal = GraphNode(nodeId: "n", chapter: 1, sceneType: "x", text: "t", choices: [],
                               presentCharacters: [], presentLocation: nil, presentCreatures: [],
                               mood: "", isEnding: false)
        XCTAssertFalse(normal.isEnding)

        let ending = GraphNode(nodeId: "e", chapter: 1, sceneType: "x", text: "t", choices: [],
                               presentCharacters: [], presentLocation: nil, presentCreatures: [],
                               mood: "", isEnding: true)
        XCTAssertTrue(ending.isEnding)
    }

    func testDecodeFromJSON() throws {
        let json = """
        {
            "node_id": "node_01",
            "chapter": 1,
            "scene_type": "exploration",
            "text": "The pass splits.\\nTwo paths.\\nChoose wisely.",
            "choices": [
                {
                    "choice_id": "ch_01_a",
                    "choice_text": "Go north",
                    "target_node": "node_02",
                    "sets_flags": ["chose_north"]
                }
            ],
            "present_characters": ["char_01"],
            "present_location": "loc_01",
            "present_creatures": [],
            "mood": "determined",
            "is_ending": false
        }
        """.data(using: .utf8)!

        let node = try JSONDecoder().decode(GraphNode.self, from: json)
        XCTAssertEqual(node.nodeId, "node_01")
        XCTAssertEqual(node.chapter, 1)
        XCTAssertEqual(node.choices.count, 1)
        XCTAssertEqual(node.choices[0].choiceId, "ch_01_a")
        XCTAssertFalse(node.isEnding)
    }
}
