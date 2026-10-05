#!/usr/bin/env bash
# Compila o binário teams-tap (Core Audio Process Tap) em modo release.
set -euo pipefail
cd "$(dirname "$0")/../native/teams-tap"
swift build -c release
echo "binário: $(pwd)/.build/release/teams-tap"
