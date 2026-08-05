package com.storyteller.droid.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReleaseModelRegistryTest {
    @Test
    fun gameMasterArtifactIsImmutableAndDeviceRequirementsAreSufficient() {
        val model = ReleaseModelRegistry.gameMaster
        assertEquals("game_master", model.role)
        assertTrue(model.downloadUrl.contains("/resolve/${model.revision}/"))
        assertFalse(model.downloadUrl.contains("/resolve/main/"))
        assertEquals(64, model.sha256.length)
        assertTrue(model.minimumFreeStorageBytes >= model.byteSize)
        assertTrue(model.minimumRamBytes >= 4_294_967_296L)
    }
}
