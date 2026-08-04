import XCTest
@testable import StoryTellerLib

final class StoryRepositoryTests: XCTestCase {

    var story: StoryPackage!
    var tmpDir: URL!

    override func setUp() {
        super.setUp()
        tmpDir = FileManager.default.temporaryDirectory.appendingPathComponent("story_test_\(UUID().uuidString)")
        try? FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)

        let contentDir = tmpDir.appendingPathComponent("content")
        try? FileManager.default.createDirectory(at: contentDir, withIntermediateDirectories: true)

        // manifest.json
        let manifest: [String: Any] = ["title": "Test Story", "seed": 42]
        try? JSONSerialization.data(withJSONObject: manifest).write(to: tmpDir.appendingPathComponent("manifest.json"))

        // graph.json
        let graph: [String: Any] = [
            "nodes": [
                [
                    "node_id": "node_01",
                    "chapter": 1,
                    "scene_type": "exploration",
                    "text": "The pass splits.\nTwo paths lie ahead.",
                    "choices": [
                        [
                            "choice_id": "ch_01_a",
                            "choice_text": "Go north",
                            "target_node": "node_02",
                            "sets_flags": ["chose_north"],
                        ] as [String: Any],
                    ],
                    "present_characters": ["char_01"],
                    "present_location": "loc_01",
                    "present_creatures": [] as [String],
                    "mood": "determined",
                    "endings": ["is_ending": false],
                ] as [String: Any],
                [
                    "node_id": "node_02",
                    "chapter": 1,
                    "scene_type": "ending",
                    "text": "You reach the summit.",
                    "choices": [] as [[String: Any]],
                    "present_characters": [] as [String],
                    "present_location": "loc_02",
                    "present_creatures": [] as [String],
                    "mood": "triumphant",
                    "endings": ["is_ending": true],
                ] as [String: Any],
            ],
        ]
        try? JSONSerialization.data(withJSONObject: graph).write(to: contentDir.appendingPathComponent("graph.json"))

        // bible.json
        try? JSONSerialization.data(withJSONObject: ["world_name": "Test World"]).write(to: contentDir.appendingPathComponent("bible.json"))

        // gm_index.json
        try? JSONSerialization.data(withJSONObject: ["keywords": [:], "entity_cache": [:]] as [String: Any]).write(to: contentDir.appendingPathComponent("gm_index.json"))

        // style_bible.json
        try? JSONSerialization.data(withJSONObject: ["art_style": ["palette": "dark"]]).write(to: contentDir.appendingPathComponent("style_bible.json"))

        story = StoryPackage(storyId: "test_story", title: "Test Story", seed: 42, storyDir: tmpDir)
    }

    override func tearDown() {
        try? FileManager.default.removeItem(at: tmpDir)
        super.tearDown()
    }

    func testLoadsGraphWithCorrectNodeCount() {
        let repo = StoryRepository(story: story)
        XCTAssertEqual(repo.nodes.count, 2)
    }

    func testNode01HasChoices() {
        let repo = StoryRepository(story: story)
        let node = repo.nodes["node_01"]
        XCTAssertNotNil(node)
        XCTAssertEqual(node?.choices.count, 1)
        XCTAssertEqual(node?.choices[0].choiceId, "ch_01_a")
    }

    func testNode02IsEnding() {
        let repo = StoryRepository(story: story)
        let node = repo.nodes["node_02"]
        XCTAssertNotNil(node)
        XCTAssertTrue(node?.isEnding ?? false)
    }

    func testChoiceSetsFlags() {
        let repo = StoryRepository(story: story)
        let node = repo.nodes["node_01"]!
        XCTAssertEqual(node.choices[0].setsFlags, ["chose_north"])
    }

    func testStartNode() {
        let repo = StoryRepository(story: story)
        XCTAssertEqual(repo.startNode.nodeId, "node_01")
    }

    func testNodeCount() {
        let repo = StoryRepository(story: story)
        XCTAssertEqual(repo.nodeCount, 2)
    }

    func testBibleParsed() {
        let repo = StoryRepository(story: story)
        let name = repo.bible["world_name"] as? String
        XCTAssertEqual(name, "Test World")
    }

    func testGmIndexLoads() {
        let repo = StoryRepository(story: story)
        XCTAssertNotNil(repo.gmIndex)
    }

    func testDisplayLinesSplitsText() {
        let repo = StoryRepository(story: story)
        let node = repo.nodes["node_01"]!
        XCTAssertEqual(node.displayLines, ["The pass splits.", "Two paths lie ahead."])
    }

    func testEmptyGraphWhenFileMissing() {
        let emptyDir = FileManager.default.temporaryDirectory.appendingPathComponent("empty_\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: emptyDir) }
        try? FileManager.default.createDirectory(at: emptyDir.appendingPathComponent("content"), withIntermediateDirectories: true)
        try? JSONSerialization.data(withJSONObject: ["title": "Empty", "seed": 0]).write(to: emptyDir.appendingPathComponent("manifest.json"))

        let emptyStory = StoryPackage(storyId: "empty", title: "Empty", seed: 0, storyDir: emptyDir)
        let repo = StoryRepository(story: emptyStory)
        XCTAssertEqual(repo.nodes.count, 0)
    }
}
