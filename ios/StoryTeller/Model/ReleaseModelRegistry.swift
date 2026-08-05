import Foundation

struct ReleaseModelSpec: Equatable {
    let id: String
    let role: String
    let displayName: String
    let publisher: String
    let repository: String
    let revision: String
    let filename: String
    let byteSize: Int64
    let sha256: String
    let licenseURL: URL
    let licenseNotice: String
    let minimumRAMBytes: Int64
    let minimumFreeStorageBytes: Int64

    var downloadURL: URL {
        URL(string: "https://huggingface.co/\(repository)/resolve/\(revision)/\(filename)")!
    }
}

enum ReleaseModelRegistry {
    /// Keep this generated boundary in exact parity with config/model_registry.json.
    static let gameMaster = ReleaseModelSpec(
        id: "gm.llama-3.2-3b-instruct.q4-k-m.v1",
        role: "game_master",
        displayName: "Llama 3.2 3B Instruct (Q4_K_M)",
        publisher: "Meta",
        repository: "bartowski/Llama-3.2-3B-Instruct-GGUF",
        revision: "c346bfc2029e79ba6d7edf026cf01fe44242db0d",
        filename: "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        byteSize: 2_019_377_696,
        sha256: "6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff",
        licenseURL: URL(string: "https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct/blob/0cb88a4f764b7a12671c53f0838cd831a0843b95/LICENSE.txt")!,
        licenseNotice: "Llama 3.2 is licensed under the Llama 3.2 Community License, Copyright © Meta Platforms, Inc. All Rights Reserved.",
        minimumRAMBytes: 6_442_450_944,
        minimumFreeStorageBytes: 4_294_967_296
    )
}
