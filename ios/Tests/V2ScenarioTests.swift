import XCTest
@testable import StoryTellerLib

final class V2ScenarioTests: XCTestCase {
    private var root: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    func testSharedScenarioCatalogAndEmitNativeResults() throws {
        let fixtures = root.appendingPathComponent("tests/fixtures/v2")
        let catalog = try JSONSerialization.jsonObject(
            with: Data(contentsOf: fixtures.appendingPathComponent("catalog.json"))
        ) as! [String: Any]
        let scenarios = catalog["scenarios"] as! [[String: Any]]
        let library = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: library) }
        let parser = StoryParser(root: library)
        var output: [String: Any] = [:]

        for scenario in scenarios {
            let id = scenario["id"] as! String
            let result = parser.importValidated(from: fixtures.appendingPathComponent(scenario["path"] as! String))
            let accepted: Bool
            let issueCodes: [String]
            switch result {
            case .imported, .alreadyImported:
                accepted = true
                issueCodes = []
            case .unsupportedVersion:
                accepted = false
                issueCodes = ["PACKAGE_UNSUPPORTED_VERSION"]
            case .invalid(let codes):
                accepted = false
                issueCodes = codes
            case .insufficientStorage:
                accepted = false
                issueCodes = ["PACKAGE_INSUFFICIENT_STORAGE"]
            case .cancelled:
                accepted = false
                issueCodes = ["PACKAGE_CANCELLED"]
            }
            XCTAssertEqual(accepted, scenario["accepted"] as! Bool, id)
            XCTAssertEqual(issueCodes, (scenario["issue_code"] as? String).map { [$0] } ?? [], id)
            output[id] = ["outcome": accepted ? "accepted" : "invalid", "issue_codes": issueCodes]
        }

        let destination = root.appendingPathComponent("tmp/contracts/ios.json")
        try FileManager.default.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
        let document: [String: Any] = [
            "format": "storyteller.contract-results.v2",
            "scenarios": output,
        ]
        try JSONSerialization.data(withJSONObject: document, options: [.sortedKeys]).write(to: destination, options: .atomic)
    }

    func testFrozenWorldInventoryContracts() throws {
        let fixtures = root.appendingPathComponent("tests/fixtures/v2")
        let library = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: library) }
        let parser = StoryParser(root: library)
        guard case .imported(let storyID) = parser.importValidated(from: fixtures.appendingPathComponent("complete.story")) else {
            return XCTFail("complete fixture was not imported")
        }
        let story = try parser.loadStory(storyId: storyID)
        XCTAssertTrue(story.storyId.range(of: #"^story_[0-9a-f]{32}$"#, options: .regularExpression) != nil)
        XCTAssertTrue(story.entryNode.range(of: #"^node_[0-9a-f]{32}$"#, options: .regularExpression) != nil)
        let repository = StoryRepository(story: story)
        let index = repository.worldIndex
        XCTAssertNotNil(index["surface_chunk_shape"])
        XCTAssertNotNil(index["local_chunk_shape"])
        XCTAssertFalse(try repository.chunk("world/terrain/index.json").isEmpty)
        XCTAssertFalse(try repository.chunk("world/local/index.json").isEmpty)
    }
}
