#!/usr/bin/env bash
# Installs teams-recorder on this Mac, from a clone of the repository. Safe to run again:
# every step checks what is already there and only does what is missing.
#
#   scripts/install.sh [--name "Your name"] [--provider claude-code|api] [--skip-model]
#                      [--no-agent] [--yes] [--dry-run]
#
# Steps: check macOS and the project location, Homebrew packages (ffmpeg, whisper-cpp),
# Xcode Command Line Tools, Python virtualenv, the teams-tap capture binary, the whisper model,
# config.toml ([user] name, llm provider), .env (API provider only), trec doctor, and the
# LaunchAgents (daemon + 6 pm planner). Installing Homebrew itself and logging in to Claude Code
# are left to you: both need your password or browser.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd -P)"
VENV="$PROJECT_DIR/.venv"
TREC="$VENV/bin/trec"
MIN_MACOS="14.2"                       # Core Audio Process Tap
BREW_PACKAGES=(ffmpeg whisper-cpp)
TEAMS_APP="/Applications/Microsoft Teams.app"
PRIVACY_PANES=(Privacy_Microphone Privacy_ScreenCapture)

NAME=""
PROVIDER=""
SKIP_MODEL=0
NO_AGENT=0
ASSUME_YES=0
DRY_RUN=0

usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="${2:?--name needs a value}"; shift 2 ;;
    --provider) PROVIDER="${2:?--provider needs claude-code or api}"; shift 2 ;;
    --skip-model) SKIP_MODEL=1; shift ;;
    --no-agent) NO_AGENT=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done
case "$PROVIDER" in ""|claude-code|api) ;; *) echo "--provider must be claude-code or api" >&2; exit 2 ;; esac

if [ -t 1 ]; then B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'; else B=""; G=""; Y=""; R=""; N=""; fi
STEP=0
WARNINGS=()
step() { STEP=$((STEP + 1)); printf '\n%s[%d] %s%s\n' "$B" "$STEP" "$1" "$N"; }
ok()   { printf '  %s✓%s %s\n' "$G" "$N" "$1"; }
warn() { printf '  %s!%s %s\n' "$Y" "$N" "$1"; WARNINGS+=("$1"); }
die()  { printf '  %s✗ %s%s\n' "$R" "$1" "$N" >&2; exit 1; }
run()  { if [ "$DRY_RUN" = 1 ]; then printf '  (dry run) %s\n' "$*" >&2; else "$@"; fi; }
interactive() { [ "$ASSUME_YES" = 0 ] && [ -t 0 ]; }
confirm() {   # confirm "question" default(y|n)
  local answer default="${2:-y}"
  interactive || { [ "$default" = y ]; return; }
  read -r -p "  $1 [$( [ "$default" = y ] && echo Y/n || echo y/N )] " answer
  answer="${answer:-$default}"
  [[ "$answer" =~ ^[Yy] ]]
}
DAEMON_PLIST="$HOME/Library/LaunchAgents/local.teams-recorder.daemon.plist"
agent_owner() {   # project folder the installed daemon runs from, if any
  [ -f "$DAEMON_PLIST" ] && /usr/libexec/PlistBuddy -c "Print :WorkingDirectory" "$DAEMON_PLIST" 2>/dev/null || true
}
version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -1)" = "$2" ]; }

# Reads values from config.toml through the project's own settings loader (scripts/config_tool.py).
settings() { "$VENV/bin/python" "$PROJECT_DIR/scripts/config_tool.py" get; }
setting() { settings | sed -n "s/^$1=//p"; }

# Rewrites `key = "value"` inside one [section] of config.toml, keeping everything else.
set_config() { run "$VENV/bin/python" "$PROJECT_DIR/scripts/config_tool.py" set "$1" "$2" "$3"; }

printf '%steams-recorder installer%s\n%s\n' "$B" "$N" "$PROJECT_DIR"
[ "$DRY_RUN" = 1 ] && printf '%sDry run: nothing will be changed.%s\n' "$Y" "$N"

# ---------------------------------------------------------------------------------------------
step "Mac and project location"
[ "$(uname -s)" = Darwin ] || die "teams-recorder runs on macOS only (the Windows port lives in native/teams-tap-win)."
MACOS="$(sw_vers -productVersion)"
version_ge "$MACOS" "$MIN_MACOS" || die "macOS $MACOS found; $MIN_MACOS or later is needed for system audio capture."
ok "macOS $MACOS on $(uname -m)"
case "$PROJECT_DIR/" in
  "$HOME/Documents/"*|"$HOME/Desktop/"*|"$HOME/Downloads/"*|"$HOME/Library/Mobile Documents/"*)
    die "The project is in a folder macOS protects from background processes (Documents, Desktop, Downloads or iCloud).
    The daemon would fail with 'Resource deadlock avoided'. Move it first, for example:
      mv \"$PROJECT_DIR\" ~/Projetos/teams-recorder && ~/Projetos/teams-recorder/scripts/install.sh" ;;
esac
ok "location is outside Documents, Desktop, Downloads and iCloud"
[ -d "$TEAMS_APP" ] && ok "Microsoft Teams installed" || warn "Microsoft Teams not found in /Applications; install it before your first call."

# ---------------------------------------------------------------------------------------------
step "Homebrew packages"
if ! command -v brew >/dev/null 2>&1; then
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$candidate" ] && eval "$("$candidate" shellenv)" && break
  done
fi
command -v brew >/dev/null 2>&1 || die "Homebrew is not installed. Install it (it asks for your password), then run this script again:
    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
for pkg in "${BREW_PACKAGES[@]}"; do
  if brew list --formula "$pkg" >/dev/null 2>&1; then ok "$pkg"; else run brew install "$pkg"; ok "$pkg installed"; fi
done

# ---------------------------------------------------------------------------------------------
step "Xcode Command Line Tools (Swift compiler)"
if xcode-select -p >/dev/null 2>&1 && command -v swift >/dev/null 2>&1; then
  ok "$(swift --version 2>/dev/null | head -1)"
else
  run xcode-select --install || true
  die "Finish the Command Line Tools installation in the window macOS opened, then run this script again."
fi

# ---------------------------------------------------------------------------------------------
step "Python environment"
PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    PYTHON="$(command -v "$candidate")"; break
  fi
done
if [ -z "$PYTHON" ]; then
  run brew install python@3.12
  PYTHON="$(brew --prefix)/bin/python3.12"
fi
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  ok "virtualenv exists ($("$VENV/bin/python" --version))"
else
  run "$PYTHON" -m venv "$VENV"
  ok "virtualenv created with $("$PYTHON" --version)"
fi
run "$VENV/bin/python" -m pip install --quiet --upgrade pip
run "$VENV/bin/python" -m pip install --quiet -e "$PROJECT_DIR"
ok "teams-recorder installed in .venv (command: $TREC)"

# ---------------------------------------------------------------------------------------------
step "Capture binary (teams-tap)"
run "$PROJECT_DIR/scripts/build-native.sh" >/dev/null
ok "built native/teams-tap/.build/release/teams-tap"

# ---------------------------------------------------------------------------------------------
step "Settings (config.toml)"
if [ "$DRY_RUN" = 1 ] && [ ! -x "$VENV/bin/python" ]; then
  warn "dry run without a virtualenv: settings, model, .env and agents steps are only listed"
  printf '\nDry run finished.\n'; exit 0
fi
CURRENT_NAME="$(setting user_name)"
if [ -z "$NAME" ] && interactive; then
  read -r -p "  Your name as people say it in meetings [${CURRENT_NAME:-none}]: " NAME
fi
NAME="${NAME:-$CURRENT_NAME}"
if [ "$NAME" != "$CURRENT_NAME" ]; then set_config user name "$NAME"; fi
ok "user name: ${NAME:-(not set; tasks addressed to you by name will not be recognized)}"

CURRENT_PROVIDER="$(setting provider)"
if [ -z "$PROVIDER" ] && interactive; then
  echo "  The analysis can use your Claude subscription (claude-code) or the pay-per-use API (api)."
  read -r -p "  LLM provider [${CURRENT_PROVIDER}]: " PROVIDER
  case "${PROVIDER:-$CURRENT_PROVIDER}" in claude-code|api) ;; *) die "provider must be claude-code or api" ;; esac
fi
PROVIDER="${PROVIDER:-$CURRENT_PROVIDER}"
if [ "$PROVIDER" != "$CURRENT_PROVIDER" ]; then set_config llm provider "$PROVIDER"; fi
ok "LLM provider: $PROVIDER"

if [ "$PROVIDER" = claude-code ]; then
  if command -v claude >/dev/null 2>&1 || [ -x "$HOME/.local/bin/claude" ]; then
    ok "Claude Code found; make sure you are logged in (run 'claude' once and use /login)"
  else
    warn "Claude Code is not installed. Install it with: curl -fsSL https://claude.ai/install.sh | bash, then run 'claude' and log in."
  fi
else
  ENV_FILE="$PROJECT_DIR/.env"
  if [ ! -f "$ENV_FILE" ]; then
    run cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
    warn "created .env; paste your ANTHROPIC_API_KEY into it (console.anthropic.com)"
  else
    ok ".env exists"
  fi
  run chmod 600 "$ENV_FILE"
fi

# ---------------------------------------------------------------------------------------------
step "Transcription model"
MODEL_PATH="$(setting model_path)"
if [ -s "$MODEL_PATH" ]; then
  ok "$(basename "$MODEL_PATH") present"
elif [ "$SKIP_MODEL" = 1 ]; then
  warn "model skipped (--skip-model); download it later with scripts/download-model.sh"
else
  MODEL_NAME="$(basename "$MODEL_PATH" .bin)"; MODEL_NAME="${MODEL_NAME#ggml-}"
  echo "  downloading $MODEL_NAME (several hundred MB)"
  run "$PROJECT_DIR/scripts/download-model.sh" "$MODEL_NAME" "$(dirname "$MODEL_PATH")"
  ok "model saved to $MODEL_PATH"
fi
VAD_PATH="$(setting vad_path)"
if [ -n "$VAD_PATH" ] && [ ! -s "$VAD_PATH" ] && [ "$SKIP_MODEL" = 0 ]; then
  VAD_NAME="$(basename "$VAD_PATH" .bin)"; VAD_NAME="${VAD_NAME#ggml-}"
  run "$PROJECT_DIR/scripts/download-model.sh" "$VAD_NAME" "$(dirname "$VAD_PATH")"
  ok "VAD model saved"
fi

# ---------------------------------------------------------------------------------------------
step "Checking the installation (trec doctor)"
if [ "$DRY_RUN" = 1 ]; then echo "  (dry run) $TREC doctor"
elif "$TREC" doctor | sed 's/^/  /'; then ok "all checks passed"
else warn "trec doctor reported a problem above; fix it and run 'trec doctor' again"; fi

# ---------------------------------------------------------------------------------------------
step "Background services (LaunchAgents)"
if [ "$NO_AGENT" = 1 ]; then
  warn "skipped (--no-agent); install later with: $TREC agent install"
else
  ACTIVE="$(setting active)"
  OTHER="$(agent_owner)"
  if [ -n "$OTHER" ] && [ "$OTHER" != "$PROJECT_DIR" ] && ! confirm "The services currently run the copy at $OTHER. Point them to this one instead?" n; then
    warn "services left pointing to $OTHER"
  elif [ -f "$ACTIVE" ]; then
    warn "a recording is in progress; services not reinstalled. Run '$TREC agent install' after the call."
  elif confirm "Install the recorder daemon (starts at login) and the 6 pm planner?" y; then
    run "$TREC" agent install | sed 's/^/  /'
    ok "daemon and planner installed"
  else
    warn "services not installed; run '$TREC agent install' when ready"
  fi
fi

# ---------------------------------------------------------------------------------------------
step "macOS permissions"
cat <<TXT
  On the first recorded call macOS asks for two permissions. Allow both, or the Teams track
  comes out silent or the microphone track empty:
    - Microphone
    - Screen & System Audio Recording (System Audio Recording Only is enough)
  Both live in System Settings > Privacy & Security.
TXT
if [ "$DRY_RUN" = 0 ] && interactive && confirm "Open those settings pages now?" n; then
  for pane in "${PRIVACY_PANES[@]}"; do open "x-apple.systempreferences:com.apple.preference.security?$pane"; done
fi

# ---------------------------------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then printf '\n%sDry run finished; nothing was changed.%s\n' "$B" "$N"; exit 0; fi
printf '\n%sDone.%s ' "$B" "$N"
if [ ${#WARNINGS[@]} -eq 0 ]; then echo "Everything is installed."; else
  echo "Installed, with ${#WARNINGS[@]} item(s) to check:"
  for w in "${WARNINGS[@]}"; do printf '  %s!%s %s\n' "$Y" "$N" "$w"; done
fi
cat <<TXT

Next: join a Teams call; recording starts by itself. Useful commands:
  $TREC status          meetings and their state
  $TREC agent status    is the daemon running?
  tail -f "$(setting data_dir)/log/teams-recorder.log"
TXT
