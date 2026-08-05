import Foundation
import ZIPFoundation

enum ImportResult: Equatable {
    case imported(storyID:String), alreadyImported(storyID:String)
    case unsupportedVersion(found:Int,supported:Int)
    case invalid(errorCodes:[String])
    case insufficientStorage(requiredBytes:Int64)
    case cancelled
}

final class StoryParser {
    private let fm=FileManager.default
    let storiesDir:URL
    let savesDir:URL
    init(root:URL?=nil){
        let base=root ?? fm.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0]
        storiesDir=base.appendingPathComponent("stories-v2");savesDir=base.appendingPathComponent("saves")
        try? fm.createDirectory(at:storiesDir,withIntermediateDirectories:true)
    }

    func importValidated(from source:URL,cancelled:()->Bool={false})->ImportResult{
        var staging:URL?
        defer {
            if let staging, fm.fileExists(atPath: staging.path) {
                try? fm.removeItem(at: staging)
            }
        }
        do{
            let validation = V2PackageValidator.validate(source)
            guard validation.accepted, let manifest = validation.manifest else {
                if validation.issueCodes == ["PACKAGE_UNSUPPORTED_VERSION"] {
                    return .unsupportedVersion(found: validation.manifest?.packageVersion ?? 0, supported: 2)
                }
                return .invalid(errorCodes: validation.issueCodes)
            }
            let archive = try Archive(url: source, accessMode: .read)
            let entries=Array(archive)
            let destination=storiesDir.appendingPathComponent(manifest.storyId)
            let required=validation.requiredBytes
            let attrs=try fm.attributesOfFileSystem(forPath:storiesDir.path)
            if let free=attrs[.systemFreeSize] as? NSNumber,free.int64Value<required{return.insufficientStorage(requiredBytes:required)}
            // A package with an existing identity must still pass every byte,
            // inventory, and provenance check.  Otherwise a corrupt archive
            // could be reported as valid merely because a good copy was
            // imported earlier.
            if fm.fileExists(atPath:destination.path){return.alreadyImported(storyID:manifest.storyId)}
            let stage=storiesDir.appendingPathComponent(".\(manifest.storyId).importing");staging=stage
            try? fm.removeItem(at:stage);try fm.createDirectory(at:stage,withIntermediateDirectories:true)
            for entry in entries{
                if cancelled(){return.cancelled}
                let target=stage.appendingPathComponent(entry.path).standardizedFileURL
                guard target.path.hasPrefix(stage.path+"/")else{return.invalid(errorCodes:["PACKAGE_UNSAFE_PATH"])}
                try fm.createDirectory(at:target.deletingLastPathComponent(),withIntermediateDirectories:true)
                _ = try archive.extract(entry,to:target)
            }
            try fm.moveItem(at:stage,to:destination);staging=nil
            try makeReadOnly(destination)
            return.imported(storyID:manifest.storyId)
        }catch{return.invalid(errorCodes:["PACKAGE_IMPORT_FAILED"])}
    }

    func importStory(from source:URL)throws->StoryPackage{
        switch importValidated(from:source){
        case.imported(let id),.alreadyImported(let id):return try loadStory(storyId:id)
        case.unsupportedVersion(let found,_):throw StoryParserError.unsupportedVersion(found)
        case.invalid(let codes):throw StoryParserError.invalid(codes)
        case.insufficientStorage(let size):throw StoryParserError.insufficientStorage(size)
        case.cancelled:throw StoryParserError.cancelled
        }
    }
    func loadStory(storyId:String)throws->StoryPackage{
        let dir=storiesDir.appendingPathComponent(storyId)
        let manifest=try JSONDecoder().decode(V2Manifest.self,from:Data(contentsOf:dir.appendingPathComponent("manifest.json")))
        return StoryPackage(storyId:manifest.storyId,title:manifest.title,masterSeed:manifest.masterSeed,
            contentHash:manifest.contentHash,entryNode:manifest.entryNode,storyDir:dir)
    }
    func listStories()->[StoryPackage]{
        ((try? fm.contentsOfDirectory(at:storiesDir,includingPropertiesForKeys:nil)) ?? [])
            .filter{!$0.lastPathComponent.hasPrefix(".")}.compactMap{try? loadStory(storyId:$0.lastPathComponent)}.sorted{$0.title<$1.title}
    }
    func delete(storyId:String,deleteLocalData:Bool=false)throws{
        let content=storiesDir.appendingPathComponent(storyId);try makeWritable(content);if fm.fileExists(atPath:content.path){try fm.removeItem(at:content)}
        if deleteLocalData{let save=savesDir.appendingPathComponent(storyId);if fm.fileExists(atPath:save.path){try fm.removeItem(at:save)}}
    }

    private func makeReadOnly(_ root:URL)throws{for url in ([root]+((fm.enumerator(at:root,includingPropertiesForKeys:[.isDirectoryKey])?.allObjects as? [URL]) ?? [])){let directory=(try? url.resourceValues(forKeys:[.isDirectoryKey]).isDirectory)==true;try fm.setAttributes([.posixPermissions:directory ? 0o555:0o444],ofItemAtPath:url.path)}}
    private func makeWritable(_ root:URL)throws{guard fm.fileExists(atPath:root.path)else{return};for url in ([root]+((fm.enumerator(at:root,includingPropertiesForKeys:nil)?.allObjects as? [URL]) ?? [])){try? fm.setAttributes([.posixPermissions:0o755],ofItemAtPath:url.path)}}
}

enum StoryParserError:LocalizedError{case unsupportedVersion(Int),invalid([String]),insufficientStorage(Int64),cancelled
    var errorDescription:String?{switch self{case.unsupportedVersion(let v):return"PACKAGE_UNSUPPORTED_VERSION: v\(v); regenerate v2";case.invalid(let c):return c.joined(separator:",");case.insufficientStorage:return"PACKAGE_INSUFFICIENT_STORAGE";case.cancelled:return"PACKAGE_CANCELLED"}}}
