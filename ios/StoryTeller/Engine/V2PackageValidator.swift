import CryptoKit
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
    private static let maxRatio = 1_000.0

    // P8.C2: frozen ordered acceptance stages matching Python/Kotlin
    static func validate(_ source: URL) -> V2ArchiveValidation {
        do {
            guard FileManager.default.fileExists(atPath: source.path) else { return invalid("PACKAGE_NOT_FOUND") }
            let archive = try Archive(url: source, accessMode: .read)
            let entries = Array(archive)
            let names = Set(entries.map(\.path))
            // Stage 1: central-directory safety
            if let code = safetyCode(entries) { return invalid(code) }
            // Stage 2: manifest existence, format, version
            guard let manifestEntry = archive["manifest.json"] else { return invalid("PACKAGE_MISSING_MANIFEST") }
            let manifest = try JSONDecoder().decode(V2Manifest.self, from: read(manifestEntry, archive))
            guard manifest.packageVersion == 2 && manifest.packageFormat == "storyteller.story" else {
                return invalid("PACKAGE_UNSUPPORTED_VERSION", manifest)
            }
            // Stage 3: declared member inventory and internal hashes
            if let code = try inventoryCode(manifest, archive, names) {
                return invalid(code, manifest)
            }
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

    private static func safetyCode(_ entries: [Entry]) -> String? {
        if entries.count > maxEntries { return "PACKAGE_ENTRY_LIMIT" }
        var seen = Set<String>()
        var portable = Set<String>()
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
            if entry.uncompressedSize > maxEntryBytes { return "PACKAGE_SIZE_LIMIT" }
            if entry.uncompressedSize > 0 &&
                (entry.compressedSize == 0 || Double(entry.uncompressedSize) / Double(entry.compressedSize) > maxRatio) {
                return "PACKAGE_COMPRESSION_LIMIT"
            }
        }
        return nil
    }

    private static func inventoryCode(
        _ manifest: V2Manifest,
        _ archive: Archive,
        _ names: Set<String>
    ) throws -> String? {
        var declared: Set<String> = ["manifest.json"]
        let artifactIDs = Set(manifest.artifacts.map(\.artifactId))
        if artifactIDs.count != manifest.artifacts.count { return "PACKAGE_DUPLICATE_ID" }
        for artifact in manifest.artifacts {
            guard let entry = archive[artifact.path] else { return "PACKAGE_MISSING_ARTIFACT" }
            let data = try read(entry, archive)
            if Int64(data.count) != artifact.sizeBytes || SHA256.hash(data: data).hex != artifact.sha256 {
                return "PACKAGE_HASH_MISMATCH"
            }
            declared.insert(artifact.path)
        }
        if manifest.artifacts.contains(where: { artifact in
            artifact.dependsOn.contains(where: { !artifactIDs.contains($0) })
        }) { return "PACKAGE_PROVENANCE_BROKEN" }
        if declared != names { return "PACKAGE_UNDECLARED_ENTRY" }
        return nil
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
            let expected = [
                "image": "assets/images/\(node).png",
                "thumbnail": "assets/thumbnails/\(node).png",
                "score": "assets/music/\(node).score.json",
                "midi": "assets/midi/\(node).mid",
            ]
            if assets != expected || !expected.values.allSatisfy(names.contains) {
                return "PACKAGE_MEDIA_COVERAGE"
            }
        }

        // Region maps: every declared region map must exist
        if manifest.regionMaps.values.contains(where: { !names.contains($0) }) {
            return "PACKAGE_REGION_MAP_COVERAGE"
        }

        return nil
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
