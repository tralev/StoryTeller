import Foundation
import ZIPFoundation

/// Imports and manages .story ZIP archives on iOS.
///
/// The .story archive contains:
///   manifest.json, content/{bible,story,graph,gm_index,style_bible}.json,
///   content/images/*.png, content/midi/*.mid, content/thumbnails/*.png,
///   save/.gitkeep
final class StoryParser {
    private let fileManager = FileManager.default
    
    var storiesDir: URL {
        fileManager.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("stories")
    }
    
    init() {
        try? fileManager.createDirectory(at: storiesDir, withIntermediateDirectories: true)
    }
    
    /// Import a .story file from a URL (file picker or share sheet).
    func importStory(from sourceURL: URL) throws -> StoryPackage {
        let storyId = sourceURL.deletingPathExtension().lastPathComponent
        let destDir = storiesDir.appendingPathComponent(storyId)
        
        // Skip if already imported
        if fileManager.fileExists(atPath: destDir.path) {
            return try loadStory(storyId: storyId)
        }
        
        try fileManager.createDirectory(at: destDir, withIntermediateDirectories: true)
        
        // Extract ZIP
        try fileManager.unzipItem(at: sourceURL, to: destDir)
        
        // Read manifest
        let manifestURL = destDir.appendingPathComponent("manifest.json")
        let manifestData = try Data(contentsOf: manifestURL)
        let manifest = try JSONSerialization.jsonObject(with: manifestData) as? [String: Any] ?? [:]
        
        let title = manifest["title"] as? String ?? storyId
        let seed = manifest["seed"] as? Int ?? 0
        
        let story = StoryPackage(
            storyId: storyId,
            title: title,
            seed: seed,
            storyDir: destDir
        )
        
        print("[StoryParser] Imported: \(storyId)")
        return story
    }
    
    /// Load a previously imported story.
    func loadStory(storyId: String) throws -> StoryPackage {
        let dir = storiesDir.appendingPathComponent(storyId)
        guard fileManager.fileExists(atPath: dir.path) else {
            throw StoryParserError.notFound(storyId)
        }
        
        let manifestURL = dir.appendingPathComponent("manifest.json")
        let manifestData = try Data(contentsOf: manifestURL)
        let manifest = try JSONSerialization.jsonObject(with: manifestData) as? [String: Any] ?? [:]
        
        return StoryPackage(
            storyId: storyId,
            title: manifest["title"] as? String ?? storyId,
            seed: manifest["seed"] as? Int ?? 0,
            storyDir: dir
        )
    }
    
    /// List all imported stories.
    func listStories() -> [StoryPackage] {
        guard let contents = try? fileManager.contentsOfDirectory(
            at: storiesDir,
            includingPropertiesForKeys: nil
        ) else { return [] }
        
        return contents
            .filter { $0.hasDirectoryPath }
            .compactMap { try? loadStory(storyId: $0.lastPathComponent) }
            .sorted { $0.storyId > $1.storyId }
    }
    
    /// Delete an imported story.
    func delete(storyId: String) throws {
        let dir = storiesDir.appendingPathComponent(storyId)
        if fileManager.fileExists(atPath: dir.path) {
            try fileManager.removeItem(at: dir)
            print("[StoryParser] Deleted: \(storyId)")
        }
    }
    
    /// Read a JSON file from a story directory.
    func readJSON(at url: URL) -> [String: Any]? {
        guard fileManager.fileExists(atPath: url.path),
              let data = try? Data(contentsOf: url),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return json
    }
}

enum StoryParserError: LocalizedError {
    case notFound(String)
    
    var errorDescription: String? {
        switch self {
        case .notFound(let id): return "Story not found: \(id)"
        }
    }
}
