package com.storyteller.droid.model

import java.io.File

/** Immutable, fully accepted `.story` v2 content in the private library. */
data class StoryPackage(
    val storyId: String,
    val title: String,
    val masterSeed: Long,
    val contentHash: String,
    val entryNode: String,
    val storyDir: File,
) {
    // Transitional display alias; package identity never depends on it.
    val seed: Int get() = masterSeed.toInt()
    val bibleFile get() = confined("narrative/bible.json")
    val storyFile get() = confined("narrative/story.json")
    val graphFile get() = confined("narrative/graph.json")
    val gmIndexFile get() = confined("narrative/gm_index.json")
    val styleBibleFile get() = confined("narrative/style_bible.json")
    val worldIndexFile get() = confined("world/index.json")
    val regionsFile get() = confined("world/regions.json")
    val routesFile get() = confined("world/routes.json")
    val sitesFile get() = confined("world/sites.json")
    /** App-private compatibility location, deliberately outside [storyDir]. */
    val saveDir get() = File(storyDir.parentFile?.parentFile ?: storyDir.parentFile,
                             "saves/$storyId/default").also { it.mkdirs() }
    fun imageFor(nodeId: String) = confined("assets/images/$nodeId.png")
    fun thumbnailFor(nodeId: String) = confined("assets/thumbnails/$nodeId.png")
    fun scoreFor(nodeId: String) = confined("assets/music/$nodeId.score.json")
    fun midiFor(nodeId: String) = confined("assets/midi/$nodeId.mid")
    fun worldMap() = confined("assets/maps/world.png")
    fun regionMap(regionId: String) = confined("assets/maps/regions/$regionId.png")
    fun localMapIndex(siteId: String) = confined("world/local/$siteId/index.json")

    fun confined(relative: String): File {
        require(!relative.startsWith('/') && '\\' !in relative &&
            relative.split('/').none { it.isEmpty() || it == "." || it == ".." })
        val root = storyDir.canonicalFile
        val result = File(root, relative).canonicalFile
        require(result.path.startsWith(root.path + File.separator))
        return result
    }
}
