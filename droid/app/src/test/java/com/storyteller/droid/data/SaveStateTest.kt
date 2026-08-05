package com.storyteller.droid.data
import com.storyteller.droid.model.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class SaveStateTest {
 @get:Rule val temp=TemporaryFolder()
 @Test fun `save is external atomic and hash bound`() {
  val root=temp.newFolder();val content=temp.newFolder("content")
  val story=StoryPackage("story_00000000000000000000000000000001","T",1,"a".repeat(64),"node_00000000000000000000000000000001",content)
  val state=SaveState(storyId=story.storyId,packageContentHash=story.contentHash,playthroughId="p",currentNode=story.entryNode)
  val repo=SaveRepository(root);repo.save(state);assertEquals(state,repo.load(story,"p"));assertFalse(File(content,"save").exists())
 }
}
