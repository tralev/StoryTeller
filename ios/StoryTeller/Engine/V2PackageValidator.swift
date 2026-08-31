import CryptoKit
import Compression
import CoreFoundation
import Foundation
import ZIPFoundation

struct V2ArchiveValidation {
    let accepted: Bool
    let issueCodes: [String]
    let manifest: V2Manifest?
    let requiredBytes: Int64
}

/** Platform-independent validation of the exact v2 ZIP bytes supplied.
 *
 * P8.C2 — Three-validator parity: matches Python validate_v2_package and
 * Kotlin V2PackageValidator on all acceptance stages.
 */
enum V2PackageValidator {
    private static let maxEntries = 100_000
    private static let maxEntryBytes: UInt64 = 4 * 1024 * 1024 * 1024
    private static let maxTotalBytes: UInt64 = 32 * 1024 * 1024 * 1024 * 1024
    private static let maxRatio = 1_000.0

    /// A malformed package is untrusted input, so failed shape checks must
    /// unwind into `PACKAGE_INVALID_ZIP` instead of trapping the process.
    private enum PackageShapeError: Error { case invalid }

    private static func required<T>(_ value: Any?, _ type: T.Type = T.self) throws -> T {
        guard let typed = value as? T else { throw PackageShapeError.invalid }
        return typed
    }

    private static func requiredEntry(_ path: String, _ archive: Archive) throws -> Entry {
        guard let entry = archive[path] else { throw PackageShapeError.invalid }
        return entry
    }

    static func hasExtractionSpace(requiredBytes: Int64, freeBytes: Int64) -> Bool {
        precondition(requiredBytes >= 0 && freeBytes >= 0, "extraction byte counts must be non-negative")
        return freeBytes >= requiredBytes
    }

    // P8.C2: frozen ordered acceptance stages matching Python/Kotlin
    static func validate(_ source: URL) -> V2ArchiveValidation {
        do {
            guard FileManager.default.fileExists(atPath: source.path) else { return invalid("PACKAGE_NOT_FOUND") }
            let archive = try Archive(url: source, accessMode: .read)
            let entries = Array(archive)
            let names = Set(entries.map(\.path))
            // Stage 1: central-directory safety
            if entries.map(\.path) != entries.map(\.path).sorted(by: utf8PathLessThan) {
                return invalid("PACKAGE_PATH_ORDER")
            }
            if let code = safetyCode(entries) { return invalid(code) }
            if let code = try rawMetadataCode(source) { return invalid(code) }
            if entries.contains(where: { !hasCanonicalMetadata($0) }) {
                return invalid("PACKAGE_ZIP_METADATA")
            }
            if try entries.contains(where: { entry in
                guard entry.path.hasSuffix(".bin") else { return false }
                return secondaryCompression(try prefix(entry, archive))
            }) { return invalid("PACKAGE_SECONDARY_COMPRESSION") }
            if try entries.contains(where: { entry in
                guard entry.path.hasSuffix(".json") else { return false }
                return try exceedsJSONDepth(entry, archive)
            }) { return invalid("PACKAGE_JSON_DEPTH") }
            for entry in entries where entry.path.hasSuffix(".json") {
                if let code = try jsonEncodingCode(entry, archive) { return invalid(code) }
            }
            for entry in entries where entry.path.hasSuffix(".json") {
                if let code = try jsonProfileCode(entry, archive),
                   code != "PACKAGE_JSON_NONCANONICAL" { return invalid(code) }
            }
            // Stage 2: manifest existence, format, version
            guard let manifestEntry = archive["manifest.json"] else { return invalid("PACKAGE_MISSING_MANIFEST") }
            guard let rawManifest = try JSONSerialization.jsonObject(
                with: read(manifestEntry, archive)
            ) as? [String: Any], let rawVersion = rawManifest["package_version"] as? NSNumber,
                  CFGetTypeID(rawVersion) != CFBooleanGetTypeID(),
                  rawVersion.doubleValue.rounded() == rawVersion.doubleValue else {
                return invalid("PACKAGE_TYPE_COERCION")
            }
            guard rawVersion.intValue == 2 else {
                return invalid("PACKAGE_UNSUPPORTED_VERSION")
            }
            guard let rawFormat = rawManifest["package_format"] as? String else {
                return invalid("PACKAGE_TYPE_COERCION")
            }
            if rawFormat != "storyteller.story" { return invalid("PACKAGE_UNSUPPORTED_VERSION") }
            if let code = featureCode(rawManifest) { return invalid(code) }
            let manifestData = try read(manifestEntry, archive)
            if !TrustedJSONSchema.validates(schemaName: "manifest", document: manifestData) {
                return invalid("PACKAGE_SCHEMA")
            }
            let manifest = try JSONDecoder().decode(V2Manifest.self, from: manifestData)
            guard manifest.packageVersion == 2 && manifest.packageFormat == "storyteller.story" else {
                return invalid("PACKAGE_UNSUPPORTED_VERSION", manifest)
            }
            for entry in entries where entry.path.hasSuffix(".json") {
                if let code = try jsonProfileCode(entry, archive) { return invalid(code, manifest) }
            }
            // Stage 3: declared member inventory and internal hashes
            if let code = try inventoryCode(manifest, archive, names) {
                return invalid(code, manifest)
            }
            if let code = try sourceCoverageCode(archive, names) { return invalid(code, manifest) }
            if let code = try physicalLayerCode(archive) { return invalid(code, manifest) }
            if let code = try gridDomainCode(archive, names) { return invalid(code, manifest) }
            if let code = try climateLayerCode(archive) { return invalid(code, manifest) }
            if let code = try regionSiteCode(archive) { return invalid(code, manifest) }
            if let code = try routeTopologyCode(archive, manifest) { return invalid(code, manifest) }
            if let code = try hydrologyCatalogCode(archive) { return invalid(code, manifest) }
            if let code = try resourceGeologyCode(archive, manifest) { return invalid(code, manifest) }
            if let code = try civilizationCode(archive) { return invalid(code, manifest) }
            if let code = try localMapCode(archive, names) { return invalid(code, manifest) }
            if let code = try eventOrderCode(archive) { return invalid(code, manifest) }
            if let code = try snapshotCode(archive) { return invalid(code, manifest) }
            if let code = try historyReplayCode(archive) { return invalid(code, manifest) }
            if let code = try storyGraphCode(archive, manifest) { return invalid(code, manifest) }
            if let code = try narrativeAuthorityCode(archive, manifest) { return invalid(code, manifest) }
            if let code = try gmCoverageCode(archive, manifest) { return invalid(code, manifest) }
            if let code = try structuredScoreCode(archive, manifest) { return invalid(code, manifest) }
            if let code = try pngProfileCode(archive, manifest) { return invalid(code, manifest) }
            // Stage 4: layout, node assets, entry node, region maps
            if let code = layoutCode(manifest, names) {
                return invalid(code, manifest)
            }
            return V2ArchiveValidation(
                accepted: true,
                issueCodes: [],
                manifest: manifest,
                requiredBytes: entries.reduce(0) { $0 + Int64($1.uncompressedSize) }
            )
        } catch {
            return invalid("PACKAGE_INVALID_ZIP")
        }
    }

    private static func invalid(_ code: String, _ manifest: V2Manifest? = nil) -> V2ArchiveValidation {
        V2ArchiveValidation(accepted: false, issueCodes: [code], manifest: manifest, requiredBytes: 0)
    }

    private static func utf8PathLessThan(_ left: String, _ right: String) -> Bool {
        left.utf8.lexicographicallyPrecedes(right.utf8)
    }

    private static func featureCode(_ manifest: V2Manifest) -> String? {
        let required = manifest.requiredFeatures
        let optional = manifest.optionalFeatures
        if required != Array(Set(required)).sorted() || optional != Array(Set(optional)).sorted() {
            return "PACKAGE_FEATURE_ORDER"
        }
        let frozen = [
            "all_site_local_maps", "complete_history", "complete_world", "embedded_schemas",
            "fixed_media_profile", "structured_score_midi",
        ]
        if required != frozen { return "PACKAGE_REQUIRED_FEATURE" }
        if !optional.isEmpty { return "PACKAGE_OPTIONAL_FEATURE" }
        return nil
    }

    private static func featureCode(_ manifest: [String: Any]) -> String? {
        guard let required = manifest["required_features"] as? [String],
              let optional = manifest["optional_features"] as? [String] else { return nil }
        if required != Array(Set(required)).sorted() || optional != Array(Set(optional)).sorted() {
            return "PACKAGE_FEATURE_ORDER"
        }
        let frozen = [
            "all_site_local_maps", "complete_history", "complete_world", "embedded_schemas",
            "fixed_media_profile", "structured_score_midi",
        ]
        if required != frozen { return "PACKAGE_REQUIRED_FEATURE" }
        if !optional.isEmpty { return "PACKAGE_OPTIONAL_FEATURE" }
        return nil
    }

    private static func hasCanonicalMetadata(_ entry: Entry) -> Bool {
        guard entry.type == .file,
              let permissions = entry.fileAttributes[.posixPermissions] as? NSNumber,
              permissions.intValue == 0o644,
              let modified = entry.fileAttributes[.modificationDate] as? Date else { return false }
        var calendar = Calendar(identifier: .gregorian)
        guard let utc = TimeZone(secondsFromGMT: 0) else { return false }
        calendar.timeZone = utc
        let parts = calendar.dateComponents(
            [.year, .month, .day, .hour, .minute, .second], from: modified
        )
        let canonicalDate = parts.year == 1980 && parts.month == 1 && parts.day == 1 &&
            parts.hour == 0 && parts.minute == 0 && parts.second == 0
        let canonicalCompression = entry.path.hasSuffix(".png") ? !entry.isCompressed : entry.isCompressed
        return canonicalDate && canonicalCompression
    }

    private enum PrefixComplete: Error { case done }

    private static func prefix(_ entry: Entry, _ archive: Archive) throws -> Data {
        var result = Data()
        do {
            _ = try archive.extract(entry, bufferSize: 8) { chunk in
                result.append(chunk.prefix(8 - result.count))
                if result.count == 8 { throw PrefixComplete.done }
            }
        } catch PrefixComplete.done {
            // Expected bounded stop after the signature-sized prefix.
        }
        return result
    }

    private static func secondaryCompression(_ prefix: Data) -> Bool {
        let signatures: [[UInt8]] = [
            [0x1f, 0x8b], [0x42, 0x5a, 0x68], [0xfd, 0x37, 0x7a, 0x58, 0x5a, 0x00],
            [0x28, 0xb5, 0x2f, 0xfd], [0x50, 0x4b, 0x03, 0x04], [0x04, 0x22, 0x4d, 0x18],
        ]
        return signatures.contains { prefix.starts(with: $0) }
    }

    private enum JSONDepthExceeded: Error { case exceeded }

    private static func exceedsJSONDepth(_ entry: Entry, _ archive: Archive) throws -> Bool {
        var depth = 0
        var inString = false
        var escaped = false
        do {
            _ = try archive.extract(entry, bufferSize: 64 * 1024) { chunk in
                for value in chunk {
                    if inString {
                        if escaped { escaped = false }
                        else if value == 0x5c { escaped = true }
                        else if value == 0x22 { inString = false }
                    } else if value == 0x22 { inString = true }
                    else if value == 0x7b || value == 0x5b {
                        depth += 1
                        if depth > 128 { throw JSONDepthExceeded.exceeded }
                    } else if value == 0x7d || value == 0x5d { depth -= 1 }
                }
            }
        } catch JSONDepthExceeded.exceeded {
            return true
        }
        return false
    }

    private static func jsonEncodingCode(_ entry: Entry, _ archive: Archive) throws -> String? {
        var prefix: [UInt8] = []
        var validator = UTF8Validator()
        var valid = true
        _ = try archive.extract(entry, bufferSize: 64 * 1024) { chunk in
            if prefix.count < 3 { prefix.append(contentsOf: chunk.prefix(3 - prefix.count)) }
            if !validator.consume(chunk) { valid = false }
        }
        if prefix == [0xef, 0xbb, 0xbf] { return "PACKAGE_JSON_BOM" }
        return valid && validator.complete ? nil : "PACKAGE_JSON_UTF8"
    }

    private enum JSONScanError: Error { case malformed, duplicateKey, numberProfile, numberRange }

    private static func jsonProfileCode(_ entry: Entry, _ archive: Archive) throws -> String? {
        var scanner = JSONKeyScanner(bytes: Array(try read(entry, archive)))
        do {
            try scanner.parseDocument()
            return scanner.canonical ? nil : "PACKAGE_JSON_NONCANONICAL"
        } catch JSONScanError.duplicateKey {
            return "PACKAGE_JSON_DUPLICATE_KEY"
        } catch JSONScanError.numberProfile {
            return "PACKAGE_NUMBER_PROFILE"
        } catch JSONScanError.numberRange {
            return "PACKAGE_NUMBER_RANGE"
        } catch {
            return "PACKAGE_INVALID_JSON"
        }
    }

    private struct JSONKeyScanner {
        let bytes: [UInt8]
        var index = 0
        var canonical = true

        mutating func parseDocument() throws {
            skipWhitespace()
            try parseValue()
            skipWhitespace()
            if index != bytes.count { throw JSONScanError.malformed }
        }

        mutating func parseValue() throws {
            skipWhitespace()
            guard index < bytes.count else { throw JSONScanError.malformed }
            switch bytes[index] {
            case 0x7b: try parseObject()
            case 0x5b: try parseArray()
            case 0x22: _ = try parseString()
            case 0x74: try consumeLiteral([0x74, 0x72, 0x75, 0x65])
            case 0x66: try consumeLiteral([0x66, 0x61, 0x6c, 0x73, 0x65])
            case 0x6e: try consumeLiteral([0x6e, 0x75, 0x6c, 0x6c])
            case 0x2d, 0x30...0x39: try consumeNumber()
            default: throw JSONScanError.malformed
            }
        }

        mutating func parseObject() throws {
            index += 1
            skipWhitespace()
            if consume(0x7d) { return }
            var keys = Set<String>()
            var previousKey: String?
            while true {
                let key = try parseString()
                if !keys.insert(key).inserted { throw JSONScanError.duplicateKey }
                if let previousKey,
                   !Array(previousKey.utf16).lexicographicallyPrecedes(Array(key.utf16)) {
                    canonical = false
                }
                previousKey = key
                skipWhitespace()
                guard consume(0x3a) else { throw JSONScanError.malformed }
                try parseValue()
                skipWhitespace()
                if consume(0x7d) { return }
                guard consume(0x2c) else { throw JSONScanError.malformed }
                skipWhitespace()
            }
        }

        mutating func parseArray() throws {
            index += 1
            skipWhitespace()
            if consume(0x5d) { return }
            while true {
                try parseValue()
                skipWhitespace()
                if consume(0x5d) { return }
                guard consume(0x2c) else { throw JSONScanError.malformed }
            }
        }

        mutating func parseString() throws -> String {
            skipWhitespace()
            guard index < bytes.count, bytes[index] == 0x22 else {
                throw JSONScanError.malformed
            }
            let start = index
            index += 1
            var escaped = false
            while index < bytes.count {
                let byte = bytes[index]
                index += 1
                if escaped { escaped = false; continue }
                if byte == 0x5c { escaped = true; continue }
                if byte == 0x22 {
                    let value = try JSONDecoder().decode(
                        String.self, from: Data(bytes[start..<index])
                    )
                    if Array(bytes[start..<index]) != canonicalJSONString(value) {
                        canonical = false
                    }
                    return value
                }
                if byte < 0x20 { throw JSONScanError.malformed }
            }
            throw JSONScanError.malformed
        }

        mutating func consumeLiteral(_ literal: [UInt8]) throws {
            guard index + literal.count <= bytes.count,
                  Array(bytes[index..<(index + literal.count)]) == literal else {
                throw JSONScanError.malformed
            }
            index += literal.count
        }

        mutating func consumeNumber() throws {
            let start = index
            while index < bytes.count,
                  ![0x20, 0x09, 0x0a, 0x0d, 0x2c, 0x5d, 0x7d].contains(bytes[index]) {
                index += 1
            }
            if index == start { throw JSONScanError.malformed }
            let token = Array(bytes[start..<index])
            if token.contains(0x2e) || token.contains(0x65) || token.contains(0x45) {
                throw JSONScanError.numberProfile
            }
            var digits = token
            if digits.first == 0x2d { digits.removeFirst() }
            guard !digits.isEmpty, digits.allSatisfy({ $0 >= 0x30 && $0 <= 0x39 }),
                  digits.count == 1 || digits.first != 0x30 else {
                throw JSONScanError.malformed
            }
            while digits.count > 1 && digits.first == 0x30 { digits.removeFirst() }
            let maximum = Array("9007199254740991".utf8)
            if digits.count > maximum.count ||
                (digits.count == maximum.count && digits.lexicographicallyPrecedes(maximum) == false &&
                    digits != maximum) {
                throw JSONScanError.numberRange
            }
            if token == [0x2d, 0x30] { canonical = false }
        }

        mutating func skipWhitespace() {
            let start = index
            while index < bytes.count, [0x20, 0x09, 0x0a, 0x0d].contains(bytes[index]) {
                index += 1
            }
            if index != start { canonical = false }
        }

        mutating func consume(_ byte: UInt8) -> Bool {
            guard index < bytes.count, bytes[index] == byte else { return false }
            index += 1
            return true
        }

        func canonicalJSONString(_ value: String) -> [UInt8] {
            var output: [UInt8] = [0x22]
            let hex = Array("0123456789abcdef".utf8)
            for scalar in value.unicodeScalars {
                switch scalar.value {
                case 0x22: output += [0x5c, 0x22]
                case 0x5c: output += [0x5c, 0x5c]
                case 0x08: output += [0x5c, 0x62]
                case 0x09: output += [0x5c, 0x74]
                case 0x0a: output += [0x5c, 0x6e]
                case 0x0c: output += [0x5c, 0x66]
                case 0x0d: output += [0x5c, 0x72]
                case 0x00...0x1f:
                    output += [0x5c, 0x75, 0x30, 0x30,
                               hex[Int(scalar.value >> 4)], hex[Int(scalar.value & 0x0f)]]
                default: output += Array(String(scalar).utf8)
                }
            }
            output.append(0x22)
            return output
        }
    }

    private struct UTF8Validator {
        var remaining = 0
        var scalar = 0
        var minimum = 0
        var complete: Bool { remaining == 0 }

        mutating func consume(_ data: Data) -> Bool {
            for byte in data {
                if remaining == 0 {
                    if byte <= 0x7f { continue }
                    if byte >= 0xc2 && byte <= 0xdf {
                        remaining = 1; scalar = Int(byte & 0x1f); minimum = 0x80
                    } else if byte >= 0xe0 && byte <= 0xef {
                        remaining = 2; scalar = Int(byte & 0x0f); minimum = 0x800
                    } else if byte >= 0xf0 && byte <= 0xf4 {
                        remaining = 3; scalar = Int(byte & 0x07); minimum = 0x10000
                    } else { return false }
                } else {
                    guard byte >= 0x80 && byte <= 0xbf else { return false }
                    scalar = scalar << 6 | Int(byte & 0x3f)
                    remaining -= 1
                    if remaining == 0 && (scalar < minimum || scalar > 0x10ffff ||
                        (scalar >= 0xd800 && scalar <= 0xdfff)) { return false }
                }
            }
            return true
        }
    }

    /// Inspect fields not exposed by ZIPFoundation without loading the archive into memory.
    private static func rawMetadataCode(_ source: URL) throws -> String? {
        let file = try FileHandle(forReadingFrom: source)
        defer { try? file.close() }
        let length = try file.seekToEnd()
        let tailStart = length > maxEndSearch ? length - maxEndSearch : 0
        let tail = try read(file, at: tailStart, count: Int(length - tailStart))
        guard tail.count >= 22 else { throw CocoaError(.fileReadCorruptFile) }
        var relativeEnd: Int?
        for offset in stride(from: tail.count - 22, through: 0, by: -1) {
            if u32(tail, offset) == endHeader {
                relativeEnd = offset
                break
            }
        }
        guard let relativeEnd else { throw CocoaError(.fileReadCorruptFile) }
        let end = tailStart + UInt64(relativeEnd)
        if u16(tail, relativeEnd + 20) != 0 { return "PACKAGE_ZIP_METADATA" }
        var entryCount = UInt64(u16(tail, relativeEnd + 10))
        var centralOffset = UInt64(u32(tail, relativeEnd + 16))
        if entryCount == 0xffff || centralOffset == 0xffff_ffff {
            guard end >= 20 else { throw CocoaError(.fileReadCorruptFile) }
            let locator = try read(file, at: end - 20, count: 20)
            guard u32(locator, 0) == zip64Locator else { throw CocoaError(.fileReadCorruptFile) }
            let zip64Offset = u64(locator, 8)
            let zip64 = try read(file, at: zip64Offset, count: 56)
            guard u32(zip64, 0) == zip64End else { throw CocoaError(.fileReadCorruptFile) }
            entryCount = u64(zip64, 32)
            centralOffset = u64(zip64, 48)
        }
        guard entryCount <= UInt64(maxEntries) else { return nil }
        var cursor = centralOffset
        for _ in 0..<entryCount {
            let header = try read(file, at: cursor, count: 46)
            guard u32(header, 0) == centralHeader else { throw CocoaError(.fileReadCorruptFile) }
            let nameLength = UInt64(u16(header, 28))
            let extraLength = UInt64(u16(header, 30))
            let commentLength = UInt64(u16(header, 32))
            if extraLength != 0 || commentLength != 0 { return "PACKAGE_ZIP_METADATA" }
            cursor += 46 + nameLength + extraLength + commentLength
            guard cursor <= length else { throw CocoaError(.fileReadCorruptFile) }
        }
        return nil
    }

    private static func read(_ file: FileHandle, at offset: UInt64, count: Int) throws -> Data {
        try file.seek(toOffset: offset)
        guard let data = try file.read(upToCount: count), data.count == count else {
            throw CocoaError(.fileReadCorruptFile)
        }
        return data
    }

    private static func u16(_ data: Data, _ offset: Int) -> UInt16 {
        UInt16(data[offset]) | UInt16(data[offset + 1]) << 8
    }

    private static func u32(_ data: Data, _ offset: Int) -> UInt32 {
        UInt32(u16(data, offset)) | UInt32(u16(data, offset + 2)) << 16
    }

    private static func u64(_ data: Data, _ offset: Int) -> UInt64 {
        UInt64(u32(data, offset)) | UInt64(u32(data, offset + 4)) << 32
    }

    private static let endHeader: UInt32 = 0x0605_4b50
    private static let centralHeader: UInt32 = 0x0201_4b50
    private static let zip64End: UInt32 = 0x0606_4b50
    private static let zip64Locator: UInt32 = 0x0706_4b50
    private static let maxEndSearch: UInt64 = 65_557
    private static let forbiddenSuffixes = [
        ".app", ".apk", ".bat", ".cmd", ".dll", ".dylib", ".exe", ".gguf",
        ".html", ".htm", ".jar", ".js", ".model", ".safetensors", ".sh", ".so",
    ]
    private static let requiredSourceKinds = [
        "biome_grid_catalog", "biomes", "civilizations", "climate", "climate_grid_catalog",
        "ecology", "economy", "genealogy", "geology", "geology_grid_catalog", "history",
        "hydrology", "hydrology_grid_catalog", "identities", "legendary_artifact_histories",
        "legendary_artifacts", "map_layers", "maps", "megabeasts", "plates", "reference_index",
        "region_grid_catalog", "regions", "registries", "resource_grid_catalog", "resources",
        "routes", "settlements", "simulation_index", "sites", "snapshots", "soil",
        "soil_grid_catalog", "spatial_index", "species", "terrain", "terrain_grid_catalog",
        "validation_report", "world_index",
    ]
    private static let climateSeasonFields = [
        "temperature_millic", "precipitation_mm", "evaporation_mm", "snowpack_mm", "ice",
        "storm_ppm", "wind_x_mmps", "wind_y_mmps", "hazard_ppm",
    ]

    private static func safetyCode(_ entries: [Entry]) -> String? {
        if entries.count > maxEntries { return "PACKAGE_ENTRY_LIMIT" }
        var seen = Set<String>()
        var portable = Set<String>()
        var totalBytes: UInt64 = 0
        for entry in entries {
            let name = entry.path
            let parts = name.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
                .split(separator: "/", omittingEmptySubsequences: false)
            if name.isEmpty || name.contains("\\") || name.hasPrefix("/") ||
                parts.contains(where: { $0.isEmpty || $0 == "." || $0 == ".." }) {
                return "PACKAGE_UNSAFE_PATH"
            }
            if entry.type == .symlink { return "PACKAGE_LINK" }
            let normalized = name.precomposedStringWithCanonicalMapping.lowercased()
            if !seen.insert(name).inserted || !portable.insert(normalized).inserted {
                return "PACKAGE_DUPLICATE_PATH"
            }
            if forbiddenMember(name) { return "PACKAGE_FORBIDDEN_ENTRY" }
            if entry.uncompressedSize > maxEntryBytes { return "PACKAGE_SIZE_LIMIT" }
            if totalBytes > maxTotalBytes - entry.uncompressedSize { return "PACKAGE_SIZE_LIMIT" }
            totalBytes += entry.uncompressedSize
            if entry.uncompressedSize > 0 &&
                (entry.compressedSize == 0 || Double(entry.uncompressedSize) / Double(entry.compressedSize) > maxRatio) {
                return "PACKAGE_COMPRESSION_LIMIT"
            }
        }
        return nil
    }

    private static func forbiddenMember(_ path: String) -> Bool {
        let lowered = path.lowercased()
        return path == "save" || path.hasPrefix("save/") || path.hasPrefix("content/") ||
            forbiddenSuffixes.contains(where: lowered.hasSuffix)
    }

    private static func inventoryCode(
        _ manifest: V2Manifest,
        _ archive: Archive,
        _ names: Set<String>
    ) throws -> String? {
        if manifest.artifacts.map(\.path) != manifest.artifacts.sorted(by: {
            utf8PathLessThan($0.path, $1.path)
        }).map(\.path) { return "PACKAGE_ARRAY_ORDER" }
        var declared: Set<String> = ["manifest.json"]
        let artifactIDs = Set(manifest.artifacts.map(\.artifactId))
        if artifactIDs.count != manifest.artifacts.count { return "PACKAGE_DUPLICATE_ID" }
        let artifactPaths = Set(manifest.artifacts.map(\.path))
        if artifactPaths.count != manifest.artifacts.count { return "PACKAGE_DUPLICATE_ID" }
        for artifact in manifest.artifacts {
            guard let entry = archive[artifact.path] else { return "PACKAGE_MISSING_ARTIFACT" }
            let data = try read(entry, archive)
            if Int64(data.count) != artifact.sizeBytes || SHA256.hash(data: data).hex != artifact.sha256 {
                return "PACKAGE_HASH_MISMATCH"
            }
            if artifact.producer.schemaSha256 != TrustedV2Schemas.digest {
                return "PACKAGE_SCHEMA_IDENTITY"
            }
            declared.insert(artifact.path)
        }
        if manifest.artifacts.contains(where: { artifact in
            artifact.dependsOn.contains(where: { !artifactIDs.contains($0) })
        }) { return "PACKAGE_PROVENANCE_BROKEN" }
        if hasDependencyCycle(manifest.artifacts) { return "PACKAGE_PROVENANCE_CYCLE" }
        for artifact in manifest.artifacts {
            let identity: [String: Any] = [
                "depends_on": artifact.dependsOn.sorted(), "kind": artifact.kind,
                "producer_fingerprint": artifact.producer.fingerprint, "sha256": artifact.sha256,
            ]
            let bytes = try JSONSerialization.data(
                withJSONObject: identity, options: [.sortedKeys, .withoutEscapingSlashes]
            )
            let prefix = artifact.kind.lowercased().filter { $0.isLetter || $0.isNumber }
            let expected = "\(prefix)_\(SHA256.hash(data: bytes).hex.prefix(32))"
            if artifact.artifactId != expected { return "PACKAGE_ARTIFACT_ID" }
        }
        let reduced: [[String: Any]] = manifest.artifacts.sorted {
            utf8PathLessThan($0.path, $1.path)
        }.map { artifact in
            [
                "artifact_id": artifact.artifactId,
                "depends_on": artifact.dependsOn.sorted(),
                "kind": artifact.kind,
                "path": artifact.path,
                "producer_fingerprint": artifact.producer.fingerprint,
                "sha256": artifact.sha256,
                "size_bytes": artifact.sizeBytes,
            ]
        }
        let contentBytes = try JSONSerialization.data(
            withJSONObject: reduced, options: [.sortedKeys, .withoutEscapingSlashes]
        )
        let contentHash = SHA256.hash(data: contentBytes).hex
        if manifest.contentHash != contentHash ||
            manifest.storyId != "story_\(contentHash.prefix(32))" { return "PACKAGE_CONTENT_ID" }
        if declared != names { return "PACKAGE_UNDECLARED_ENTRY" }
        return nil
    }

    private static func hasDependencyCycle(_ artifacts: [ArtifactRecord]) -> Bool {
        let byID = Dictionary(uniqueKeysWithValues: artifacts.map { ($0.artifactId, $0) })
        var visiting = Set<String>()
        var visited = Set<String>()
        func visit(_ id: String) -> Bool {
            if visiting.contains(id) { return true }
            if visited.contains(id) { return false }
            visited.insert(id)
            visiting.insert(id)
            guard let artifact = byID[id] else { return true }
            if artifact.dependsOn.contains(where: visit) { return true }
            visiting.remove(id)
            return false
        }
        return byID.keys.contains(where: visit)
    }

    private static func sourceCoverageCode(_ archive: Archive, _ names: Set<String>) throws -> String? {
        let coveragePath = "world/source/coverage.json"
        guard let coverageEntry = archive[coveragePath],
              let ledger = try JSONSerialization.jsonObject(
                with: read(coverageEntry, archive)
              ) as? [String: Any],
              ledger["format"] as? String == "storyteller.world-source-coverage.v1",
              ledger["required_domains"] as? [String] == requiredSourceKinds,
              let rows = ledger["sources"] as? [[String: Any]] else {
            return "PACKAGE_WORLD_SOURCE_COVERAGE"
        }
        let sourcePaths = Set(names.filter {
            $0.hasPrefix("world/source/") && $0.hasSuffix(".json") && $0 != coveragePath
        })
        let rowPaths = rows.compactMap { $0["archive_path"] as? String }
        if rowPaths.count != Set(rowPaths).count || Set(rowPaths) != sourcePaths {
            return "PACKAGE_WORLD_SOURCE_COVERAGE"
        }
        guard let worldEntry = archive["world/index.json"],
              let world = try JSONSerialization.jsonObject(
                with: read(worldEntry, archive)
              ) as? [String: Any], let domains = world["domains"] as? [String] else {
            return "PACKAGE_WORLD_SOURCE_COVERAGE"
        }
        let sourceNames = Set(sourcePaths.map {
            URL(fileURLWithPath: $0).deletingPathExtension().lastPathComponent
        })
        if Set(domains) != sourceNames || !Set(requiredSourceKinds).isSubset(of: Set(domains)) {
            return "PACKAGE_WORLD_SOURCE_COVERAGE"
        }
        for row in rows {
            guard let path = row["archive_path"] as? String, let entry = archive[path] else {
                return "PACKAGE_WORLD_SOURCE_COVERAGE"
            }
            let data = try read(entry, archive)
            guard let envelope = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                  row["source_name"] as? String == URL(fileURLWithPath: path)
                    .deletingPathExtension().lastPathComponent,
                  row["retention"] as? String == "byte_for_byte",
                  (row["size_bytes"] as? NSNumber)?.int64Value == Int64(data.count),
                  row["sha256"] as? String == SHA256.hash(data: data).hex,
                  row["artifact_id"] as? String == envelope["artifact_id"] as? String else {
                return "PACKAGE_WORLD_SOURCE_COVERAGE"
            }
        }
        return nil
    }

    private static func gridDomainCode(_ archive: Archive, _ names: Set<String>) throws -> String? {
        for domain in ["terrain", "geology", "hydrology", "climate", "biomes", "resource_grid"] {
            let indexPath = "world/\(domain)/index.json"
            guard let entry = archive[indexPath],
                  let index = try JSONSerialization.jsonObject(
                    with: read(entry, archive)
                  ) as? [String: Any],
                  index["format"] as? String == "storyteller.grid-domain-index.v1",
                  let width = (index["width"] as? NSNumber)?.intValue,
                  let height = (index["height"] as? NSNumber)?.intValue,
                  let layers = index["layers"] as? [String: Any], !layers.isEmpty else {
                return "PACKAGE_GRID_DOMAIN"
            }
            for (layer, rawLayerIndex) in layers {
                guard let layerIndex = rawLayerIndex as? [String: Any],
                      let chunkWidth = (layerIndex["chunk_width"] as? NSNumber)?.intValue,
                      let chunkHeight = (layerIndex["chunk_height"] as? NSNumber)?.intValue,
                      (1...256).contains(chunkWidth), (1...256).contains(chunkHeight),
                      let descriptors = layerIndex["chunks"] as? [[String: Any]] else {
                    return "PACKAGE_GRID_DOMAIN"
                }
                var expected: [[Int]] = []
                for y in stride(from: 0, to: height, by: chunkHeight) {
                    for x in stride(from: 0, to: width, by: chunkWidth) {
                        expected.append([
                            y / chunkHeight, x / chunkWidth,
                            min(chunkWidth, width - x), min(chunkHeight, height - y),
                        ])
                    }
                }
                let actual = try descriptors.map { descriptor in
                    try ["chunk_y", "chunk_x", "width", "height"].map {
                        try required(descriptor[$0], NSNumber.self).intValue
                    }
                }
                if actual != expected { return "PACKAGE_GRID_DOMAIN" }
                for descriptor in descriptors {
                    guard let hash = descriptor["sha256"] as? String else {
                        return "PACKAGE_GRID_DOMAIN"
                    }
                    let path = "world/\(domain)/chunks/\(layer)/\(hash).bin"
                    guard names.contains(path), let chunkEntry = archive[path] else {
                        return "PACKAGE_GRID_CHUNK_COVERAGE"
                    }
                    let data = try read(chunkEntry, archive)
                    if SHA256.hash(data: data).hex != hash ||
                        !validGridChunk(data, layer, descriptor) {
                        return "PACKAGE_GRID_CHUNK_HASH"
                    }
                }
            }
        }
        return nil
    }

    private static func validGridChunk(
        _ data: Data, _ layer: String, _ descriptor: [String: Any]
    ) -> Bool {
        guard data.count >= 5 else { return false }
        let headerSize = Int(data[0]) << 24 | Int(data[1]) << 16 | Int(data[2]) << 8 | Int(data[3])
        guard (1...1024).contains(headerSize), 4 + headerSize <= data.count else { return false }
        let headerBytes = data.subdata(in: 4..<(4 + headerSize))
        guard let header = try? JSONSerialization.jsonObject(with: headerBytes) as? [String: Any],
              let canonical = try? JSONSerialization.data(
                withJSONObject: header, options: [.sortedKeys, .withoutEscapingSlashes]
              ), canonical == headerBytes,
              header["format"] as? String == "storyteller.grid.i32be.v1",
              header["layer"] as? String == layer,
              let width = (header["width"] as? NSNumber)?.intValue,
              let height = (header["height"] as? NSNumber)?.intValue,
              (1...256).contains(width), (1...256).contains(height),
              data.count == 4 + headerSize + width * height * 4 else { return false }
        for name in ["chunk_x", "chunk_y", "width", "height"] {
            if (header[name] as? NSNumber)?.intValue != (descriptor[name] as? NSNumber)?.intValue {
                return false
            }
        }
        return true
    }

    private static func climateLayerCode(_ archive: Archive) throws -> String? {
        guard let sourceEntry = archive["world/source/climate.json"],
              let source = try JSONSerialization.jsonObject(
                with: read(sourceEntry, archive)
              ) as? [String: Any], let payload = source["payload"] as? [String: Any],
              let seasonCount = (payload["season_count"] as? NSNumber)?.intValue,
              (1...12).contains(seasonCount) else { return "PACKAGE_CLIMATE_LAYERS" }
        var expected: Set<String> = [
            "climate_annual_temperature_millic", "climate_annual_precipitation_mm",
            "climate_weather_regime",
        ]
        for index in 0..<seasonCount {
            let prefix = String(format: "climate_season_%02d", index)
            for field in climateSeasonFields { expected.insert("\(prefix)_\(field)") }
        }
        guard let climateEntry = archive["world/climate/index.json"],
              let climate = try JSONSerialization.jsonObject(
                with: read(climateEntry, archive)
              ) as? [String: Any], let layers = climate["layers"] as? [String: Any],
              Set(layers.keys) == expected else { return "PACKAGE_CLIMATE_LAYERS" }
        return nil
    }

    private static func physicalLayerCode(_ archive: Archive) throws -> String? {
        let expected: [String: Set<String>] = [
            "hydrology": [
                "hydrology_filled_elevation_mm", "hydrology_flow_to", "hydrology_accumulation",
                "hydrology_watershed_id", "hydrology_coastline", "hydrology_aquifer_capacity_mm",
                "hydrology_salinity_ppm", "hydrology_snowpack_mm", "hydrology_glacier",
                "hydrology_delta",
            ],
            "geology": [
                "geology_rock_class_id", "geology_strata_id", "geology_parent_material_id",
                "geology_fault", "geology_volcano", "geology_tectonic_relief_mm",
            ],
            "resource_grid": ["resource_renewable_yield"],
        ]
        for (domain, required) in expected {
            guard let entry = archive["world/\(domain)/index.json"],
                  let document = try JSONSerialization.jsonObject(
                    with: read(entry, archive)
                  ) as? [String: Any], let layers = document["layers"] as? [String: Any],
                  Set(layers.keys) == required else {
                return domain == "hydrology" ?
                    "PACKAGE_HYDROLOGY_CATALOG" : "PACKAGE_RESOURCE_CATALOG"
            }
        }
        return nil
    }

    private static func regionSiteCode(_ archive: Archive) throws -> String? {
        func document(_ path: String) throws -> [String: Any] {
            guard let entry = archive[path], let value = try JSONSerialization.jsonObject(
                with: read(entry, archive)
            ) as? [String: Any] else { throw CocoaError(.fileReadCorruptFile) }
            return value
        }
        let world = try document("world/index.json")
        guard let width = (world["width"] as? NSNumber)?.intValue,
              let height = (world["height"] as? NSNumber)?.intValue,
              width > 0, height > 0,
              let regions = try document("world/regions.json")["regions"] as? [[String: Any]],
              !regions.isEmpty else { return "PACKAGE_REGION_PARTITION" }
        var owners: [String: Set<Int>] = [:]
        var allCells: [Int] = []
        var neighborMap: [String: [String]] = [:]
        for region in regions {
            guard let id = region["region_id"] as? String, owners[id] == nil,
                  let numbers = region["cells"] as? [NSNumber], !numbers.isEmpty,
                  let neighbors = region["neighbors"] as? [String] else {
                return "PACKAGE_REGION_PARTITION"
            }
            let cells = numbers.map(\.intValue)
            guard cells.count == Set(cells).count else { return "PACKAGE_REGION_PARTITION" }
            owners[id] = Set(cells); allCells.append(contentsOf: cells); neighborMap[id] = neighbors
        }
        guard allCells.sorted() == Array(0..<(width * height)) else {
            return "PACKAGE_REGION_PARTITION"
        }
        for (id, neighbors) in neighborMap {
            guard !neighbors.contains(id), neighbors.count == Set(neighbors).count,
                  neighbors.allSatisfy({ owners[$0] != nil && neighborMap[$0]?.contains(id) == true })
            else { return "PACKAGE_REGION_PARTITION" }
        }
        guard let sites = try document("world/sites.json")["sites"] as? [[String: Any]] else {
            return "PACKAGE_SITE_REGION"
        }
        var siteIDs: Set<String> = []
        for site in sites {
            guard let id = site["site_id"] as? String, siteIDs.insert(id).inserted,
                  let region = site["region_id"] as? String,
                  let cell = (site["cell"] as? NSNumber)?.intValue,
                  owners[region]?.contains(cell) == true else { return "PACKAGE_SITE_REGION" }
        }
        return nil
    }

    private static func routeTopologyCode(_ archive: Archive, _ manifest: V2Manifest) throws -> String? {
        func document(_ path: String) throws -> [String: Any] {
            guard let entry = archive[path], let value = try JSONSerialization.jsonObject(
                with: read(entry, archive)
            ) as? [String: Any] else { throw CocoaError(.fileReadCorruptFile) }
            return value
        }
        let world = try document("world/index.json")
        guard let width = (world["width"] as? NSNumber)?.intValue,
              let height = (world["height"] as? NSNumber)?.intValue,
              let regions = try document("world/regions.json")["regions"] as? [[String: Any]]
        else { return "PACKAGE_ROUTE_TOPOLOGY" }
        var owners: [String: Set<Int>] = [:]
        for region in regions {
            guard let id = region["region_id"] as? String,
                  let cells = region["cells"] as? [NSNumber], owners[id] == nil else {
                return "PACKAGE_ROUTE_TOPOLOGY"
            }
            owners[id] = Set(cells.map(\.intValue))
        }
        guard let routes = try document("world/routes.json")["routes"] as? [[String: Any]] else {
            return "PACKAGE_ROUTE_TOPOLOGY"
        }
        let sources = Set(manifest.artifacts.map(\.artifactId))
        var ids: Set<String> = []
        func contiguous(_ cells: [Int]) -> Bool {
            zip(cells, cells.dropFirst()).allSatisfy { left, right in
                abs(left % width - right % width) + abs(left / width - right / width) == 1
            }
        }
        for route in routes {
            guard let id = route["route_id"] as? String, ids.insert(id).inserted,
                  let start = route["start_region"] as? String,
                  let end = route["end_region"] as? String, start != end,
                  let startCells = owners[start], let endCells = owners[end],
                  let numbers = route["cells"] as? [NSNumber], !numbers.isEmpty,
                  let seasonalNumbers = route["seasonal_cells"] as? [[NSNumber]],
                  seasonalNumbers.count == 4, let refs = route["source_ids"] as? [String]
            else { return "PACKAGE_ROUTE_TOPOLOGY" }
            let cells = numbers.map(\.intValue)
            let seasonal = seasonalNumbers.map { $0.map(\.intValue) }
            guard cells.allSatisfy({ (0..<(width * height)).contains($0) }),
                  let first = cells.first, let last = cells.last,
                  startCells.contains(first), endCells.contains(last),
                  contiguous(cells), seasonal.allSatisfy({ !$0.isEmpty &&
                      $0.first == cells.first && $0.last == cells.last && contiguous($0) }),
                  refs.allSatisfy(sources.contains)
            else { return "PACKAGE_ROUTE_TOPOLOGY" }
        }
        return nil
    }

    private static func hydrologyCatalogCode(_ archive: Archive) throws -> String? {
        func document(_ path: String) throws -> [String: Any] {
            guard let entry = archive[path], let value = try JSONSerialization.jsonObject(
                with: read(entry, archive)
            ) as? [String: Any] else { throw CocoaError(.fileReadCorruptFile) }
            return value
        }
        let world = try document("world/index.json")
        guard let width = (world["width"] as? NSNumber)?.intValue,
              let height = (world["height"] as? NSNumber)?.intValue else {
            return "PACKAGE_HYDROLOGY_CATALOG"
        }
        let cellCount = width * height
        let hydro = try document("world/hydrology.json")
        guard let lakes = hydro["lakes"] as? [[String: Any]],
              let rivers = hydro["rivers"] as? [[String: Any]],
              let terminals = hydro["terminals"] as? [[String: Any]] else {
            return "PACKAGE_HYDROLOGY_CATALOG"
        }
        var lakeIDs: Set<String> = []; var lakeCells: Set<Int> = []
        for lake in lakes {
            guard let id = lake["lake_id"] as? String, lakeIDs.insert(id).inserted,
                  let values = lake["cells"] as? [NSNumber] else {
                return "PACKAGE_HYDROLOGY_CATALOG"
            }
            let cells = values.map(\.intValue)
            let spillway = (lake["spillway_cell"] as? NSNumber)?.intValue
            let outlet = (lake["outlet"] as? NSNumber)?.intValue
            guard cells.count == Set(cells).count,
                  cells.allSatisfy({ (0..<cellCount).contains($0) }),
                  lakeCells.isDisjoint(with: cells),
                  spillway.map(cells.contains) ?? true,
                  outlet.map({ (0..<cellCount).contains($0) }) ?? true else {
                return "PACKAGE_HYDROLOGY_CATALOG"
            }
            lakeCells.formUnion(cells)
        }
        var edges: Set<String> = []
        for river in rivers {
            guard let up = (river["upstream"] as? NSNumber)?.intValue,
                  let down = (river["downstream"] as? NSNumber)?.intValue,
                  let discharge = (river["discharge_m3s"] as? NSNumber)?.int64Value,
                  let seasonal = river["seasonal_discharge_m3s"] as? [NSNumber],
                  up != down, (0..<cellCount).contains(up), (0..<cellCount).contains(down),
                  edges.insert("\(up):\(down)").inserted, discharge >= 0, seasonal.count == 4,
                  seasonal.allSatisfy({ $0.int64Value >= 0 }) else {
                return "PACKAGE_HYDROLOGY_CATALOG"
            }
        }
        var terminalIDs: Set<String> = []; var terminalCells: Set<Int> = []
        for terminal in terminals {
            guard let id = terminal["terminal_id"] as? String, terminalIDs.insert(id).inserted,
                  let cell = (terminal["cell"] as? NSNumber)?.intValue,
                  (0..<cellCount).contains(cell), terminalCells.insert(cell).inserted else {
                return "PACKAGE_HYDROLOGY_CATALOG"
            }
        }
        return nil
    }

    private static func gridValues(_ archive: Archive, _ domain: String, _ layer: String) throws -> [Int] {
        let indexEntry = try requiredEntry("world/\(domain)/index.json", archive)
        let index: [String: Any] = try required(
            JSONSerialization.jsonObject(with: read(indexEntry, archive))
        )
        let width = try required(index["width"], NSNumber.self).intValue
        let height = try required(index["height"], NSNumber.self).intValue
        let layers: [String: [String: Any]] = try required(index["layers"])
        let layerIndex: [String: Any] = try required(layers[layer])
        let chunks: [[String: Any]] = try required(layerIndex["chunks"])
        var output = Array(repeating: 0, count: width * height)
        for descriptor in chunks {
            let hash: String = try required(descriptor["sha256"])
            let data = try read(
                requiredEntry("world/\(domain)/chunks/\(layer)/\(hash).bin", archive), archive
            )
            let bytes = [UInt8](data)
            guard bytes.count >= 4 else { throw PackageShapeError.invalid }
            let headerSize = Int(bytes[0]) << 24 | Int(bytes[1]) << 16 |
                Int(bytes[2]) << 8 | Int(bytes[3])
            guard headerSize >= 0, 4 + headerSize <= bytes.count else {
                throw PackageShapeError.invalid
            }
            let header: [String: Any] = try required(JSONSerialization.jsonObject(
                with: Data(bytes[4..<(4 + headerSize)])
            ))
            let chunkX = try required(header["chunk_x"], NSNumber.self).intValue
            let chunkY = try required(header["chunk_y"], NSNumber.self).intValue
            let chunkWidth = try required(header["width"], NSNumber.self).intValue
            let chunkHeight = try required(header["height"], NSNumber.self).intValue
            guard chunkX >= 0, chunkY >= 0, chunkWidth > 0, chunkHeight > 0,
                  chunkX + chunkWidth <= width, chunkY + chunkHeight <= height,
                  4 + headerSize + chunkWidth * chunkHeight * 4 == bytes.count else {
                throw PackageShapeError.invalid
            }
            var offset = 4 + headerSize
            for y in 0..<chunkHeight { for x in 0..<chunkWidth {
                let raw = UInt32(bytes[offset]) << 24 | UInt32(bytes[offset + 1]) << 16 |
                    UInt32(bytes[offset + 2]) << 8 | UInt32(bytes[offset + 3])
                output[(chunkY + y) * width + chunkX + x] = Int(Int32(bitPattern: raw))
                offset += 4
            }}
        }
        return output
    }

    private static func resourceGeologyCode(
        _ archive: Archive, _ manifest: V2Manifest
    ) throws -> String? {
        let world: [String: Any] = try required(JSONSerialization.jsonObject(
            with: read(requiredEntry("world/index.json", archive), archive)
        ))
        guard let width = (world["width"] as? NSNumber)?.intValue,
              let height = (world["height"] as? NSNumber)?.intValue else {
            return "PACKAGE_RESOURCE_CATALOG"
        }
        let rawManifest: [String: Any] = try required(JSONSerialization.jsonObject(
            with: read(requiredEntry("manifest.json", archive), archive)
        ))
        guard let manifestWorld = rawManifest["world"] as? [String: Any],
              let scale = (manifestWorld["metres_per_world_cell"] as? NSNumber)?.int64Value else {
            return "PACKAGE_RESOURCE_CATALOG"
        }
        let rock = try gridValues(archive, "geology", "geology_rock_class_id")
        let strata = try gridValues(archive, "geology", "geology_strata_id")
        let fault = try gridValues(archive, "geology", "geology_fault")
        let volcano = try gridValues(archive, "geology", "geology_volcano")
        if try gridValues(archive, "resource_grid", "resource_renewable_yield").contains(where: { $0 < 0 }) {
            return "PACKAGE_RESOURCE_CATALOG"
        }
        let resources: [String: Any] = try required(JSONSerialization.jsonObject(
            with: read(requiredEntry("world/resources.json", archive), archive)
        ))
        guard let deposits = resources["deposits"] as? [[String: Any]] else {
            return "PACKAGE_RESOURCE_CATALOG"
        }
        let densities: [String: Int64] = ["iron": 5000, "copper": 3000, "tin": 2000,
            "coal": 1500, "flux_stone": 4000, "gems": 250]
        var ids: Set<String> = []; var occupied: Set<Int> = []
        for deposit in deposits {
            guard let id = deposit["deposit_id"] as? String, ids.insert(id).inserted,
                  let numbers = deposit["cells"] as? [NSNumber] else {
                return "PACKAGE_DEPOSIT_GEOLOGY"
            }
            let cells = numbers.map(\.intValue)
            guard cells.count >= 2, cells == Array(Set(cells)).sorted(),
                  cells.allSatisfy({ (0..<(width * height)).contains($0) }),
                  occupied.isDisjoint(with: cells) else { return "PACKAGE_DEPOSIT_GEOLOGY" }
            var reached: Set<Int> = [cells[0]]
            while true {
                let before = reached
                reached.formUnion(cells.filter { candidate in reached.contains { cell in
                    abs(cell % width - candidate % width) + abs(cell / width - candidate / width) == 1
                }})
                if reached == before { break }
            }
            guard let rockID = (deposit["rock_class_id"] as? NSNumber)?.intValue,
                  let strataID = (deposit["strata_id"] as? NSNumber)?.intValue else {
                return "PACKAGE_DEPOSIT_GEOLOGY"
            }
            let isFault = cells.contains { fault[$0] != 0 }
            let isVolcano = cells.contains { volcano[$0] != 0 }
            guard let fallback = [
                1: "coal", 2: "iron", 3: "flux_stone", 4: "copper", 5: "iron",
            ][rockID] else { return "PACKAGE_DEPOSIT_GEOLOGY" }
            let expected = isVolcano ? "gems" : isFault ?
                (rockID % 2 == 0 ? "copper" : "tin") : fallback
            guard let grade = (deposit["grade_ppm"] as? NSNumber)?.int64Value,
                  let density = densities[expected] else { return "PACKAGE_DEPOSIT_GEOLOGY" }
            let quantity = (Int64(cells.count) * scale * scale * density * grade + 500000) / 1000000
            guard reached == Set(cells), cells.allSatisfy({ rock[$0] == rockID && strata[$0] == strataID }),
                  deposit["fault_related"] as? Bool == isFault,
                  deposit["volcanic_related"] as? Bool == isVolcano,
                  deposit["resource"] as? String == expected,
                  (deposit["quantity_kg"] as? NSNumber)?.int64Value == quantity else {
                return "PACKAGE_DEPOSIT_GEOLOGY"
            }
            occupied.formUnion(cells)
        }
        return nil
    }

    private static func civilizationCode(_ archive: Archive) throws -> String? {
        func document(_ path: String) throws -> [String: Any] {
            try required(JSONSerialization.jsonObject(
                with: read(requiredEntry(path, archive), archive)
            ))
        }
        guard let regionRecords = try document("world/regions.json")["regions"] as? [[String: Any]],
              let siteRecords = try document("world/sites.json")["sites"] as? [[String: Any]] else {
            return "PACKAGE_CIVILIZATION_REFERENCES"
        }
        let regionIDs = Set(regionRecords.compactMap { $0["region_id"] as? String })
        let siteIDs = Set(siteRecords.compactMap { $0["site_id"] as? String })
        guard regionIDs.count == regionRecords.count, siteIDs.count == siteRecords.count else {
            return "PACKAGE_CIVILIZATION_REFERENCES"
        }
        guard let languagePayload = try document("world/source/identities.json")["payload"]
                as? [String: Any],
              let languageRecords = languagePayload["languages"] as? [[String: Any]],
              let civilizations = try document("world/civilizations.json")["civilizations"]
                as? [[String: Any]], !civilizations.isEmpty else {
            return "PACKAGE_CIVILIZATION_REFERENCES"
        }
        let languageIDs = Set(languageRecords.compactMap { $0["language_id"] as? String })
        var ids: Set<String> = []; var claimed: Set<String> = []
        for civilization in civilizations {
            guard let id = civilization["civilization_id"] as? String, ids.insert(id).inserted,
                  let capital = civilization["capital_site_id"] as? String, siteIDs.contains(capital),
                  let language = civilization["language_id"] as? String, languageIDs.contains(language),
                  let territory = civilization["territory"] as? [String], !territory.isEmpty,
                  territory.allSatisfy({ regionIDs.contains($0) && !claimed.contains($0) }),
                  let economy = civilization["economy"] as? [String: NSNumber],
                  economy.values.allSatisfy({ $0.int64Value >= 0 }),
                  let population = civilization["population"] as? NSNumber,
                  population.int64Value >= 0 else { return "PACKAGE_CIVILIZATION_REFERENCES" }
            claimed.formUnion(territory)
        }
        return nil
    }

    private static func localMapCode(_ archive: Archive, _ names: Set<String>) throws -> String? {
        func object(_ path: String) throws -> [String: Any] {
            try required(JSONSerialization.jsonObject(
                with: read(requiredEntry(path, archive), archive)
            ))
        }
        guard let siteRows = try object("world/sites.json")["sites"] as? [[String: Any]] else {
            return "PACKAGE_LOCAL_MAP_COVERAGE"
        }
        let expectedSites = siteRows.compactMap { $0["site_id"] as? String }
        guard expectedSites.count == siteRows.count,
              let entries = try object("world/local/index.json")["entries"] as? [[String: Any]],
              entries.compactMap({ $0["site_id"] as? String }).count == entries.count,
              Set(entries.compactMap { $0["site_id"] as? String }) == Set(expectedSites),
              entries.count == expectedSites.count else { return "PACKAGE_LOCAL_MAP_COVERAGE" }
        for entry in entries {
            guard let site = entry["site_id"] as? String else { return "PACKAGE_LOCAL_INDEX" }
            let mapPath = "world/local/\(site)/index.json"
            guard entry["archive_path"] as? String == mapPath, names.contains(mapPath),
                  let mapEntry = archive[mapPath] else { return "PACKAGE_LOCAL_MAP_COVERAGE" }
            let mapData = try read(mapEntry, archive)
            guard entry["local_map_sha256"] as? String == SHA256.hash(data: mapData).hex,
                  let local = try JSONSerialization.jsonObject(with: mapData) as? [String: Any] else {
                return "PACKAGE_LOCAL_INDEX"
            }
            let families = [
                ("material", "material_chunk_hashes", "chunks"),
                ("occupancy", "occupancy_chunk_hashes", "occupancy_chunks"),
                ("construction", "construction_chunk_hashes", "construction_chunks"),
            ]
            for (family, hashKey, mapKey) in families {
                guard let hashes = entry[hashKey] as? [String],
                      let embedded = local[mapKey] as? [[String: Any]],
                      embedded.compactMap({ $0["sha256"] as? String }) == hashes else {
                    return "PACKAGE_LOCAL_INDEX"
                }
                let pairs = embedded.compactMap { item -> (String, [String: Any])? in
                    guard let hash = item["sha256"] as? String else { return nil }
                    return (hash, item)
                }
                guard pairs.count == embedded.count else { return "PACKAGE_LOCAL_INDEX" }
                let byHash = Dictionary(uniqueKeysWithValues: pairs)
                for hash in hashes {
                    let path = "world/local/\(site)/chunks/\(family)/\(hash).bin"
                    guard let chunkEntry = archive[path] else { return "PACKAGE_LOCAL_CHUNK_COVERAGE" }
                    let data = try read(chunkEntry, archive)
                    guard SHA256.hash(data: data).hex == hash,
                          let expected = byHash[hash],
                          try validLocalChunk(data, family: family, embedded: expected) else {
                        return "PACKAGE_LOCAL_CHUNK_HASH"
                    }
                }
            }
        }
        return nil
    }

    private static func validLocalChunk(
        _ data: Data, family: String, embedded: [String: Any]
    ) throws -> Bool {
        let magic = Data("STLCBIN1".utf8)
        guard data.count >= 12, data.prefix(8) == magic else { return false }
        let size = data[8..<12].reduce(0) { ($0 << 8) | Int($1) }
        let headerData = data.dropFirst(12)
        guard size == headerData.count,
              let header = try JSONSerialization.jsonObject(with: headerData) as? [String: Any],
              try canonicalValue(header) == headerData,
              header["format"] as? String == "storyteller.local-chunk-binary.v1",
              header["family"] as? String == family,
              let payload = header["payload"] as? [String: Any] else { return false }
        var expectedPayload = embedded
        expectedPayload.removeValue(forKey: "sha256")
        return NSDictionary(dictionary: payload).isEqual(to: expectedPayload)
    }

    private static func eventOrderCode(_ archive: Archive) throws -> String? {
        let history: [String: Any] = try required(JSONSerialization.jsonObject(
            with: read(requiredEntry("world/history/index.json", archive), archive)
        ))
        guard let paths = history["events"] as? [String], paths.count == Set(paths).count else {
            return "PACKAGE_EVENT_ORDER"
        }
        var known: Set<String> = []; var previous: (Int, Int, Int, String)?
        for path in paths {
            let event: [String: Any] = try required(JSONSerialization.jsonObject(
                with: read(requiredEntry(path, archive), archive)
            ))
            guard let id = event["event_id"] as? String,
                  let year = (event["year"] as? NSNumber)?.intValue,
                  let month = (event["month"] as? NSNumber)?.intValue,
                  let sequence = (event["sequence"] as? NSNumber)?.intValue,
                  let causes = event["causes"] as? [String],
                  path == "world/history/events/\(id).json", causes.allSatisfy(known.contains)
            else { return "PACKAGE_EVENT_ORDER" }
            let key = (year, month, sequence, id)
            if let prior = previous {
                let ordered = prior.0 < year || prior.0 == year && (prior.1 < month ||
                    prior.1 == month && (prior.2 < sequence ||
                    prior.2 == sequence && prior.3 < id))
                if !ordered { return "PACKAGE_EVENT_ORDER" }
            }
            known.insert(id); previous = key
        }
        return nil
    }

    private static func canonicalValue(_ value: Any) throws -> Data {
        if let object = value as? [String: Any] {
            var data = Data("{".utf8)
            for (index, key) in object.keys.sorted().enumerated() {
                if index > 0 { data.append(contentsOf: ",".utf8) }
                let encoded = try JSONSerialization.data(withJSONObject: [key])
                data.append(encoded.dropFirst().dropLast()); data.append(contentsOf: ":".utf8)
                data.append(try canonicalValue(required(object[key])))
            }
            data.append(contentsOf: "}".utf8); return data
        }
        if let array = value as? [Any] {
            var data = Data("[".utf8)
            for (index, item) in array.enumerated() {
                if index > 0 { data.append(contentsOf: ",".utf8) }
                data.append(try canonicalValue(item))
            }
            data.append(contentsOf: "]".utf8); return data
        }
        return Data(try JSONSerialization.data(withJSONObject: [value]).dropFirst().dropLast())
    }

    private static func snapshotCode(_ archive: Archive) throws -> String? {
        let history: [String: Any] = try required(JSONSerialization.jsonObject(
            with: read(requiredEntry("world/history/index.json", archive), archive)
        ))
        let rawManifest: [String: Any] = try required(JSONSerialization.jsonObject(
            with: read(requiredEntry("manifest.json", archive), archive)
        ))
        guard let manifestWorld = rawManifest["world"] as? [String: Any],
              let present = (manifestWorld["present_year"] as? NSNumber)?.intValue,
              let eventPaths = history["events"] as? [String] else {
            return "PACKAGE_SNAPSHOT_CADENCE"
        }
        var years = Array(stride(from: 0, through: present, by: 10))
        if years.last != present { years.append(present) }
        guard let paths = history["snapshots"] as? [String], paths == years.map({
            "world/history/snapshots/year_\(String(format: "%04d", $0)).json"
        }) else { return "PACKAGE_SNAPSHOT_CADENCE" }
        let eventYears = try eventPaths.map { path -> Int in
            let event: [String: Any] = try required(JSONSerialization.jsonObject(
                with: read(requiredEntry(path, archive), archive)
            ))
            return try required(event["year"], NSNumber.self).intValue
        }
        var previous = -1
        for (path, year) in zip(paths, years) {
            let snapshot: [String: Any] = try required(JSONSerialization.jsonObject(
                with: read(requiredEntry(path, archive), archive)
            ))
            guard (snapshot["year"] as? NSNumber)?.intValue == year,
                  let position = (snapshot["ledger_position"] as? NSNumber)?.intValue,
                  position == eventYears.filter({ $0 <= year }).count, position >= previous,
                  let state = snapshot["state"] as? [String: Any],
                  snapshot["state_hash"] as? String == SHA256.hash(data: try canonicalValue(state)).hex
            else { return "PACKAGE_SNAPSHOT_CADENCE" }
            previous = position
        }
        return nil
    }

    private static func historyReplayCode(_ archive: Archive) throws -> String? {
        let history: [String: Any] = try required(JSONSerialization.jsonObject(
            with: read(requiredEntry("world/history/index.json", archive), archive)
        ))
        let eventPaths: [String] = try required(history["events"])
        let snapshotPaths: [String] = try required(history["snapshots"])
        let events: [[String: Any]] = try eventPaths.map { path in
            try required(JSONSerialization.jsonObject(
                with: read(requiredEntry(path, archive), archive)
            ))
        }
        let snapshots: [[String: Any]] = try snapshotPaths.map { path in
            try required(JSONSerialization.jsonObject(
                with: read(requiredEntry(path, archive), archive)
            ))
        }
        var byPosition: [Int: String] = [:]
        for snapshot in snapshots {
            guard let position = (snapshot["ledger_position"] as? NSNumber)?.intValue,
                  let stateHash = snapshot["state_hash"] as? String else {
                return "PACKAGE_HISTORY_REPLAY"
            }
            byPosition[position] = stateHash
        }
        var current = byPosition[0] ?? events.first?["before_state_sha256"] as? String
        for (offset, event) in events.enumerated() {
            guard event["envelope_version"] as? String == "storyteller.history-event.v1",
                  (event["algorithm_version"] as? NSNumber)?.intValue == 1,
                  let sources = event["source_ids"] as? [String], !sources.isEmpty,
                  sources == Array(Set(sources)).sorted(),
                  event["before_state_sha256"] as? String == current,
                  let after = event["after_state_sha256"] as? String else {
                return "PACKAGE_HISTORY_REPLAY"
            }
            current = after
            if let expected = byPosition[offset + 1], expected != current {
                return "PACKAGE_HISTORY_REPLAY"
            }
        }
        return nil
    }

    private static func storyGraphCode(_ archive: Archive, _ manifest: V2Manifest) throws -> String? {
        func document(_ path: String) throws -> [String: Any] {
            try required(JSONSerialization.jsonObject(
                with: read(requiredEntry(path, archive), archive)
            ))
        }
        let graph = try document("narrative/graph.json")
        guard let nodes = graph["nodes"] as? [[String: Any]], !nodes.isEmpty,
              let start = graph["starting_node"] as? String,
              let flags = graph["flags"] as? [String], flags.count == Set(flags).count else {
            return "PACKAGE_GRAPH_SEMANTICS"
        }
        let nodePairs = nodes.compactMap { node -> (String, [String: Any])? in
            guard let id = node["node_id"] as? String else { return nil }
            return (id, node)
        }
        guard nodePairs.count == nodes.count else { return "PACKAGE_GRAPH_SEMANTICS" }
        let byID = Dictionary(uniqueKeysWithValues: nodePairs)
        guard byID.count == nodes.count, byID[start] != nil, start == manifest.entryNode,
              Set(byID.keys) == Set(manifest.nodeAssets.keys) else { return "PACKAGE_GRAPH_SEMANTICS" }
        var reached: Set<String> = [start]; var queue = [start]; var choiceIDs: Set<String> = []
        while !queue.isEmpty {
            guard let node = byID[queue.removeFirst()] else { return "PACKAGE_GRAPH_SEMANTICS" }
            guard let choices = node["choices"] as? [[String: Any]],
                  choices.isEmpty != (node["ending"] == nil) else { return "PACKAGE_GRAPH_SEMANTICS" }
            for choice in choices {
                guard let id = choice["choice_id"] as? String, choiceIDs.insert(id).inserted,
                      let target = choice["target_node"] as? String, byID[target] != nil,
                      let required = choice["requires_flags"] as? [String],
                      required.allSatisfy(flags.contains),
                      let transitionYear = (choice["transition_year"] as? NSNumber)?.intValue,
                      let worldYear = (node["world_year"] as? NSNumber)?.intValue,
                      transitionYear >= worldYear else {
                    return "PACKAGE_GRAPH_SEMANTICS"
                }
                if reached.insert(target).inserted { queue.append(target) }
            }
        }
        guard reached == Set(byID.keys) else { return "PACKAGE_GRAPH_SEMANTICS" }
        guard let scenes = try document("narrative/story.json")["scenes"] as? [[String: Any]],
              let siteRecords = try document("world/sites.json")["sites"] as? [[String: Any]],
              let civilizationRecords = try document("world/civilizations.json")["civilizations"]
                as? [[String: Any]],
              let eventPaths = try document("world/history/index.json")["events"] as? [String]
        else { return "PACKAGE_STORY_GRAPH_REFERENCES" }
        let scenePairs = scenes.compactMap { scene -> (String, [String: Any])? in
            guard let id = scene["scene_id"] as? String else { return nil }
            return (id, scene)
        }
        guard scenePairs.count == scenes.count else { return "PACKAGE_STORY_GRAPH_REFERENCES" }
        let sceneByID = Dictionary(uniqueKeysWithValues: scenePairs)
        var known = Set(manifest.artifacts.map(\.artifactId))
        let siteIDs = siteRecords.compactMap { $0["site_id"] as? String }
        let civilizationIDs = civilizationRecords.compactMap { $0["civilization_id"] as? String }
        guard siteIDs.count == siteRecords.count,
              civilizationIDs.count == civilizationRecords.count else {
            return "PACKAGE_STORY_GRAPH_REFERENCES"
        }
        known.formUnion(siteIDs)
        known.formUnion(civilizationIDs)
        known.formUnion(eventPaths.map {
            URL(fileURLWithPath: $0).deletingPathExtension().lastPathComponent
        })
        guard sceneByID.count == scenes.count else { return "PACKAGE_STORY_GRAPH_REFERENCES" }
        for node in nodes {
            guard let sceneID = node["scene_id"] as? String,
                  let scene = sceneByID[sceneID] else {
                return "PACKAGE_STORY_GRAPH_REFERENCES"
            }
            let keys = ["location_id", "participant_ids", "opportunity_id", "authoritative_refs", "world_year"]
            guard keys.allSatisfy({ key in
                guard let nodeValue = node[key], let sceneValue = scene[key] else { return false }
                return NSDictionary(dictionary: ["v": nodeValue]) ==
                    NSDictionary(dictionary: ["v": sceneValue])
            }),
                  let location = node["location_id"] as? String, known.contains(location),
                  let participants = node["participant_ids"] as? [String],
                  participants.allSatisfy(known.contains),
                  let opportunity = node["opportunity_id"] as? String, known.contains(opportunity),
                  let refs = node["authoritative_refs"] as? [String],
                  refs.allSatisfy(known.contains) else {
                return "PACKAGE_STORY_GRAPH_REFERENCES"
            }
        }
        return nil
    }

    private static func narrativeAuthorityCode(
        _ archive: Archive, _ manifest: V2Manifest
    ) throws -> String? {
        func bytes(_ path: String) throws -> Data {
            try read(requiredEntry(path, archive), archive)
        }
        func document(_ path: String) throws -> [String: Any] {
            try required(JSONSerialization.jsonObject(with: bytes(path)))
        }
        let bibleBytes = try bytes("narrative/bible.json")
        let reconciliationBytes = try bytes("narrative/reconciliation.json")
        let bible = try document("narrative/bible.json")
        let reconciliation = try document("narrative/reconciliation.json")
        let story = try document("narrative/story.json")
        let world = manifest.artifacts.filter { $0.path.hasPrefix("world/") }
        let ids = Dictionary(uniqueKeysWithValues: world.map { ($0.path, $0.artifactId) })
        let hashes = Dictionary(uniqueKeysWithValues: world.map { ($0.path, $0.sha256) })
        guard bible["authoritative_refs"] as? [String] == ids.values.sorted() else {
            return "PACKAGE_BIBLE_AUTHORITY"
        }
        guard reconciliation["accepted"] as? Bool == true,
              let reconciliationIDs = reconciliation["world_artifact_ids"] as? [String: Any],
              NSDictionary(dictionary: reconciliationIDs) == NSDictionary(dictionary: ids),
              let reconciliationHashes = reconciliation["world_file_hashes"] as? [String: Any],
              NSDictionary(dictionary: reconciliationHashes) == NSDictionary(dictionary: hashes),
              (reconciliation["ruleset_version"] as? NSNumber)?.intValue == 1,
              let issues = reconciliation["issues"] as? [[String: Any]],
              !issues.contains(where: { ["error", "fatal"].contains($0["severity"] as? String) }),
              story["bible_hash"] as? String == SHA256.hash(data: bibleBytes).hex,
              story["reconciliation_hash"] as? String == SHA256.hash(data: reconciliationBytes).hex
        else { return "PACKAGE_RECONCILIATION_INPUTS" }
        guard let regionRecords = bible["regions"] as? [[String: Any]],
              let siteRecords = bible["sites"] as? [[String: Any]],
              let civilizationRecords = bible["civilizations"] as? [[String: Any]],
              let peopleRecords = bible["people"] as? [[String: Any]],
              let history = bible["history"] as? [[String: Any]] else {
            return "PACKAGE_REFERENCE_RESOLUTION"
        }
        let regionIDs = regionRecords.compactMap { $0["region_id"] as? String }
        let siteIDs = siteRecords.compactMap { $0["site_id"] as? String }
        let civilizationIDs = civilizationRecords.compactMap { $0["civilization_id"] as? String }
        let eventIDs = history.compactMap { $0["event_id"] as? String }
        guard regionIDs.count == regionRecords.count, siteIDs.count == siteRecords.count,
              civilizationIDs.count == civilizationRecords.count, eventIDs.count == history.count
        else { return "PACKAGE_REFERENCE_RESOLUTION" }
        let regions = Set(regionIDs); let sites = Set(siteIDs)
        let civilizations = Set(civilizationIDs); let events = Set(eventIDs)
        if siteRecords.contains(where: {
            guard let region = $0["region_id"] as? String else { return true }
            return !regions.contains(region)
        }) || civilizationRecords.contains(where: { item in
            guard let territory = item["territory"] as? [String] else { return true }
            return territory.contains(where: { !regions.contains($0) })
        }) || peopleRecords.contains(where: { item in
            guard let civilization = item["civilization_id"] as? String,
                  let settlement = item["settlement_id"] as? String else { return true }
            return !civilizations.contains(civilization) || !sites.contains(settlement)
        }) || history.contains(where: { item in
            guard let causes = item["causes"] as? [String],
                  let participants = item["participants"] as? [String] else { return true }
            return causes.contains(where: { !events.contains($0) }) ||
                participants.contains(where: { !civilizations.contains($0) })
        }) { return "PACKAGE_REFERENCE_RESOLUTION" }
        return nil
    }

    private static func gmCoverageCode(_ archive: Archive, _ manifest: V2Manifest) throws -> String? {
        func object(_ path: String) throws -> [String: Any] {
            try required(JSONSerialization.jsonObject(
                with: read(requiredEntry(path, archive), archive)
            ))
        }
        let gm = try object("narrative/gm_index.json")
        let reconciliation = try object("narrative/reconciliation.json")
        let graph = try object("narrative/graph.json")
        guard let entries = gm["entries"] as? [[String: Any]], !entries.isEmpty else {
            return "PACKAGE_GM_COVERAGE"
        }
        let known = Set(manifest.artifacts.map(\.artifactId))
        guard let nodeRecords = graph["nodes"] as? [[String: Any]] else {
            return "PACKAGE_GM_COVERAGE"
        }
        let nodeIDs = nodeRecords.compactMap { $0["node_id"] as? String }
        guard nodeIDs.count == nodeRecords.count else { return "PACKAGE_GM_COVERAGE" }
        let nodes = Set(nodeIDs)
        var covered = Set<String>()
        for entry in entries {
            guard let sources = entry["source_ids"] as? [String], !sources.isEmpty,
                  let reveal = entry["reveal_after_nodes"] as? [String],
                  sources.allSatisfy(known.contains), reveal.allSatisfy(nodes.contains) else {
                return "PACKAGE_GM_COVERAGE"
            }
            covered.formUnion(sources)
        }
        guard let expected = reconciliation["world_artifact_ids"] as? [String: String], !expected.isEmpty,
              Set(expected.values).isSubset(of: covered) else { return "PACKAGE_GM_COVERAGE" }
        guard let indexEntry = archive["narrative/knowledge/index.json"] else { return nil }
        guard let index = try JSONSerialization.jsonObject(with: read(indexEntry, archive)) as? [String: Any],
              let locators = index["entries"] as? [[String: Any]] else {
            return "PACKAGE_KNOWLEDGE_INDEX"
        }
        let byId = Dictionary(uniqueKeysWithValues: entries.compactMap { entry -> (String, [String: Any])? in
            guard let id = entry["entry_id"] as? String else { return nil }
            return (id, entry)
        })
        guard byId.count == entries.count else { return "PACKAGE_KNOWLEDGE_INDEX" }
        var locatorIDs: [String] = []
        for locator in locators {
            guard let id = locator["entry_id"] as? String, let legacy = byId[id],
                  let path = locator["path"] as? String, path == "chunks/\(id).json",
                  let tokens = locator["tokens"] as? [String], tokens == Array(Set(tokens)).sorted(),
                  let reveal = locator["reveal_after_nodes"] as? [String],
                  reveal == legacy["reveal_after_nodes"] as? [String],
                  let chunkEntry = archive["narrative/knowledge/\(path)"] else {
                return "PACKAGE_KNOWLEDGE_INDEX"
            }
            let payload = try read(chunkEntry, archive)
            guard let size = (locator["size_bytes"] as? NSNumber)?.intValue,
                  size == payload.count,
                  locator["sha256"] as? String == SHA256.hash(data: payload).hex,
                  let chunk = try JSONSerialization.jsonObject(with: payload) as? [String: Any],
                  let chunkText = chunk["normalized_text"] as? String,
                  let legacyText = legacy["normalized_text"] as? String,
                  chunkText.lengthOfBytes(using: .utf8) <= 2048,
                  legacyText.hasPrefix(chunkText) else { return "PACKAGE_KNOWLEDGE_CHUNK" }
            var chunkComparable = chunk
            var legacyComparable = legacy
            chunkComparable.removeValue(forKey: "normalized_text")
            legacyComparable.removeValue(forKey: "normalized_text")
            guard NSDictionary(dictionary: chunkComparable).isEqual(to: legacyComparable) else {
                return "PACKAGE_KNOWLEDGE_CHUNK"
            }
            locatorIDs.append(id)
        }
        guard locatorIDs == byId.keys.sorted(), Set(locatorIDs).count == locatorIDs.count else {
            return "PACKAGE_KNOWLEDGE_COVERAGE"
        }
        return nil
    }

    private static func structuredScoreCode(
        _ archive: Archive, _ manifest: V2Manifest
    ) throws -> String? {
        let known = Set(manifest.artifacts.map(\.artifactId))
        let kinds = ["chord", "control", "note", "pitch_bend", "rest"]
        func tick(_ value: Any?) -> Int? {
            guard let beat = value as? [String: Any],
                  let numerator = (beat["numerator"] as? NSNumber)?.intValue,
                  let denominator = (beat["denominator"] as? NSNumber)?.intValue,
                  denominator > 0, numerator * 960 % denominator == 0 else { return nil }
            return numerator * 960 / denominator
        }
        for (node, assets) in manifest.nodeAssets {
            guard let scoreEntry = archive[assets.score], let midiEntry = archive[assets.midi] else {
                continue
            }
            let score: [String: Any] = try required(JSONSerialization.jsonObject(
                with: read(scoreEntry, archive)
            ))
            guard let sources = score["source_ids"] as? [String], !sources.isEmpty,
                  score["node_id"] as? String == node, sources == Array(Set(sources)).sorted(),
                  sources.allSatisfy(known.contains) else { return "PACKAGE_SCORE_REFERENCES" }
            guard score["expected_midi_sha256"] as? String == SHA256.hash(
                data: try read(midiEntry, archive)
            ).hex else { return "PACKAGE_SCORE_MIDI_HASH" }
            guard let duration = tick(score["duration"]), duration > 0 else {
                return "PACKAGE_SCORE_BEAT_ARITHMETIC"
            }
            guard validMidi(try read(midiEntry, archive), duration) else {
                return "PACKAGE_MIDI_PROFILE"
            }
            guard let markers = score["markers"] as? [String: Any],
                  Set(markers.keys) == ["INTRO_END", "LOOP_START", "LOOP_END", "OUTRO_START"]
            else { return "PACKAGE_SCORE_MARKER_ORDER" }
            var markerTicks: [Int] = []
            for name in ["INTRO_END", "LOOP_START", "LOOP_END", "OUTRO_START"] {
                guard let value = tick(markers[name]) else { return "PACKAGE_SCORE_BEAT_ARITHMETIC" }
                markerTicks.append(value)
            }
            guard markerTicks[0] >= 0, markerTicks[0] <= markerTicks[1],
                  markerTicks[1] < markerTicks[2], markerTicks[2] <= markerTicks[3],
                  markerTicks[3] <= duration else { return "PACKAGE_SCORE_MARKER_ORDER" }
            guard let tracks = score["tracks"] as? [[String: Any]], !tracks.isEmpty else {
                return "PACKAGE_SCORE_TRACK_PROGRAM"
            }
            let trackIDs = tracks.compactMap { $0["track_id"] as? String }
            guard trackIDs.count == tracks.count, !trackIDs.contains(where: \.isEmpty),
                  trackIDs.count == Set(trackIDs).count else { return "PACKAGE_SCORE_TRACK_PROGRAM" }
            for track in tracks {
                guard let drum = track["drum_channel"] as? Bool else {
                    return "PACKAGE_SCORE_TRACK_PROGRAM"
                }
                let program = (track["gm_program"] as? NSNumber)?.intValue
                if (drum && program != nil) || (!drum && !(program.map {
                    (0...95).contains($0)
                } ?? false)) {
                    return "PACKAGE_SCORE_TRACK_PROGRAM"
                }
                guard let events = track["events"] as? [[String: Any]], !events.isEmpty else {
                    return "PACKAGE_SCORE_EVENT_SHAPE"
                }
                var ids: Set<String> = []; var previous: [String: Any]?
                func pitches(_ event: [String: Any]) -> [Int] {
                    (event["pitches"] as? [NSNumber])?.map(\.intValue) ?? []
                }
                func before(_ left: [String: Any], _ right: [String: Any]) -> Bool {
                    guard let lt = tick(left["start"]), let rt = tick(right["start"]),
                          let leftKind = left["kind"] as? String,
                          let rightKind = right["kind"] as? String,
                          let leftID = left["event_id"] as? String,
                          let rightID = right["event_id"] as? String else { return false }
                    if lt != rt { return lt < rt }
                    let lk = kinds.firstIndex(of: leftKind) ?? -1
                    let rk = kinds.firstIndex(of: rightKind) ?? -1
                    if lk != rk { return lk < rk }
                    let lp = pitches(left), rp = pitches(right)
                    for index in 0..<min(lp.count, rp.count) where lp[index] != rp[index] {
                        return lp[index] < rp[index]
                    }
                    if lp.count != rp.count { return lp.count < rp.count }
                    return leftID < rightID
                }
                for event in events {
                    guard let start = tick(event["start"]), let length = tick(event["duration"]) else {
                        return "PACKAGE_SCORE_BEAT_ARITHMETIC"
                    }
                    guard let id = event["event_id"] as? String, ids.insert(id).inserted,
                          previous.map({ before($0, event) }) ?? true else {
                        return "PACKAGE_SCORE_EVENT_ORDER"
                    }
                    guard let kind = event["kind"] as? String, kinds.contains(kind) else {
                        return "PACKAGE_SCORE_EVENT_SHAPE"
                    }
                    let pitch = pitches(event)
                    let velocity = (event["velocity"] as? NSNumber)?.intValue
                    let value = (event["value"] as? NSNumber)?.intValue
                    let sounding = kind == "note" || kind == "chord"
                    let validVelocity = velocity.map { (1...127).contains($0) } ?? false
                    let validControl = value.map { (0...127).contains($0) } ?? false
                    let validBend = value.map { (-8192...8191).contains($0) } ?? false
                    if length <= 0 || start < 0 || start + length > duration ||
                        sounding && (pitch.isEmpty || pitch.contains(where: { !(0...127).contains($0) }) ||
                            !validVelocity || value != nil) ||
                        kind == "note" && pitch.count != 1 || kind == "chord" && pitch.count < 2 ||
                        kind == "rest" && (!pitch.isEmpty || velocity != nil || value != nil) ||
                        kind == "control" && (!pitch.isEmpty || velocity != nil || !validControl) ||
                        kind == "pitch_bend" && (!pitch.isEmpty || velocity != nil || !validBend) {
                        return "PACKAGE_SCORE_EVENT_SHAPE"
                    }
                    previous = event
                }
            }
        }
        return nil
    }

    private static func validMidi(_ source: Data, _ expectedDuration: Int) -> Bool {
        let data = [UInt8](source)
        func u16(_ at: Int) -> Int? {
            guard at >= 0, at + 1 < data.count else { return nil }
            return Int(data[at]) << 8 | Int(data[at + 1])
        }
        func u32(_ at: Int) -> Int? {
            guard at >= 0, at + 3 < data.count else { return nil }
            return Int(data[at]) << 24 | Int(data[at + 1]) << 16 |
                Int(data[at + 2]) << 8 | Int(data[at + 3])
        }
        func ascii(_ at: Int, _ text: String) -> Bool {
            let bytes = Array(text.utf8)
            return at >= 0 && at + bytes.count <= data.count &&
                Array(data[at..<(at + bytes.count)]) == bytes
        }
        guard data.count >= 14, ascii(0, "MThd"), u32(4) == 6, u16(8) == 1,
              let trackCount = u16(10), trackCount >= 2, u16(12) == 960 else { return false }
        var offset = 14, notes = 0, maxTick = 0
        var markers = Set<String>()
        for _ in 0..<trackCount {
            guard ascii(offset, "MTrk"), let length = u32(offset + 4), length >= 0,
                  offset + 8 + length <= data.count else { return false }
            var cursor = offset + 8, tick = 0
            let end = cursor + length
            func vlq() -> Int? {
                var value = 0
                for _ in 0..<4 {
                    guard cursor < end else { return nil }
                    let byte = data[cursor]; cursor += 1
                    value = value << 7 | Int(byte & 0x7f)
                    if byte & 0x80 == 0 { return value }
                }
                return nil
            }
            while cursor < end {
                guard let delta = vlq(), cursor < end else { return false }
                tick += delta; maxTick = max(maxTick, tick)
                let status = data[cursor]; cursor += 1
                if status == 0xf0 || status == 0xf7 { return false }
                switch status {
                case 0xff:
                    guard cursor < end else { return false }
                    let kind = data[cursor]; cursor += 1
                    guard let size = vlq(), size >= 0, cursor + size <= end else { return false }
                    if kind == 0x06 {
                        markers.insert(String(decoding: data[cursor..<(cursor + size)], as: UTF8.self))
                    }
                    cursor += size
                case let value where value & 0xf0 == 0x80 || value & 0xf0 == 0x90:
                    guard cursor + 2 <= end, data[cursor] <= 127, data[cursor + 1] <= 127 else {
                        return false
                    }
                    notes += 1; cursor += 2
                case let value where value & 0xf0 == 0xb0 || value & 0xf0 == 0xe0:
                    guard cursor + 2 <= end, data[cursor] <= 127, data[cursor + 1] <= 127 else {
                        return false
                    }
                    cursor += 2
                case let value where value & 0xf0 == 0xc0:
                    guard cursor < end, data[cursor] <= 95 else { return false }
                    cursor += 1
                default: return false
                }
            }
            offset = end
        }
        return offset == data.count && notes > 0 && maxTick == expectedDuration &&
            markers == Set(["INTRO_END", "LOOP_START", "LOOP_END", "OUTRO_START"])
    }


    /// P8.C2: layout, node assets, entry node, and region map validation.
    private static func layoutCode(_ manifest: V2Manifest, _ names: Set<String>) -> String? {
        let required: Set<String> = [
            "world/index.json", "narrative/bible.json", "narrative/reconciliation.json",
            "narrative/style_bible.json", "narrative/story.json", "narrative/graph.json",
            "narrative/gm_index.json", "assets/maps/world.png",
        ]
        if !required.isSubset(of: names) { return "PACKAGE_LAYOUT_MISSING" }

        // Node assets: every node must have image/thumbnail/score/midi
        if manifest.entryNode.isEmpty { return "PACKAGE_ENTRY_NODE" }
        if manifest.nodeAssets[manifest.entryNode] == nil { return "PACKAGE_ENTRY_NODE" }
        for (node, assets) in manifest.nodeAssets {
            let expected = NodeAssets(
                image: "assets/images/\(node).png",
                thumbnail: "assets/thumbnails/\(node).png",
                score: "assets/music/\(node).score.json",
                midi: "assets/midi/\(node).mid"
            )
            let expectedPaths = [expected.image, expected.thumbnail, expected.score, expected.midi]
            if assets != expected || !expectedPaths.allSatisfy(names.contains) {
                return "PACKAGE_MEDIA_COVERAGE"
            }
        }

        // Region maps: every declared region map must exist
        if manifest.regionMaps.values.contains(where: { !names.contains($0) }) {
            return "PACKAGE_REGION_MAP_COVERAGE"
        }

        return nil
    }

    private static func pngProfileCode(_ archive: Archive, _ manifest: V2Manifest) throws -> String? {
        var expected = ["assets/maps/world.png": (4096, 4096)]
        for path in manifest.regionMaps.values { expected[path] = (1024, 1024) }
        for assets in manifest.nodeAssets.values {
            expected[assets.image] = (1024, 1024)
            expected[assets.thumbnail] = (256, 256)
        }
        for (path, size) in expected {
            guard let entry = archive[path], validPNG(try read(entry, archive), size.0, size.1) else {
                return "PACKAGE_PNG_PROFILE"
            }
        }
        return nil
    }

    private static func pngCRC(_ bytes: ArraySlice<UInt8>) -> UInt32 {
        var crc: UInt32 = 0xffffffff
        for byte in bytes {
            crc ^= UInt32(byte)
            for _ in 0..<8 { crc = crc & 1 == 1 ? 0xedb88320 ^ (crc >> 1) : crc >> 1 }
        }
        return crc ^ 0xffffffff
    }

    private static func validPNG(_ source: Data, _ expectedWidth: Int, _ expectedHeight: Int) -> Bool {
        let data = [UInt8](source)
        func reject(_ reason: String) -> Bool {
            _ = reason
            return false
        }
        func u32(_ at: Int) -> Int? {
            guard at >= 0, at + 3 < data.count else { return nil }
            return Int(data[at]) << 24 | Int(data[at + 1]) << 16 |
                Int(data[at + 2]) << 8 | Int(data[at + 3])
        }
        guard data.count >= 8,
              Array(data[0..<8]) == [137, 80, 78, 71, 13, 10, 26, 10] else { return reject("signature") }
        var offset = 8, width = 0, height = 0
        var sawIHDR = false, sawSRGB = false, sawIDAT = false, ended = false
        var compressed: [UInt8] = []
        while offset < data.count {
            guard let length = u32(offset), length >= 0, offset + 12 + length <= data.count else {
                return reject("chunk bounds \(offset)")
            }
            let typeStart = offset + 4, payload = offset + 8
            let type = String(decoding: data[typeStart..<(typeStart + 4)], as: UTF8.self)
            guard let storedCRC = u32(payload + length),
                  Int(pngCRC(data[typeStart..<(payload + length)])) == storedCRC else { return reject("crc \(type)") }
            switch type {
            case "IHDR":
                guard !sawIHDR, offset == 8, length == 13,
                      let parsedWidth = u32(payload), let parsedHeight = u32(payload + 4),
                      parsedWidth == expectedWidth, parsedHeight == expectedHeight,
                      data[payload + 8] == 8, data[payload + 9] == 6,
                      data[payload + 10] == 0, data[payload + 11] == 0,
                      data[payload + 12] == 0 else { return reject("ihdr \(expectedWidth)x\(expectedHeight)") }
                width = parsedWidth; height = parsedHeight; sawIHDR = true
            case "sRGB":
                guard sawIHDR, !sawIDAT, !sawSRGB, length == 1, data[payload] <= 3 else { return reject("srgb") }
                sawSRGB = true
            case "IDAT":
                guard sawIHDR, sawSRGB, !ended else { return reject("idat") }
                sawIDAT = true; compressed.append(contentsOf: data[payload..<(payload + length)])
            case "IEND":
                guard sawIDAT, length == 0, payload + 4 == data.count else { return reject("iend") }
                ended = true
            case "acTL", "fcTL", "fdAT": return false
            default:
                if sawIDAT, type.first?.isUppercase == true { return false }
            }
            offset = payload + length + 4
        }
        guard ended else { return reject("not ended") }
        let rowBytes = width * 4 + 1
        let expected = height * rowBytes
        guard compressed.count >= 6 else { return false }
        let cmf = Int(compressed[0]), flg = Int(compressed[1])
        guard cmf & 0x0f == 8, cmf >> 4 <= 7, (cmf << 8 | flg) % 31 == 0,
              flg & 0x20 == 0 else { return false }
        var decoded = [UInt8](repeating: 0, count: expected)
        let deflate = compressed.count >= 6 ? Array(compressed.dropFirst(2).dropLast(4)) : []
        let decodedCount = decoded.withUnsafeMutableBytes { destination in
            deflate.withUnsafeBytes { input in
                guard let destinationAddress = destination.bindMemory(to: UInt8.self).baseAddress,
                      let inputAddress = input.bindMemory(to: UInt8.self).baseAddress else { return 0 }
                return compression_decode_buffer(
                    destinationAddress, expected, inputAddress, deflate.count,
                    nil, COMPRESSION_ZLIB
                )
            }
        }
        guard decodedCount == expected else {
            return false
        }
        var s1: UInt32 = 1, s2: UInt32 = 0
        for byte in decoded {
            s1 = (s1 + UInt32(byte)) % 65_521
            s2 = (s2 + s1) % 65_521
        }
        let storedAdler = UInt32(compressed[compressed.count - 4]) << 24 |
            UInt32(compressed[compressed.count - 3]) << 16 |
            UInt32(compressed[compressed.count - 2]) << 8 |
            UInt32(compressed[compressed.count - 1])
        return (s2 << 16 | s1) == storedAdler &&
            (0..<height).allSatisfy { decoded[$0 * rowBytes] == 0 }
    }

    private static func read(_ entry: Entry, _ archive: Archive) throws -> Data {
        var data = Data()
        _ = try archive.extract(entry) { data.append($0) }
        return data
    }
}

private extension Digest {
    var hex: String { map { String(format: "%02x", $0) }.joined() }
}
