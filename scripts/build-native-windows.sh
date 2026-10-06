#!/usr/bin/env bash
# Builds the Windows teams-tap.exe (WASAPI process loopback + microphone) from macOS or Linux.
# Needs the .NET 8 SDK (macOS: brew install dotnet@8). The result is a self-contained
# single-file x64 executable: copy it to the Windows machine, no runtime install needed.
set -euo pipefail
cd "$(dirname "$0")/../native/teams-tap-win"
DOTNET="${DOTNET:-$(command -v dotnet || echo /opt/homebrew/opt/dotnet@8/bin/dotnet)}"
DOTNET_CLI_TELEMETRY_OPTOUT=1 "$DOTNET" publish -c Release
echo "binary: $(pwd)/bin/Release/net8.0/win-x64/publish/teams-tap.exe"
