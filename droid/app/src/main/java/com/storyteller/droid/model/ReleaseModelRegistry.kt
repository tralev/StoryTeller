package com.storyteller.droid.model

/** Release-pinned models. Keep values in parity with config/model_registry.json. */
data class ReleaseModelSpec(
    val id: String,
    val role: String,
    val displayName: String,
    val publisher: String,
    val repository: String,
    val revision: String,
    val filename: String,
    val byteSize: Long,
    val sha256: String,
    val licenseUrl: String,
    val licenseNotice: String,
    val minimumRamBytes: Long,
    val minimumFreeStorageBytes: Long,
) {
    val downloadUrl: String
        get() = "https://huggingface.co/$repository/resolve/$revision/$filename"
}

object ReleaseModelRegistry {
    val gameMaster = ReleaseModelSpec(
        id = "gm.llama-3.2-3b-instruct.q4-k-m.v1",
        role = "game_master",
        displayName = "Llama 3.2 3B Instruct (Q4_K_M)",
        publisher = "Meta",
        repository = "bartowski/Llama-3.2-3B-Instruct-GGUF",
        revision = "c346bfc2029e79ba6d7edf026cf01fe44242db0d",
        filename = "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        byteSize = 2_019_377_696L,
        sha256 = "6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff",
        licenseUrl = "https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct/blob/0cb88a4f764b7a12671c53f0838cd831a0843b95/LICENSE.txt",
        licenseNotice = "Llama 3.2 is licensed under the Llama 3.2 Community License, Copyright © Meta Platforms, Inc. All Rights Reserved.",
        minimumRamBytes = 6_442_450_944L,
        minimumFreeStorageBytes = 4_294_967_296L,
    )
}
