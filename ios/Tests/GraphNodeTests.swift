import XCTest
@testable import StoryTellerLib
final class GraphNodeTests:XCTestCase{
 func testSessionParity()throws{
  let end=GraphNode(nodeId:"node_00000000000000000000000000000002",text:"end",choices:[],ending:"complete")
  let choice=Choice(choiceId:"choice",choiceText:"Go",targetNode:end.nodeId,setsFlags:["opened"])
  let start=GraphNode(nodeId:"node_00000000000000000000000000000001",text:"start",choices:[choice])
  let save=SaveState(storyId:"story",packageContentHash:"hash",currentNode:start.nodeId,visitedNodes:[start.nodeId])
  var session=StorySession(nodes:[start.nodeId:start,end.nodeId:end],state:save);try session.choose("choice")
  XCTAssertEqual(session.current.nodeId,end.nodeId);XCTAssertEqual(session.state.flags["opened"],true)
 }
}
