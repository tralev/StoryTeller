package com.storyteller.droid.data
import com.storyteller.droid.model.StoryPackage
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class StoryRepositoryTest {
 @get:Rule val temp=TemporaryFolder()
 @Test fun `repository reads v2 graph and exact media paths`() {
  val root=temp.newFolder();File(root,"narrative").mkdirs();File(root,"world").mkdirs()
  File(root,"narrative/graph.json").writeText("""{"nodes":[{"node_id":"node_00000000000000000000000000000001","text":"End","choices":[],"scene_id":"s","location_id":"l","participant_ids":[],"authoritative_refs":[],"ending":"complete"}]}""")
  for(name in listOf("bible.json","gm_index.json","style_bible.json"))File(root,"narrative/$name").writeText("{}")
  File(root,"world/index.json").writeText("{}")
  val id="node_00000000000000000000000000000001";val story=StoryPackage("story_"+"0".repeat(32),"T",1,"0".repeat(64),id,root)
  val repo=StoryRepository(story);assertEquals(id,repo.startNode.nodeId);assertTrue(story.imageFor(id).path.contains("assets/images"))
 }
}
