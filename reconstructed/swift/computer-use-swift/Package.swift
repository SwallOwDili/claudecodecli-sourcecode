// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "ComputerUseSwift",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "ComputerUseSwift", type: .dynamic, targets: ["ComputerUseSwift"]),
    ],
    targets: [
        .systemLibrary(
            name: "CNodeAPI",
            path: "Sources/CNodeAPI"
        ),
        .target(
            name: "ComputerUseSwift",
            dependencies: ["CNodeAPI"],
            path: "Sources/ComputerUseSwift",
            swiftSettings: [
                .swiftLanguageMode(.v5),
            ],
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("ApplicationServices"),
                .linkedFramework("CoreGraphics"),
                .linkedFramework("ScreenCaptureKit"),
                .unsafeFlags(["-Xlinker", "-undefined", "-Xlinker", "dynamic_lookup"]),
            ]
        ),
    ]
)
