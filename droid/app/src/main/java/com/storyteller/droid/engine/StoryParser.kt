package com.storyteller.droid.engine

import android.content.Context
import com.google.gson.Gson
import com.storyteller.droid.model.StoryPackage
import java.io.File
import java.io.FileOutputStream
import java.util.zip.ZipFile

sealed class ImportResult {
    data class Imported(val story: StoryPackage) : ImportResult()
    data class AlreadyImported(val story: StoryPackage) : ImportResult()
    data class UnsupportedVersion(val found: Int, val supported: Int = 2) : ImportResult()
    data class Invalid(val errorCodes: List<String>) : ImportResult()
    data class InsufficientStorage(val requiredBytes: Long) : ImportResult()
    data object Cancelled : ImportResult()
}

/** v2-only staged importer. ZIP bytes are never used as content identity. */
class StoryParser(private val context: Context) {
    private val gson = Gson()
    private val library get() = File(context.filesDir, "stories-v2").also { it.mkdirs() }

    fun importValidated(filePath: String, cancelled: () -> Boolean = { false }): ImportResult {
        val source = File(filePath)
        if (!source.isFile) return ImportResult.Invalid(listOf("PACKAGE_NOT_FOUND"))
        var staging: File? = null
        return try {
            val validation = V2PackageValidator.validate(source)
            if (!validation.accepted) {
                val version = (validation.manifest?.get("package_version") as? Double)?.toInt()
                if (validation.issueCodes == listOf("PACKAGE_UNSUPPORTED_VERSION")) {
                    return ImportResult.UnsupportedVersion(version ?: 0)
                }
                return ImportResult.Invalid(validation.issueCodes)
            }
            val manifest = validation.manifest!!
            ZipFile(source).use { zip ->
                val entries = zip.entries().asSequence().toList()
                val storyId = manifest["story_id"] as? String
                    ?: return ImportResult.Invalid(listOf("PACKAGE_IDENTITY"))
                val contentHash = manifest["content_hash"] as? String
                    ?: return ImportResult.Invalid(listOf("PACKAGE_IDENTITY"))
                val destination = File(library, storyId)
                val required = validation.requiredBytes
                if (library.usableSpace < required) return ImportResult.InsufficientStorage(required)
                // Validate the supplied bytes even when this identity already
                // exists locally; presence of a good copy must not bless a
                // corrupt or provenance-broken archive.
                if (destination.isDirectory) return ImportResult.AlreadyImported(load(storyId)!!)
                staging = File(library, ".$storyId.importing").also { it.deleteRecursively(); it.mkdirs() }
                val root = staging!!.canonicalFile
                for (entry in entries) {
                    if (cancelled()) return ImportResult.Cancelled
                    val target = File(root, entry.name).canonicalFile
                    require(target.path.startsWith(root.path + File.separator))
                    if (entry.isDirectory) target.mkdirs() else {
                        target.parentFile?.mkdirs()
                        zip.getInputStream(entry).use { input -> FileOutputStream(target).use { input.copyTo(it); it.fd.sync() } }
                    }
                }
                require(staging!!.renameTo(destination)) { "atomic publish failed" }
                destination.walkBottomUp().forEach { it.setWritable(false, false) }
                ImportResult.Imported(packageFrom(manifest, destination, storyId, contentHash))
            }
        } catch (_: Exception) {
            ImportResult.Invalid(listOf("PACKAGE_IMPORT_FAILED"))
        } finally { staging?.takeIf { it.exists() }?.deleteRecursively() }
    }

    /** UI compatibility; callers needing diagnostics use [importValidated]. */
    fun import(filePath: String): StoryPackage? = when (val result = importValidated(filePath)) {
        is ImportResult.Imported -> result.story
        is ImportResult.AlreadyImported -> result.story
        else -> null
    }

    fun load(storyId: String): StoryPackage? = runCatching {
        val dir = File(library, storyId); val manifest = gson.fromJson(File(dir, "manifest.json").reader(), Map::class.java)
        packageFrom(manifest, dir, storyId, manifest["content_hash"] as String)
    }.getOrNull()
    fun listStories() = library.listFiles()?.filter { it.isDirectory && !it.name.startsWith('.') }
        ?.mapNotNull { load(it.name) }?.sortedBy { it.title }.orEmpty()
    fun delete(storyId: String, deleteLocalData: Boolean = false): Boolean {
        val deleted = File(library, storyId).also { it.walk().forEach { file -> file.setWritable(true) } }.deleteRecursively()
        if (deleteLocalData) File(context.filesDir, "saves/$storyId").deleteRecursively()
        return deleted
    }

    private fun packageFrom(m: Map<*, *>, dir: File, id: String, hash: String) = StoryPackage(
        id, m["title"] as? String ?: id, (m["master_seed"] as? Double)?.toLong() ?: 0,
        hash, m["entry_node"] as String, dir)

}
