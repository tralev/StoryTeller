import Foundation

struct GmLookup {
    let promptContext: String
    let counters: KnowledgeReadCounters?
    let usedBoundedSource: Bool
}

/** Lazy, read-only view of a fully accepted v2 package. */
final class StoryRepository {
    let story: StoryPackage
    private var nodeCache: [String: GraphNode]?
    init(story: StoryPackage) { self.story=story }
    var nodes: [String:GraphNode] {
        if let nodeCache{return nodeCache}
        struct Graph:Decodable{let nodes:[GraphNode]}
        let values=(try? JSONDecoder().decode(Graph.self,from:Data(contentsOf:story.graphFile)).nodes) ?? []
        let result=Dictionary(uniqueKeysWithValues:values.map{($0.nodeId,$0)});nodeCache=result;return result
    }
    var startNode: GraphNode { nodes[story.entryNode] ?? { fatalError("PACKAGE_ENTRY_NODE") }() }
    var nodeCount:Int{nodes.count}
    var bible:[String:Any]{json(story.bibleFile)}
    var styleBible:[String:Any]{json(story.styleBibleFile)}
    var gmIndex:GmIndex{GmIndex(from:json(story.gmIndexFile))}
    private var knowledgeSource: DirectoryKnowledgeSource? {
        try? DirectoryKnowledgeSource(root: story.knowledgeDir)
    }
    var worldIndex:[String:Any]{json(story.worldIndexFile)}
    func historyEvent(_ relative:String)->[String:Any]{json(story.confined(relative))}
    func localMapIndex(_ siteId:String)->[String:Any]{json(story.localMapIndex(siteId))}
    func chunk(_ relative:String)throws->Data{try Data(contentsOf:story.confined(relative),options:.mappedIfSafe)}
    func gmPromptContext(
        query: String,
        visitedNodes: Set<String>,
        currentNodeId: String? = nil,
        visitedRefs: Set<String> = []
    ) -> String {
        gmLookup(
            query: query, visitedNodes: visitedNodes,
            currentNodeId: currentNodeId, visitedRefs: visitedRefs
        ).promptContext
    }
    func gmLookup(
        query: String,
        visitedNodes: Set<String>,
        currentNodeId: String? = nil,
        visitedRefs: Set<String> = []
    ) -> GmLookup {
        guard let source = knowledgeSource,
              let read = try? source.read(
                  queryTokens: Set(GmIndex.tokens(query)), visitedNodes: visitedNodes,
                  maxRecords: 64, maxExcerptBytes: 32768
              ) else {
            return GmLookup(
                promptContext: gmIndex.promptContext(
                    query: query, visitedNodes: visitedNodes,
                    currentNodeId: currentNodeId, visitedRefs: visitedRefs
                ),
                counters: nil,
                usedBoundedSource: false
            )
        }
        return GmLookup(
            promptContext: GmIndex(entries: read.excerpts).promptContext(
                query: query, visitedNodes: visitedNodes,
                currentNodeId: currentNodeId, visitedRefs: visitedRefs
            ),
            counters: read.counters,
            usedBoundedSource: true
        )
    }
    private func json(_ url:URL)->[String:Any]{
        guard let data=try? Data(contentsOf:url),let value=try? JSONSerialization.jsonObject(with:data) as? [String:Any] else{return[:]};return value
    }
}
