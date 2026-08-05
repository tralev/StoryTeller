package com.storyteller.droid.data

import com.google.gson.Gson
import com.storyteller.droid.engine.V2PackageValidator
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import java.util.zip.ZipFile

/** Executes the one shared corpus through the real context-free Android validator. */
class V2ScenarioCatalogTest {
    private val gson = Gson()
    private val root: File by lazy {
        generateSequence(File(requireNotNull(System.getProperty("user.dir")))) { it.parentFile }
            .first { File(it, "tests/fixtures/v2/catalog.json").isFile }
    }

    @Test
    fun `all shared archives match acceptance and exact issue codes`() {
        val fixtureDir = File(root, "tests/fixtures/v2")
        val catalog = gson.fromJson(File(fixtureDir, "catalog.json").readText(), Map::class.java)
        @Suppress("UNCHECKED_CAST")
        val scenarios = catalog["scenarios"] as List<Map<String, Any>>
        val output = linkedMapOf<String, Any>()

        for (scenario in scenarios) {
            val id = scenario["id"] as String
            val result = V2PackageValidator.validate(File(fixtureDir, scenario["path"] as String))
            val expectedAccepted = scenario["accepted"] as Boolean
            val expectedCodes = (scenario["issue_code"] as? String)?.let(::listOf).orEmpty()
            assertEquals(id, expectedAccepted, result.accepted)
            assertEquals(id, expectedCodes, result.issueCodes)
            output[id] = mapOf(
                "outcome" to if (result.accepted) "accepted" else "invalid",
                "issue_codes" to result.issueCodes,
            )
        }

        val resultFile = File(root, "tmp/contracts/android.json")
        resultFile.parentFile?.mkdirs()
        resultFile.writeText(gson.toJson(mapOf(
            "format" to "storyteller.contract-results.v2",
            "scenarios" to output,
        )))
    }

    @Test
    fun `accepted world inventory uses frozen paths IDs units and dependencies`() {
        val story = File(root, "tests/fixtures/v2/complete.story")
        val result = V2PackageValidator.validate(story)
        assertTrue(result.issueCodes.toString(), result.accepted)
        val manifest = result.manifest!!
        val storyId = manifest["story_id"] as String
        val entryNode = manifest["entry_node"] as String
        assertTrue(storyId.matches(Regex("story_[0-9a-f]{32}")))
        assertTrue(entryNode.matches(Regex("node_[0-9a-f]{32}")))

        @Suppress("UNCHECKED_CAST")
        val artifacts = manifest["artifacts"] as List<Map<String, Any>>
        val ids = artifacts.map { it["artifact_id"] as String }.toSet()
        assertEquals(ids.size, artifacts.size)
        assertTrue(artifacts.any { it["path"] == "world/index.json" })
        assertTrue(artifacts.any { (it["path"] as String).contains("/chunks/") })
        assertTrue(artifacts.all { artifact ->
            @Suppress("UNCHECKED_CAST")
            (artifact["depends_on"] as List<String>).all(ids::contains)
        })

        ZipFile(story).use { zip ->
            val encoded = zip.getInputStream(zip.getEntry("world/index.json")).reader().readText()
            assertTrue(encoded.contains("\"surface_chunk_shape\""))
            assertTrue(encoded.contains("\"local_chunk_shape\""))
            assertFalse("floating units are forbidden", Regex("\"(?:x|y|width|height|elevation|distance|duration|year)[^\"]*\"\\s*:\\s*-?\\d+\\.\\d+").containsMatchIn(encoded))
        }
    }
}
