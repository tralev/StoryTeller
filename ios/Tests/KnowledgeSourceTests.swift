import CryptoKit
import XCTest
@testable import StoryTeller

final class KnowledgeSourceTests: XCTestCase {
    func testRevealGateRunsBeforeBoundedChunkOpen() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let chunks = root.appendingPathComponent("chunks")
        try FileManager.default.createDirectory(at: chunks, withIntermediateDirectories: true)
        let known = try write(root: chunks, id: "known", text: "known eastern gate", reveal: [])
        let hidden = try write(
            root: chunks, id: "hidden", text: "UNOPENED_SENTINEL eastern gate", reveal: ["node_2"]
        )
        let index = try JSONSerialization.data(withJSONObject: ["entries": [known, hidden]])
        try index.write(to: root.appendingPathComponent("index.json"))

        let read = try DirectoryKnowledgeSource(root: root).read(
            queryTokens: ["eastern"], maxRecords: 8, maxExcerptBytes: 4096
        )

        XCTAssertEqual(read.excerpts.map(\.entryId), ["known"])
        let knownSize = try XCTUnwrap(known["size_bytes"] as? Int)
        XCTAssertEqual(
            read.counters,
            KnowledgeReadCounters(bytesRead: knownSize, chunksOpened: 1, recordsDecoded: 1)
        )
        XCTAssertFalse(String(describing: read.excerpts).contains("UNOPENED_SENTINEL"))
    }

    func testRepositorySelectsBoundedSourceAndExposesCounters() throws {
        let storyRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let narrative = storyRoot.appendingPathComponent("narrative")
        let knowledge = narrative.appendingPathComponent("knowledge")
        let chunks = knowledge.appendingPathComponent("chunks")
        try FileManager.default.createDirectory(at: chunks, withIntermediateDirectories: true)
        let known = try write(root: chunks, id: "known", text: "known eastern gate", reveal: [])
        let index = try JSONSerialization.data(withJSONObject: ["entries": [known]])
        try index.write(to: knowledge.appendingPathComponent("index.json"))
        try Data("{\"entries\":[]}".utf8).write(to: narrative.appendingPathComponent("gm_index.json"))
        let story = StoryPackage(
            storyId: "story", title: "Story", masterSeed: 1, contentHash: "hash",
            entryNode: "node", storyDir: storyRoot
        )

        let lookup = StoryRepository(story: story).gmLookup(query: "eastern", visitedNodes: [])

        XCTAssertTrue(lookup.usedBoundedSource)
        XCTAssertEqual(lookup.counters?.chunksOpened, 1)
        XCTAssertTrue(lookup.promptContext.contains("[known]"))
    }

    func testRepositoryFallsBackForPreSliceV2Package() throws {
        let storyRoot = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let narrative = storyRoot.appendingPathComponent("narrative")
        try FileManager.default.createDirectory(at: narrative, withIntermediateDirectories: true)
        let record: [String: Any] = [
            "entry_id": "legacy", "kind": "event", "normalized_text": "legacy eastern gate",
            "source_ids": ["source"], "incoming_refs": [], "outgoing_refs": [],
            "reveal_after_nodes": [],
        ]
        let gm = try JSONSerialization.data(withJSONObject: ["entries": [record]])
        try gm.write(to: narrative.appendingPathComponent("gm_index.json"))
        let story = StoryPackage(
            storyId: "story", title: "Story", masterSeed: 1, contentHash: "hash",
            entryNode: "node", storyDir: storyRoot
        )

        let lookup = StoryRepository(story: story).gmLookup(query: "eastern", visitedNodes: [])

        XCTAssertFalse(lookup.usedBoundedSource)
        XCTAssertNil(lookup.counters)
        XCTAssertTrue(lookup.promptContext.contains("[legacy]"))
    }

    func testHostileLocatorIsRejectedBeforeChunkIO() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let locator: [String: Any] = [
            "entry_id": "hostile", "tokens": ["eastern"], "reveal_after_nodes": [],
            "path": "../escape.json", "sha256": String(repeating: "0", count: 64),
            "size_bytes": 1,
        ]
        let index = try JSONSerialization.data(withJSONObject: ["entries": [locator]])
        try index.write(to: root.appendingPathComponent("index.json"))

        XCTAssertThrowsError(try DirectoryKnowledgeSource(root: root))
    }

    func testDuplicateLocatorIdentityIsRejected() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let locator: [String: Any] = [
            "entry_id": "duplicate", "tokens": ["eastern"], "reveal_after_nodes": [],
            "path": "chunks/duplicate.json", "sha256": String(repeating: "0", count: 64),
            "size_bytes": 1,
        ]
        let index = try JSONSerialization.data(withJSONObject: ["entries": [locator, locator]])
        try index.write(to: root.appendingPathComponent("index.json"))

        XCTAssertThrowsError(try DirectoryKnowledgeSource(root: root))
    }

    private func write(root: URL, id: String, text: String, reveal: [String]) throws -> [String: Any] {
        let record: [String: Any] = [
            "entry_id": id, "kind": "event", "normalized_text": text,
            "source_ids": ["source"], "incoming_refs": [], "outgoing_refs": [],
            "reveal_after_nodes": reveal,
        ]
        let payload = try JSONSerialization.data(withJSONObject: record, options: [.sortedKeys])
        try payload.write(to: root.appendingPathComponent("\(id).json"))
        return [
            "entry_id": id, "tokens": ["eastern", "gate"], "reveal_after_nodes": reveal,
            "path": "chunks/\(id).json",
            "sha256": SHA256.hash(data: payload)
                .map { String(format: "%02x", $0) }.joined(),
            "size_bytes": payload.count,
        ]
    }
}
