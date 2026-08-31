import Foundation

struct StoryPackage: Identifiable, Codable {
    let storyId: String
    let title: String
    let masterSeed: Int64
    let contentHash: String
    let entryNode: String
    let storyDir: URL
    var id: String { storyId }
    var seed: Int { Int(masterSeed) }
    var bibleFile: URL { confined("narrative/bible.json") }
    var storyFile: URL { confined("narrative/story.json") }
    var graphFile: URL { confined("narrative/graph.json") }
    var gmIndexFile: URL { confined("narrative/gm_index.json") }
    var knowledgeDir: URL { confined("narrative/knowledge") }
    var styleBibleFile: URL { confined("narrative/style_bible.json") }
    var worldIndexFile: URL { confined("world/index.json") }
    func imageFor(nodeId: String) -> URL { confined("assets/images/\(nodeId).png") }
    func thumbnailFor(nodeId: String) -> URL { confined("assets/thumbnails/\(nodeId).png") }
    func scoreFor(nodeId: String) -> URL { confined("assets/music/\(nodeId).score.json") }
    func midiFor(nodeId: String) -> URL { confined("assets/midi/\(nodeId).mid") }
    func worldMap() -> URL { confined("assets/maps/world.png") }
    func regionMap(_ regionId: String) -> URL { confined("assets/maps/regions/\(regionId).png") }
    func localMapIndex(_ siteId: String) -> URL { confined("world/local/\(siteId)/index.json") }
    var saveDir: URL { // compatibility location, outside immutable content
        storyDir.deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("saves/\(storyId)/default")
    }
    func confined(_ relative: String) -> URL {
        precondition(!relative.hasPrefix("/") && !relative.contains("\\"))
        precondition(relative.split(separator: "/", omittingEmptySubsequences: false)
            .allSatisfy { !$0.isEmpty && $0 != "." && $0 != ".." })
        let root = storyDir.standardizedFileURL
        let result = root.appendingPathComponent(relative).standardizedFileURL
        precondition(result.path.hasPrefix(root.path + "/"))
        return result
    }
}

struct V2Manifest: Codable {
    let packageFormat: String
    let packageVersion: Int
    let storyId: String
    let title: String
    let masterSeed: Int64
    let requiredFeatures: [String]
    let optionalFeatures: [String]
    let entryNode: String
    let contentHash: String
    let artifacts: [ArtifactRecord]
    let nodeAssets: [String: NodeAssets]
    let regionMaps: [String: String]
    enum CodingKeys: String, CodingKey {
        case packageFormat = "package_format", packageVersion = "package_version"
        case storyId = "story_id", title, masterSeed = "master_seed"
        case requiredFeatures = "required_features", optionalFeatures = "optional_features"
        case entryNode = "entry_node", contentHash = "content_hash", artifacts
        case nodeAssets = "node_assets", regionMaps = "region_maps"
    }
}
struct ArtifactRecord: Codable {
    let artifactId, kind, path, sha256: String
    let sizeBytes: Int64
    let dependsOn: [String]
    let producer: ArtifactProducer
    enum CodingKeys: String, CodingKey {
        case artifactId = "artifact_id", kind, path, sha256
        case sizeBytes = "size_bytes", dependsOn = "depends_on", producer
    }
}
struct ArtifactProducer: Codable {
    let schemaSha256: String
    let fingerprint: String
    enum CodingKeys: String, CodingKey { case schemaSha256 = "schema_sha256", fingerprint }
}
struct NodeAssets: Codable, Equatable { let image, thumbnail, score, midi: String }
