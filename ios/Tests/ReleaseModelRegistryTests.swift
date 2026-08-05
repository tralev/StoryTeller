import XCTest
@testable import StoryTellerLib

final class ReleaseModelRegistryTests: XCTestCase {
    func testGameMasterArtifactIsImmutableAndRequirementsAreSufficient() {
        let model = ReleaseModelRegistry.gameMaster
        XCTAssertEqual(model.role, "game_master")
        XCTAssertTrue(model.downloadURL.absoluteString.contains("/resolve/\(model.revision)/"))
        XCTAssertFalse(model.downloadURL.absoluteString.contains("/resolve/main/"))
        XCTAssertEqual(model.sha256.count, 64)
        XCTAssertGreaterThanOrEqual(model.minimumFreeStorageBytes, model.byteSize)
        XCTAssertGreaterThanOrEqual(model.minimumRAMBytes, 4_294_967_296)
    }

    func testStreamingHashAndAtomicPublication() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let partial = directory.appendingPathComponent("model.gguf.part")
        let installed = directory.appendingPathComponent("model.gguf")
        try Data("StoryTeller".utf8).write(to: partial)
        XCTAssertEqual(try ModelDownloadManager.sha256(partial), "62aad81d5f84ea420ae5a9ac0b3a3b9e2bc230a37488f0737862da0af5597ad5")
        try ModelDownloadManager.publishAtomically(partial, to: installed)
        XCTAssertFalse(FileManager.default.fileExists(atPath: partial.path))
        XCTAssertEqual(try Data(contentsOf: installed), Data("StoryTeller".utf8))
    }
}
