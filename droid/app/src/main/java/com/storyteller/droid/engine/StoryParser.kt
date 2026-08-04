package com.storyteller.droid.engine

import android.content.Context
import android.util.Log
import com.google.gson.Gson
import com.storyteller.droid.model.StoryPackage
import java.io.File
import java.io.FileOutputStream
import java.util.zip.ZipFile

/**
 * Extracts and parses .story ZIP archives into the app's internal storage.
 *
 * The .story archive contains:
 *   manifest.json          — metadata, version, seed
 *   content/
 *     bible.json           — World Bible
 *     story.json           — Linear story text
 *     graph.json           — CYOA branching graph
 *     gm_index.json        — Game Master keyword index
 *     images/              — 512×512 PNG illustrations
 *     midi/                — MIDI music files
 *     thumbnails/          — 128×128 PNG thumbnails
 *   save/
 *     .gitkeep             — Placeholder for save state
 */
class StoryParser(private val context: Context) {
    companion object {
        private const val TAG = "StoryParser"
        private const val STORIES_DIR = "stories"
    }

    private val gson = Gson()
    private val storiesDir: File
        get() = File(context.filesDir, STORIES_DIR).also { it.mkdirs() }

    /**
     * Import a .story file from a URI (via SAF file picker or share intent).
     *
     * @param filePath Absolute path to the .story file.
     * @return The parsed [StoryPackage], or null if import failed.
     */
    fun import(filePath: String): StoryPackage? {
        val source = File(filePath)
        if (!source.exists()) {
            Log.e(TAG, "Source file not found: $filePath")
            return null
        }

        val storyId = source.nameWithoutExtension
        val destDir = File(storiesDir, storyId)
        if (destDir.exists()) {
            Log.d(TAG, "Story already imported: $storyId")
            return load(storyId)
        }
        destDir.mkdirs()

        return try {
            ZipFile(source).use { zip ->
                zip.entries().asSequence().forEach { entry ->
                    val targetFile = File(destDir, entry.name)
                    if (entry.isDirectory) {
                        targetFile.mkdirs()
                    } else {
                        targetFile.parentFile?.mkdirs()
                        zip.getInputStream(entry).use { input ->
                            FileOutputStream(targetFile).use { output ->
                                input.copyTo(output)
                            }
                        }
                    }
                }
            }
            Log.i(TAG, "Imported: $storyId (${destDir.listFiles()?.size ?: 0} files)")
            load(storyId)
        } catch (e: Exception) {
            Log.e(TAG, "Import failed: $filePath", e)
            destDir.deleteRecursively()
            null
        }
    }

    /**
     * Load an already-imported story by its ID.
     */
    fun load(storyId: String): StoryPackage? {
        val storyDir = File(storiesDir, storyId)
        if (!storyDir.exists()) return null

        return try {
            val manifest = gson.fromJson(
                File(storyDir, "manifest.json").readText(),
                Map::class.java,
            ) as Map<String, Any>

            StoryPackage(
                storyId = storyId,
                title = (manifest["title"] as? String) ?: storyId,
                seed = (manifest["seed"] as? Double)?.toInt() ?: 0,
                storyDir = storyDir,
            )
        } catch (e: Exception) {
            Log.e(TAG, "Failed to load story: $storyId", e)
            null
        }
    }

    /**
     * List all imported stories.
     */
    fun listStories(): List<StoryPackage> {
        return storiesDir.listFiles()
            ?.filter { it.isDirectory }
            ?.mapNotNull { load(it.name) }
            ?.sortedByDescending { it.storyId }
            ?: emptyList()
    }

    /**
     * Delete an imported story and all its data.
     */
    fun delete(storyId: String): Boolean {
        val storyDir = File(storiesDir, storyId)
        return storyDir.deleteRecursively()
    }

    /**
     * Read a JSON file from a story directory.
     */
    fun readJson(storyDir: File, filename: String): Map<String, Any>? {
        val file = File(storyDir, filename)
        if (!file.exists()) return null
        return try {
            gson.fromJson(file.readText(), Map::class.java) as? Map<String, Any>
        } catch (e: Exception) {
            Log.e(TAG, "Failed to read JSON: $filename", e)
            null
        }
    }
}
