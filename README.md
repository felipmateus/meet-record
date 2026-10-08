# teams-recorder

Automatically records the audio of Microsoft Teams meetings on macOS and Windows, transcribes it locally with whisper.cpp, extracts actions and decisions with the Claude API, and generates a daily activity plan in Markdown.

The tool targets meetings held in Brazilian Portuguese, and the analysis and plan content it produces is in Portuguese; the code, documentation and CLI are in English.

Requirements and architecture documentation: `docs/REQUIREMENTS-AND-ARCHITECTURE.md`.

## Current status

- Phase 1 done: domain, ports, use cases, file-based repository, CLI (`trec status`, `trec doctor`) and tests.
- Phase 2 done: Teams audio capture via Core Audio Process Tap (Swift binary `teams-tap`), microphone capture and mixing with ffmpeg, `trec start`, `trec stop` and `trec cancel` commands.
- Phase 3 done: local Portuguese transcription with whisper.cpp (`trec transcribe`), model `large-v3-turbo-q5_0`.
- Phase 4 done: transcript analysis with the Claude API (`trec analyze`): summary, decisions, actions, deadlines and open questions in `analysis.json`.
- Phase 5 done: call detector, daemon and LaunchAgent (`trec agent install`). Recording, transcription and analysis run on their own.
- Phase 6 done: daily planner (`trec plan`), scheduled Monday to Friday at 6 pm by the same `trec agent install`, with purging of old audio.
- Phase 7 done: installer (`scripts/install.sh`, or double-click `install.command`) and uninstaller (`scripts/uninstall.sh`).
- Windows port: the whole flow has Windows adapters (see [Windows](#windows)). It is built and unit-tested on macOS but **has not run on a Windows PC yet**.

## Installation (phase 7)

On a Mac with macOS 14.2 or later and [Homebrew](https://brew.sh):

```bash
git clone https://github.com/felipmateus/meet-record.git ~/Projetos/teams-recorder
~/Projetos/teams-recorder/scripts/install.sh
```

Or double-click `install.command` in Finder. Keep the project out of Documents, Desktop, Downloads and iCloud: macOS blocks background processes there, and the installer refuses to run in those folders.

The installer can be run again at any time; it only does what is missing:

1. Checks macOS, the project location and whether Teams is installed.
2. Installs `ffmpeg` and `whisper-cpp` with Homebrew, and asks for the Xcode Command Line Tools if they are missing.
3. Creates `.venv` with Python 3.11 or later and installs the package.
4. Builds `teams-tap`.
5. Asks for your name and the LLM provider, and writes them to `config.toml`. With the `api` provider it creates `.env` with permission 600 for the key.
6. Downloads the whisper model (574 MB).
7. Runs `trec doctor`.
8. Installs the daemon and the 6 pm planner. It skips this while a recording is in progress, and asks before taking over services that run another copy of the project.
9. Explains the two macOS permissions and can open their settings pages.

Options: `--name "Your name"`, `--provider claude-code|api`, `--skip-model`, `--no-agent`, `--yes` (no questions), `--dry-run` (shows what it would do).

Installing Homebrew and logging in to Claude Code are left to you, since both need your password or browser.

`scripts/uninstall.sh` removes the services of this copy; `--all` also deletes `.venv` and the `teams-tap` build. Recordings, transcripts, plans and models are never deleted.

## Windows

The same program runs on Windows 10 version 2004 or later and Windows 11. Transcription, analysis, minutes, the daily plan and the keep-or-discard question work the same; only the parts that talk to the operating system change:

| Part | macOS | Windows |
|---|---|---|
| Teams audio and microphone | `teams-tap` (Swift, Core Audio) | `teams-tap.exe` (C#, WASAPI), stopped through a stop file |
| Call detection | Teams' power assertion in `pmset` | Teams holding the microphone, read from the registry Windows keeps for the privacy indicator |
| Background service | LaunchAgents | Task Scheduler tasks `\teams-recorder\daemon` (at logon) and `\teams-recorder\planner` (Mon–Fri 6 pm) |
| Notifications | Notification Center | Toasts, shown under "Windows PowerShell" |
| Keep-or-discard question | Dialog on the main screen | Message box, always on top, with Yes (keep) and No (discard) |

Install from a clone, outside OneDrive, in PowerShell:

```powershell
git clone https://github.com/felipmateus/meet-record.git C:\Projetos\teams-recorder
C:\Projetos\teams-recorder\scripts\install.ps1
```

Or double-click `install.cmd`. The installer uses winget for Python 3.12, ffmpeg and, when `teams-tap.exe` must be built, the .NET 8 SDK. It downloads whisper.cpp into `tools\whisper` and the model into `data\models`, then installs the scheduled tasks. Options mirror the macOS installer: `-Name`, `-Provider`, `-SkipModel`, `-NoAgent`, `-Yes`, `-DryRun`. `scripts\uninstall.ps1` removes the tasks; `-All` also removes `.venv` and the build.

Windows asks for no permission to capture Teams audio. The microphone needs "Let desktop apps access your microphone" under Settings > Privacy & security > Microphone. In `config.toml`, `audio.teams_process_name_windows` (default `ms-teams.exe`) names the Teams process; `audio.mic_backend` applies only to macOS.

## Manual recording (phase 2)

```bash
scripts/build-native.sh          # builds native/teams-tap/.build/release/teams-tap
trec start --title "Daily"       # Teams must be open; or use --pid
trec status                      # shows the recording in progress
trec stop                        # mixes and produces data/recordings/<id>/audio.m4a
```

## Transcription (phase 3)

```bash
brew install whisper-cpp
scripts/download-model.sh            # ggml-large-v3-turbo-q5_0.bin (574 MB) into data/models/
trec transcribe                      # every recorded meeting not yet transcribed
trec transcribe 2026-10-06_14-00-00  # one specific meeting
```

Produces `transcript.txt` (with timestamps) and `transcript.json` in the meeting folder. Data (recordings, plans, models, logs) lives where `paths.data_dir` in `config.toml` points; this repository keeps it in `./data` (git-ignored). Left empty, it is chosen automatically: `./data`, or `~/Library/Application Support/teams-recorder` when the project is under Documents/Desktop/Downloads or iCloud, since macOS can block background processes there. `trec status` shows the folder in use.

## Analysis with Claude (phase 4)

```bash
cp .env.example .env && chmod 600 .env   # paste the API key (console.anthropic.com)
trec analyze                             # every transcribed meeting not yet analyzed
trec analyze 2026-10-06_14-00-00         # one specific meeting
```

Each analysis also writes `minutes.md` in the meeting folder: minutes in the structure of the `meeting-notes` skill (title, date, participants, type and purpose, summary, topics, decisions, an action table with owner, due date, priority and the transcript timestamp where it was said, risks, open questions, next steps), in Portuguese. Untitled automatic recordings take the title inferred by the model. `trec minutes [id] [--all]` re-renders minutes from existing analyses without calling the model. Set `[user] name` in `config.toml` so tasks addressed to you by name are attributed to you.

Only the transcript text and the prompt leave the Mac. Model `claude-opus-5-5` with schema-validated structured output, system prompt in `prompts/analyze_system.md` with caching, and a server-side fallback for occasional refusals by the safety classifier. Each call logs tokens to `data/log/llm_usage.jsonl`. Typical cost: about US$ 0.10 per hour of meeting.

### Provider: API or Claude Code

In `config.toml`, `llm.provider` selects the transport:

| `provider` | Uses | Billing | Notes |
|---|---|---|---|
| `api` (default) | Claude API with `ANTHROPIC_API_KEY` | Prepaid, pay-per-use credit | Refusal fallback and caching controlled by the project |
| `claude-code` | Installed Claude Code, in headless mode (`claude -p`) | Claude Code subscription | Requires a logged-in session on the Mac; no refusal fallback; model by alias in `llm.cli_model` |

The `TREC_LLM_PROVIDER` environment variable overrides the file, which is handy for testing: `TREC_LLM_PROVIDER=claude-code trec analyze`.

## Automatic (phase 5)

```bash
trec agent install                                   # starts at login, restarts if it crashes
trec agent install --env TREC_LLM_PROVIDER=claude-code   # same, analyzing via the subscription
trec agent status | restart | uninstall
trec daemon --once                                   # diagnostic: does the detector see Teams in a call?
```

The daemon polls `pmset -g assertions` every second. Teams, while in a call, keeps the Mac from sleeping, and that assertion is the signal: recording starts on the first confirmation (~1-2 s after the call starts) and stops after 5 readings without a call (~5 s after hanging up). If the daemon crashes in the middle of a recording, it finalizes the orphaned recording on startup and resumes pending meetings. Log in `data/log/teams-recorder.log`; manual `trec start/stop` keeps working, and the daemon adopts a manual recording already in progress.

### Keep or discard each recording

When the daemon starts a recording, a dialog asks whether to keep it. It opens centered on the main screen, above other windows, with two buttons: **Keep recording** (the default, also chosen by pressing Return) and **Discard**.

- Recording starts before the answer, so the beginning of the meeting is never lost.
- **Discard** stops the recording, deletes its files and ignores the rest of that call. The next call is asked again.
- No answer within 30 seconds keeps the recording.
- If the call ends while the dialog is open, the capture stops at hang-up and transcription waits for the answer.
- Recordings started with `trec start` are not asked about.

Configure it in `config.toml` under `[confirmation]`: `enabled = false` turns the question off, and `timeout_seconds` sets the wait. The dialog takes keyboard focus while it is open. If Teams is in full screen, the dialog may show on another desktop.

### Microphone and Teams track

When the call ends the recorders stop at once and the "recording in progress" marker is released; mixing, transcription and analysis then run in the background, so a call that starts right after is recorded normally. Mixing writes `audio.partial.m4a` and renames it to `audio.m4a` only on success, with a time limit of twice the meeting length (at least 10 minutes). If mixing fails or the daemon stops before it, the raw tracks stay in the meeting folder and the next daemon start mixes them again. The time limit only stops an ffmpeg that hangs: an 86-minute meeting mixed in 11 minutes.

The raw tracks are 16-bit WAV by default, about 1 GB per hour of meeting until they are mixed; `audio.bit_depth = 32` in `config.toml` records 32-bit float instead (about 2 GB per hour, no gain for transcription). A notification warns when a recording starts with room for less than 2 hours, and again during a call if less than 1 GB is left; `trec doctor` shows the free space.

Both tracks are aligned to the meeting start: `teams-tap` places every audio buffer at its Core Audio timestamp, so time without audio (start-up, or the system pausing delivery mid-call) is written as silence instead of being dropped. Each padded gap is logged in `data/log/capture.log` as `gap of X s at Y s`.

`teams-tap` handles both sides: `--pid` captures Teams (the main process and the helpers that actually emit audio) and `--mic default` records the microphone through AVAudioEngine, following the system default input and surviving the reconfiguration Teams performs when it opens the microphone. `teams-tap --list` shows who the current audio clients are. The `ffmpeg` microphone backend remains available in `config.toml` (`audio.mic_backend`).

## Daily plan (phase 6)

```bash
trec plan                      # consolidates today's analyzed meetings into data/plans/YYYY-MM-DD.md
trec plan --date 2026-10-06    # rebuilds the plan for a given day
trec plan --purge              # same + deletes audio from old meetings (retention)
```

New actions come from the day's analyses (deterministic); overdue ones are open actions whose deadline has passed; the model writes the Markdown and the priorities and points out which open actions were completed according to the analyses, and may only cite existing ids. The accumulated list lives in `data/plans/open_actions.json`. The `local.teams-recorder.planner` LaunchAgent runs `trec plan --purge` at 6 pm (config `planner.hour`), Monday to Friday.

On first run, macOS asks for two permissions: **Microphone** (for ffmpeg) and **Screen & System Audio Recording** (for teams-tap), under System Settings > Privacy & Security. Without the second one, the Teams track comes out silent.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                                             # fast suite (no coverage)
pytest --cov=teams_recorder --cov-report=term-missing   # with coverage (target: 70%)
TREC_REAL_WHISPER=1 pytest -m slow                 # includes real transcription with the model
trec --help
```
