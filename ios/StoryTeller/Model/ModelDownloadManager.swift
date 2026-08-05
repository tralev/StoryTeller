import CryptoKit
import Foundation

enum ModelDownloadState: Equatable {
    case notInstalled
    case downloading(downloadedBytes: Int64, totalBytes: Int64)
    case verifying
    case installed
    case cancelled
    case failed(code: String, detail: String)
}

/// Resumable downloader which verifies the release digest before atomic publication.
@MainActor
final class ModelDownloadManager: ObservableObject {
    @Published private(set) var state: ModelDownloadState
    private(set) var task: Task<Void, Never>?
    let spec: ReleaseModelSpec
    let modelsDirectory: URL

    var installedURL: URL { modelsDirectory.appendingPathComponent(spec.filename) }
    var partialURL: URL { modelsDirectory.appendingPathComponent("\(spec.filename).part") }
    var isInstalled: Bool { Self.fileSize(installedURL) == spec.byteSize }

    init(modelsDirectory: URL, spec: ReleaseModelSpec = ReleaseModelRegistry.gameMaster) {
        self.modelsDirectory = modelsDirectory
        self.spec = spec
        state = Self.fileSize(modelsDirectory.appendingPathComponent(spec.filename)) == spec.byteSize ? .installed : .notInstalled
    }

    /// The caller must present the registry source/license and obtain explicit consent first.
    func downloadAfterConsent() {
        guard task == nil, !isInstalled else {
            state = .installed
            return
        }
        task = Task { [weak self] in
            guard let self else { return }
            defer { task = nil }
            do {
                try await performDownload()
            } catch is CancellationError {
                state = .cancelled
            } catch let failure as ModelDownloadFailure {
                state = .failed(code: failure.code, detail: failure.detail)
            } catch {
                state = Task.isCancelled
                    ? .cancelled
                    : .failed(code: "MODEL_NETWORK_ERROR", detail: error.localizedDescription)
            }
        }
    }

    func cancel() {
        task?.cancel()
    }

    func deleteInstalledAndPartial() throws {
        cancel()
        for url in [installedURL, partialURL] where FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
        state = .notInstalled
    }

    private func performDownload() async throws {
        let fileManager = FileManager.default
        try fileManager.createDirectory(at: modelsDirectory, withIntermediateDirectories: true)
        let existing = Self.fileSize(partialURL) ?? 0
        let remaining = spec.byteSize - existing
        guard remaining > 0 else {
            throw ModelDownloadFailure(code: "MODEL_SIZE_MISMATCH", detail: "Partial file is not resumable")
        }
        guard try availableBytes() >= remaining else {
            throw ModelDownloadFailure(code: "MODEL_INSUFFICIENT_STORAGE", detail: "At least \(remaining) additional bytes are required")
        }

        var request = URLRequest(url: spec.downloadURL)
        if existing > 0 { request.setValue("bytes=\(existing)-", forHTTPHeaderField: "Range") }
        let (bytes, response) = try await URLSession.shared.bytes(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw ModelDownloadFailure(code: "MODEL_INVALID_RESPONSE", detail: "Download did not return HTTP")
        }
        let validStatus = (existing == 0 && http.statusCode == 200) || (existing > 0 && http.statusCode == 206)
        guard validStatus else {
            throw ModelDownloadFailure(code: "MODEL_RESUME_REJECTED", detail: "Unexpected HTTP \(http.statusCode) for offset \(existing)")
        }
        if existing > 0 && !(http.value(forHTTPHeaderField: "Content-Range")?.hasPrefix("bytes \(existing)-") ?? false) {
            throw ModelDownloadFailure(code: "MODEL_RESUME_REJECTED", detail: "Invalid Content-Range for offset \(existing)")
        }

        if existing == 0 { fileManager.createFile(atPath: partialURL.path, contents: nil) }
        let handle = try FileHandle(forWritingTo: partialURL)
        defer { try? handle.close() }
        try handle.seekToEnd()
        var downloaded = existing
        var buffer = Data()
        buffer.reserveCapacity(1024 * 1024)
        for try await byte in bytes {
            try Task.checkCancellation()
            buffer.append(byte)
            if buffer.count >= 1024 * 1024 {
                try handle.write(contentsOf: buffer)
                downloaded += Int64(buffer.count)
                buffer.removeAll(keepingCapacity: true)
                state = .downloading(downloadedBytes: downloaded, totalBytes: spec.byteSize)
            }
        }
        if !buffer.isEmpty {
            try handle.write(contentsOf: buffer)
            downloaded += Int64(buffer.count)
        }
        try handle.synchronize()
        guard downloaded == spec.byteSize else {
            throw ModelDownloadFailure(code: "MODEL_SIZE_MISMATCH", detail: "Expected \(spec.byteSize), got \(downloaded)")
        }

        state = .verifying
        guard try Self.sha256(partialURL) == spec.sha256 else {
            try? fileManager.removeItem(at: partialURL)
            throw ModelDownloadFailure(code: "MODEL_CHECKSUM_MISMATCH", detail: "Downloaded model failed SHA-256 verification")
        }
        try Self.publishAtomically(partialURL, to: installedURL)
        state = .installed
    }

    private func availableBytes() throws -> Int64 {
        let values = try modelsDirectory.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
        return values.volumeAvailableCapacityForImportantUsage ?? 0
    }

    nonisolated static func fileSize(_ url: URL) -> Int64? {
        let attributes = try? FileManager.default.attributesOfItem(atPath: url.path)
        return (attributes?[.size] as? NSNumber)?.int64Value
    }

    nonisolated static func sha256(_ url: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var digest = SHA256()
        while let data = try handle.read(upToCount: 1024 * 1024), !data.isEmpty { digest.update(data: data) }
        return digest.finalize().map { String(format: "%02x", $0) }.joined()
    }

    nonisolated static func publishAtomically(_ partial: URL, to destination: URL) throws {
        let fileManager = FileManager.default
        if fileManager.fileExists(atPath: destination.path) {
            _ = try fileManager.replaceItemAt(destination, withItemAt: partial)
        } else {
            try fileManager.moveItem(at: partial, to: destination)
        }
    }
}

private struct ModelDownloadFailure: Error {
    let code: String
    let detail: String
}
