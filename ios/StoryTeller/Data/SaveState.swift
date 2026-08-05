import Foundation

struct ChatTurn: Codable, Equatable { let role: String; let text: String }

struct SaveState: Codable, Equatable {
    let saveVersion: Int
    let storyId: String
    let packageContentHash: String
    let playthroughId: String
    var currentNode: String
    var visitedNodes: [String]
    var flags: [String: Bool]
    var bookmarks: [String]
    var gmHistory: [ChatTurn]
    var choiceHistory: [String]
    var currentNodeId: String { get { currentNode } set { currentNode = newValue } }

    init(storyId: String = "", packageContentHash: String = "", playthroughId: String = UUID().uuidString,
         currentNode: String = "", visitedNodes: [String] = [], flags: [String: Bool] = [:],
         bookmarks: [String] = [], gmHistory: [ChatTurn] = [], choiceHistory: [String] = []) {
        saveVersion=1; self.storyId=storyId; self.packageContentHash=packageContentHash
        self.playthroughId=playthroughId; self.currentNode=currentNode; self.visitedNodes=visitedNodes
        self.flags=flags; self.bookmarks=bookmarks; self.gmHistory=gmHistory; self.choiceHistory=choiceHistory
    }
    mutating func visitNode(_ id: String) { currentNode=id; if !visitedNodes.contains(id) { visitedNodes.append(id) } }
    mutating func makeChoice(_ choice: Choice) { choiceHistory.append(choice.choiceId); choice.setsFlags.forEach { flags[$0]=true } }
    mutating func addGMExchange(question: String, answer: String) {
        gmHistory += [ChatTurn(role:"user", text:question), ChatTurn(role:"assistant", text:answer)]
    }
    mutating func toggleBookmark() -> Bool {
        if let index=bookmarks.firstIndex(of:currentNode) { bookmarks.remove(at:index); return false }
        bookmarks.append(currentNode); return true
    }
    mutating func reset(entryNode: String? = nil) {
        let entry=entryNode ?? visitedNodes.first ?? currentNode
        currentNode=entry; visitedNodes=[entry]; flags=[:]; bookmarks=[]; gmHistory=[]; choiceHistory=[]
    }
    static func load(from directory: URL) -> SaveState {
        (try? SaveRepository(root: directory.deletingLastPathComponent()).loadAny(directory)) ?? SaveState()
    }
    func save(to directory: URL) { try? SaveRepository(root: directory.deletingLastPathComponent()).saveAt(self, directory.appendingPathComponent("save_state.json")) }
}

enum SaveRepositoryError: Error, Equatable { case packageHashMismatch }

struct SaveRepository {
    let root: URL
    private let fm = FileManager.default
    private func url(_ story: String, _ playthrough: String) -> URL {
        root.appendingPathComponent("saves/\(story)/\(playthrough).json")
    }
    func load(story: StoryPackage, playthroughId: String) throws -> SaveState? {
        let path=url(story.storyId, playthroughId); guard fm.fileExists(atPath:path.path) else{return nil}
        let state=try JSONDecoder().decode(SaveState.self, from:Data(contentsOf:path))
        guard state.storyId==story.storyId && state.packageContentHash==story.contentHash else{throw SaveRepositoryError.packageHashMismatch}
        return state
    }
    func save(_ state: SaveState) throws { try saveAt(state, url(state.storyId,state.playthroughId)) }
    func saveAt(_ state: SaveState, _ destination: URL) throws {
        try fm.createDirectory(at:destination.deletingLastPathComponent(),withIntermediateDirectories:true)
        let data=try JSONEncoder().encode(state); let temp=destination.deletingLastPathComponent().appendingPathComponent(".\(destination.lastPathComponent).tmp")
        try data.write(to:temp,options:.atomic); if fm.fileExists(atPath:destination.path){_ = try fm.replaceItemAt(destination,withItemAt:temp)}else{try fm.moveItem(at:temp,to:destination)}
    }
    func loadAny(_ directory: URL) throws -> SaveState? {
        let path=directory.appendingPathComponent("save_state.json"); guard fm.fileExists(atPath:path.path) else{return nil}
        return try JSONDecoder().decode(SaveState.self,from:Data(contentsOf:path))
    }
    func deleteStoryData(_ storyId:String)throws{let p=root.appendingPathComponent("saves/\(storyId)");if fm.fileExists(atPath:p.path){try fm.removeItem(at:p)}}
}
