import CryptoKit
import Foundation
import ZIPFoundation

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
    precondition(
        result.accepted == scenario.accepted,
        "\(scenario.id): acceptance mismatch \(result.issueCodes)"
    )
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
let extractionRequired = V2PackageValidator.validate(fixtures.appendingPathComponent("complete.story")).requiredBytes
precondition(extractionRequired > 0)
precondition(V2PackageValidator.hasExtractionSpace(
    requiredBytes: extractionRequired, freeBytes: extractionRequired
))
precondition(!V2PackageValidator.hasExtractionSpace(
    requiredBytes: extractionRequired, freeBytes: extractionRequired - 1
))
print("validated iOS extraction-space boundary")

let schemaCatalog = try JSONSerialization.jsonObject(
    with: Data(contentsOf: fixtures.appendingPathComponent("schema_fixtures.json"))
) as! [String: Any]
let schemaScenarios = schemaCatalog["scenarios"] as! [[String: Any]]
for scenario in schemaScenarios {
    let valid = TrustedJSONSchema.validates(
        schemaName: scenario["schema"] as! String,
        document: try Data(contentsOf: fixtures.appendingPathComponent(scenario["path"] as! String)),
        definition: scenario["definition"] as? String
    )
    precondition(valid == scenario["valid"] as! Bool, "\(scenario["id"]!): schema mismatch")
}
print("validated \(schemaScenarios.count) iOS schema scenarios")

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

let spoilerURL = root.appendingPathComponent("tests/fixtures/gm_retrieval/spoiler_catalog.json")
let spoilerRaw = try JSONSerialization.jsonObject(with: Data(contentsOf: spoilerURL)) as! [String: Any]
let spoilerIndex = GmIndex(from: ["entries": spoilerRaw["entries"] as! [[String: Any]]])
for scenario in spoilerRaw["scenarios"] as! [[String: Any]] {
    let ids = spoilerIndex.retrieve(
        query: scenario["query"] as! String,
        visitedNodes: Set(scenario["visited_nodes"] as! [String])
    ).map(\.entry.entryId)
    precondition(
        ids == scenario["expected_ids"] as! [String],
        "\(scenario["id"]!): spoiler retrieval mismatch"
    )
}
print("validated shared cross-domain iOS spoiler scenarios")

let spoilerSentinels = spoilerRaw["sentinels"] as! [String]
let spoilerBeforeHits = spoilerIndex.lookup(query: "sentinel marker", visitedNodes: [])
let spoilerBeforePrompt = spoilerIndex.formatForPrompt(spoilerBeforeHits)
let spoilerDiagnostics = String(describing: spoilerBeforeHits)
let spoilerHistoryURL = output.deletingLastPathComponent().appendingPathComponent(
    "spoiler-history-ios.json"
)
try? FileManager.default.removeItem(at: spoilerHistoryURL)
_ = try ConversationHistoryStore.addExchange(
    Exchange(
        exchangeId: "ex_0000", userText: "sentinel marker",
        assistantText: spoilerBeforePrompt.isEmpty ? "No revealed lore." : spoilerBeforePrompt,
        sequence: 0, createdAt: 1.0
    ),
    to: spoilerHistoryURL, storyId: "spoiler_story", contentHash: "package_hash",
    conversationId: "spoiler_conversation"
)
let spoilerHistoryText = String(data: try Data(contentsOf: spoilerHistoryURL), encoding: .utf8)!
let spoilerBeforeSurfaces = [
    spoilerBeforePrompt, spoilerDiagnostics, "GM_RETRIEVAL_EMPTY", spoilerHistoryText,
]
for sentinel in spoilerSentinels {
    precondition(
        spoilerBeforeSurfaces.allSatisfy { !$0.contains(sentinel) },
        "hidden sentinel reached an iOS runtime boundary: \(sentinel)"
    )
}
let spoilerAfterPrompt = spoilerIndex.promptContext(
    query: "sentinelglobaltext7e15", visitedNodes: ["node_global_reveal"]
)
precondition(spoilerAfterPrompt.contains("sentinel-global-id-7e15"))
precondition(spoilerAfterPrompt.contains("sentinelglobaltext7e15"))
print("validated iOS spoiler prompt/diagnostic/history boundaries")

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

let sourceRoot = output.deletingLastPathComponent().appendingPathComponent("knowledge-source-ios")
try? FileManager.default.removeItem(at: sourceRoot)
let sourceChunks = sourceRoot.appendingPathComponent("chunks")
try FileManager.default.createDirectory(at: sourceChunks, withIntermediateDirectories: true)
let sourceRecord: [String: Any] = [
    "entry_id": "known", "kind": "event", "normalized_text": "known eastern gate",
    "source_ids": ["source"], "incoming_refs": [], "outgoing_refs": [],
    "reveal_after_nodes": [],
]
let sourcePayload = try JSONSerialization.data(withJSONObject: sourceRecord, options: [.sortedKeys])
try sourcePayload.write(to: sourceChunks.appendingPathComponent("known.json"))
let sourceHash = SHA256.hash(data: sourcePayload).map { String(format: "%02x", $0) }.joined()
let sourceLocator: [String: Any] = [
    "entry_id": "known", "tokens": ["eastern", "gate"], "reveal_after_nodes": [],
    "path": "chunks/known.json", "sha256": sourceHash, "size_bytes": sourcePayload.count,
]
let sourceIndex = try JSONSerialization.data(
    withJSONObject: ["entries": [sourceLocator]], options: [.sortedKeys]
)
try sourceIndex.write(to: sourceRoot.appendingPathComponent("index.json"))
let sourceRead = try DirectoryKnowledgeSource(root: sourceRoot).read(
    queryTokens: ["eastern"], maxRecords: 1, maxExcerptBytes: sourcePayload.count
)
precondition(sourceRead.excerpts.map(\.entryId) == ["known"])
precondition(sourceRead.counters == KnowledgeReadCounters(
    bytesRead: sourcePayload.count, chunksOpened: 1, recordsDecoded: 1
))
var hostileLocator = sourceLocator
hostileLocator["path"] = "../escape.json"
let hostileIndex = try JSONSerialization.data(
    withJSONObject: ["entries": [hostileLocator]], options: [.sortedKeys]
)
try hostileIndex.write(to: sourceRoot.appendingPathComponent("index.json"), options: .atomic)
do {
    _ = try DirectoryKnowledgeSource(root: sourceRoot)
    preconditionFailure("hostile knowledge locator was accepted")
} catch {
    // Expected: rejected before a chunk can be opened.
}
print("validated iOS bounded knowledge source")

let spoilerSourceRoot = output.deletingLastPathComponent()
    .appendingPathComponent("knowledge-spoiler-shared-ios")
try? FileManager.default.removeItem(at: spoilerSourceRoot)
let spoilerSourceChunks = spoilerSourceRoot.appendingPathComponent("chunks")
try FileManager.default.createDirectory(at: spoilerSourceChunks, withIntermediateDirectories: true)
let localSpoiler = (spoilerRaw["entries"] as! [[String: Any]]).first {
    $0["kind"] as? String == "local_map"
}!
let localSpoilerId = localSpoiler["entry_id"] as! String
let localSpoilerPayload = try JSONSerialization.data(
    withJSONObject: localSpoiler, options: [.sortedKeys]
)
try localSpoilerPayload.write(
    to: spoilerSourceChunks.appendingPathComponent("\(localSpoilerId).json")
)
let localSpoilerHash = SHA256.hash(data: localSpoilerPayload)
    .map { String(format: "%02x", $0) }.joined()
let localSpoilerLocator: [String: Any] = [
    "entry_id": localSpoilerId,
    "tokens": ["sentinellocaltext31d8"],
    "reveal_after_nodes": localSpoiler["reveal_after_nodes"] as! [String],
    "path": "chunks/\(localSpoilerId).json",
    "sha256": localSpoilerHash,
    "size_bytes": localSpoilerPayload.count,
]
let localSpoilerIndex = try JSONSerialization.data(
    withJSONObject: ["entries": [localSpoilerLocator]], options: [.sortedKeys]
)
try localSpoilerIndex.write(to: spoilerSourceRoot.appendingPathComponent("index.json"))
let spoilerSource = try DirectoryKnowledgeSource(root: spoilerSourceRoot)
let localBefore = try spoilerSource.read(
    queryTokens: ["sentinellocaltext31d8"], maxRecords: 8, maxExcerptBytes: 8192
)
precondition(localBefore.excerpts.isEmpty)
precondition(localBefore.counters == KnowledgeReadCounters(
    bytesRead: 0, chunksOpened: 0, recordsDecoded: 0
))
let localAfter = try spoilerSource.read(
    queryTokens: ["sentinellocaltext31d8"], visitedNodes: ["node_local_reveal"],
    maxRecords: 8, maxExcerptBytes: 8192
)
precondition(localAfter.excerpts.map(\.entryId) == [localSpoilerId])
precondition(localAfter.counters == KnowledgeReadCounters(
    bytesRead: localSpoilerPayload.count, chunksOpened: 1, recordsDecoded: 1
))
print("validated shared physical-I/O iOS spoiler sentinel")

let sharedSourceRoot = output.deletingLastPathComponent().appendingPathComponent("knowledge-shared-ios")
try? FileManager.default.removeItem(at: sharedSourceRoot)
try FileManager.default.createDirectory(at: sharedSourceRoot, withIntermediateDirectories: true)
let sharedArchive = try Archive(url: fixtures.appendingPathComponent("complete.story"), accessMode: .read)
for entry in sharedArchive where entry.path.hasPrefix("narrative/knowledge/") {
    let relative = String(entry.path.dropFirst("narrative/knowledge/".count))
    let target = sharedSourceRoot.appendingPathComponent(relative)
    try FileManager.default.createDirectory(
        at: target.deletingLastPathComponent(), withIntermediateDirectories: true
    )
    var data = Data()
    _ = try sharedArchive.extract(entry) { data.append($0) }
    try data.write(to: target)
}
let sharedRead = try DirectoryKnowledgeSource(root: sharedSourceRoot).read(
    queryTokens: ["eastern"],
    visitedNodes: ["node_00000000000000000000000000000001"],
    maxRecords: 1,
    maxExcerptBytes: 8192
)
precondition(sharedRead.excerpts.map(\.entryId) == [
    "knowledge_00000000000000000000000000000001",
])
precondition(sharedRead.counters.chunksOpened == 1 && sharedRead.counters.recordsDecoded == 1)
print("validated iOS shared-package bounded lookup")

var streamBuilder = StreamBuilder(requestId: "contract-stream")
let streamEvents = [
    streamBuilder.started(),
    streamBuilder.text("first "),
    streamBuilder.text("second"),
    streamBuilder.completed(["chunks": 2]),
]
precondition(streamEvents.map(\.eventType) == [.started, .text, .text, .completed])
precondition(streamEvents.map(\.sequence) == [0, 1, 2, 3])
precondition(streamEvents.compactMap { $0.text.isEmpty ? nil : $0.text }.joined() == "first second")
print("validated iOS semantic stream ordering")

let boundedChannel = BoundedChunkChannel(capacity: 4)
let producerDone = DispatchSemaphore(value: 0)
let consumerDone = DispatchSemaphore(value: 0)
final class LockedStrings: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String] = []
    func append(_ value: String) { lock.lock(); values.append(value); lock.unlock() }
    func snapshot() -> [String] { lock.lock(); defer { lock.unlock() }; return values }
}
let boundedReceived = LockedStrings()
Task.detached {
    var builder = StreamBuilder(requestId: "bounded-contract")
    for index in 1...80 { boundedChannel.send(builder.text("chunk-\(index)")) }
    boundedChannel.send(builder.completed(["chunks": 80]))
    producerDone.signal()
}
Task.detached {
    for await event in boundedChannel {
        if event.eventType == .text {
            boundedReceived.append(event.text)
            usleep(500)
        }
    }
    consumerDone.signal()
}
precondition(producerDone.wait(timeout: .now() + 10) == .success)
precondition(consumerDone.wait(timeout: .now() + 10) == .success)
precondition(boundedReceived.snapshot() == (1...80).map { "chunk-\($0)" })
print("validated iOS slow-consumer lossless backpressure")

let cancelledChannel = BoundedChunkChannel(capacity: 4)
let cancellationObserved = DispatchSemaphore(value: 0)
cancelledChannel.onCancellation { cancellationObserved.signal() }
let cancelledConsumer = Task.detached {
    for await _ in cancelledChannel { }
}
usleep(1_000)
cancelledConsumer.cancel()
precondition(cancellationObserved.wait(timeout: .now() + 10) == .success)

let terminalChannel = BoundedChunkChannel(capacity: 4)
var terminalBuilder = StreamBuilder(requestId: "terminal-contract")
terminalChannel.send(terminalBuilder.completed(["chunks": 0]))
terminalChannel.send(terminalBuilder.text("must-not-escape"))
let terminalDone = DispatchSemaphore(value: 0)
let terminalTypes = LockedStrings()
Task.detached {
    for await event in terminalChannel { terminalTypes.append(event.eventType.rawValue) }
    terminalDone.signal()
}
precondition(terminalDone.wait(timeout: .now() + 10) == .success)
precondition(terminalTypes.snapshot() == ["completed"])
print("validated iOS cancellation and no-post-terminal boundary")
