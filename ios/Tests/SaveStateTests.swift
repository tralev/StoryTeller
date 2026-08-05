import XCTest
@testable import StoryTellerLib
final class SaveStateTests:XCTestCase{
 func testAtomicExternalHashBoundSave()throws{
  let root=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString);try FileManager.default.createDirectory(at:root,withIntermediateDirectories:true);defer{try? FileManager.default.removeItem(at:root)}
  let content=root.appendingPathComponent("stories/s");try FileManager.default.createDirectory(at:content,withIntermediateDirectories:true)
  let story=StoryPackage(storyId:"story_"+String(repeating:"0",count:32),title:"T",masterSeed:1,contentHash:String(repeating:"a",count:64),entryNode:"node_"+String(repeating:"0",count:32),storyDir:content)
  let state=SaveState(storyId:story.storyId,packageContentHash:story.contentHash,playthroughId:"p",currentNode:story.entryNode)
  let repo=SaveRepository(root:root);try repo.save(state);XCTAssertEqual(try repo.load(story:story,playthroughId:"p"),state);XCTAssertFalse(FileManager.default.fileExists(atPath:content.appendingPathComponent("save").path))
 }
}
