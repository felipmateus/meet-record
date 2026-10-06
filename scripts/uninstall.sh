#!/usr/bin/env bash
# Removes what scripts/install.sh set up for this copy of teams-recorder.
#
#   scripts/uninstall.sh [--all] [--yes]
#
# Always: stops and removes the LaunchAgents (daemon and planner), but only when they run this
# copy of the project. With --all: also deletes .venv and the teams-tap build. Never deletes
# your recordings, transcripts, plans or models (the data folder), nor Homebrew packages.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
LABELS=(local.teams-recorder.daemon local.teams-recorder.planner)
ALL=0
ASSUME_YES=0
while [ $# -gt 0 ]; do
  case "$1" in
    --all) ALL=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
confirm() {
  local answer
  [ "$ASSUME_YES" = 1 ] && return 0
  [ -t 0 ] || return 1
  read -r -p "$1 [y/N] " answer
  [[ "$answer" =~ ^[Yy] ]]
}

DATA_DIR="$PROJECT_DIR/data"
if [ -x "$PROJECT_DIR/.venv/bin/trec" ]; then
  DATA_DIR="$("$PROJECT_DIR/.venv/bin/trec" status 2>/dev/null | sed -n 's/^Data dir: //p')"
fi

for label in "${LABELS[@]}"; do
  plist="$AGENTS_DIR/$label.plist"
  if [ ! -f "$plist" ]; then echo "$label: not installed"; continue; fi
  owner="$(/usr/libexec/PlistBuddy -c "Print :WorkingDirectory" "$plist" 2>/dev/null || true)"
  if [ "$owner" != "$PROJECT_DIR" ]; then
    echo "$label: runs another copy ($owner); left alone"
    continue
  fi
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  rm -f "$plist"
  echo "$label: removed"
done

if [ "$ALL" = 1 ] && confirm "Delete .venv and the teams-tap build in $PROJECT_DIR?"; then
  rm -rf "$PROJECT_DIR/.venv" "$PROJECT_DIR/native/teams-tap/.build"
  echo "removed .venv and native/teams-tap/.build"
fi

echo "Your data was kept: ${DATA_DIR:-$PROJECT_DIR/data}"
echo "macOS permissions (Microphone, System Audio Recording) can be removed in System Settings > Privacy & Security."
