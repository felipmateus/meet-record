# teams-recorder — Product Requirements Document (PRD)

> Generated from the code on 2026-10-05 (phase 5 commit + noise handling). Written in product language; technical details only where they affect behavior. Items marked `[TBC]` could not be confirmed from the code.

## 1. System overview

teams-recorder is a personal macOS (and, untested so far, Windows) utility that automatically records a single user's Microsoft Teams meetings, transcribes the audio locally in Portuguese, extracts a structured record from the transcript (summary, decisions, actions, deadlines, open questions) using a language model and, in the next phase, consolidates the day's meetings into an activity plan.

It runs in the background with no graphical interface: a daemon watches Teams and starts recording when a call begins; when the call ends, it processes everything on its own and reports through macOS notifications. A command line (`trec`) lets the user operate and inspect each step manually. Audio and transcripts never leave the Mac; only the transcript text is sent to the language model, through the API or through the locally installed Claude Code.

**User**: one person, owner of the Mac and of the Teams account, who attends several meetings a day and wants a reliable record of commitments without taking notes. **Context**: corporate environment; native Teams recording may be disabled; consent and internal policy are the user's responsibility (see §6).

## 2. Modules

| Module | Flows | Core function | Status |
|---|---|---|---|
| Recording | start, stop, cancel | Capture Teams and microphone audio on separate tracks and mix them into an M4A | Delivered (phase 2) |
| Transcription | transcribe | Convert the audio into timestamped text, locally | Delivered (phase 3) |
| Analysis | analyze | Extract summary, decisions, actions, deadlines and questions from the transcript | Delivered (phase 4) |
| Automation | daemon, agent | Detect Teams calls and chain recording → transcription → analysis with no intervention | Delivered (phase 5) |
| Operations | status, doctor, purge, version | Inspect state, check dependencies, apply retention | Delivered (phases 1 to 5) |
| Planning | plan, scheduler | Consolidate the day's analyses into a Markdown plan and keep open actions up to date | Delivered (phase 6) |
| Installation | install.sh, uninstall.sh | Install from scratch on another Mac/user | Delivered (phase 7) |
| Windows | install.ps1, Windows adapters | Same flows on Windows 10 2004+/11 | Implemented, not yet run on Windows |

## 3. Flow inventory

| # | Flow | Command | Module | Doc |
|---|---|---|---|---|
| 1 | Manual recording | `trec start` / `trec stop` / `trec cancel` | Recording | [→](./pages/01-manual-recording.md) |
| 2 | Transcription | `trec transcribe [id]` | Transcription | [→](./pages/02-transcription.md) |
| 3 | Analysis | `trec analyze [id]` | Analysis | [→](./pages/03-analysis.md) |
| 4 | Automatic recording | `trec daemon`, `trec agent …` | Automation | [→](./pages/04-automation.md) |
| 5 | Operations and diagnostics | `trec status` / `doctor` / `purge` / `version` | Operations | [→](./pages/05-operations.md) |
| 6 | Daily plan | `trec plan` | Planning | [→](./pages/06-daily-plan.md) |
| 7 | Installation | `scripts/install.sh` / `install.command` / `scripts/uninstall.sh` | Installation | [→](./pages/07-installation.md) |

Appendices: [state and enumeration dictionary](./appendix/enum-dictionary.md) · [external integrations](./appendix/integrations.md) · [data layout and schemas](./appendix/data-layout.md) · [relationships between flows](./appendix/relationships.md).

## 4. Global notes

### State model: "the state is the file"
There is no database. Each meeting is a folder at `<data_dir>/recordings/<id>/` (see the data layout for where `<data_dir>` lives), and the meeting's state is derived from which files exist in it (see the dictionary). Any step can be repeated from the existing files; failures are recorded in `error.txt` inside the meeting folder and do not affect other meetings.

### Meeting identity
The id is the start instant in the format `YYYY-MM-DD_HH-MM-SS`. There is no automatic title; the `title` field is only filled when provided manually through `trec start --title`. `[TBC]` Calendar integration to name meetings was dropped in the requirements interview (decision 9), but the field exists in the model.

### Configuration
`config.toml` at the project root, with no secrets; `.env` holding the API key (git-ignored, permission 600 recommended). Environment variables override specific points: `TEAMS_RECORDER_DIR` (project folder), `TREC_LLM_PROVIDER` (api | claude-code), `TREC_TEAMS_PROCESS` (name of the watched process; used in tests).

### macOS permissions
Two permissions are required and requested on the first recording: **Microphone** and **Screen & System Audio Recording**. Without the second, the Teams track comes out silent and the mix proceeds with the microphone only.

### Interaction patterns
- Processing commands (`transcribe`, `analyze`) with no argument act on **all** meetings pending that step and keep going even when one fails; they exit with code 1 if any failed.
- Every error line starts with `error: `; commands from future phases exist in the help and report which phase they arrive in (exit code 2).
- macOS notifications: "Recording started", "Recording stopped", "Recording cancelled", "Transcription failed" / "Analysis failed", "Daily plan ready".

### Language
Analysis and plan content (summaries, actions, the daily Markdown plan) is produced in Brazilian Portuguese because the meetings are in Portuguese; CLI messages and notifications are also in Portuguese, and this document quotes them verbatim with an English gloss.

### Cost and privacy
- Transcription is 100 % local (whisper.cpp). Model `large-v3-turbo-q5_0`, 574 MB.
- Analysis: Claude Opus 5.5 through the API (prepaid, ~US$ 0.10 per hour of meeting) or headless Claude Code (subscription). Each call logs tokens and cost to `data/log/llm_usage.jsonl`.
- Transcripts with fewer than 20 words are not sent to the model.
- Audio is deleted after 30 days (configurable) once transcribed; transcript and analysis remain.

## 5. Roadmap

| Phase | Deliverable | Status |
|---|---|---|
| 1–5 | Recording, transcription, analysis, automation, operations | Delivered and validated with real Teams calls on 2026-10-05 |
| 6 | Daily planner (`trec plan`), scheduling at 6 pm, open-action updates | Delivered 2026-10-05; validation with a real meeting pending |
| 7 | `install.sh`, `trec status` with the month's spend, installation README | Pending |

## 6. Out of scope and user responsibilities
- Speaker identification (diarization): not implemented; the model infers speakers from context.
- Notifying participants and complying with company policy and LGPD (Brazil's data protection law): the user's responsibility. The project offers a sensitive-term filter only as a future improvement (risk R5 in `docs/REQUIREMENTS-AND-ARCHITECTURE.md`).
- Integration with Microsoft To Do, Obsidian or the calendar: deferred until after phase 7.
