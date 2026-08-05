import XCTest
@testable import StoryTellerLib
final class StoryRepositoryTests:XCTestCase{
 func testV2GraphAndPaths()throws{
  let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString);try FileManager.default.createDirectory(at:root.appendingPathComponent("narrative"),withIntermediateDirectories:true);try FileManager.default.createDirectory(at:root.appendingPathComponent("world"),withIntermediateDirectories:true);defer{try? FileManager.default.removeItem(at:root)}
  let node="node_"+String(repeating:"0",count:32);let graph="{\"nodes\":[{\"node_id\":\"\(node)\",\"text\":\"End\",\"choices\":[],\"scene_id\":\"s\",\"location_id\":\"l\",\"participant_ids\":[],\"authoritative_refs\":[],\"ending\":\"complete\"}]}";try graph.data(using:.utf8)!.write(to:root.appendingPathComponent("narrative/graph.json"));for name in ["bible.json","gm_index.json","style_bible.json"]{try Data("{}".utf8).write(to:root.appendingPathComponent("narrative/\(name)"))};try Data("{}".utf8).write(to:root.appendingPathComponent("world/index.json"))
  let story=StoryPackage(storyId:"story_"+String(repeating:"0",count:32),title:"T",masterSeed:1,contentHash:String(repeating:"0",count:64),entryNode:node,storyDir:root);let repo=StoryRepository(story:story);XCTAssertEqual(repo.startNode.nodeId,node);XCTAssertTrue(story.imageFor(nodeId:node).path.contains("assets/images"))
 }
}
