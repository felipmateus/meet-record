// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "teams-tap",
    platforms: [.macOS("14.2")],
    targets: [
        .executableTarget(
            name: "teams-tap",
            path: "Sources/teams-tap",
            exclude: ["Info.plist"],
            linkerSettings: [
                .linkedFramework("CoreAudio"),
                .linkedFramework("AVFoundation"),
                // Embeds the Info.plist in the binary so that TCC identifies the utility
                // and shows the usage description when requesting system audio permission.
                .unsafeFlags([
                    "-Xlinker", "-sectcreate",
                    "-Xlinker", "__TEXT",
                    "-Xlinker", "__info_plist",
                    "-Xlinker", "Sources/teams-tap/Info.plist",
                ]),
            ]
        ),
    ]
)
