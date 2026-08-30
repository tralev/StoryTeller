package com.storyteller.droid.engine

import com.google.gson.Gson
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File

class TrustedJSONSchemaTest {
    private val root: File by lazy {
        generateSequence(File(requireNotNull(System.getProperty("user.dir")))) { it.parentFile }
            .first { File(it, "tests/fixtures/v2/schema_fixtures.json").isFile }
    }

    @Test
    fun `all generated schema fixtures have the frozen outcome`() {
        val fixtureRoot = File(root, "tests/fixtures/v2")
        @Suppress("UNCHECKED_CAST")
        val scenarios = (Gson().fromJson(
            File(fixtureRoot, "schema_fixtures.json").readText(), Map::class.java
        )["scenarios"] as List<Map<String, Any>>)
        for (scenario in scenarios) {
            val actual = TrustedJSONSchema.validates(
                scenario["schema"] as String,
                File(fixtureRoot, scenario["path"] as String).readBytes(),
                scenario["definition"] as? String,
            )
            assertEquals(scenario["id"] as String, scenario["valid"] as Boolean, actual)
        }
    }
}
