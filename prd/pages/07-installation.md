# Installation (phase 7)

> **Deliverables:** `scripts/install.sh`, `install.command`, `scripts/uninstall.sh`, installation section in the README
> **Module:** Installation · **Updated:** 2026-10-05

## Goal
Install from scratch on another Mac, or for another user, with a single script, meeting non-functional requirement NFR10.

## How the user runs it
- Terminal: `scripts/install.sh` from a clone of the repository.
- Finder: double-click `install.command`, which opens Terminal and runs the same script.

## Steps
1. Check macOS 14.2 or later, and that the project is not in Documents, Desktop, Downloads or iCloud. If it is, stop and show how to move it.
2. Warn if Microsoft Teams is not in /Applications.
3. Homebrew: install `ffmpeg` and `whisper-cpp` when missing. If Homebrew itself is missing, stop and show the official install command.
4. Xcode Command Line Tools: if missing, open the macOS installer and stop, asking the user to run the script again.
5. Python 3.11 or later (installs `python@3.12` with Homebrew if none is found): create `.venv` and install the package.
6. Build `teams-tap`.
7. Ask for the user's name (default: the current `[user] name`) and the LLM provider (`claude-code` or `api`), and write them to `config.toml`. For `claude-code`, check that Claude Code is installed. For `api`, create `.env` from the example with permission 600.
8. Download the whisper model (and the VAD model when `vad = true`) into the configured models folder.
9. Run `trec doctor`.
10. Install the daemon and the planner, unless a recording is in progress, or the services run another copy of the project and the user declines.
11. Explain the two macOS permissions and offer to open their settings pages.
12. Summarize the items that need attention.

## Options

| Option | Effect |
|---|---|
| `--name "Name"` | Sets `[user] name` without asking |
| `--provider claude-code\|api` | Sets `[llm] provider` without asking |
| `--skip-model` | Does not download the whisper model |
| `--no-agent` | Does not install the LaunchAgents |
| `--yes` | Asks nothing; keeps current settings and installs the services |
| `--dry-run` | Shows what would be done and changes nothing |

## Business rules
- Running it again is safe: each step only does what is missing.
- Installing Homebrew, logging in to Claude Code and granting the macOS permissions stay with the user.
- `scripts/uninstall.sh` removes only the services that run its own copy. `--all` also deletes `.venv` and the `teams-tap` build. Data (recordings, transcripts, plans, models) is never deleted.

## Acceptance criterion
A from-scratch installation for another user on the Mac works and `trec doctor` comes up green.

Verified on 2026-10-05 with a fresh copy outside the repository: every step passed in under a minute, with the model download and services skipped on purpose; a second run changed nothing. Pending from the original plan: the month's LLM spend in `trec status`.
