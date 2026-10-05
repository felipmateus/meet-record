#!/usr/bin/env bash
# Builds the teams-tap binary (Core Audio Process Tap) in release mode.
set -euo pipefail
cd "$(dirname "$0")/../native/teams-tap"
swift build -c release
echo "binary: $(pwd)/.build/release/teams-tap"
