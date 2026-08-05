import Foundation

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
    var worldIndex:[String:Any]{json(story.worldIndexFile)}
    func historyEvent(_ relative:String)->[String:Any]{json(story.confined(relative))}
    func localMapIndex(_ siteId:String)->[String:Any]{json(story.localMapIndex(siteId))}
    func chunk(_ relative:String)throws->Data{try Data(contentsOf:story.confined(relative),options:.mappedIfSafe)}
    private func json(_ url:URL)->[String:Any]{
        guard let data=try? Data(contentsOf:url),let value=try? JSONSerialization.jsonObject(with:data) as? [String:Any] else{return[:]};return value
    }
}
