#!/usr/bin/env bash
# Builds the native helpers in release mode: teams-tap (Core Audio Process Tap) and teams-speakers
# (reads the Teams window through the Accessibility API; read-only on Teams).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

# The helper must never act on the Teams UI (safety invariant 4 of docs/tasks/speaker-attribution/_spec.md):
# refuse to build it when its sources contain a call that sets an accessibility attribute.
if grep -rn "AXUIElementSetAttributeValue" "$root/native/teams-speakers/Sources"; then
    echo "build-native: teams-speakers sources must not call AXUIElementSetAttributeValue (the helper is read-only)" >&2
    exit 1
fi

(cd "$root/native/teams-tap" && swift build -c release)
(cd "$root/native/teams-speakers" && swift build -c release)

echo "binary: $root/native/teams-tap/.build/release/teams-tap"
echo "binary: $root/native/teams-speakers/.build/release/teams-speakers"
echo "note: if macOS asked for the Accessibility permission before, it may ask again for the rebuilt teams-speakers (trec doctor tells)"
