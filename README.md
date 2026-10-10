# teams-recorder

A background tool for macOS (and Windows, not yet run on real hardware) that notices when a Microsoft Teams call starts, records Teams audio and your microphone, transcribes the call locally with whisper.cpp, and uses Claude to pull out decisions, actions and deadlines. Every weekday evening it turns the day's meetings into a Markdown activity plan and drafts user stories for your backlog.

It is built for one person who sits in several meetings a day and wants a reliable record of what they committed to, without taking notes. Meetings are expected in Brazilian Portuguese, so the minutes, plans and stories it writes are in Portuguese. The code, CLI and documentation are in English.

```
Teams call ──► record ──► mix ──► transcribe ──► analyze ──► minutes.md
 (detected)   (2 tracks)  (m4a)   (whisper.cpp,   (Claude)        │
                                   on your Mac)                   ▼
                                     6 pm, Mon–Fri:  daily plan ──► story drafts ──► Backlog.md board
```

## Key features

- **Automatic recording.** A daemon watches Teams and starts recording about 1–2 s after a call begins. It stops about 5 s after you hang up. A dialog lets you discard any recording.
- **Two aligned tracks.** Teams audio is captured through a Core Audio process tap and the microphone separately. The tracks are aligned to the call's start, then mixed with noise reduction and loudness normalization.
- **Local transcription.** whisper.cpp (`large-v3-turbo-q5_0`, 574 MB) runs on your Mac. Audio never leaves the machine.
- **Structured analysis.** Claude extracts the summary, topics, decisions, your actions, other people's actions, deadlines, risks and open questions. Every item carries the transcript timestamp where it was said.
- **Meeting minutes.** A `minutes.md` file is written for each meeting, with no extra model call.
- **Daily plan.** The day's meetings and the running list of open actions are consolidated into a prioritized Markdown plan. Overdue and completed actions are tracked.
- **User stories.** Actions are routed by kind: features and bugs become user stories written by your own guide, technical and operation work becomes task cards, and the rest stays in the plan. They are published to a local Backlog.md board for review.
- **Two ways to pay for the model.** Use the Claude API with prepaid credit (about US$ 0.10 per hour of meeting), or your Claude Code subscription.
- **No database.** A meeting's state is the set of files in its folder, so any step can be re-run, and one meeting's failure never blocks the others.

## Table of contents

- [How it works](#how-it-works)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation on macOS](#installation-on-macos)
- [Installation on Windows](#installation-on-windows)
- [First run checklist](#first-run-checklist)
- [Daily use](#daily-use)
- [Command reference](#command-reference)
- [Recording in detail](#recording-in-detail)
- [Transcription](#transcription)
- [Analysis with Claude](#analysis-with-claude)
- [Daily plan](#daily-plan)
- [User stories and the Backlog.md board](#user-stories-and-the-backlogmd-board)
- [Configuration](#configuration)
- [Data, privacy and retention](#data-privacy-and-retention)
- [Architecture](#architecture)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Project status](#project-status)
- [Further documentation](#further-documentation)
- [License](#license)

## How it works

1. **Detect.** Every second the daemon reads `pmset -g assertions`. While Teams is in a call, it holds a "prevent sleep" assertion, and that is the signal. On Windows, the signal is Teams holding the microphone, as recorded by the privacy indicator in the registry.
2. **Record.** Recording starts on the first positive reading. `teams-tap` (a small Swift binary) writes Teams audio to `tap.wav` and the microphone to `mic.wav`. A dialog asks whether to keep the recording; recording does not wait for the answer.
3. **Mix.** After hang-up, ffmpeg cleans each track (80 Hz high-pass, noise reduction), mixes them, normalizes to -18 LUFS and writes `audio.m4a`. The raw tracks are deleted.
4. **Transcribe.** whisper.cpp writes `transcript.json` and `transcript.txt` (`[hh:mm:ss] text`).
5. **Analyze.** The transcript text is sent to Claude with a JSON schema. The result is saved as `analysis.json` and rendered to `minutes.md`.
6. **Plan.** At 6 pm, Monday to Friday, `trec plan` builds `plans/YYYY-MM-DD.md` and updates `open_actions.json`.
7. **Draft and publish stories.** If enabled, stories are drafted into `plans/YYYY-MM-DD.stories.md` and sent to the **Triagem** column of a Backlog.md board.

Steps 3–5 run in the background, so a call that starts right after another one is still recorded. Every step can also be run by hand with `trec`.

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | Python 3.11+ (Typer CLI, Pydantic, python-dotenv), hexagonal architecture |
| Audio capture (macOS) | Swift binary `native/teams-tap`: Core Audio Process Tap (macOS 14.2+) and AVAudioEngine for the microphone |
| Audio capture (Windows) | C# binary `native/teams-tap-win`: WASAPI process loopback (.NET 8) |
| Mixing and conversion | ffmpeg |
| Transcription | whisper.cpp (`whisper-cli`), ggml models from Hugging Face, optional Silero VAD |
| Analysis, plan, stories | Claude Opus 5.5 (`claude-opus-5-5`) through the `anthropic` SDK, or Claude Code headless (`claude -p`) |
| Background service | launchd LaunchAgents (macOS), Task Scheduler (Windows) |
| Story board | [Backlog.md](https://github.com/MrLesk/Backlog.md) (local Markdown kanban) |
| Tests and types | pytest, pytest-cov, mypy |

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
4. Builds `teams-tap` (`scripts/build-native.sh`).
5. Asks for your name and the LLM provider, and writes them to `config.toml`. With the `api` provider it creates `.env` with permission 600 for the key.
6. Downloads the whisper model (574 MB) into the models folder.
7. Runs `trec doctor`.
8. Installs the daemon and the 6 pm planner as LaunchAgents. It skips this while a recording is in progress, and asks before taking over services that run another copy of the project.
9. Explains the two macOS permissions and can open their settings pages.

| Option | Effect |
|---|---|
| `--name "Your name"` | Sets `[user] name` without asking |
| `--provider claude-code\|api` | Sets `[llm] provider` without asking |
| `--skip-model` | Does not download the whisper model |
| `--no-agent` | Does not install the LaunchAgents |
| `--yes` | Asks nothing; keeps current settings and installs the services |
| `--dry-run` | Shows what it would do and changes nothing |

Installing Homebrew, logging in to Claude Code and granting macOS permissions need your password or browser, so they are left to you.

**Uninstall.** `scripts/uninstall.sh` removes this copy's LaunchAgents. `--all` also deletes `.venv` and the `teams-tap` build. Recordings, transcripts, plans and models are never deleted.

### Manual installation

If you prefer to do the installer's steps yourself:

```bash
brew install ffmpeg whisper-cpp
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
scripts/build-native.sh                 # → native/teams-tap/.build/release/teams-tap
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

Or double-click `install.cmd`. The installer uses winget for Python 3.12, ffmpeg and, when `teams-tap.exe` must be built, the .NET 8 SDK. It downloads whisper.cpp into `tools\whisper` and the model into `data\models`, then installs the scheduled tasks. Options mirror the macOS installer: `-Name`, `-Provider`, `-SkipModel`, `-NoAgent`, `-Yes`, `-DryRun`. `scripts\uninstall.ps1` removes the tasks; `-All` also removes `.venv` and the build.

Only the parts that talk to the operating system differ:

| Part | macOS | Windows |
|---|---|---|
| Teams audio and microphone | `teams-tap` (Swift, Core Audio) | `teams-tap.exe` (C#, WASAPI), stopped through a stop file |
| Call detection | Teams' power assertion in `pmset` | Teams holding the microphone (registry `ConsentStore\microphone`) |
| Background service | LaunchAgents | Task Scheduler tasks `\teams-recorder\daemon` (at logon) and `\teams-recorder\planner` (Mon–Fri 6 pm) |
| Notifications | Notification Center | Toasts, shown under "Windows PowerShell" |
| Keep-or-discard question | Dialog on the main screen | Message box, always on top: Yes keeps, No discards |

Windows asks for no permission to capture Teams audio. The microphone needs "Let desktop apps access your microphone" under Settings > Privacy & security > Microphone. `audio.teams_process_name_windows` (default `ms-teams.exe`) names the Teams process; `audio.mic_backend` applies only to macOS.

## First run checklist

1. **`trec doctor` is all `ok`.** It checks ffmpeg, whisper-cli, swift, osascript, the `teams-tap` build, Claude Code or the API key, the models, the `.env` permission, free disk, the story guide and each story destination. It exits 0 only when everything your configuration needs is present.
2. **Grant the two macOS permissions** under System Settings > Privacy & Security. Both are requested on the first recording:
   - **Microphone**, for the process that records the microphone.
   - **Screen & System Audio Recording**, for `teams-tap`. Without it, the Teams track comes out silent and only your voice is recorded.
3. **Set your name** in `config.toml` (`[user] name`), as people say it in meetings, so tasks addressed to you by name are attributed to you.
4. **Check that the detector sees a call.** Join a test call and run `trec daemon --once`. It should report Teams in a call along with its PID.
5. **Check the services** with `trec agent status`.

## Daily use

Once installed, there is nothing to do: join Teams calls as usual.

- When a call starts, you get a notification and a **Keep recording / Discard** dialog. Press Return, or ignore it, to keep the recording.
- After hang-up, the meeting is mixed, transcribed and analyzed in the background. The minutes land in `data/recordings/<id>/minutes.md`.
- At 6 pm, Monday to Friday, the plan for the day lands in `data/plans/YYYY-MM-DD.md`, followed by the story drafts if they are enabled.
- `trec status` shows every meeting and its state, the recording in progress, the open actions and the stories waiting to be published.

## Command reference

`trec --help` and `trec <command> --help` list everything. All commands work from any terminal with the venv active (`source .venv/bin/activate`).

| Command | What it does |
|---|---|
| `trec status` | Data folder, API key status, meetings with state and next step, recording in progress, open actions, stories waiting to be published |
| `trec doctor` | Checks dependencies, models, permissions, disk and story destinations |
| `trec start [--pid N] [--title T]` | Starts a manual recording (Teams must be running, or pass `--pid`) |
| `trec stop` | Stops the recording, mixes the tracks and writes `audio.m4a`. Works from any terminal |
| `trec cancel` | Discards the recording in progress and deletes its files |
| `trec transcribe [id]` | Transcribes one meeting, or all meetings in state `recorded` |
| `trec analyze [id]` | Analyzes one meeting, or all meetings in state `transcribed`, and writes `minutes.md` |
| `trec minutes [id] [--all]` | Re-renders `minutes.md` from existing analyses, with no model call |
| `trec plan [--date YYYY-MM-DD] [--purge]` | Builds the day's plan; `--purge` also applies audio retention afterwards |
| `trec stories [--date YYYY-MM-DD]` | Drafts user stories from a day's plan |
| `trec publish [--date YYYY-MM-DD] [--only 1,3]` | Sends a day's drafts to the configured boards, skipping what is already there |
| `trec purge` | Deletes `audio.m4a` from transcribed meetings older than `planner.retention_days` |
| `trec daemon [--once]` | Runs the detector loop (used by the LaunchAgent); `--once` is a single diagnostic reading |
| `trec agent install [--env K=V]` | Installs the daemon and the planner as services (starts at login, restarts on a crash) |
| `trec agent status \| restart \| uninstall` | Inspects, restarts or removes the services |
| `trec version` | Prints the version |

Processing commands without an id act on every pending meeting and keep going when one fails. They exit with code 1 if any failed. Errors are written to `error.txt` in the meeting folder, and re-running clears them.

## Recording in detail

### Manual recording

```bash
trec start --title "Daily"   # Teams must be open; or use --pid
trec status                  # shows the recording in progress
trec stop                    # mixes into data/recordings/<id>/audio.m4a
```

Only one recording runs at a time, manual or automatic. The daemon adopts a manual recording that is already running instead of starting a second one. Recordings started with `trec start` are not asked about.

### Keep or discard

When the daemon starts a recording, a dialog opens centered on the main screen, above other windows, with **Keep recording** (the default, chosen with Return) and **Discard**.

- Recording starts before the answer, so the beginning of the meeting is never lost.
- **Discard** stops the recording, deletes its files and ignores the rest of that call. The next call is asked again.
- No answer within 30 seconds keeps the recording. If the dialog cannot be shown, the recording is also kept.
- If the call ends while the dialog is open, the capture stops at hang-up and transcription waits for the answer.

Configure it under `[confirmation]`: `enabled = false` turns the question off, and `timeout_seconds` sets the wait. If Teams is in full screen, the dialog may appear on another desktop.

### Tracks, alignment and mixing

- `teams-tap --pid` captures Teams: the main process and the helper processes that actually emit audio, since Teams' main process emits none. `teams-tap --mic default` records the microphone through AVAudioEngine. It follows the system default input (so it switches to a headset) and survives the reconfiguration Teams performs when it opens the microphone. `teams-tap --list` shows the current audio clients.
- Both tracks share the meeting start as their epoch. Every buffer is placed at its Core Audio timestamp, and missing time is written as silence, so the tracks keep the real call length and stay in sync. Each gap is logged in `data/log/capture.log` as `gap of X s at Y s`.
- Raw tracks are 16-bit WAV (about 1 GB per hour). `audio.bit_depth = 32` records 32-bit float instead (about 2 GB per hour), with no gain for transcription.
- When the call ends, the recorders stop at once and the "recording in progress" marker is released. Mixing writes `audio.partial.m4a` and renames it only on success, with a time limit of twice the meeting length (at least 10 minutes). If mixing fails or the daemon stops first, the raw tracks stay and the next daemon start mixes them again.
- A track that is missing or under 1 KB is dropped, and the mix uses the other one. If one track is shorter than half the other, raw copies are kept in `<meeting>/debug/` for diagnosis.
- A notification warns when a recording starts with room for less than 2 hours, and again during a call if less than 1 GB is left.
- If the daemon crashes during a recording, it finalizes the orphaned recording when it starts again and resumes stalled meetings.

The ffmpeg microphone backend is still available (`audio.mic_backend = "ffmpeg"`), but it stops recording a few seconds after Teams opens the microphone.

## Transcription

```bash
trec transcribe                      # every recorded meeting not yet transcribed
trec transcribe 2026-10-06_14-00-00  # one meeting
```

The M4A is converted to 16 kHz mono WAV and passed to `whisper-cli` with the language fixed to `pt`. The output is `transcript.json` (segments with start, end and text) and `transcript.txt`. On a MacBook Air M1, long meetings transcribe at about a quarter of their length.

Voice activity detection (Silero) is off by default. In a test with short sentences it cut off speech, and the noise reduction in the mix is what improved the text. To try it, run `scripts/download-model.sh silero-v5.1.2` and set `transcription.vad = true`.

## Analysis with Claude

```bash
trec analyze                         # every transcribed meeting not yet analyzed
trec analyze 2026-10-06_14-00-00     # one meeting
```

The model returns a schema-validated record:

| Field | Content |
|---|---|
| `title`, `purpose`, `meeting_type` | Inferred title (names untitled automatic recordings), why the meeting happened, and its type (`standup`, `client`, `project_review`, `one_on_one`, `other`) |
| `participants`, `summary`, `topics` | Names mentioned, 3–6 sentence summary, topics with key points |
| `decisions` | Only what was actually decided, with timestamp |
| `my_actions`, `others_actions` | Description, owner, ISO due date, priority (only when urgency was stated), timestamp, and **kind** |
| `deadlines`, `open_questions`, `next_meetings`, `risks` | Relative dates are resolved against the meeting date |

Each action's kind decides where it goes after the plan: `feature` or `bug` (user story), `technical` or `operation` (task card), `management` or `communication` (stays in the plan). The rules are in `prompts/analyze_system.md`.

`minutes.md` follows the structure of the `meeting-notes` skill: title, date, participants, type and purpose, summary, topics, decisions, an action table (owner, due date, priority, timestamp), risks, open questions and next steps.

Safeguards:

- Transcripts under 20 words are not sent to the model, because whisper hallucinates on silence. They get a local "transcript too short" analysis instead.
- Refusals, truncated responses and schema violations are errors. A partial analysis is never saved.
- The model is told not to invent tasks, deadlines or decisions.
- Every call logs tokens (and cost, or its equivalent) to `data/log/llm_usage.jsonl`.

### Provider: API or Claude Code

`llm.provider` in `config.toml` selects the transport. The same provider serves the analysis, the plan and the stories.

| `provider` | Uses | Billing | Notes |
|---|---|---|---|
| `api` (default when unset) | Claude API with `ANTHROPIC_API_KEY` from `.env` | Prepaid credit, about US$ 0.10 per hour of meeting | Cached system prompt, server-side fallback for occasional safety-classifier refusals |
| `claude-code` | Claude Code in headless mode (`claude -p`) | Your Claude Code subscription | Needs a logged-in session on the Mac; no refusal fallback; model alias in `llm.cli_model` |

`TREC_LLM_PROVIDER` overrides the file, for example `TREC_LLM_PROVIDER=claude-code trec analyze`. To set it for the daemon, run `trec agent install --env TREC_LLM_PROVIDER=claude-code`.

## Daily plan

```bash
trec plan                      # today → data/plans/YYYY-MM-DD.md
trec plan --date 2026-10-06    # rebuilds a given day
trec plan --purge              # same, then deletes old audio (retention)
```

The work is split between code and model:

- **Code** computes the new actions (your actions from the day's analyses that are not yet in the open list) and the overdue ones (due date before the plan day).
- **The model** writes the Markdown and the priorities, and points out which open actions the analyses show as done. It may only cite existing action ids.

The plan has the sections **Prioridades**, **Ações novas**, **Vencidas**, **Aguardando terceiros**, **Agenda** and **Conflitos e alertas**. The running list lives in `data/plans/open_actions.json`. A day with no meetings and no open actions gets a minimal plan with no model call.

`trec agent install` schedules the planner (`local.teams-recorder.planner`) to run `trec plan --purge` at `planner.hour` (default 18), Monday to Friday.

## User stories and the Backlog.md board

### Drafting

```bash
trec stories                    # drafts from today's plan → data/plans/YYYY-MM-DD.stories.md
trec stories --date 2026-10-09  # redrafts a given day (the plan must exist)
```

With `[stories] enabled = true`, `trec plan` (and so the 6 pm planner) drafts stories right after the plan.

- `feature` and `bug` actions, plus actions with no kind (extracted before 2026-10-10), go to the model. It groups related actions and writes the stories by the rules of your guide (`[stories] guide`, default `prompts/user_story_guide.md`). Edit that file to change how stories are written; it is re-read on every call.
- `technical` and `operation` actions become task cards with no model call.
- `management` and `communication` actions stay only in the daily plan.
- The model also sees the stories of the previous `dedup_days` days (default 30). A topic raised again is left out as a duplicate instead of becoming a second story.
- The code keeps traceability: a story may only cite action ids it received, and every action left out is listed with a reason.
- A day whose stories were already published is never drafted again.

### Publishing

```bash
trec publish                               # today's drafts → the boards in [stories] destinations
trec publish --date 2026-10-09 --only 1,3  # a given day, only stories 1 and 3
backlog board                              # view the board in the terminal (or `backlog browser`)
```

Each story becomes a task in the **Triagem** column, with its acceptance criteria, priority, labels and where it came from. Move a task to To Do to approve it, or archive it to reject it. teams-recorder never edits a task after creating it. Publishing again never duplicates a task: each publication is saved in `plans/<day>.stories.json` as soon as it succeeds. With `[stories] publish = true`, stories are published right after drafting.

The board lives in `./backlog`, which is **git-ignored**, because stories carry meeting content and this repository is public. Publishing is refused when Git would version the board (or cannot confirm it is ignored), or when Backlog.md is configured to commit or reach remotes.

One-time setup:

```bash
brew install backlog-md                 # or: npm i -g backlog.md
```

```bash
backlog init "teams-recorder" --no-git --defaults --integration-mode none --auto-open-browser false
```

Then add `"Triagem"` to `statuses` in `backlog/config.yml` (for example, `statuses: ["Triagem", "To Do", "In Progress", "Done"]`) and check that `trec doctor` reports `story destination backlog-md: ready`. `--no-git` keeps Backlog.md from committing, and `--integration-mode none` keeps it from editing `AGENTS.md` and `CLAUDE.md`.

## Configuration

### `config.toml`

All settings live in `config.toml` at the project root. It holds no secrets, and every key is commented in the file. **After changing it, run `trec agent restart`** so the daemon picks the change up.

| Section | Key | Default | Meaning |
|---|---|---|---|
| `[paths]` | `data_dir` | `"data"` | Where recordings, plans, models and logs live. Relative paths resolve against the project. Empty means `./data`, or `~/Library/Application Support/teams-recorder` when the project sits in a protected or iCloud folder |
| `[audio]` | `mic_device` | `"default"` | `default` follows the system input; or an exact device name |
| | `mic_backend` | `"coreaudio"` | `coreaudio` (`teams-tap --mic`) or `ffmpeg` (macOS only) |
| | `teams_process_name` / `_windows` | `"MSTeams"` / `"ms-teams.exe"` | Process the detector and the capture watch |
| | `bitrate_kbps` | `64` | AAC bitrate of `audio.m4a` |
| | `bit_depth` | `16` | Raw WAV tracks: `16` or `32` (float) |
| `[detector]` | `poll_seconds` | `1` | Detector interval |
| | `start_after_positive_polls` | `1` | Readings needed to start recording |
| | `stop_after_negative_polls` | `5` | Readings without a call needed to stop |
| `[transcription]` | `whisper_model` | `"large-v3-turbo-q5_0"` | ggml model name |
| | `language` | `"pt"` | Transcription language |
| | `models_dir` | `""` | Empty means `<data_dir>/models` |
| | `threads` | `0` | `0` means automatic |
| | `vad`, `vad_model` | `false`, `"silero-v5.1.2"` | Voice activity detection |
| `[llm]` | `provider` | `"api"` | `api` or `claude-code` |
| | `model` | `"claude-opus-5-5"` | Model for the `api` provider |
| | `cli_model` | `"opus"` | Model alias for `claude-code` |
| | `effort` | `"high"` | Reasoning effort (`low` … `max`) |
| | `max_tokens` | `16000` | Output cap (API) |
| `[user]` | `name` | `""` | Your name as said in meetings, sent to the model |
| `[confirmation]` | `enabled`, `timeout_seconds` | `true`, `30` | Keep-or-discard dialog |
| `[planner]` | `hour` | `18` | When the planner runs, Monday to Friday |
| | `retention_days` | `30` | Audio of transcribed meetings older than this is purged |
| `[stories]` | `enabled` | — | Draft stories after each plan |
| | `guide` | `"prompts/user_story_guide.md"` | Your story-writing rules; drafting fails if it is missing or empty |
| | `destinations` | — | Boards to publish to; `["backlog-md"]` or empty for drafts only |
| | `publish` | — | Publish right after drafting |
| | `dedup_days` | `30` | Days of earlier stories shown to the model |
| `[stories.backlog_md]` | `project_dir`, `status`, `labels` | `"."`, `"Triagem"`, `["teams-recorder"]` | Backlog.md project, intake column and labels |

### Environment variables

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | API key for the `api` provider. Lives in `.env` (git-ignored, permission 600); copy `.env.example` to create it |
| `TREC_LLM_PROVIDER` | Overrides `llm.provider` (`api` \| `claude-code`) |
| `TEAMS_RECORDER_DIR` | Overrides the project folder (used in tests) |
| `TREC_TEAMS_PROCESS` | Overrides the watched process name (`tests/fixtures/fake_call.py` simulates a call as `python3.11`) |
| `TREC_REAL_WHISPER`, `TREC_REAL_CLAUDE`, `TREC_REAL_CLAUDE_CLI`, `TREC_REAL_BACKLOG` | Enable the slow integration tests against the real tools |

### Prompts

| File | Used by |
|---|---|
| `prompts/analyze_system.md` | Meeting analysis, including the rules for action kinds |
| `prompts/plan_system.md` | Daily plan |
| `prompts/stories_system.md` | Story drafting (your guide is appended to it) |
| `prompts/user_story_guide.md` | Your story-writing rules; edit freely |

The prompts are written in English and ask the model for Brazilian Portuguese output.

## Data, privacy and retention

### What leaves your machine

- **Audio and transcription never leave the Mac.** whisper.cpp runs locally.
- **Only the transcript text and the prompt** are sent to Claude, through the API or your local Claude Code. The plan and story steps send the analyses, not the audio.
- Stories go to a local Backlog.md board with no network access, and they are never versioned.
- Telling participants you are recording, and following company policy and LGPD (Brazil's data protection law), are your responsibility. Native Teams recording may be disabled in corporate tenants; this tool does not change that policy.

### Data layout

```
data/                                   # paths.data_dir (git-ignored)
├── current_recording.json              # pointer to the active recording (at most one)
├── recordings/<YYYY-MM-DD_HH-MM-SS>/   # one folder per meeting
│   ├── meta.json                       # id, start, end, PID, title
│   ├── tap.wav, mic.wav                # raw tracks, only until mixed
│   ├── audio.m4a                       # mono AAC 48 kHz mix
│   ├── transcript.json, transcript.txt
│   ├── analysis.json, minutes.md
│   ├── error.txt                       # "step: message" after a failure
│   └── debug/                          # raw copies kept on a track anomaly
├── plans/
│   ├── YYYY-MM-DD.md / .json           # daily plan
│   ├── YYYY-MM-DD.stories.md / .json   # story drafts and where they were published
│   └── open_actions.json               # running list of open actions
├── models/                             # ggml-*.bin
└── log/
    ├── teams-recorder.log              # daemon (daily rotation, 30 days)
    ├── daemon.out.log, daemon.err.log
    ├── capture.log                     # recorders' stderr, padded gaps
    └── llm_usage.jsonl                 # one line per model call
```

A meeting's state comes from its files, checked from top to bottom:

| State | Condition | Next step |
|---|---|---|
| `failed` | `error.txt` exists | Fix the cause and re-run the step |
| `analyzed` | `analysis.json` exists | None (included in the daily plan) |
| `transcribed` | `transcript.json` exists | `trec analyze` |
| `recorded` | `audio.m4a` exists | `trec transcribe` |
| `recording` | only `meta.json` (and raw tracks) | `trec stop` |

All JSON files are written atomically (temporary file, then rename). A `.lock` file stops two processes from working on the same meeting at once.

### Retention

`trec purge`, and the planner through `trec plan --purge`, deletes `audio.m4a` from meetings older than `planner.retention_days` (30) that already have a transcript. Transcripts, analyses, minutes and plans are kept.

## Architecture

The Python code follows a hexagonal (ports and adapters) layout with a strict import direction: `domain ← application ← adapters/container`.

```
src/teams_recorder/
├── domain/              # pure Python, no I/O: Meeting, Transcript, Analysis, Action, DailyPlan,
│                        # MeetingStatus and derive_status() (state = files)
├── application/
│   ├── ports.py         # typing.Protocol interfaces for every external capability
│   ├── use_cases/       # recording, processing, planning (daily plan, stories, purge)
│   └── pipeline.py      # derives the next step from files; stops at the first failure
├── adapters/
│   ├── inbound/         # cli.py (Typer app `trec`), daemon.py (detector loop with hysteresis)
│   └── outbound/        # one file per port implementation
├── container.py         # composition root: the only place concrete adapters are built
├── config.py            # config.toml + .env → frozen Settings, env overrides
├── messages.py          # every user-facing string (CLI, notifications, errors, logs)
└── constants.py         # enums, env var names, binaries, file names, defaults
native/
├── teams-tap/           # Swift package: Core Audio process tap + microphone recorder
└── teams-tap-win/       # C# (.NET 8): WASAPI counterpart with the same CLI
prompts/                 # system prompts and the story guide
scripts/                 # installers, native builds, model download
tests/                   # unit/, integration/, fakes/, fixtures/
```

### Ports and adapters

| Port | macOS adapter | Windows adapter |
|---|---|---|
| `MeetingRepository` | `repository_fs` (folder per meeting, atomic writes, `.lock`) | same |
| `ProcessAudioCapture` | `capture_coreaudio` → `teams-tap --pid` | `capture_wasapi` → `teams-tap.exe --pid --stop-file` |
| `MicCapture` | `capture_mic_coreaudio` (default) or `capture_mic_ffmpeg` | `capture_wasapi.WasapiMicCapture` |
| `AudioMixer` | `mixer_ffmpeg` | same |
| `Transcriber` | `transcriber_whispercpp` | same |
| `MeetingAnalyzer`, `Planner`, `StoryWriter` | `llm_claude`, `planner_claude`, `stories_claude` over one shared transport (`llm_transport.ApiTransport` or `ClaudeCodeTransport`) | same |
| `MinutesRenderer`, `StoryRenderer` | `minutes_markdown`, `stories_markdown` | same |
| `StoryPublisher` | `publisher_backlogmd` | same |
| `CallDetector` | `detector_pmset` | `detector_windows` |
| `Notifier` | `notifier_macos` (osascript) | `notifier_windows` (PowerShell toast) |
| `RecordingConfirmation` | `confirm_macos` (osascript dialog) | `confirm_windows` (`MessageBoxTimeoutW`) |
| `DiskSpace`, `Clock` | `disk_space`, `clock` | same |
| Scheduler (not a port) | `launchd.LaunchAgent` | `scheduler_windows.ScheduledTask` |

`Settings.platform` (from `sys.platform`) decides which set `container.py` builds. Every port has an in-memory fake in `tests/fakes/`, so use cases are tested without real I/O.

### Design decisions worth knowing

- **State is files.** There is no database. `Pipeline.process()` looks at which files exist, runs the next step, and writes `error.txt` on failure. Re-running a command resumes from where it stopped.
- **Recording is cross-process.** `CaptureHandle` is a plain dataclass (PID and path) stored in `current_recording.json`, so `trec stop` in one terminal can stop recorders started by the daemon or by another `trec start`.
- **No hardcoded strings.** User-facing text lives in `messages.py`, and identifiers in `constants.py`. `tests/unit/test_no_hardcoded_strings.py` enforces this.
- **Lazy SDK import.** The `anthropic` SDK is imported only inside the analyzer; at module level it made cold starts very slow.
- **Fail closed when publishing.** The Backlog.md adapter checks the binary, the board, the column, the Git ignore status and the absence of auto-commit before every publish.

The full requirements, interview decisions, risks and per-phase design notes are in [`docs/REQUIREMENTS-AND-ARCHITECTURE.md`](docs/REQUIREMENTS-AND-ARCHITECTURE.md).

## Development

### Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
scripts/build-native.sh        # needed only for capture tests and real recordings
trec --help
```

### Tests and type checks

```bash
pytest                                                   # fast suite, no coverage (~10 s warm)
pytest tests/unit/test_daemon.py -k hysteresis           # a single test
pytest --cov=teams_recorder --cov-report=term-missing    # coverage, opt-in (target 70%)
mypy                                                     # keep it clean
```

Slow tests against the real tools are opt-in:

```bash
TREC_REAL_WHISPER=1 pytest -m slow tests/integration/test_transcriber_whispercpp.py   # loads the model
TREC_REAL_CLAUDE=1 pytest -m slow tests/integration/test_llm_claude_real.py           # spends API credit
TREC_REAL_CLAUDE_CLI=1 pytest -m slow tests/integration/test_llm_claude_cli_real.py   # Claude Code headless
TREC_REAL_BACKLOG=1 pytest -m slow tests/integration/test_publisher_backlogmd_real.py # throwaway board
```

Test layout:

```
tests/
├── unit/          # use cases on fakes, adapters with scripted stand-ins, config, string policy
├── integration/   # subprocess adapters and opt-in real-tool tests
├── fakes/         # in-memory fake for every port
└── fixtures/      # fake_recorder.py, fake_whisper_cli.py, fake_claude_cli.py, fake_backlog_cli.py,
                   # fake_call.py, sample transcripts and analyses
```

Do not run two pytest sessions at once: subprocess-based tests time out under contention. Coverage is opt-in because on a machine with little free memory, macOS has killed test subprocesses.

### Simulating a call without Teams

```bash
TREC_TEAMS_PROCESS=python3.11 trec daemon --once   # while tests/fixtures/fake_call.py runs
```

### Adding an adapter

1. Declare the port as a `typing.Protocol` in `application/ports.py`, if it is new.
2. Implement it in `adapters/outbound/<capability>_<tech>.py`, translating every external failure into a domain error with a message that tells the user what to do.
3. Add a fake in `tests/fakes/` and tests (with a scripted stand-in in `tests/fixtures/` if it spawns processes).
4. Register it in `container.py`. If it is selectable, add the switch to `config.toml` and `config.Settings`, with a test.
5. Surface it in `trec doctor` if it depends on an external binary, and update `docs/` and `prd/`.

### Conventions

- Everything in the repository is in English. The only Portuguese is user-facing content built from LLM output (minutes labels, story labels, plan section names) and test fixtures.
- Commits are grouped per layer in dependency order (`docs`, `feat(domain)`, `feat(application)`, `feat(adapters)`, `feat(native)`, `feat(cli)`, `test`); see [`docs/COMMITS.md`](docs/COMMITS.md).
- **After changing Python code, run `trec agent restart`**, or the running daemon keeps the old code. The Swift binary is spawned again for each recording, so rebuilding it is enough.
- Coding agents: see [`AGENTS.md`](AGENTS.md).

## Troubleshooting

**The Teams track is silent; only my voice is recorded.**
`teams-tap` lacks **Screen & System Audio Recording** permission. Grant it under System Settings > Privacy & Security, then record again. Running `teams-tap --list` during a call shows whether the Teams processes are audio clients.

**The daemon does not start recording.**
Run `trec daemon --once` during a call. If Teams is not seen, check `audio.teams_process_name` (new Teams is `MSTeams`) and look at `pmset -g assertions` for the Teams process. Make sure the service runs with `trec agent status`, and read `data/log/teams-recorder.log`.

**`[Errno 11] Resource deadlock avoided` in the logs.**
The project or its data is in `~/Documents`, `~/Desktop`, `~/Downloads` or iCloud, where macOS blocks background processes. Move the project (for example to `~/Projetos/teams-recorder`) and run `scripts/install.sh` again.

**A meeting is stuck in `failed`.**
Read `data/recordings/<id>/error.txt`, fix the cause and re-run the step (`trec transcribe <id>` or `trec analyze <id>`). Re-running clears the error.

**Transcription fails with "model not found" or "whisper-cli not found".**
Run `scripts/download-model.sh` or `brew install whisper-cpp`. `trec doctor` lists what is missing.

**Analysis fails with an authentication error.**
With `api`, check that `.env` has `ANTHROPIC_API_KEY` and permission 600. With `claude-code`, run `claude` once in a terminal and log in. The daemon needs a logged-in session too.

**The keep-or-discard dialog never shows up.**
If Teams is in full screen, the dialog may be on another desktop. When the dialog cannot be shown, the recording is kept. To turn the question off, set `[confirmation] enabled = false`.

**`trec publish` refuses to publish.**
`trec doctor` lists the board's problems: missing `backlog` binary, an uninitialized project, no `Triagem` status, a board Git does not ignore, or a configuration that auto-commits or reaches remotes.

**I changed `config.toml` or the code and nothing changed.**
Run `trec agent restart`.

**The first `pytest` after big edits hangs for minutes.**
Endpoint security scanning on the first open of new files (`.pyc` included) can stall a cold run. It then completes in about 10 s.

## Project status

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Domain, ports, use cases, file repository, `trec status` / `doctor` | Done |
| 2 | Teams and microphone capture, mixing, `trec start` / `stop` / `cancel` | Done |
| 3 | Local transcription with whisper.cpp | Done |
| 4 | Analysis with Claude and meeting minutes | Done |
| 5 | Call detector, daemon, LaunchAgent | Done, validated with real calls |
| 6 | Daily plan at 6 pm and audio retention | Done |
| 7 | Installer and uninstaller | Done |
| — | User story drafts and Backlog.md publishing | Done; publishing is manual (`publish = false`) until story quality is approved |
| — | Windows port | Implemented and unit-tested; not yet run on Windows |

Not done yet: the month's LLM spend in `trec status`, GitHub Projects and Azure Boards destinations, reading approvals back from the board, and speaker identification (diarization). Calendar integration was dropped.

## Further documentation

| Document | Content |
|---|---|
| [`prd/README.md`](prd/README.md) | Product requirements: modules, flows, global rules, with one page per flow and appendices (states, integrations, data layout) |
| [`docs/REQUIREMENTS-AND-ARCHITECTURE.md`](docs/REQUIREMENTS-AND-ARCHITECTURE.md) | Requirements, architecture, risks and per-phase implementation notes |
| [`tasks/prd-story-publishing/`](tasks/prd-story-publishing/) | PRD, tech spec and tasks for story publishing |
| [`docs/COMMITS.md`](docs/COMMITS.md) | Commit conventions |
| [`AGENTS.md`](AGENTS.md) | Guidance for coding agents |
| [`native/teams-tap-win/README.md`](native/teams-tap-win/README.md) | The Windows capture binary |

## License

MIT, as declared in `pyproject.toml`.
