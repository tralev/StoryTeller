package com.storyteller.droid.engine

import com.google.gson.Gson
import com.google.gson.JsonElement
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.gson.stream.JsonReader
import com.google.gson.stream.JsonToken
import java.io.File
import java.io.InputStream
import java.io.InputStreamReader
import java.io.PushbackInputStream
import java.io.RandomAccessFile
import java.math.BigInteger
import java.nio.charset.CodingErrorAction
import java.security.MessageDigest
import java.text.Normalizer
import java.util.zip.ZipFile
import java.util.zip.CRC32
import java.util.zip.Inflater

/** Context-free validation of the exact archive bytes supplied by the user.
 *
 * P8.C2 — Three-validator parity: matches Python validate_v2_package and
 * Swift V2PackageValidator on acceptance stages: safety, manifest, inventory,
 * provenance, layout, and content identity.
 */
object V2PackageValidator {
    private const val MAX_ENTRIES = 100_000
    private const val MAX_ENTRY_BYTES = 4L * 1024 * 1024 * 1024
    private const val MAX_TOTAL_BYTES = 32L * 1024 * 1024 * 1024 * 1024
    private const val MAX_RATIO = 1_000.0
    private val gson = Gson()

    fun hasExtractionSpace(requiredBytes: Long, freeBytes: Long): Boolean {
        require(requiredBytes >= 0 && freeBytes >= 0) { "extraction byte counts must be non-negative" }
        return freeBytes >= requiredBytes
    }

    data class Result(
        val accepted: Boolean,
        val issueCodes: List<String> = emptyList(),
        val manifest: Map<*, *>? = null,
        val requiredBytes: Long = 0,
    )

    // P8.C2: frozen ordered acceptance stages matching Python/Swift
    fun validate(source: File): Result {
        if (!source.isFile) return invalid("PACKAGE_NOT_FOUND")
        return try {
            ZipFile(source).use { zip ->
                val entries = zip.entries().asSequence().toList()
                val names = entries.map { it.name }.toSet()
                // Stage 1: central-directory safety
                if (entries.map { it.name } !=
                    entries.map { it.name }.sortedWith(Comparator(::compareUtf8))
                ) {
                    return invalid("PACKAGE_PATH_ORDER")
                }
                safetyCode(entries.map { ZipMeta(it.name, it.size, it.compressedSize) })
                    ?.let { return invalid(it) }
                centralDirectoryCode(source)?.let { return invalid(it) }
                secondaryCompressionCode(zip, entries.map { it.name })
                    ?.let { return invalid(it) }
                jsonEncodingCode(zip, entries.map { it.name })
                    ?.let { return invalid(it) }
                jsonDepthCode(zip, entries.map { it.name })
                    ?.let { return invalid(it) }
                jsonProfileCode(zip, entries.map { it.name })
                    ?.let { return invalid(it) }
                // Stage 2: manifest existence, format, version
                val manifestEntry = zip.getEntry("manifest.json")
                    ?: return invalid("PACKAGE_MISSING_MANIFEST")
                val manifest = gson.fromJson(zip.getInputStream(manifestEntry).reader(), Map::class.java)
                val versionNumber = manifest["package_version"] as? Double
                    ?: return invalid("PACKAGE_TYPE_COERCION", manifest)
                if (versionNumber != versionNumber.toInt().toDouble()) {
                    return invalid("PACKAGE_TYPE_COERCION", manifest)
                }
                val version = versionNumber.toInt()
                if (version != 2) {
                    return invalid("PACKAGE_UNSUPPORTED_VERSION", manifest)
                }
                val format = manifest["package_format"] as? String
                    ?: return invalid("PACKAGE_TYPE_COERCION", manifest)
                if (format != "storyteller.story") return invalid("PACKAGE_UNSUPPORTED_VERSION", manifest)
                canonicalJSONCode(zip, entries.map { it.name })
                    ?.let { return invalid(it, manifest) }
                featureCode(manifest)?.let { return invalid(it, manifest) }
                if (!TrustedJSONSchema.validates(
                        "manifest", zip.getInputStream(manifestEntry).use { it.readBytes() }
                    )
                ) return invalid("PACKAGE_SCHEMA", manifest)
                if (manifest["story_id"] !is String || manifest["content_hash"] !is String) {
                    return invalid("PACKAGE_IDENTITY", manifest)
                }
                // Stage 3: declared member inventory and internal hashes
                inventoryCode(zip, manifest, names)
                    ?.let { return invalid(it, manifest) }
                sourceCoverageCode(zip, names)?.let { return invalid(it, manifest) }
                physicalLayerCode(zip)?.let { return invalid(it, manifest) }
                gridDomainCode(zip, names)?.let { return invalid(it, manifest) }
                climateLayerCode(zip)?.let { return invalid(it, manifest) }
                regionSiteCode(zip)?.let { return invalid(it, manifest) }
                routeTopologyCode(zip, manifest)?.let { return invalid(it, manifest) }
                hydrologyCatalogCode(zip)?.let { return invalid(it, manifest) }
                resourceGeologyCode(zip, manifest)?.let { return invalid(it, manifest) }
                civilizationCode(zip)?.let { return invalid(it, manifest) }
                eventOrderCode(zip)?.let { return invalid(it, manifest) }
                snapshotCode(zip, manifest)?.let { return invalid(it, manifest) }
                historyReplayCode(zip)?.let { return invalid(it, manifest) }
                storyGraphCode(zip, manifest)?.let { return invalid(it, manifest) }
                narrativeAuthorityCode(zip, manifest)?.let { return invalid(it, manifest) }
                gmCoverageCode(zip, manifest)?.let { return invalid(it, manifest) }
                structuredScoreCode(zip, manifest)?.let { return invalid(it, manifest) }
                pngProfileCode(zip, manifest)?.let { return invalid(it, manifest) }
                // Stage 4: layout, node assets, entry node, region maps
                layoutCode(manifest, names)
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

    private fun compareUtf8(left: String, right: String): Int {
        val leftBytes = left.toByteArray(Charsets.UTF_8)
        val rightBytes = right.toByteArray(Charsets.UTF_8)
        for (index in 0 until minOf(leftBytes.size, rightBytes.size)) {
            val difference = (leftBytes[index].toInt() and 0xff) -
                (rightBytes[index].toInt() and 0xff)
            if (difference != 0) return difference
        }
        return leftBytes.size - rightBytes.size
    }

    private fun secondaryCompressionCode(zip: ZipFile, names: List<String>): String? {
        for (name in names.filter { it.endsWith(".bin") }) {
            val entry = zip.getEntry(name) ?: return "PACKAGE_MISSING_ARTIFACT"
            val prefix = zip.getInputStream(entry).use { input ->
                val buffer = ByteArray(8)
                val count = input.read(buffer)
                if (count < 0) ByteArray(0) else buffer.copyOf(count)
            }
            if (SECONDARY_SIGNATURES.any { signature ->
                    prefix.size >= signature.size &&
                        signature.indices.all { prefix[it] == signature[it] }
                }
            ) {
                return "PACKAGE_SECONDARY_COMPRESSION"
            }
        }
        return null
    }

    private fun jsonDepthCode(zip: ZipFile, names: List<String>): String? {
        for (name in names.filter { it.endsWith(".json") }) {
            val entry = zip.getEntry(name) ?: return "PACKAGE_MISSING_ARTIFACT"
            var depth = 0
            var inString = false
            var escaped = false
            zip.getInputStream(entry).use { input ->
                while (true) {
                    val value = input.read()
                    if (value < 0) break
                    if (inString) {
                        if (escaped) escaped = false
                        else if (value == '\\'.code) escaped = true
                        else if (value == '"'.code) inString = false
                    } else if (value == '"'.code) inString = true
                    else if (value == '{'.code || value == '['.code) {
                        depth++
                        if (depth > MAX_JSON_DEPTH) return "PACKAGE_JSON_DEPTH"
                    } else if (value == '}'.code || value == ']'.code) depth--
                }
            }
        }
        return null
    }

    private fun jsonEncodingCode(zip: ZipFile, names: List<String>): String? {
        for (name in names.filter { it.endsWith(".json") }) {
            val entry = zip.getEntry(name) ?: return "PACKAGE_MISSING_ARTIFACT"
            try {
                PushbackInputStream(zip.getInputStream(entry), 3).use { input ->
                    val prefix = ByteArray(3)
                    val count = input.read(prefix)
                    if (count > 0) input.unread(prefix, 0, count)
                    val bom = byteArrayOf(0xef.toByte(), 0xbb.toByte(), 0xbf.toByte())
                    if (count == 3 && prefix.contentEquals(bom)) return "PACKAGE_JSON_BOM"
                    val decoder = Charsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                    InputStreamReader(input, decoder).use { reader ->
                        val buffer = CharArray(64 * 1024)
                        while (reader.read(buffer) >= 0) { /* strict streaming decode */ }
                    }
                }
            } catch (_: Exception) {
                return "PACKAGE_JSON_UTF8"
            }
        }
        return null
    }

    private class DuplicateJSONKey : Exception()
    private class JSONNumberProfile : Exception()
    private class JSONNumberRange : Exception()

    private fun jsonProfileCode(zip: ZipFile, names: List<String>): String? {
        for (name in names.filter { it.endsWith(".json") }) {
            val entry = zip.getEntry(name) ?: return "PACKAGE_MISSING_ARTIFACT"
            try {
                zip.getInputStream(entry).use { input ->
                    val decoder = Charsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                    JsonReader(InputStreamReader(input, decoder)).use { reader ->
                        reader.isLenient = false
                        readJSONValue(reader)
                        if (reader.peek() != JsonToken.END_DOCUMENT) {
                            return "PACKAGE_INVALID_JSON"
                        }
                    }
                }
            } catch (_: DuplicateJSONKey) {
                return "PACKAGE_JSON_DUPLICATE_KEY"
            } catch (_: JSONNumberProfile) {
                return "PACKAGE_NUMBER_PROFILE"
            } catch (_: JSONNumberRange) {
                return "PACKAGE_NUMBER_RANGE"
            } catch (_: Exception) {
                return "PACKAGE_INVALID_JSON"
            }
        }
        return null
    }

    private fun readJSONValue(reader: JsonReader) {
        when (reader.peek()) {
            JsonToken.BEGIN_OBJECT -> {
                reader.beginObject()
                val keys = mutableSetOf<String>()
                while (reader.hasNext()) {
                    if (!keys.add(reader.nextName())) throw DuplicateJSONKey()
                    readJSONValue(reader)
                }
                reader.endObject()
            }
            JsonToken.BEGIN_ARRAY -> {
                reader.beginArray()
                while (reader.hasNext()) readJSONValue(reader)
                reader.endArray()
            }
            JsonToken.STRING -> reader.nextString()
            JsonToken.NUMBER -> {
                val number = reader.nextString()
                if (!INTEGER_PATTERN.matches(number)) throw JSONNumberProfile()
                val parsed = try { BigInteger(number) } catch (_: Exception) {
                    throw JSONNumberProfile()
                }
                if (parsed.abs() > MAX_SAFE_INTEGER) throw JSONNumberRange()
            }
            JsonToken.BOOLEAN -> reader.nextBoolean()
            JsonToken.NULL -> reader.nextNull()
            else -> reader.skipValue()
        }
    }

    private fun canonicalJSONCode(zip: ZipFile, names: List<String>): String? {
        for (name in names.filter { it.endsWith(".json") }) {
            val entry = zip.getEntry(name) ?: return "PACKAGE_MISSING_ARTIFACT"
            val data = zip.getInputStream(entry).use { it.readBytes() }
            val value = try {
                JsonParser.parseString(data.toString(Charsets.UTF_8))
            } catch (_: Exception) {
                return "PACKAGE_INVALID_JSON"
            }
            if (!canonicalJSON(value).contentEquals(data)) return "PACKAGE_JSON_NONCANONICAL"
        }
        return null
    }

    private fun canonicalJSON(value: JsonElement): ByteArray {
        fun appendString(text: String, output: StringBuilder) {
            output.append('"')
            for (character in text) {
                when (character) {
                    '"' -> output.append("\\\"")
                    '\\' -> output.append("\\\\")
                    '\b' -> output.append("\\b")
                    '\t' -> output.append("\\t")
                    '\n' -> output.append("\\n")
                    '\u000c' -> output.append("\\f")
                    '\r' -> output.append("\\r")
                    else -> if (character.code < 0x20) {
                        output.append("\\u").append(character.code.toString(16).padStart(4, '0'))
                    } else {
                        output.append(character)
                    }
                }
            }
            output.append('"')
        }

        fun appendValue(element: JsonElement, output: StringBuilder) {
            when {
                element.isJsonObject -> {
                    output.append('{')
                    element.asJsonObject.entrySet().sortedBy { it.key }.forEachIndexed { index, item ->
                        if (index > 0) output.append(',')
                        appendString(item.key, output)
                        output.append(':')
                        appendValue(item.value, output)
                    }
                    output.append('}')
                }
                element.isJsonArray -> {
                    output.append('[')
                    element.asJsonArray.forEachIndexed { index, child ->
                        if (index > 0) output.append(',')
                        appendValue(child, output)
                    }
                    output.append(']')
                }
                element.isJsonNull -> output.append("null")
                element.asJsonPrimitive.isString -> appendString(element.asString, output)
                element.asJsonPrimitive.isBoolean -> output.append(element.asBoolean)
                else -> output.append(BigInteger(element.asString).toString())
            }
        }

        return buildString { appendValue(value, this) }.toByteArray(Charsets.UTF_8)
    }

    private fun featureCode(manifest: Map<*, *>): String? {
        val required = (manifest["required_features"] as? List<*>)?.map {
            it as? String ?: return "PACKAGE_REQUIRED_FEATURE"
        } ?: return "PACKAGE_REQUIRED_FEATURE"
        val optional = (manifest["optional_features"] as? List<*>)?.map {
            it as? String ?: return "PACKAGE_OPTIONAL_FEATURE"
        } ?: return "PACKAGE_OPTIONAL_FEATURE"
        if (required != required.distinct().sorted() || optional != optional.distinct().sorted()) {
            return "PACKAGE_FEATURE_ORDER"
        }
        if (required != REQUIRED_FEATURES) return "PACKAGE_REQUIRED_FEATURE"
        if (optional.isNotEmpty()) return "PACKAGE_OPTIONAL_FEATURE"
        return null
    }

    /** Read Unix mode bits that java.util.zip.ZipEntry does not expose on Android. */
    private fun centralDirectoryCode(source: File): String? = RandomAccessFile(source, "r").use { file ->
        val eocd = findEndOfCentralDirectory(file)
        if (file.u16(eocd + 20) != 0) return@use "PACKAGE_ZIP_METADATA"
        var entryCount = file.u16(eocd + 10).toLong()
        var centralOffset = file.u32(eocd + 16)
        if (entryCount == 0xffffL || centralOffset == 0xffff_ffffL) {
            val locator = eocd - 20
            require(locator >= 0 && file.u32(locator) == ZIP64_LOCATOR)
            val zip64 = file.u64(locator + 8)
            require(file.u32(zip64) == ZIP64_END)
            entryCount = file.u64(zip64 + 32)
            centralOffset = file.u64(zip64 + 48)
        }
        require(entryCount <= MAX_ENTRIES.toLong())
        var cursor = centralOffset
        repeat(entryCount.toInt()) {
            require(file.u32(cursor) == CENTRAL_HEADER)
            val madeBy = file.u16(cursor + 4)
            val hostSystem = madeBy ushr 8
            val compressionMethod = file.u16(cursor + 10)
            val modifiedTime = file.u16(cursor + 12)
            val modifiedDate = file.u16(cursor + 14)
            val externalAttributes = file.u32(cursor + 38)
            val unixMode = (externalAttributes ushr 16).toInt()
            if (hostSystem == UNIX_HOST && unixMode and FILE_TYPE_MASK == SYMLINK_TYPE) {
                return@use "PACKAGE_LINK"
            }
            val nameLength = file.u16(cursor + 28)
            val extraLength = file.u16(cursor + 30)
            val commentLength = file.u16(cursor + 32)
            val nameBytes = ByteArray(nameLength)
            file.seek(cursor + 46)
            file.readFully(nameBytes)
            val name = nameBytes.toString(Charsets.UTF_8)
            val expectedCompression = if (name.endsWith(".png")) ZIP_STORED else ZIP_DEFLATED
            if (hostSystem != UNIX_HOST || unixMode and FILE_TYPE_MASK != REGULAR_TYPE ||
                unixMode and PERMISSION_MASK != CANONICAL_PERMISSIONS || modifiedTime != 0 ||
                modifiedDate != CANONICAL_DOS_DATE || extraLength != 0 || commentLength != 0 ||
                compressionMethod != expectedCompression
            ) return@use "PACKAGE_ZIP_METADATA"
            cursor += 46L + nameLength + extraLength + commentLength
            require(cursor <= file.length())
        }
        null
    }

    private fun findEndOfCentralDirectory(file: RandomAccessFile): Long {
        val lowerBound = maxOf(0L, file.length() - MAX_END_SEARCH)
        var cursor = file.length() - 22
        while (cursor >= lowerBound) {
            if (file.u32(cursor) == END_HEADER) return cursor
            cursor--
        }
        error("ZIP end-of-central-directory record is missing")
    }

    private fun RandomAccessFile.u16(offset: Long): Int {
        seek(offset)
        return readUnsignedByte() or (readUnsignedByte() shl 8)
    }

    private fun RandomAccessFile.u32(offset: Long): Long =
        u16(offset).toLong() or (u16(offset + 2).toLong() shl 16)

    private fun RandomAccessFile.u64(offset: Long): Long =
        u32(offset) or (u32(offset + 4) shl 32)

    private const val END_HEADER = 0x0605_4b50L
    private const val CENTRAL_HEADER = 0x0201_4b50L
    private const val ZIP64_END = 0x0606_4b50L
    private const val ZIP64_LOCATOR = 0x0706_4b50L
    private const val MAX_END_SEARCH = 65_557L
    private const val UNIX_HOST = 3
    private const val FILE_TYPE_MASK = 0xf000
    private const val SYMLINK_TYPE = 0xa000
    private const val REGULAR_TYPE = 0x8000
    private const val PERMISSION_MASK = 0x01ff
    private const val CANONICAL_PERMISSIONS = 0x01a4
    private const val CANONICAL_DOS_DATE = 0x0021
    private const val ZIP_STORED = 0
    private const val ZIP_DEFLATED = 8
    private const val MAX_JSON_DEPTH = 128
    private val INTEGER_PATTERN = Regex("-?(0|[1-9][0-9]*)")
    private val MAX_SAFE_INTEGER = BigInteger("9007199254740991")
    private val REQUIRED_FEATURES = listOf(
        "all_site_local_maps", "complete_history", "complete_world", "embedded_schemas",
        "fixed_media_profile", "structured_score_midi",
    )
    private val FORBIDDEN_SUFFIXES = listOf(
        ".app", ".apk", ".bat", ".cmd", ".dll", ".dylib", ".exe", ".gguf",
        ".html", ".htm", ".jar", ".js", ".model", ".safetensors", ".sh", ".so",
    )
    private val REQUIRED_SOURCE_KINDS = listOf(
        "biome_grid_catalog", "biomes", "civilizations", "climate", "climate_grid_catalog",
        "ecology", "economy", "genealogy", "geology", "geology_grid_catalog", "history",
        "hydrology", "hydrology_grid_catalog", "identities", "legendary_artifact_histories",
        "legendary_artifacts", "map_layers", "maps", "megabeasts", "plates", "reference_index",
        "region_grid_catalog", "regions", "registries", "resource_grid_catalog", "resources",
        "routes", "settlements", "simulation_index", "sites", "snapshots", "soil",
        "soil_grid_catalog", "spatial_index", "species", "terrain", "terrain_grid_catalog",
        "validation_report", "world_index",
    )
    private val CLIMATE_SEASON_FIELDS = listOf(
        "temperature_millic", "precipitation_mm", "evaporation_mm", "snowpack_mm", "ice",
        "storm_ppm", "wind_x_mmps", "wind_y_mmps", "hazard_ppm",
    )
    private val SECONDARY_SIGNATURES = listOf(
        byteArrayOf(0x1f, 0x8b.toByte()),
        byteArrayOf(0x42, 0x5a, 0x68),
        byteArrayOf(0xfd.toByte(), 0x37, 0x7a, 0x58, 0x5a, 0x00),
        byteArrayOf(0x28, 0xb5.toByte(), 0x2f, 0xfd.toByte()),
        byteArrayOf(0x50, 0x4b, 0x03, 0x04),
        byteArrayOf(0x04, 0x22, 0x4d, 0x18),
    )

    private fun safetyCode(entries: List<ZipMeta>): String? {
        if (entries.size > MAX_ENTRIES) return "PACKAGE_ENTRY_LIMIT"
        val seen = mutableSetOf<String>()
        val portable = mutableSetOf<String>()
        var totalBytes = 0L
        for (entry in entries) {
            val parts = entry.name.removeSuffix("/").split('/')
            if (entry.name.isEmpty() || '\u0000' in entry.name || '\\' in entry.name ||
                entry.name.startsWith('/') || parts.any { it.isEmpty() || it == "." || it == ".." }
            ) return "PACKAGE_UNSAFE_PATH"
            val normalized = Normalizer.normalize(entry.name, Normalizer.Form.NFC).lowercase()
            if (!seen.add(entry.name) || !portable.add(normalized)) return "PACKAGE_DUPLICATE_PATH"
            if (forbiddenMember(entry.name)) return "PACKAGE_FORBIDDEN_ENTRY"
            if (entry.size > MAX_ENTRY_BYTES) return "PACKAGE_SIZE_LIMIT"
            if (entry.size < 0 || totalBytes > MAX_TOTAL_BYTES - entry.size) {
                return "PACKAGE_SIZE_LIMIT"
            }
            totalBytes += entry.size
            if (entry.size > 0 && (entry.compressed <= 0 || entry.size.toDouble() / entry.compressed > MAX_RATIO)) {
                return "PACKAGE_COMPRESSION_LIMIT"
            }
        }
        return null
    }

    private fun forbiddenMember(path: String): Boolean {
        val lowered = path.lowercase()
        return path == "save" || path.startsWith("save/") || path.startsWith("content/") ||
            FORBIDDEN_SUFFIXES.any(lowered::endsWith)
    }

    @Suppress("UNCHECKED_CAST")
    private fun inventoryCode(zip: ZipFile, manifest: Map<*, *>, names: Set<String>): String? {
        val artifacts = manifest["artifacts"] as? List<Map<String, Any>> ?: return "PACKAGE_INVENTORY"
        if (artifacts.map { it["path"] as? String } !=
            artifacts.sortedWith(compareByUtf8Path()).map { it["path"] as? String }) {
            return "PACKAGE_ARRAY_ORDER"
        }
        val artifactIds = artifacts.mapNotNull { it["artifact_id"] as? String }.toSet()
        if (artifactIds.size != artifacts.size) return "PACKAGE_DUPLICATE_ID"
        val artifactPaths = artifacts.mapNotNull { it["path"] as? String }.toSet()
        if (artifactPaths.size != artifacts.size) return "PACKAGE_DUPLICATE_ID"
        val declared = mutableSetOf("manifest.json")
        for (item in artifacts) {
            val path = item["path"] as? String ?: return "PACKAGE_INVENTORY"
            val expected = item["sha256"] as? String ?: return "PACKAGE_INVENTORY"
            val entry = zip.getEntry(path) ?: return "PACKAGE_MISSING_ARTIFACT"
            if (zip.getInputStream(entry).use(::digest) != expected ||
                (item["size_bytes"] as? Double)?.toLong() != entry.size
            ) return "PACKAGE_HASH_MISMATCH"
            val producer = item["producer"] as? Map<*, *> ?: return "PACKAGE_PRODUCER"
            if (producer["schema_sha256"] != TrustedV2Schemas.digest) {
                return "PACKAGE_SCHEMA_IDENTITY"
            }
            declared += path
        }
        if (artifacts.any { item ->
                (item["depends_on"] as? List<*>)?.any { dependency -> dependency !in artifactIds } == true
            }
        ) return "PACKAGE_PROVENANCE_BROKEN"
        if (hasDependencyCycle(artifacts)) return "PACKAGE_PROVENANCE_CYCLE"
        for (item in artifacts) {
            val kind = item["kind"] as? String ?: return "PACKAGE_INVENTORY"
            val producer = item["producer"] as? Map<*, *> ?: return "PACKAGE_PRODUCER"
            val fingerprint = producer["fingerprint"] as? String ?: return "PACKAGE_PRODUCER"
            @Suppress("UNCHECKED_CAST")
            val dependencies = item["depends_on"] as? List<String> ?: return "PACKAGE_INVENTORY"
            val identity = JsonObject().apply {
                add("depends_on", JsonArray().also { array -> dependencies.sorted().forEach(array::add) })
                addProperty("kind", kind)
                addProperty("producer_fingerprint", fingerprint)
                addProperty("sha256", item["sha256"] as String)
            }
            val prefix = kind.lowercase().filter { it in 'a'..'z' || it in '0'..'9' }
            val expectedId = "${prefix}_${digest(canonicalJSON(identity).inputStream()).take(32)}"
            if (item["artifact_id"] != expectedId) return "PACKAGE_ARTIFACT_ID"
        }
        val reduced = JsonArray()
        for (item in artifacts.sortedWith(compareByUtf8Path())) {
            @Suppress("UNCHECKED_CAST")
            val dependencies = item["depends_on"] as List<String>
            val producer = item["producer"] as Map<*, *>
            reduced.add(JsonObject().apply {
                addProperty("artifact_id", item["artifact_id"] as String)
                add("depends_on", JsonArray().also { array -> dependencies.sorted().forEach(array::add) })
                addProperty("kind", item["kind"] as String)
                addProperty("path", item["path"] as String)
                addProperty("producer_fingerprint", producer["fingerprint"] as String)
                addProperty("sha256", item["sha256"] as String)
                addProperty("size_bytes", (item["size_bytes"] as Double).toLong())
            })
        }
        val contentHash = digest(canonicalJSON(reduced).inputStream())
        if (manifest["content_hash"] != contentHash ||
            manifest["story_id"] != "story_${contentHash.take(32)}"
        ) return "PACKAGE_CONTENT_ID"
        if (declared != names) return "PACKAGE_UNDECLARED_ENTRY"
        return null
    }

    private fun compareByUtf8Path() = Comparator<Map<String, Any>> { left, right ->
        compareUtf8(left["path"] as String, right["path"] as String)
    }

    @Suppress("UNCHECKED_CAST")
    private fun sourceCoverageCode(zip: ZipFile, names: Set<String>): String? {
        val coveragePath = "world/source/coverage.json"
        val coverageEntry = zip.getEntry(coveragePath) ?: return "PACKAGE_WORLD_SOURCE_COVERAGE"
        val ledger = gson.fromJson(zip.getInputStream(coverageEntry).reader(), Map::class.java)
        val required = ledger["required_domains"] as? List<String>
            ?: return "PACKAGE_WORLD_SOURCE_COVERAGE"
        if (ledger["format"] != "storyteller.world-source-coverage.v1" ||
            required != REQUIRED_SOURCE_KINDS
        ) return "PACKAGE_WORLD_SOURCE_COVERAGE"
        val sourcePaths = names.filterTo(mutableSetOf()) {
            it.startsWith("world/source/") && it.endsWith(".json") && it != coveragePath
        }
        val rows = ledger["sources"] as? List<Map<String, Any>>
            ?: return "PACKAGE_WORLD_SOURCE_COVERAGE"
        val rowPaths = rows.mapNotNull { it["archive_path"] as? String }
        if (rowPaths.size != rowPaths.toSet().size || rowPaths.toSet() != sourcePaths) {
            return "PACKAGE_WORLD_SOURCE_COVERAGE"
        }
        val worldEntry = zip.getEntry("world/index.json") ?: return "PACKAGE_WORLD_SOURCE_COVERAGE"
        val world = gson.fromJson(zip.getInputStream(worldEntry).reader(), Map::class.java)
        val domains = world["domains"] as? List<String> ?: return "PACKAGE_WORLD_SOURCE_COVERAGE"
        val sourceNames = sourcePaths.mapTo(mutableSetOf()) {
            it.substringAfterLast('/').removeSuffix(".json")
        }
        if (domains.toSet() != sourceNames || !domains.containsAll(REQUIRED_SOURCE_KINDS)) {
            return "PACKAGE_WORLD_SOURCE_COVERAGE"
        }
        for (row in rows) {
            val path = row["archive_path"] as? String ?: return "PACKAGE_WORLD_SOURCE_COVERAGE"
            val entry = zip.getEntry(path) ?: return "PACKAGE_WORLD_SOURCE_COVERAGE"
            val data = zip.getInputStream(entry).use { it.readBytes() }
            val envelope = gson.fromJson(data.toString(Charsets.UTF_8), Map::class.java)
            if (row["source_name"] != path.substringAfterLast('/').removeSuffix(".json") ||
                row["retention"] != "byte_for_byte" ||
                (row["size_bytes"] as? Double)?.toLong() != data.size.toLong() ||
                row["sha256"] != digest(data.inputStream()) ||
                row["artifact_id"] != envelope["artifact_id"]
            ) return "PACKAGE_WORLD_SOURCE_COVERAGE"
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun gridDomainCode(zip: ZipFile, names: Set<String>): String? {
        for (domain in listOf(
            "terrain", "geology", "hydrology", "climate", "biomes", "resource_grid",
        )) {
            val indexPath = "world/$domain/index.json"
            val entry = zip.getEntry(indexPath) ?: return "PACKAGE_GRID_DOMAIN"
            val index = gson.fromJson(zip.getInputStream(entry).reader(), Map::class.java)
            if (index["format"] != "storyteller.grid-domain-index.v1") return "PACKAGE_GRID_DOMAIN"
            val width = (index["width"] as? Double)?.toInt() ?: return "PACKAGE_GRID_DOMAIN"
            val height = (index["height"] as? Double)?.toInt() ?: return "PACKAGE_GRID_DOMAIN"
            val layers = index["layers"] as? Map<String, Map<String, Any>>
                ?: return "PACKAGE_GRID_DOMAIN"
            if (layers.isEmpty()) return "PACKAGE_GRID_DOMAIN"
            for ((layer, layerIndex) in layers) {
                val chunkWidth = (layerIndex["chunk_width"] as? Double)?.toInt()
                    ?: return "PACKAGE_GRID_DOMAIN"
                val chunkHeight = (layerIndex["chunk_height"] as? Double)?.toInt()
                    ?: return "PACKAGE_GRID_DOMAIN"
                if (chunkWidth !in 1..256 || chunkHeight !in 1..256) return "PACKAGE_GRID_DOMAIN"
                val descriptors = layerIndex["chunks"] as? List<Map<String, Any>>
                    ?: return "PACKAGE_GRID_DOMAIN"
                val expected = mutableListOf<List<Int>>()
                for (y in 0 until height step chunkHeight) for (x in 0 until width step chunkWidth) {
                    expected += listOf(
                        y / chunkHeight, x / chunkWidth,
                        minOf(chunkWidth, width - x), minOf(chunkHeight, height - y),
                    )
                }
                val actual = descriptors.map {
                    listOf(
                        (it["chunk_y"] as Double).toInt(), (it["chunk_x"] as Double).toInt(),
                        (it["width"] as Double).toInt(), (it["height"] as Double).toInt(),
                    )
                }
                if (actual != expected) return "PACKAGE_GRID_DOMAIN"
                for (descriptor in descriptors) {
                    val hash = descriptor["sha256"] as? String ?: return "PACKAGE_GRID_DOMAIN"
                    val path = "world/$domain/chunks/$layer/$hash.bin"
                    if (path !in names) return "PACKAGE_GRID_CHUNK_COVERAGE"
                    val data = zip.getInputStream(zip.getEntry(path)).use { it.readBytes() }
                    if (digest(data.inputStream()) != hash) return "PACKAGE_GRID_CHUNK_HASH"
                    if (!validGridChunk(data, layer, descriptor)) return "PACKAGE_GRID_CHUNK_HASH"
                }
            }
        }
        return null
    }

    private fun validGridChunk(
        data: ByteArray, layer: String, descriptor: Map<String, Any>,
    ): Boolean {
        return try {
        if (data.size < 5) return false
        val headerSize = ((data[0].toInt() and 0xff) shl 24) or
            ((data[1].toInt() and 0xff) shl 16) or
            ((data[2].toInt() and 0xff) shl 8) or (data[3].toInt() and 0xff)
        if (headerSize !in 1..1024 || 4 + headerSize > data.size) return false
        val headerBytes = data.copyOfRange(4, 4 + headerSize)
        val header = JsonParser.parseString(headerBytes.toString(Charsets.UTF_8)).asJsonObject
        if (!canonicalJSON(header).contentEquals(headerBytes) ||
            header["format"].asString != "storyteller.grid.i32be.v1" ||
            header["layer"].asString != layer
        ) return false
        fun number(name: String) = header[name].asInt
        val width = number("width")
        val height = number("height")
        if (width !in 1..256 || height !in 1..256 || data.size != 4 + headerSize + width * height * 4) {
            return false
        }
        number("chunk_x") == (descriptor["chunk_x"] as Double).toInt() &&
            number("chunk_y") == (descriptor["chunk_y"] as Double).toInt() &&
            width == (descriptor["width"] as Double).toInt() &&
            height == (descriptor["height"] as Double).toInt()
        } catch (_: Exception) { false }
    }

    @Suppress("UNCHECKED_CAST")
    private fun climateLayerCode(zip: ZipFile): String? {
        val source = gson.fromJson(
            zip.getInputStream(zip.getEntry("world/source/climate.json")).reader(), Map::class.java,
        )
        val payload = source["payload"] as? Map<String, Any> ?: return "PACKAGE_CLIMATE_LAYERS"
        val seasonCount = (payload["season_count"] as? Double)?.toInt()
            ?: return "PACKAGE_CLIMATE_LAYERS"
        if (seasonCount !in 1..12) return "PACKAGE_CLIMATE_LAYERS"
        val expected = mutableSetOf(
            "climate_annual_temperature_millic", "climate_annual_precipitation_mm",
            "climate_weather_regime",
        )
        for (index in 0 until seasonCount) {
            val prefix = "climate_season_${index.toString().padStart(2, '0')}"
            for (field in CLIMATE_SEASON_FIELDS) expected += "${prefix}_$field"
        }
        val climate = gson.fromJson(
            zip.getInputStream(zip.getEntry("world/climate/index.json")).reader(), Map::class.java,
        )
        val layers = climate["layers"] as? Map<String, Any> ?: return "PACKAGE_CLIMATE_LAYERS"
        return if (layers.keys == expected) null else "PACKAGE_CLIMATE_LAYERS"
    }

    @Suppress("UNCHECKED_CAST")
    private fun physicalLayerCode(zip: ZipFile): String? {
        val expected = mapOf(
            "hydrology" to setOf(
                "hydrology_filled_elevation_mm", "hydrology_flow_to", "hydrology_accumulation",
                "hydrology_watershed_id", "hydrology_coastline", "hydrology_aquifer_capacity_mm",
                "hydrology_salinity_ppm", "hydrology_snowpack_mm", "hydrology_glacier",
                "hydrology_delta",
            ),
            "geology" to setOf(
                "geology_rock_class_id", "geology_strata_id", "geology_parent_material_id",
                "geology_fault", "geology_volcano", "geology_tectonic_relief_mm",
            ),
            "resource_grid" to setOf("resource_renewable_yield"),
        )
        for ((domain, required) in expected) {
            val document = gson.fromJson(
                zip.getInputStream(zip.getEntry("world/$domain/index.json")).reader(), Map::class.java,
            )
            val layers = document["layers"] as? Map<String, Any>
            if (layers?.keys != required) return if (domain == "hydrology") {
                "PACKAGE_HYDROLOGY_CATALOG"
            } else "PACKAGE_RESOURCE_CATALOG"
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun regionSiteCode(zip: ZipFile): String? {
        fun document(path: String) = gson.fromJson(
            zip.getInputStream(zip.getEntry(path)).reader(), Map::class.java,
        ) as Map<String, Any>
        val world = document("world/index.json")
        val width = (world["width"] as? Double)?.toInt() ?: return "PACKAGE_REGION_PARTITION"
        val height = (world["height"] as? Double)?.toInt() ?: return "PACKAGE_REGION_PARTITION"
        if (width < 1 || height < 1) return "PACKAGE_REGION_PARTITION"
        val regions = document("world/regions.json")["regions"] as? List<Map<String, Any>>
            ?: return "PACKAGE_REGION_PARTITION"
        if (regions.isEmpty()) return "PACKAGE_REGION_PARTITION"
        val owners = mutableMapOf<String, Set<Int>>()
        val allCells = mutableListOf<Int>()
        for (region in regions) {
            val id = region["region_id"] as? String ?: return "PACKAGE_REGION_PARTITION"
            val cells = (region["cells"] as? List<Double>)?.map(Double::toInt)
                ?: return "PACKAGE_REGION_PARTITION"
            if (id in owners || cells.isEmpty() || cells.size != cells.toSet().size) {
                return "PACKAGE_REGION_PARTITION"
            }
            owners[id] = cells.toSet()
            allCells += cells
        }
        if (allCells.sorted() != (0 until width * height).toList()) return "PACKAGE_REGION_PARTITION"
        val neighbors = regions.associate { region ->
            (region["region_id"] as String) to
                ((region["neighbors"] as? List<String>) ?: return "PACKAGE_REGION_PARTITION")
        }
        for ((id, adjacent) in neighbors) {
            if (id in adjacent || adjacent.size != adjacent.toSet().size ||
                adjacent.any { it !in owners || id !in neighbors.getValue(it) }
            ) return "PACKAGE_REGION_PARTITION"
        }
        val sites = document("world/sites.json")["sites"] as? List<Map<String, Any>>
            ?: return "PACKAGE_SITE_REGION"
        val siteIds = mutableSetOf<String>()
        for (site in sites) {
            val id = site["site_id"] as? String ?: return "PACKAGE_SITE_REGION"
            val region = site["region_id"] as? String ?: return "PACKAGE_SITE_REGION"
            val cell = (site["cell"] as? Double)?.toInt() ?: return "PACKAGE_SITE_REGION"
            if (!siteIds.add(id) || cell !in (owners[region] ?: return "PACKAGE_SITE_REGION")) {
                return "PACKAGE_SITE_REGION"
            }
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun routeTopologyCode(zip: ZipFile, manifest: Map<*, *>): String? {
        fun document(path: String) = gson.fromJson(
            zip.getInputStream(zip.getEntry(path)).reader(), Map::class.java,
        ) as Map<String, Any>
        val world = document("world/index.json")
        val width = (world["width"] as Double).toInt()
        val height = (world["height"] as Double).toInt()
        val regions = document("world/regions.json")["regions"] as List<Map<String, Any>>
        val owners = regions.associate {
            (it["region_id"] as String) to (it["cells"] as List<Double>).map(Double::toInt).toSet()
        }
        val routes = document("world/routes.json")["routes"] as? List<Map<String, Any>>
            ?: return "PACKAGE_ROUTE_TOPOLOGY"
        val sources = (manifest["artifacts"] as List<Map<String, Any>>)
            .map { it["artifact_id"] as String }.toSet()
        val ids = mutableSetOf<String>()
        fun contiguous(cells: List<Int>) = cells.zipWithNext().all { (left, right) ->
            kotlin.math.abs(left % width - right % width) +
                kotlin.math.abs(left / width - right / width) == 1
        }
        for (route in routes) {
            val id = route["route_id"] as? String ?: return "PACKAGE_ROUTE_TOPOLOGY"
            val start = route["start_region"] as? String ?: return "PACKAGE_ROUTE_TOPOLOGY"
            val end = route["end_region"] as? String ?: return "PACKAGE_ROUTE_TOPOLOGY"
            val cells = (route["cells"] as? List<Double>)?.map(Double::toInt)
                ?: return "PACKAGE_ROUTE_TOPOLOGY"
            val seasonal = (route["seasonal_cells"] as? List<List<Double>>)
                ?.map { path -> path.map(Double::toInt) } ?: return "PACKAGE_ROUTE_TOPOLOGY"
            val refs = route["source_ids"] as? List<String> ?: return "PACKAGE_ROUTE_TOPOLOGY"
            if (!ids.add(id) || start == end || start !in owners || end !in owners || cells.isEmpty() ||
                cells.any { it !in 0 until width * height } || cells.first() !in owners.getValue(start) ||
                cells.last() !in owners.getValue(end) || !contiguous(cells) || seasonal.size != 4 ||
                seasonal.any { it.isEmpty() || it.first() != cells.first() ||
                    it.last() != cells.last() || !contiguous(it) } || refs.any { it !in sources }
            ) return "PACKAGE_ROUTE_TOPOLOGY"
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun hydrologyCatalogCode(zip: ZipFile): String? {
        fun document(path: String) = gson.fromJson(
            zip.getInputStream(zip.getEntry(path)).reader(), Map::class.java,
        ) as Map<String, Any>
        val world = document("world/index.json")
        val cells = (world["width"] as Double).toInt() * (world["height"] as Double).toInt()
        val hydro = document("world/hydrology.json")
        val lakes = hydro["lakes"] as? List<Map<String, Any>> ?: return "PACKAGE_HYDROLOGY_CATALOG"
        val rivers = hydro["rivers"] as? List<Map<String, Any>> ?: return "PACKAGE_HYDROLOGY_CATALOG"
        val terminals = hydro["terminals"] as? List<Map<String, Any>>
            ?: return "PACKAGE_HYDROLOGY_CATALOG"
        val lakeIds = mutableSetOf<String>(); val lakeCells = mutableSetOf<Int>()
        for (lake in lakes) {
            val id = lake["lake_id"] as? String ?: return "PACKAGE_HYDROLOGY_CATALOG"
            val occupied = (lake["cells"] as? List<Double>)?.map(Double::toInt)
                ?: return "PACKAGE_HYDROLOGY_CATALOG"
            val spillway = (lake["spillway_cell"] as? Double)?.toInt()
            val outlet = (lake["outlet"] as? Double)?.toInt()
            if (!lakeIds.add(id) || occupied.size != occupied.toSet().size ||
                occupied.any { it !in 0 until cells } || occupied.any { it in lakeCells } ||
                (spillway != null && spillway !in occupied) || (outlet != null && outlet !in 0 until cells)
            ) return "PACKAGE_HYDROLOGY_CATALOG"
            lakeCells += occupied
        }
        val edges = mutableSetOf<Pair<Int, Int>>()
        for (river in rivers) {
            val up = (river["upstream"] as? Double)?.toInt() ?: return "PACKAGE_HYDROLOGY_CATALOG"
            val down = (river["downstream"] as? Double)?.toInt() ?: return "PACKAGE_HYDROLOGY_CATALOG"
            val discharge = (river["discharge_m3s"] as? Double)?.toLong()
                ?: return "PACKAGE_HYDROLOGY_CATALOG"
            val seasonal = river["seasonal_discharge_m3s"] as? List<Double>
                ?: return "PACKAGE_HYDROLOGY_CATALOG"
            if (up == down || up !in 0 until cells || down !in 0 until cells ||
                !edges.add(up to down) || discharge < 0 || seasonal.size != 4 || seasonal.any { it < 0 }
            ) return "PACKAGE_HYDROLOGY_CATALOG"
        }
        val terminalIds = mutableSetOf<String>(); val terminalCells = mutableSetOf<Int>()
        for (terminal in terminals) {
            val id = terminal["terminal_id"] as? String ?: return "PACKAGE_HYDROLOGY_CATALOG"
            val cell = (terminal["cell"] as? Double)?.toInt() ?: return "PACKAGE_HYDROLOGY_CATALOG"
            if (!terminalIds.add(id) || cell !in 0 until cells || !terminalCells.add(cell)) {
                return "PACKAGE_HYDROLOGY_CATALOG"
            }
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun gridValues(zip: ZipFile, domain: String, layer: String): List<Int> {
        val index = gson.fromJson(
            zip.getInputStream(zip.getEntry("world/$domain/index.json")).reader(), Map::class.java,
        ) as Map<String, Any>
        val width = (index["width"] as Double).toInt()
        val height = (index["height"] as Double).toInt()
        val layers = index["layers"] as Map<String, Map<String, Any>>
        val chunks = layers.getValue(layer)["chunks"] as List<Map<String, Any>>
        val output = MutableList(width * height) { 0 }
        for (descriptor in chunks) {
            val hash = descriptor["sha256"] as String
            val data = zip.getInputStream(
                zip.getEntry("world/$domain/chunks/$layer/$hash.bin")
            ).readBytes()
            val headerSize = java.nio.ByteBuffer.wrap(data, 0, 4).int
            val header = JsonParser.parseString(
                data.copyOfRange(4, 4 + headerSize).toString(Charsets.UTF_8)
            ).asJsonObject
            val chunkX = header["chunk_x"].asInt; val chunkY = header["chunk_y"].asInt
            val chunkWidth = header["width"].asInt; val chunkHeight = header["height"].asInt
            val body = java.nio.ByteBuffer.wrap(data, 4 + headerSize, chunkWidth * chunkHeight * 4)
            for (y in 0 until chunkHeight) for (x in 0 until chunkWidth) {
                output[(chunkY + y) * width + chunkX + x] = body.int
            }
        }
        return output
    }

    @Suppress("UNCHECKED_CAST")
    private fun resourceGeologyCode(zip: ZipFile, manifest: Map<*, *>): String? {
        val world = gson.fromJson(
            zip.getInputStream(zip.getEntry("world/index.json")).reader(), Map::class.java,
        ) as Map<String, Any>
        val width = (world["width"] as Double).toInt()
        val height = (world["height"] as Double).toInt()
        val scale = (((manifest["world"] as Map<String, Any>)["metres_per_world_cell"] as Double)).toLong()
        val rock = gridValues(zip, "geology", "geology_rock_class_id")
        val strata = gridValues(zip, "geology", "geology_strata_id")
        val fault = gridValues(zip, "geology", "geology_fault")
        val volcano = gridValues(zip, "geology", "geology_volcano")
        if (gridValues(zip, "resource_grid", "resource_renewable_yield").any { it < 0 }) {
            return "PACKAGE_RESOURCE_CATALOG"
        }
        val resources = gson.fromJson(
            zip.getInputStream(zip.getEntry("world/resources.json")).reader(), Map::class.java,
        ) as Map<String, Any>
        val deposits = resources["deposits"] as? List<Map<String, Any>>
            ?: return "PACKAGE_RESOURCE_CATALOG"
        val densities = mapOf("iron" to 5000L, "copper" to 3000L, "tin" to 2000L,
            "coal" to 1500L, "flux_stone" to 4000L, "gems" to 250L)
        val ids = mutableSetOf<String>(); val occupied = mutableSetOf<Int>()
        for (deposit in deposits) {
            val id = deposit["deposit_id"] as? String ?: return "PACKAGE_DEPOSIT_GEOLOGY"
            val cells = (deposit["cells"] as? List<Double>)?.map(Double::toInt)
                ?: return "PACKAGE_DEPOSIT_GEOLOGY"
            if (!ids.add(id) || cells.size < 2 || cells != cells.toSet().sorted() ||
                cells.any { it !in 0 until width * height } || cells.any { it in occupied }
            ) return "PACKAGE_DEPOSIT_GEOLOGY"
            val reached = mutableSetOf(cells.first())
            do {
                val before = reached.size
                reached += cells.filter { candidate -> reached.any { cell ->
                    kotlin.math.abs(cell % width - candidate % width) +
                        kotlin.math.abs(cell / width - candidate / width) == 1
                } }
            } while (reached.size != before)
            val rockId = (deposit["rock_class_id"] as Double).toInt()
            val strataId = (deposit["strata_id"] as Double).toInt()
            val isFault = cells.any { fault[it] != 0 }; val isVolcano = cells.any { volcano[it] != 0 }
            val expected = if (isVolcano) "gems" else if (isFault) {
                if (rockId % 2 == 0) "copper" else "tin"
            } else mapOf(1 to "coal", 2 to "iron", 3 to "flux_stone", 4 to "copper", 5 to "iron")[rockId]
            val grade = (deposit["grade_ppm"] as Double).toLong()
            val quantity = (cells.size * scale * scale * densities.getValue(expected!!) * grade + 500000) / 1000000
            if (reached != cells.toSet() || cells.any { rock[it] != rockId || strata[it] != strataId } ||
                deposit["fault_related"] != isFault || deposit["volcanic_related"] != isVolcano ||
                deposit["resource"] != expected || (deposit["quantity_kg"] as Double).toLong() != quantity
            ) return "PACKAGE_DEPOSIT_GEOLOGY"
            occupied += cells
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun civilizationCode(zip: ZipFile): String? {
        fun document(path: String) = gson.fromJson(
            zip.getInputStream(zip.getEntry(path)).reader(), Map::class.java,
        ) as Map<String, Any>
        val regionIds = (document("world/regions.json")["regions"] as List<Map<String, Any>>)
            .map { it["region_id"] as String }.toSet()
        val siteIds = (document("world/sites.json")["sites"] as List<Map<String, Any>>)
            .map { it["site_id"] as String }.toSet()
        val languagePayload = document("world/source/identities.json")["payload"] as? Map<String, Any>
            ?: return "PACKAGE_CIVILIZATION_REFERENCES"
        val languageIds = (languagePayload["languages"] as? List<Map<String, Any>>)
            ?.mapNotNull { it["language_id"] as? String }?.toSet()
            ?: return "PACKAGE_CIVILIZATION_REFERENCES"
        val civilizations = document("world/civilizations.json")["civilizations"]
            as? List<Map<String, Any>> ?: return "PACKAGE_CIVILIZATION_REFERENCES"
        if (civilizations.isEmpty()) return "PACKAGE_CIVILIZATION_REFERENCES"
        val ids = mutableSetOf<String>(); val claimed = mutableSetOf<String>()
        for (civilization in civilizations) {
            val id = civilization["civilization_id"] as? String
                ?: return "PACKAGE_CIVILIZATION_REFERENCES"
            val territory = civilization["territory"] as? List<String>
                ?: return "PACKAGE_CIVILIZATION_REFERENCES"
            val economy = civilization["economy"] as? Map<String, Double>
                ?: return "PACKAGE_CIVILIZATION_REFERENCES"
            val population = civilization["population"] as? Double
                ?: return "PACKAGE_CIVILIZATION_REFERENCES"
            if (!ids.add(id) || civilization["capital_site_id"] !in siteIds ||
                civilization["language_id"] !in languageIds || territory.isEmpty() ||
                territory.any { it !in regionIds || it in claimed } || economy.values.any { it < 0 } ||
                population < 0) return "PACKAGE_CIVILIZATION_REFERENCES"
            claimed += territory
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun eventOrderCode(zip: ZipFile): String? {
        val history = gson.fromJson(
            zip.getInputStream(zip.getEntry("world/history/index.json")).reader(), Map::class.java,
        ) as Map<String, Any>
        val paths = history["events"] as? List<String> ?: return "PACKAGE_EVENT_ORDER"
        if (paths.size != paths.toSet().size) return "PACKAGE_EVENT_ORDER"
        val known = mutableSetOf<String>(); var previous: Triple<Double, Double, Double>? = null
        var previousId = ""
        for (path in paths) {
            val event = gson.fromJson(zip.getInputStream(zip.getEntry(path)).reader(), Map::class.java)
                as Map<String, Any>
            val id = event["event_id"] as? String ?: return "PACKAGE_EVENT_ORDER"
            val key = Triple(event["year"] as Double, event["month"] as Double,
                event["sequence"] as Double)
            val causes = event["causes"] as? List<String> ?: return "PACKAGE_EVENT_ORDER"
            val ordered = previous?.let { prior -> prior.first < key.first ||
                prior.first == key.first && (prior.second < key.second ||
                prior.second == key.second && (prior.third < key.third ||
                prior.third == key.third && previousId < id)) } ?: true
            if (path != "world/history/events/$id.json" || !ordered ||
                causes.any { it !in known }) return "PACKAGE_EVENT_ORDER"
            known += id; previous = key; previousId = id
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun snapshotCode(zip: ZipFile, manifest: Map<*, *>): String? {
        val history = gson.fromJson(
            zip.getInputStream(zip.getEntry("world/history/index.json")).reader(), Map::class.java,
        ) as Map<String, Any>
        val paths = history["snapshots"] as? List<String> ?: return "PACKAGE_SNAPSHOT_CADENCE"
        val present = (((manifest["world"] as Map<String, Any>)["present_year"] as Double)).toInt()
        val years = (0..present step 10).toMutableSet().apply { add(present) }.sorted()
        if (paths != years.map { "world/history/snapshots/year_${it.toString().padStart(4, '0')}.json" }) {
            return "PACKAGE_SNAPSHOT_CADENCE"
        }
        val eventYears = (history["events"] as List<String>).map { path ->
            val event = gson.fromJson(zip.getInputStream(zip.getEntry(path)).reader(), Map::class.java)
            (event["year"] as Double).toInt()
        }
        var previous = -1
        for ((path, year) in paths.zip(years)) {
            val snapshot = JsonParser.parseReader(zip.getInputStream(zip.getEntry(path)).reader()).asJsonObject
            val position = snapshot["ledger_position"]?.asInt ?: return "PACKAGE_SNAPSHOT_CADENCE"
            val expected = eventYears.count { it <= year }
            val state = snapshot["state"] ?: return "PACKAGE_SNAPSHOT_CADENCE"
            val hash = digest(canonicalJSON(state).inputStream())
            if (snapshot["year"]?.asInt != year || position != expected || position < previous ||
                snapshot["state_hash"]?.asString != hash) return "PACKAGE_SNAPSHOT_CADENCE"
            previous = position
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun historyReplayCode(zip: ZipFile): String? {
        val history = gson.fromJson(
            zip.getInputStream(zip.getEntry("world/history/index.json")).reader(), Map::class.java,
        ) as Map<String, Any>
        val events = (history["events"] as List<String>).map { path ->
            gson.fromJson(zip.getInputStream(zip.getEntry(path)).reader(), Map::class.java)
                as Map<String, Any>
        }
        val snapshots = (history["snapshots"] as List<String>).map { path ->
            gson.fromJson(zip.getInputStream(zip.getEntry(path)).reader(), Map::class.java)
                as Map<String, Any>
        }
        val byPosition = snapshots.associate {
            (it["ledger_position"] as Double).toInt() to (it["state_hash"] as String)
        }
        var current = byPosition[0] ?: events.firstOrNull()?.get("before_state_sha256") as? String
        for ((index, event) in events.withIndex()) {
            val sources = event["source_ids"] as? List<String> ?: return "PACKAGE_HISTORY_REPLAY"
            if (event["envelope_version"] != "storyteller.history-event.v1" ||
                (event["algorithm_version"] as? Double)?.toInt() != 1 || sources.isEmpty() ||
                sources != sources.toSet().sorted() || event["before_state_sha256"] != current ||
                event["after_state_sha256"] !is String) return "PACKAGE_HISTORY_REPLAY"
            current = event["after_state_sha256"] as String
            if (byPosition[index + 1]?.let { it != current } == true) return "PACKAGE_HISTORY_REPLAY"
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun storyGraphCode(zip: ZipFile, manifest: Map<*, *>): String? {
        fun document(path: String) = gson.fromJson(
            zip.getInputStream(zip.getEntry(path)).reader(), Map::class.java,
        ) as Map<String, Any>
        val graph = document("narrative/graph.json")
        val nodes = graph["nodes"] as? List<Map<String, Any>> ?: return "PACKAGE_GRAPH_SEMANTICS"
        if (nodes.isEmpty()) return "PACKAGE_GRAPH_SEMANTICS"
        val byId = nodes.associateBy { it["node_id"] as? String }
        val start = graph["starting_node"] as? String ?: return "PACKAGE_GRAPH_SEMANTICS"
        val assets = manifest["node_assets"] as? Map<String, Any> ?: return "PACKAGE_GRAPH_SEMANTICS"
        if (byId.size != nodes.size || start !in byId || start != manifest["entry_node"] ||
            byId.keys != assets.keys) return "PACKAGE_GRAPH_SEMANTICS"
        val flags = graph["flags"] as? List<String> ?: return "PACKAGE_GRAPH_SEMANTICS"
        if (flags.size != flags.toSet().size) return "PACKAGE_GRAPH_SEMANTICS"
        val reached = mutableSetOf(start); val queue = ArrayDeque(listOf(start)); val choiceIds = mutableSetOf<String>()
        while (queue.isNotEmpty()) {
            val node = byId.getValue(queue.removeFirst())
            val choices = node["choices"] as? List<Map<String, Any>> ?: return "PACKAGE_GRAPH_SEMANTICS"
            if ((choices.isNotEmpty()) == (node["ending"] != null)) return "PACKAGE_GRAPH_SEMANTICS"
            for (choice in choices) {
                val id = choice["choice_id"] as? String ?: return "PACKAGE_GRAPH_SEMANTICS"
                val target = choice["target_node"] as? String ?: return "PACKAGE_GRAPH_SEMANTICS"
                val required = choice["requires_flags"] as? List<String> ?: return "PACKAGE_GRAPH_SEMANTICS"
                if (!choiceIds.add(id) || target !in byId || required.any { it !in flags } ||
                    (choice["transition_year"] as Double) < (node["world_year"] as Double)
                ) return "PACKAGE_GRAPH_SEMANTICS"
                if (reached.add(target)) queue.add(target)
            }
        }
        if (reached != byId.keys) return "PACKAGE_GRAPH_SEMANTICS"
        val scenes = document("narrative/story.json")["scenes"] as? List<Map<String, Any>>
            ?: return "PACKAGE_STORY_GRAPH_REFERENCES"
        val sceneById = scenes.associateBy { it["scene_id"] as? String }
        val known = mutableSetOf<String>()
        known += (manifest["artifacts"] as List<Map<String, Any>>).map { it["artifact_id"] as String }
        known += (document("world/sites.json")["sites"] as List<Map<String, Any>>).map { it["site_id"] as String }
        known += (document("world/civilizations.json")["civilizations"] as List<Map<String, Any>>)
            .map { it["civilization_id"] as String }
        known += (document("world/history/index.json")["events"] as List<String>)
            .map { it.substringAfterLast('/').removeSuffix(".json") }
        if (sceneById.size != scenes.size) return "PACKAGE_STORY_GRAPH_REFERENCES"
        for (node in nodes) {
            val scene = sceneById[node["scene_id"]] ?: return "PACKAGE_STORY_GRAPH_REFERENCES"
            val keys = listOf("location_id", "participant_ids", "opportunity_id", "authoritative_refs", "world_year")
            if (keys.any { node[it] != scene[it] } || node["location_id"] !in known ||
                (node["participant_ids"] as List<String>).any { it !in known } ||
                node["opportunity_id"] !in known ||
                (node["authoritative_refs"] as List<String>).any { it !in known }
            ) return "PACKAGE_STORY_GRAPH_REFERENCES"
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun narrativeAuthorityCode(zip: ZipFile, manifest: Map<*, *>): String? {
        fun bytes(path: String) = zip.getInputStream(zip.getEntry(path)).readBytes()
        fun document(path: String) = gson.fromJson(bytes(path).toString(Charsets.UTF_8), Map::class.java)
            as Map<String, Any>
        val bibleBytes = bytes("narrative/bible.json")
        val reconciliationBytes = bytes("narrative/reconciliation.json")
        val bible = document("narrative/bible.json")
        val reconciliation = document("narrative/reconciliation.json")
        val story = document("narrative/story.json")
        val worldRecords = (manifest["artifacts"] as List<Map<String, Any>>)
            .filter { (it["path"] as String).startsWith("world/") }
        val ids = worldRecords.associate { it["path"] as String to it["artifact_id"] as String }
        val hashes = worldRecords.associate { it["path"] as String to it["sha256"] as String }
        if (bible["authoritative_refs"] != ids.values.sorted()) return "PACKAGE_BIBLE_AUTHORITY"
        val issues = reconciliation["issues"] as? List<Map<String, Any>>
            ?: return "PACKAGE_RECONCILIATION_INPUTS"
        if (reconciliation["accepted"] != true || reconciliation["world_artifact_ids"] != ids ||
            reconciliation["world_file_hashes"] != hashes ||
            (reconciliation["ruleset_version"] as? Double)?.toInt() != 1 ||
            issues.any { it["severity"] in setOf("error", "fatal") } ||
            story["bible_hash"] != digest(bibleBytes.inputStream()) ||
            story["reconciliation_hash"] != digest(reconciliationBytes.inputStream())
        ) return "PACKAGE_RECONCILIATION_INPUTS"
        val regions = (bible["regions"] as List<Map<String, Any>>).map { it["region_id"] }.toSet()
        val sites = (bible["sites"] as List<Map<String, Any>>).map { it["site_id"] }.toSet()
        val civilizations = (bible["civilizations"] as List<Map<String, Any>>)
            .map { it["civilization_id"] }.toSet()
        val history = bible["history"] as List<Map<String, Any>>
        val events = history.map { it["event_id"] }.toSet()
        if ((bible["sites"] as List<Map<String, Any>>).any { it["region_id"] !in regions } ||
            (bible["civilizations"] as List<Map<String, Any>>).any { item ->
                (item["territory"] as List<String>).any { it !in regions }
            } || (bible["people"] as List<Map<String, Any>>).any {
                it["civilization_id"] !in civilizations || it["settlement_id"] !in sites
            } || history.any { item -> (item["causes"] as List<String>).any { it !in events } ||
                (item["participants"] as List<String>).any { it !in civilizations }
            }) return "PACKAGE_REFERENCE_RESOLUTION"
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun gmCoverageCode(zip: ZipFile, manifest: Map<*, *>): String? {
        val gm = gson.fromJson(
            zip.getInputStream(zip.getEntry("narrative/gm_index.json")).reader(), Map::class.java,
        ) as Map<String, Any>
        val reconciliation = gson.fromJson(
            zip.getInputStream(zip.getEntry("narrative/reconciliation.json")).reader(), Map::class.java,
        ) as Map<String, Any>
        val graph = gson.fromJson(
            zip.getInputStream(zip.getEntry("narrative/graph.json")).reader(), Map::class.java,
        ) as Map<String, Any>
        val known = (manifest["artifacts"] as List<Map<String, Any>>)
            .map { it["artifact_id"] as String }.toSet()
        val nodes = (graph["nodes"] as List<Map<String, Any>>).map { it["node_id"] as String }.toSet()
        val entries = gm["entries"] as? List<Map<String, Any>> ?: return "PACKAGE_GM_COVERAGE"
        if (entries.isEmpty()) return "PACKAGE_GM_COVERAGE"
        val covered = mutableSetOf<String>()
        for (entry in entries) {
            val sources = entry["source_ids"] as? List<String> ?: return "PACKAGE_GM_COVERAGE"
            val reveal = entry["reveal_after_nodes"] as? List<String> ?: return "PACKAGE_GM_COVERAGE"
            if (sources.isEmpty() || sources.any { it !in known } || reveal.any { it !in nodes }) {
                return "PACKAGE_GM_COVERAGE"
            }
            covered += sources
        }
        val expected = (reconciliation["world_artifact_ids"] as? Map<String, String>)?.values
            ?: return "PACKAGE_GM_COVERAGE"
        return if (expected.isEmpty() || !covered.containsAll(expected)) "PACKAGE_GM_COVERAGE" else null
    }

    @Suppress("UNCHECKED_CAST")
    private fun structuredScoreCode(zip: ZipFile, manifest: Map<*, *>): String? {
        val known = (manifest["artifacts"] as List<Map<String, Any>>)
            .map { it["artifact_id"] as String }.toSet()
        val assets = manifest["node_assets"] as Map<String, Map<String, String>>
        val kinds = listOf("chord", "control", "note", "pitch_bend", "rest")
        fun tick(value: Any?): Int? {
            val beat = value as? Map<String, Double> ?: return null
            val numerator = beat["numerator"]?.toInt() ?: return null
            val denominator = beat["denominator"]?.toInt() ?: return null
            return if (denominator > 0 && numerator.toLong() * 960 % denominator == 0L) {
                numerator * 960 / denominator
            } else null
        }
        for ((node, nodeAssets) in assets) {
            if (nodeAssets.values.any { zip.getEntry(it) == null }) continue
            val score = gson.fromJson(
                zip.getInputStream(zip.getEntry(nodeAssets.getValue("score"))).reader(), Map::class.java,
            ) as Map<String, Any>
            val sources = score["source_ids"] as? List<String> ?: return "PACKAGE_SCORE_REFERENCES"
            if (score["node_id"] != node || sources.isEmpty() || sources != sources.toSet().sorted() ||
                sources.any { it !in known }) return "PACKAGE_SCORE_REFERENCES"
            if (score["expected_midi_sha256"] != digest(
                    zip.getInputStream(zip.getEntry(nodeAssets.getValue("midi")))
                )) return "PACKAGE_SCORE_MIDI_HASH"
            val duration = tick(score["duration"]) ?: return "PACKAGE_SCORE_BEAT_ARITHMETIC"
            if (duration <= 0) return "PACKAGE_SCORE_BEAT_ARITHMETIC"
            if (!validMidi(zip.getInputStream(zip.getEntry(nodeAssets.getValue("midi"))).readBytes(), duration)) {
                return "PACKAGE_MIDI_PROFILE"
            }
            val markers = score["markers"] as? Map<String, Any> ?: return "PACKAGE_SCORE_MARKER_ORDER"
            if (markers.keys != setOf("INTRO_END", "LOOP_START", "LOOP_END", "OUTRO_START")) {
                return "PACKAGE_SCORE_MARKER_ORDER"
            }
            val markerTicks = listOf("INTRO_END", "LOOP_START", "LOOP_END", "OUTRO_START")
                .map { tick(markers[it]) ?: return "PACKAGE_SCORE_BEAT_ARITHMETIC" }
            if (!(markerTicks[0] in 0..markerTicks[1] && markerTicks[1] < markerTicks[2] &&
                    markerTicks[2] <= markerTicks[3] && markerTicks[3] <= duration)) {
                return "PACKAGE_SCORE_MARKER_ORDER"
            }
            val tracks = score["tracks"] as? List<Map<String, Any>>
                ?: return "PACKAGE_SCORE_TRACK_PROGRAM"
            val trackIds = tracks.map { it["track_id"] as? String }
            if (tracks.isEmpty() || trackIds.any { it.isNullOrEmpty() } || trackIds.size != trackIds.toSet().size) {
                return "PACKAGE_SCORE_TRACK_PROGRAM"
            }
            for (track in tracks) {
                val drum = track["drum_channel"] as? Boolean ?: return "PACKAGE_SCORE_TRACK_PROGRAM"
                val program = (track["gm_program"] as? Double)?.toInt()
                if ((drum && program != null) || (!drum && (program == null || program !in 0..95))) {
                    return "PACKAGE_SCORE_TRACK_PROGRAM"
                }
                val events = track["events"] as? List<Map<String, Any>>
                    ?: return "PACKAGE_SCORE_EVENT_SHAPE"
                if (events.isEmpty()) return "PACKAGE_SCORE_EVENT_SHAPE"
                val ids = mutableSetOf<String>(); var previous: Map<String, Any>? = null
                fun pitches(event: Map<String, Any>) =
                    (event["pitches"] as? List<Double>)?.map(Double::toInt) ?: emptyList()
                fun before(left: Map<String, Any>, right: Map<String, Any>): Boolean {
                    val leftTick = tick(left["start"])!!; val rightTick = tick(right["start"])!!
                    if (leftTick != rightTick) return leftTick < rightTick
                    val leftKind = kinds.indexOf(left["kind"]); val rightKind = kinds.indexOf(right["kind"])
                    if (leftKind != rightKind) return leftKind < rightKind
                    val lp = pitches(left); val rp = pitches(right)
                    for (index in 0 until minOf(lp.size, rp.size)) if (lp[index] != rp[index]) return lp[index] < rp[index]
                    if (lp.size != rp.size) return lp.size < rp.size
                    return (left["event_id"] as String) < (right["event_id"] as String)
                }
                for (event in events) {
                    val start = tick(event["start"]) ?: return "PACKAGE_SCORE_BEAT_ARITHMETIC"
                    val length = tick(event["duration"]) ?: return "PACKAGE_SCORE_BEAT_ARITHMETIC"
                    val id = event["event_id"] as? String ?: return "PACKAGE_SCORE_EVENT_SHAPE"
                    if (!ids.add(id) || previous?.let { !before(it, event) } == true) {
                        return "PACKAGE_SCORE_EVENT_ORDER"
                    }
                    val kind = event["kind"] as? String ?: return "PACKAGE_SCORE_EVENT_SHAPE"
                    val pitch = pitches(event); val velocity = (event["velocity"] as? Double)?.toInt()
                    val value = (event["value"] as? Double)?.toInt()
                    val sounding = kind == "note" || kind == "chord"
                    if (kind !in kinds || length <= 0 || start < 0 || start + length > duration ||
                        sounding && (pitch.isEmpty() || pitch.any { it !in 0..127 } ||
                            velocity == null || velocity !in 1..127 || value != null) ||
                        kind == "note" && pitch.size != 1 || kind == "chord" && pitch.size < 2 ||
                        kind == "rest" && (pitch.isNotEmpty() || velocity != null || value != null) ||
                        kind == "control" && (pitch.isNotEmpty() || velocity != null ||
                            value == null || value !in 0..127) ||
                        kind == "pitch_bend" && (pitch.isNotEmpty() || velocity != null ||
                            value == null || value !in -8192..8191)
                    ) return "PACKAGE_SCORE_EVENT_SHAPE"
                    previous = event
                }
            }
        }
        return null
    }

    private fun validMidi(data: ByteArray, expectedDuration: Int): Boolean {
        fun byte(at: Int) = if (at in data.indices) data[at].toInt() and 0xff else -1
        fun u16(at: Int) = (byte(at) shl 8) or byte(at + 1)
        fun u32(at: Int): Long = (byte(at).toLong() shl 24) or (byte(at + 1).toLong() shl 16) or
            (byte(at + 2).toLong() shl 8) or byte(at + 3).toLong()
        fun ascii(at: Int, text: String) = at >= 0 && at + text.length <= data.size &&
            text.indices.all { byte(at + it) == text[it].code }
        if (data.size < 14 || !ascii(0, "MThd") || u32(4) != 6L || u16(8) != 1 ||
            u16(10) < 2 || u16(12) != 960) return false
        var offset = 14; var notes = 0; var maxTick = 0
        val markers = mutableSetOf<String>()
        repeat(u16(10)) {
            if (!ascii(offset, "MTrk") || offset + 8 > data.size) return false
            val length = u32(offset + 4)
            if (length < 0 || length > Int.MAX_VALUE || offset + 8L + length > data.size) return false
            var cursor = offset + 8; val end = cursor + length.toInt(); var tick = 0
            fun vlq(): Int? {
                var value = 0
                repeat(4) {
                    if (cursor >= end) return null
                    val b = byte(cursor++)
                    value = (value shl 7) or (b and 0x7f)
                    if (b and 0x80 == 0) return value
                }
                return null
            }
            while (cursor < end) {
                tick += vlq() ?: return false; maxTick = maxOf(maxTick, tick)
                if (cursor >= end) return false
                val status = byte(cursor++)
                if (status == 0xf0 || status == 0xf7) return false
                when {
                    status == 0xff -> {
                        if (cursor >= end) return false
                        val kind = byte(cursor++); val size = vlq() ?: return false
                        if (size < 0 || cursor + size > end) return false
                        if (kind == 0x06) markers += data.copyOfRange(cursor, cursor + size)
                            .toString(Charsets.US_ASCII)
                        cursor += size
                    }
                    status and 0xf0 == 0x80 || status and 0xf0 == 0x90 -> {
                        if (cursor + 2 > end || byte(cursor) > 127 || byte(cursor + 1) > 127) return false
                        notes++; cursor += 2
                    }
                    status and 0xf0 == 0xb0 || status and 0xf0 == 0xe0 -> {
                        if (cursor + 2 > end || byte(cursor) > 127 || byte(cursor + 1) > 127) return false
                        cursor += 2
                    }
                    status and 0xf0 == 0xc0 -> {
                        if (cursor >= end || byte(cursor) !in 0..95) return false
                        cursor++
                    }
                    else -> return false
                }
            }
            offset = end
        }
        return offset == data.size && notes > 0 && maxTick == expectedDuration &&
            markers == setOf("INTRO_END", "LOOP_START", "LOOP_END", "OUTRO_START")
    }

    @Suppress("UNCHECKED_CAST")
    private fun pngProfileCode(zip: ZipFile, manifest: Map<*, *>): String? {
        val expected = mutableMapOf("assets/maps/world.png" to (4096 to 4096))
        (manifest["region_maps"] as Map<String, String>).values.forEach { expected[it] = 1024 to 1024 }
        (manifest["node_assets"] as Map<String, Map<String, String>>).values.forEach {
            expected[it.getValue("image")] = 1024 to 1024
            expected[it.getValue("thumbnail")] = 256 to 256
        }
        for ((path, size) in expected) {
            val entry = zip.getEntry(path) ?: return "PACKAGE_PNG_PROFILE"
            if (!validPng(zip.getInputStream(entry).readBytes(), size.first, size.second)) {
                return "PACKAGE_PNG_PROFILE"
            }
        }
        return null
    }

    private fun validPng(data: ByteArray, expectedWidth: Int, expectedHeight: Int): Boolean {
        fun b(i: Int) = if (i in data.indices) data[i].toInt() and 0xff else -1
        fun u32(i: Int): Long = (b(i).toLong() shl 24) or (b(i + 1).toLong() shl 16) or
            (b(i + 2).toLong() shl 8) or b(i + 3).toLong()
        val signature = byteArrayOf(-119, 80, 78, 71, 13, 10, 26, 10)
        if (data.size < 8 || !data.copyOfRange(0, 8).contentEquals(signature)) return false
        var offset = 8; var width = 0; var height = 0; var sawIhdr = false
        var sawSrgb = false; var sawIdat = false; var ended = false
        val compressed = java.io.ByteArrayOutputStream()
        while (offset < data.size) {
            if (offset + 12 > data.size) return false
            val length = u32(offset)
            if (length > Int.MAX_VALUE || offset + 12L + length > data.size) return false
            val count = length.toInt(); val typeStart = offset + 4; val payload = offset + 8
            val type = data.copyOfRange(typeStart, typeStart + 4).toString(Charsets.US_ASCII)
            val crc = CRC32().apply { update(data, typeStart, 4 + count) }.value
            if (crc != u32(payload + count)) return false
            when (type) {
                "IHDR" -> {
                    if (sawIhdr || offset != 8 || count != 13) return false
                    width = u32(payload).toInt(); height = u32(payload + 4).toInt()
                    if (width != expectedWidth || height != expectedHeight || b(payload + 8) != 8 ||
                        b(payload + 9) != 6 || b(payload + 10) != 0 || b(payload + 11) != 0 ||
                        b(payload + 12) != 0) return false
                    sawIhdr = true
                }
                "sRGB" -> {
                    if (!sawIhdr || sawIdat || sawSrgb || count != 1 || b(payload) !in 0..3) return false
                    sawSrgb = true
                }
                "IDAT" -> {
                    if (!sawIhdr || !sawSrgb || ended) return false
                    sawIdat = true; compressed.write(data, payload, count)
                }
                "IEND" -> {
                    if (!sawIdat || count != 0 || payload + 4 != data.size) return false
                    ended = true
                }
                "acTL", "fcTL", "fdAT" -> return false
                else -> if (sawIdat && type[0].isUpperCase()) return false
            }
            offset = payload + count + 4
        }
        if (!ended) return false
        val expected = height.toLong() * (width.toLong() * 4 + 1)
        if (expected > Int.MAX_VALUE) return false
        val inflater = Inflater(); inflater.setInput(compressed.toByteArray())
        val raw = ByteArray(expected.toInt()); var written = 0
        return try {
            while (!inflater.finished() && written < raw.size) {
                val count = inflater.inflate(raw, written, raw.size - written)
                if (count == 0 && inflater.needsInput()) break
                if (count == 0) return false
                written += count
            }
            inflater.finished() && written == raw.size && !inflater.needsDictionary() &&
                (0 until height).all { raw[it * (width * 4 + 1)].toInt() == 0 }
        } catch (_: Exception) { false } finally { inflater.end() }
    }

    @Suppress("UNCHECKED_CAST")
    private fun hasDependencyCycle(artifacts: List<Map<String, Any>>): Boolean {
        val byId = artifacts.associateBy { it["artifact_id"] as String }
        val visiting = mutableSetOf<String>()
        val visited = mutableSetOf<String>()
        fun visit(id: String): Boolean {
            if (id in visiting) return true
            if (!visited.add(id)) return false
            visiting += id
            val dependencies = byId.getValue(id)["depends_on"] as List<String>
            if (dependencies.any(::visit)) return true
            visiting -= id
            return false
        }
        return byId.keys.any(::visit)
    }

    /** P8.C2: layout, node assets, entry node, and region map validation. */
    @Suppress("UNCHECKED_CAST")
    private fun layoutCode(manifest: Map<*, *>, names: Set<String>): String? {
        val required = setOf(
            "world/index.json", "narrative/bible.json", "narrative/reconciliation.json",
            "narrative/style_bible.json", "narrative/story.json", "narrative/graph.json",
            "narrative/gm_index.json", "assets/maps/world.png",
        )
        if (!required.all(names::contains)) return "PACKAGE_LAYOUT_MISSING"

        // Node assets: every node must have image/thumbnail/score/midi
        val nodeAssets = manifest["node_assets"] as? Map<String, Map<String, String>> ?: return "PACKAGE_MEDIA_COVERAGE"
        val entryNode = manifest["entry_node"] as? String ?: return "PACKAGE_ENTRY_NODE"
        if (entryNode !in nodeAssets) return "PACKAGE_ENTRY_NODE"
        for ((node, assets) in nodeAssets) {
            val expected = mapOf(
                "image" to "assets/images/$node.png",
                "thumbnail" to "assets/thumbnails/$node.png",
                "score" to "assets/music/$node.score.json",
                "midi" to "assets/midi/$node.mid",
            )
            if (assets != expected || !expected.values.all(names::contains)) {
                return "PACKAGE_MEDIA_COVERAGE"
            }
        }

        // Region maps: every declared region map must exist
        val regionMaps = manifest["region_maps"] as? Map<String, String> ?: return "PACKAGE_REGION_MAP_COVERAGE"
        if (regionMaps.values.any { it !in names }) return "PACKAGE_REGION_MAP_COVERAGE"

        return null
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
