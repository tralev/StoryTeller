import Foundation

/// Loads and caches content from an extracted .story package.
///
/// Provides access to the graph, bible, and GM index without
/// re-parsing JSON on every access.
final class StoryRepository {
    let story: StoryPackage
    private let storyParser = StoryParser()
    
    private var _nodes: [String: GraphNode]?
    private var _bible: [String: Any]?
    private var _gmIndex: GmIndex?
    private var _styleBible: [String: Any]?
    
    init(story: StoryPackage) {
        self.story = story
    }
    
    var nodes: [String: GraphNode] {
        if let n = _nodes { return n }
        _nodes = loadGraph()
        return _nodes ?? [:]
    }
    
    var bible: [String: Any] {
        if let b = _bible { return b }
        _bible = storyParser.readJSON(at: story.bibleFile)
        return _bible ?? [:]
    }
    
    var gmIndex: GmIndex {
        if let g = _gmIndex { return g }
        _gmIndex = GmIndex(from: storyParser.readJSON(at: story.gmIndexFile) ?? [:])
        return _gmIndex ?? GmIndex()
    }
    
    var styleBible: [String: Any] {
        if let s = _styleBible { return s }
        _styleBible = storyParser.readJSON(at: story.styleBibleFile)
        return _styleBible ?? [:]
    }
    
    var nodeCount: Int { nodes.count }
    
    var startNode: GraphNode {
        nodes["node_01"] ?? GraphNode(
            nodeId: "node_01", chapter: 1, sceneType: "narrative",
            text: "Error: no start node found.", choices: [],
            presentCharacters: [], presentLocation: nil,
            presentCreatures: [], mood: "", isEnding: false
        )
    }
    
    // MARK: - Graph loading
    
    private func loadGraph() -> [String: GraphNode] {
        guard let raw = storyParser.readJSON(at: story.graphFile),
              let rawNodes = raw["nodes"] as? [[String: Any]]
        else { return [:] }
        
        var result: [String: GraphNode] = [:]
        let decoder = JSONDecoder()
        
        for nodeDict in rawNodes {
            guard let nodeId = nodeDict["node_id"] as? String else { continue }
            do {
                let data = try JSONSerialization.data(withJSONObject: nodeDict)
                let node = try decoder.decode(GraphNode.self, from: data)
                result[nodeId] = node
            } catch {
                print("[StoryRepository] Failed to parse node \(nodeId): \(error)")
            }
        }
        
        return result
    }
}
