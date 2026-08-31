// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "StoryTellerContractTools",
    platforms: [.macOS(.v13)],
    products: [.executable(name: "storyteller-contract-runner", targets: ["ContractRunner"])],
    dependencies: [
        .package(url: "https://github.com/weichsel/ZIPFoundation.git", exact: "0.9.20"),
    ],
    targets: [
        .executableTarget(
            name: "ContractRunner",
            dependencies: [.product(name: "ZIPFoundation", package: "ZIPFoundation")],
            path: ".",
            sources: [
                "ContractRunner/main.swift",
                "StoryTeller/Engine/V2PackageValidator.swift",
                "StoryTeller/Engine/TrustedV2Schemas.swift",
                "StoryTeller/Engine/TrustedJSONSchema.swift",
                "StoryTeller/Engine/ConversationHistoryStore.swift",
                "StoryTeller/Engine/ChunkStream.swift",
                "StoryTeller/Data/GmIndex.swift",
                "StoryTeller/Data/KnowledgeSource.swift",
                "StoryTeller/Data/SaveState.swift",
                "StoryTeller/Data/StoryRepository.swift",
                "StoryTeller/Model/GraphNode.swift",
                "StoryTeller/Model/StoryPackage.swift",
            ]
        ),
    ]
)
