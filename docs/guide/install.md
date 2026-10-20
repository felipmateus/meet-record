# Installation

## Prerequisites

**macOS**

- macOS 14.2 or later (needed for Core Audio process taps)
- [Homebrew](https://brew.sh)
- Xcode Command Line Tools (the installer asks for them if they are missing)
- Microsoft Teams (the new client, process `MSTeams`)
- About 1 GB of disk for the model and tools, plus about 1 GB per hour of meeting while a call is recorded (raw tracks are deleted after mixing)
- For analysis, **one** of:
  - a Claude API key ([console.anthropic.com](https://console.anthropic.com)) for the `api` provider, or
  - [Claude Code](https://claude.com/claude-code) installed and logged in, for the `claude-code` provider
- Optional: [Backlog.md](https://github.com/MrLesk/Backlog.md) (`brew install backlog-md`) to publish stories

**Windows**: Windows 10 version 2004 or later, or Windows 11, with winget. See [Installation on Windows](#installation-on-windows).

> **Important:** keep the project out of `~/Documents`, `~/Desktop`, `~/Downloads` and iCloud Drive. macOS privacy controls (TCC) block background processes there, first now and then and later all the time ("Resource deadlock avoided"). The installer refuses to run in those folders. On Windows, keep it out of OneDrive.

## Installation on macOS

```bash
git clone https://github.com/felipmateus/meet-record.git ~/Projetos/teams-recorder
```

```bash
~/Projetos/teams-recorder/scripts/install.sh
```

Or double-click `install.command` in Finder. The installer is idempotent: run it again at any time and it only does what is missing.

What it does:

1. Checks macOS, the project location and whether Teams is installed.
2. Installs `ffmpeg` and `whisper-cpp` with Homebrew, and asks for the Xcode Command Line Tools if they are missing.
3. Creates `.venv` with Python 3.11 or later (installing `python@3.12` if needed) and installs the package.
4. Builds `teams-tap` and `teams-speakers` (`scripts/build-native.sh`).
5. Asks for your name and the LLM provider, and writes them to `config.toml`. With the `api` provider it creates `.env` with permission 600 for the key.
6. Downloads the whisper model (574 MB) into the models folder.
7. Runs `trec doctor`.
8. Installs the daemon as a LaunchAgent (and removes the daily planner job an older version installed). It skips this while a recording is in progress, and asks before taking over services that run another copy of the project.
9. Explains the three macOS permissions (Microphone, Screen & System Audio Recording, Accessibility) and can open their settings pages. The Accessibility entry has to be added by hand, see the [first run checklist](#first-run-checklist).

| Option | Effect |
|---|---|
| `--name "Your name"` | Sets `[user] name` without asking |
| `--provider claude-code\|api` | Sets `[llm] provider` without asking |
| `--skip-model` | Does not download the whisper model |
| `--no-agent` | Does not install the LaunchAgents |
| `--yes` | Asks nothing; keeps current settings and installs the services |
| `--dry-run` | Shows what it would do and changes nothing |

Installing Homebrew, logging in to Claude Code and granting macOS permissions need your password or browser, so they are left to you.

**Uninstall.** `scripts/uninstall.sh` removes this copy's LaunchAgents (the daemon, and the planner job an older version installed). `--all` also deletes `.venv` and the `teams-tap` build (not yet the `teams-speakers` build); `--yes` asks nothing. Recordings, transcripts, the activities document, story drafts and models are never deleted.

### Manual installation

If you prefer to do the installer's steps yourself:

```bash
brew install ffmpeg whisper-cpp
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
scripts/build-native.sh                 # → native/teams-tap/.build/release/teams-tap and native/teams-speakers/.build/release/teams-speakers
scripts/download-model.sh               # → data/models/ggml-large-v3-turbo-q5_0.bin
cp .env.example .env && chmod 600 .env  # only for the api provider; paste the key
trec doctor
trec agent install
```

## Installation on Windows

> The Windows port is built and unit-tested on macOS but **has not run on a Windows PC yet**.

Install from a clone outside OneDrive, in PowerShell:

```powershell
git clone https://github.com/felipmateus/meet-record.git C:\Projetos\teams-recorder
C:\Projetos\teams-recorder\scripts\install.ps1
```

Or double-click `install.cmd`. The installer installs with winget only what is missing: Python 3.12, ffmpeg and, when `teams-tap.exe` must be built, the .NET 8 SDK (a .NET runtime alone cannot build it), so a PC that already has them needs no winget. It downloads whisper.cpp from a pinned release (checked by SHA-256) into `tools\whisper` and the model into `data\models` (`scripts\download-model.ps1`), then installs the daemon's scheduled task and removes the planner task an older version installed. Options mirror the macOS installer: `-Name`, `-Provider`, `-SkipModel`, `-NoAgent`, `-Yes`, `-DryRun`; `-NoActivities` also sets `[activities] enabled = false`, and `-RetentionDays N` sets `[audio] retention_days`. `scripts\uninstall.ps1` removes the tasks; `-All` also removes `.venv` and the build.

Only the parts that talk to the operating system differ:

| Part | macOS | Windows |
|---|---|---|
| Teams audio and microphone | `teams-tap` (Swift, Core Audio) | `teams-tap.exe` (C#, WASAPI), stopped through a stop file |
| Speaker labels from the Teams window | `teams-speakers` (Swift, Accessibility API) | Not available yet; your own lines are still labelled from the two tracks |
| Call detection | Teams' power assertion in `pmset` | Teams holding the microphone (registry `ConsentStore\microphone`) |
| Background service | LaunchAgents | Task Scheduler task `\teams-recorder\daemon` (at logon) |
| Notifications | Notification Center | Toasts, shown under "Windows PowerShell" |
| Keep-or-discard question | Dialog on the main screen | Message box, always on top: Yes keeps, No discards |

Windows asks for no permission to capture Teams audio. The microphone needs "Let desktop apps access your microphone" under Settings > Privacy & security > Microphone. `audio.teams_process_name_windows` (default `ms-teams.exe`) names the Teams process; `audio.mic_backend` applies only to macOS.

## First run checklist

1. **`trec doctor` is all `ok`.** It checks ffmpeg, whisper-cli, swift, osascript, the `teams-tap` build, Claude Code or the API key, the models, the transcript-loop guard, the claim verifier, the speaker labels, the activities document, the `.env` permission, free disk, the story guide and each story destination. It exits 0 only when everything your configuration needs is present. The `speaker labels` line is information only and never fails the doctor: it says whether `teams-speakers` is built and whether it holds the Accessibility permission (the check runs the helper as its own short-lived launchd job, the same context the daemon uses), and how the last recording was labelled.
2. **Grant the three macOS permissions** under System Settings > Privacy & Security. The first two are requested on the first recording; the third is not requested by macOS, you add it by hand:
   - **Microphone**, for the process that records the microphone.
   - **Screen & System Audio Recording**, for `teams-tap`. Without it, the Teams track comes out silent and only your voice is recorded.
   - **Accessibility**, for `teams-speakers`, so it can read the Teams window. Open the Accessibility pane, press the **+** button, press Cmd+Shift+G, enter `<project>/native/teams-speakers/.build/release/teams-speakers`, choose Open and switch the entry on. A request made by a background job creates no entry, so the **+** button is the only way. The grant has to be on the helper itself: the daemon runs it as its own launchd job (`local.teams-recorder.speakers`), so granting your terminal or Python does not cover it. macOS ties the grant to the binary, so a rebuild (`scripts/build-native.sh`) may require adding it again; `trec doctor` tells. Without it recordings work as before, only without names (see [Speaker labels](speaker-labels.md)).
3. **Set your name** in `config.toml` (`[user] name`), as people say it in meetings, so tasks addressed to you by name are attributed to you.
4. **Check that the detector sees a call.** Join a test call and run `trec daemon --once`. It should report Teams in a call along with its PID.
5. **Check the services** with `trec agent status`. After an update that adds the speaker labels or the activities curator, run `trec agent restart` so the daemon starts using them.
