// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "teams-speakers",
    platforms: [.macOS("14.2")],
    targets: [
        .executableTarget(
            name: "teams-speakers",
            path: "Sources/teams-speakers",
            exclude: ["Info.plist"],
            linkerSettings: [
                .linkedFramework("ApplicationServices"),
                // Embeds the Info.plist in the binary so that TCC identifies the helper
                // by its bundle id when it asks for the Accessibility permission.
                .unsafeFlags([
                    "-Xlinker", "-sectcreate",
                    "-Xlinker", "__TEXT",
                    "-Xlinker", "__info_plist",
                    "-Xlinker", "Sources/teams-speakers/Info.plist",
                ]),
            ]
        ),
    ]
)
