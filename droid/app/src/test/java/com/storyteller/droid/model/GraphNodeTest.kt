package com.storyteller.droid.model
import org.junit.Assert.*
import org.junit.Test

class GraphNodeTest {
 @Test fun `v2 session applies flags and visits target`() {
  val end=GraphNode("node_00000000000000000000000000000002","end", emptyList(),ending="complete")
  val choice=Choice("choice","Go",end.nodeId,listOf("opened"))
  val start=GraphNode("node_00000000000000000000000000000001","start",listOf(choice))
  val state=SaveState(storyId="story",packageContentHash="hash",currentNode=start.nodeId,visitedNodes= mutableListOf(start.nodeId))
  val session=StorySession(mapOf(start.nodeId to start,end.nodeId to end),start.nodeId,state)
  assertEquals(end,session.choose("choice"));assertTrue(state.flags["opened"]==true);assertTrue(end.nodeId in state.visitedNodes)
 }
 @Test fun `choice requires every true flag`() { assertFalse(Choice("c","go","n",requiresFlags=listOf("x")).isAvailable(mapOf("x" to false))) }
}
