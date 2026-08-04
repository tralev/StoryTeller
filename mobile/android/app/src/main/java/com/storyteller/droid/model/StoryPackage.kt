package com.storyteller.droid.model

import java.io.File

/**
 * An imported .story package on the device.
 *
 * Contains paths to all extracted content and mutable save state.
 */
data class StoryPackage(
    /** Unique story identifier (derived from .story filename). */
    val storyId: String,

    /** Human-readable title from manifest.json. */
    val title: String,

    /** RNG seed used during generation. */
    val seed: Int,

    /** Root directory of the extracted .story content. */
    val storyDir: File,
) {
    /** Path to the World Bible JSON. */
    val bibleFile get() = File(storyDir, "content/bible.json")

    /** Path to the story text JSON. */
    val storyFile get() = File(storyDir, "content/story.json")

    /** Path to the CYOA graph JSON. */
    val graphFile get() = File(storyDir, "content/graph.json")

    /** Path to the Game Master index JSON. */
    val gmIndexFile get() = File(storyDir, "content/gm_index.json")

    /** Path to the style bible JSON. */
    val styleBibleFile get() = File(storyDir, "content/style_bible.json")

    /** Directory containing 512×512 PNG images. */
    val imagesDir get() = File(storyDir, "content/images")

    /** Directory containing .mid MIDI files. */
    val midiDir get() = File(storyDir, "content/midi")

    /** Directory containing 128×128 PNG thumbnails. */
    val thumbnailsDir get() = File(storyDir, "content/thumbnails")

    /** Directory for mutable save state. */
    val saveDir get() = File(storyDir, "save").also { it.mkdirs() }

    /**
     * Get the image file for a specific node.
     */
    fun imageFor(nodeId: String): File = File(imagesDir, "${nodeId}.png")

    /**
     * Get the MIDI file for a specific node.
     */
    fun midiFor(nodeId: String): File = File(midiDir, "${nodeId}.mid")

    /**
     * Get the thumbnail for a specific node.
     */
    fun thumbnailFor(nodeId: String): File = File(thumbnailsDir, "${nodeId}.png")
}
