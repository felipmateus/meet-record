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
                // Embute o Info.plist no binário para que o TCC identifique o utilitário
                // e mostre a descrição de uso ao pedir permissão de áudio do sistema.
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
