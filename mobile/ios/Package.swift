// swift-tools-version: 5.9
// StoryTeller — SPM dependencies for iOS app
//
// Usage: Add this package as a local dependency in Xcode,
// or add the individual packages via File → Add Package Dependencies.

import PackageDescription

let package = Package(
    name: "StoryTeller",
    platforms: [
        .iOS(.v16),
    ],
    products: [
        .library(name: "StoryTellerLib", targets: ["StoryTellerLib"]),
    ],
    dependencies: [
        // ZIPFoundation for .story ZIP extraction
        .package(url: "https://github.com/weichsel/ZIPFoundation.git", from: "0.9.19"),
    ],
    targets: [
        .target(
            name: "StoryTellerLib",
            dependencies: [
                .product(name: "ZIPFoundation", package: "ZIPFoundation"),
            ],
            path: "StoryTeller",
            exclude: ["Info.plist", "BridgingHeader.h", "Engine/LlamaBridge.c"]
        ),
        .testTarget(
            name: "StoryTellerTests",
            dependencies: ["StoryTellerLib"],
            path: "Tests"
        ),
    ]
)
