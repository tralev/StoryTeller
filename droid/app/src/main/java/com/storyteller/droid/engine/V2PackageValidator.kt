package com.storyteller.droid.engine

import com.google.gson.Gson
import java.io.File
import java.io.InputStream
import java.security.MessageDigest
import java.text.Normalizer
import java.util.zip.ZipFile

/** Context-free validation of the exact archive bytes supplied by the user. */
object V2PackageValidator {
    private const val MAX_ENTRIES = 100_000
    private const val MAX_ENTRY_BYTES = 4L * 1024 * 1024 * 1024
    private const val MAX_RATIO = 1_000.0
    private val gson = Gson()

    data class Result(
        val accepted: Boolean,
        val issueCodes: List<String> = emptyList(),
        val manifest: Map<*, *>? = null,
        val requiredBytes: Long = 0,
    )

    fun validate(source: File): Result {
        if (!source.isFile) return invalid("PACKAGE_NOT_FOUND")
        return try {
            ZipFile(source).use { zip ->
                val entries = zip.entries().asSequence().toList()
                safetyCode(entries.map { ZipMeta(it.name, it.size, it.compressedSize) })
                    ?.let { return invalid(it) }
                val manifestEntry = zip.getEntry("manifest.json")
                    ?: return invalid("PACKAGE_MISSING_MANIFEST")
                val manifest = gson.fromJson(zip.getInputStream(manifestEntry).reader(), Map::class.java)
                val version = (manifest["package_version"] as? Double)?.toInt() ?: 0
                if (version != 2 || manifest["package_format"] != "storyteller.story") {
                    return invalid("PACKAGE_UNSUPPORTED_VERSION", manifest)
                }
                if (manifest["story_id"] !is String || manifest["content_hash"] !is String) {
                    return invalid("PACKAGE_IDENTITY", manifest)
                }
                inventoryCode(zip, manifest, entries.map { it.name }.toSet())
                    ?.let { return invalid(it, manifest) }
                Result(true, manifest = manifest, requiredBytes = entries.sumOf { maxOf(0L, it.size) })
            }
        } catch (_: Exception) {
            invalid("PACKAGE_INVALID_ZIP")
        }
    }

    private fun invalid(code: String, manifest: Map<*, *>? = null) =
        Result(false, listOf(code), manifest)

    private data class ZipMeta(val name: String, val size: Long, val compressed: Long)

    private fun safetyCode(entries: List<ZipMeta>): String? {
        if (entries.size > MAX_ENTRIES) return "PACKAGE_ENTRY_LIMIT"
        val seen = mutableSetOf<String>()
        val portable = mutableSetOf<String>()
        for (entry in entries) {
            val parts = entry.name.removeSuffix("/").split('/')
            if (entry.name.isEmpty() || '\u0000' in entry.name || '\\' in entry.name ||
                entry.name.startsWith('/') || parts.any { it.isEmpty() || it == "." || it == ".." }
            ) return "PACKAGE_UNSAFE_PATH"
            val normalized = Normalizer.normalize(entry.name, Normalizer.Form.NFC).lowercase()
            if (!seen.add(entry.name) || !portable.add(normalized)) return "PACKAGE_DUPLICATE_PATH"
            if (entry.size > MAX_ENTRY_BYTES) return "PACKAGE_SIZE_LIMIT"
            if (entry.size > 0 && (entry.compressed <= 0 || entry.size.toDouble() / entry.compressed > MAX_RATIO)) {
                return "PACKAGE_COMPRESSION_LIMIT"
            }
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun inventoryCode(zip: ZipFile, manifest: Map<*, *>, names: Set<String>): String? {
        if (names.any { it.startsWith("save/") || it.startsWith("content/") }) return "PACKAGE_FORBIDDEN_ENTRY"
        val artifacts = manifest["artifacts"] as? List<Map<String, Any>> ?: return "PACKAGE_INVENTORY"
        val artifactIds = artifacts.mapNotNull { it["artifact_id"] as? String }.toSet()
        val declared = mutableSetOf("manifest.json")
        for (item in artifacts) {
            val path = item["path"] as? String ?: return "PACKAGE_INVENTORY"
            val expected = item["sha256"] as? String ?: return "PACKAGE_INVENTORY"
            val entry = zip.getEntry(path) ?: return "PACKAGE_MISSING_ARTIFACT"
            if (zip.getInputStream(entry).use(::digest) != expected ||
                (item["size_bytes"] as? Double)?.toLong() != entry.size
            ) return "PACKAGE_HASH_MISMATCH"
            declared += path
        }
        if (artifacts.any { item ->
                (item["depends_on"] as? List<*>)?.any { dependency -> dependency !in artifactIds } == true
            }
        ) return "PACKAGE_PROVENANCE_BROKEN"
        if (declared != names) return "PACKAGE_UNDECLARED_ENTRY"
        val required = setOf(
            "world/index.json", "narrative/bible.json", "narrative/graph.json",
            "narrative/gm_index.json", "assets/maps/world.png",
        )
        return if (required.all(names::contains)) null else "PACKAGE_LAYOUT_MISSING"
    }

    private fun digest(input: InputStream): String {
        val md = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(64 * 1024)
        while (true) {
            val count = input.read(buffer)
            if (count < 0) break
            md.update(buffer, 0, count)
        }
        return md.digest().joinToString("") { "%02x".format(it) }
    }
}
