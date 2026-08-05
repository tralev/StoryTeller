import XCTest
@testable import StoryTellerLib

final class LlamaEngineLifecycleTests: XCTestCase {
    func testContextBoundsFailBeforeNativeLoad() async {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try? Data().write(to: file)
        defer { try? FileManager.default.removeItem(at: file) }
        let engine = LlamaEngine()
        do {
            try await engine.loadModel(path: file.path, contextSize: 128)
            XCTFail("invalid context was accepted")
        } catch LlamaError.invalidContextSize {
            XCTAssertFalse(engine.isLoaded)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testMissingModelFailsWithoutChangingLifecycle() async {
        let engine = LlamaEngine()
        do {
            try await engine.loadModel(path: "/missing/storyteller-model.gguf")
            XCTFail("missing model was accepted")
        } catch LlamaError.fileNotFound {
            XCTAssertEqual(engine.state, .unloaded)
        } catch {
            XCTFail("unexpected error: \(error)")
        }
    }

    func testBackgroundReleaseIsIdempotentWhenUnloaded() {
        let engine = LlamaEngine()
        engine.suspendForBackground()
        engine.releaseForMemoryPressure()
        XCTAssertEqual(engine.state, .unloaded)
    }
}
