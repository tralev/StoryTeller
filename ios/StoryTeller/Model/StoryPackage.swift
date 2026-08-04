import Foundation

/// An imported .story package on the device.
struct StoryPackage: Identifiable, Codable {
    let storyId: String
    let title: String
    let seed: Int
    let storyDir: URL
    
    var id: String { storyId }
    
    var bibleFile: URL { storyDir.appendingPathComponent("content/bible.json") }
    var storyFile: URL { storyDir.appendingPathComponent("content/story.json") }
    var graphFile: URL { storyDir.appendingPathComponent("content/graph.json") }
    var gmIndexFile: URL { storyDir.appendingPathComponent("content/gm_index.json") }
    var styleBibleFile: URL { storyDir.appendingPathComponent("content/style_bible.json") }
    var imagesDir: URL { storyDir.appendingPathComponent("content/images") }
    var midiDir: URL { storyDir.appendingPathComponent("content/midi") }
    var thumbnailsDir: URL { storyDir.appendingPathComponent("content/thumbnails") }
    var saveDir: URL {
        let dir = storyDir.appendingPathComponent("save")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }
    
    func imageFor(nodeId: String) -> URL {
        imagesDir.appendingPathComponent("\(nodeId).png")
    }
    
    func midiFor(nodeId: String) -> URL {
        midiDir.appendingPathComponent("\(nodeId).mid")
    }
    
    func thumbnailFor(nodeId: String) -> URL {
        thumbnailsDir.appendingPathComponent("\(nodeId).png")
    }
}
