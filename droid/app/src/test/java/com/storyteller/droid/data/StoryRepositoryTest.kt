package com.storyteller.droid.data

import com.google.gson.Gson
import com.storyteller.droid.model.StoryPackage
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

class StoryRepositoryTest {

    @Rule
    @JvmField
    val tempFolder = TemporaryFolder()

    private lateinit var story: StoryPackage
    private val gson = Gson()

    @Before
    fun setUp() {
        // Create a minimal .story directory structure
        val storyDir = tempFolder.newFolder("test_story")

        // content/
        val contentDir = File(storyDir, "content")
        contentDir.mkdirs()

        // manifest.json
        val manifest = mapOf(
            "title" to "Test Story",
            "seed" to 42,
            "schema_version" to 1,
        )
        File(storyDir, "manifest.json").writeText(gson.toJson(manifest))

        // graph.json with 2 nodes
        val graph = mapOf(
            "nodes" to listOf(
                mapOf(
                    "node_id" to "node_01",
                    "chapter" to 1,
                    "scene_type" to "exploration",
                    "text" to "The pass splits ahead.\nTwo paths lie before you.",
                    "choices" to listOf(
                        mapOf(
                            "choice_id" to "ch_01_a",
                            "choice_text" to "Go north",
                            "target_node" to "node_02",
                            "sets_flags" to listOf("chose_north"),
                        ) as Map<String, Any>,
                    ),
                    "present_characters" to listOf("char_01"),
                    "present_location" to "loc_01",
                    "present_creatures" to listOf<String>(),
                    "mood" to "determined",
                    "endings" to mapOf("is_ending" to false),
                ) as Map<String, Any>,
                mapOf(
                    "node_id" to "node_02",
                    "chapter" to 1,
                    "scene_type" to "ending",
                    "text" to "You reach the summit.",
                    "choices" to listOf<Map<String, Any>>(),
                    "present_characters" to listOf<String>(),
                    "present_location" to "loc_02",
                    "present_creatures" to listOf<String>(),
                    "mood" to "triumphant",
                    "endings" to mapOf("is_ending" to true),
                ) as Map<String, Any>,
            ),
        )
        File(contentDir, "graph.json").writeText(gson.toJson(graph))

        // bible.json (minimal)
        File(contentDir, "bible.json").writeText("""{"world_name": "Test World"}""")

        // gm_index.json (minimal)
        File(contentDir, "gm_index.json").writeText("""{"keywords": {}, "entity_cache": {}}""")

        // style_bible.json (minimal)
        File(contentDir, "style_bible.json").writeText("""{"art_style": {"palette": "dark"}}""")

        story = StoryPackage(
            storyId = "test_story",
            title = "Test Story",
            seed = 42,
            storyDir = storyDir,
        )
    }

    @Test
    fun `loads graph with correct node count`() {
        val repo = StoryRepository(story)
        assertEquals(2, repo.nodes.size)
    }

    @Test
    fun `node 01 has choices`() {
        val repo = StoryRepository(story)
        val node = repo.nodes["node_01"]
        assertNotNull(node)
        assertEquals(1, node!!.choices.size)
        assertEquals("ch_01_a", node.choices[0].choiceId)
    }

    @Test
    fun `node 02 is ending`() {
        val repo = StoryRepository(story)
        val node = repo.nodes["node_02"]
        assertNotNull(node)
        assertTrue(node!!.isEnding)
    }

    @Test
    fun `choice sets flags correctly`() {
        val repo = StoryRepository(story)
        val node = repo.nodes["node_01"]!!
        assertEquals(listOf("chose_north"), node.choices[0].setsFlags)
    }

    @Test
    fun `startNode returns node_01`() {
        val repo = StoryRepository(story)
        assertEquals("node_01", repo.startNode.nodeId)
    }

    @Test
    fun `nodeCount matches graph size`() {
        val repo = StoryRepository(story)
        assertEquals(2, repo.nodeCount)
    }

    @Test
    fun `bible is parsed correctly`() {
        val repo = StoryRepository(story)
        assertEquals("Test World", repo.bible["world_name"])
    }

    @Test
    fun `gmIndex loads without errors`() {
        val repo = StoryRepository(story)
        assertNotNull(repo.gmIndex)
    }

    @Test
    fun `empty graph when file missing`() {
        val emptyDir = tempFolder.newFolder("empty_story")
        File(emptyDir, "manifest.json").writeText("""{"title":"Empty","seed":0}""")
        val contentDir = File(emptyDir, "content")
        contentDir.mkdirs()
        // No graph.json

        val emptyStory = StoryPackage("empty", "Empty", 0, emptyDir)
        val repo = StoryRepository(emptyStory)
        assertEquals(0, repo.nodes.size)
    }

    @Test
    fun `displayLines splits text`() {
        val repo = StoryRepository(story)
        val node = repo.nodes["node_01"]!!
        assertEquals(listOf("The pass splits ahead.", "Two paths lie before you."), node.displayLines)
    }
}
