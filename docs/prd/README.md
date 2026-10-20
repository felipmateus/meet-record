# teams-recorder — Product Requirements Document (PRD)

> Generated from the code on 2026-10-05 (phase 5 commit + noise handling). Written in product language; technical details only where they affect behavior. Items marked `[TBC]` could not be confirmed from the code.

## 1. System overview

teams-recorder is a personal macOS (and, untested so far, Windows) utility that automatically records a single user's Microsoft Teams meetings, transcribes the audio locally in Portuguese, extracts a structured record from the transcript (summary, decisions, actions, deadlines, open questions) using a language model and keeps one activities document that an agent updates after each meeting (it replaced a daily activity plan on 2026-10-20). User stories for a backlog are drafted on demand from the items the user tags in that document.

It runs in the background with no graphical interface: a daemon watches Teams and starts recording when a call begins; when the call ends, it processes everything on its own and reports through macOS notifications. A command line (`trec`) lets the user operate and inspect each step manually. Audio and transcripts never leave the Mac; only the transcript text is sent to the language model, through the API or through the locally installed Claude Code.

**User**: one person, owner of the Mac and of the Teams account, who attends several meetings a day and wants a reliable record of commitments without taking notes. **Context**: corporate environment; native Teams recording may be disabled; consent and internal policy are the user's responsibility (see §6).

## 2. Modules

| Module | Flows | Core function | Status |
|---|---|---|---|
| Recording | start, stop, cancel | Capture Teams and microphone audio on separate tracks and mix them into an M4A | Delivered (phase 2) |
| Transcription | transcribe | Convert the audio into timestamped text, locally | Delivered (phase 3) |
| Analysis | analyze | Extract summary, decisions, actions, deadlines and questions from the transcript | Delivered (phase 4) |
| Automation | daemon, agent | Detect Teams calls and chain recording → transcription → analysis with no intervention | Delivered (phase 5) |
| Speaker labels | (inside recording and transcription) | Read who is speaking from the Teams window and label each transcript line with the person's name; the user's own lines from the two tracks | Delivered on macOS (2026-10-17); gates on real meetings pending |
| Operations | status, doctor, purge, version | Inspect state, check dependencies, apply retention (the daemon also applies it once a day) | Delivered (phases 1 to 5) |
| Planning (retired) | — | Consolidated the day's analyses into a Markdown plan at 6 pm and kept open actions up to date | Delivered in phase 6, removed on 2026-10-20 and replaced by the Activities module |
| Activities | activities, activities curate, activities undo | A curator agent updates one document (`data/activities/atividades.md`) after each analyzed meeting: the user's open actions, what they wait on, dates, recent context; the user's edits and ticks are respected, nothing is deleted | Delivered (`docs/tasks/activities-curator/`); replaced the daily plan on 2026-10-20; the quality evaluations on real data were not run |
| User stories | stories, publish | Draft a user story for each item of the activities document the user tags `#história`, following the user's guide, and publish them to a board for review | Delivered: drafts from tagged items and the Backlog.md board; publishing by hand until the user approves the stories, then automatic (GitHub and Azure later) |
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
| 6 | Daily plan (removed 2026-10-20) | — (`trec plan` no longer exists) | Planning (retired) | [→](./pages/06-daily-plan.md) |
| 7 | Installation | `scripts/install.sh` / `install.command` / `scripts/uninstall.sh` | Installation | [→](./pages/07-installation.md) |
| 8 | User story drafts and publishing | `trec stories`, `trec publish` | User stories | [→](./pages/08-user-stories.md) |
| 9 | Activities document | `trec activities [--open]`, `trec activities curate`, `trec activities undo` (automatic after each analysis) | Activities | [→](./pages/09-activities.md) |

Appendices: [state and enumeration dictionary](./appendix/enum-dictionary.md) · [external integrations](./appendix/integrations.md) · [data layout and schemas](./appendix/data-layout.md) · [relationships between flows](./appendix/relationships.md).

## 4. Global notes

### State model: "the state is the file"
There is no database. Each meeting is a folder at `<data_dir>/recordings/<id>/` (see the data layout for where `<data_dir>` lives), and the meeting's state is derived from which files exist in it (see the dictionary). Any step can be repeated from the existing files; failures are recorded in `error.txt` inside the meeting folder and do not affect other meetings.

### Meeting identity
The id is the start instant in the format `YYYY-MM-DD_HH-MM-SS`. The `title` field is filled through `trec start --title`, or, for a recording with none, with the meeting subject the speaker observer read from the Teams window when the recording stops. `[TBC]` Calendar integration to name meetings was dropped in the requirements interview (decision 9), but the field exists in the model.

### Configuration
`config.toml` at the project root, with no secrets; `.env` holding the API key (git-ignored, permission 600 recommended). Environment variables override specific points: `TEAMS_RECORDER_DIR` (project folder), `TREC_LLM_PROVIDER` (api | claude-code), `TREC_TEAMS_PROCESS` (name of the watched process; used in tests).

### macOS permissions
Two permissions are required and requested on the first recording: **Microphone** and **Screen & System Audio Recording**. Without the second, the Teams track comes out silent and the mix proceeds with the microphone only. A third, **Accessibility**, is optional: it lets `teams-speakers` read the Teams window for speaker labels. macOS does not ask for it on its own (a background job's request creates no entry): the user adds `native/teams-speakers/.build/release/teams-speakers` to the list with the **+** button, and `trec doctor` checks it. Without it recordings are unchanged and only the user's own lines are labelled.

### Interaction patterns
- Processing commands (`transcribe`, `analyze`) with no argument act on **all** meetings pending that step and keep going even when one fails; they exit with code 1 if any failed.
- Every error line starts with `error: `; commands from future phases exist in the help and report which phase they arrive in (exit code 2).
- macOS notifications: "Recording started", "Recording stopped", "Recording cancelled", "Transcription failed" / "Analysis failed", "Activities updated" / "Activity curation failed", "User story drafts failed", "User stories published" / "Publishing user stories failed".

### Language
Analysis and activities-document content (summaries, actions, progress statements, the activities document, the story drafts) is produced in Brazilian Portuguese because the meetings are in Portuguese; CLI messages and notifications are also in Portuguese, and this document quotes them verbatim with an English gloss.

### Cost and privacy
- Transcription is 100 % local (whisper.cpp). Model `large-v3-turbo-q5_0`, 574 MB.
- Analysis: Claude Opus 5.5 through the API (prepaid, ~US$ 0.10 per hour of meeting) or headless Claude Code (subscription). Each call logs tokens and cost to `data/log/llm_usage.jsonl`. The activities curator makes one more call per pass (up to four meetings), at medium effort, on the same provider, and `trec stories` makes one call per run that has new tagged items.
- Transcripts with fewer than 20 words are not sent to the model.
- Audio is deleted after 30 days (`[audio] retention_days`) once transcribed, by the daemon once a day; transcript and analysis remain.

## 5. Roadmap

| Phase | Deliverable | Status |
|---|---|---|
| 1–5 | Recording, transcription, analysis, automation, operations | Delivered and validated with real Teams calls on 2026-10-05 |
| 6 | Daily planner (`trec plan`), scheduling at 6 pm, open-action updates | Delivered 2026-10-05; removed 2026-10-20 (replaced by the activities document) |
| — | Activities document, slice 1: progress statements in the analysis and minutes, the curator, `trec activities`, doctor and status lines | Implemented 2026-10-20 (`docs/tasks/activities-curator/`) |
| — | Activities document, slice 2: planner removed, stories drafted from `#história` items, audio retention in the daemon | Implemented 2026-10-20 after the user's go; the quality evaluations on real data were not run |
| 7 | `install.sh`, `trec status` with the month's spend, installation README | Pending |
| — | Speaker labels from the Teams window (`teams-speakers`, track energy, labelling at transcription) | Implemented 2026-10-17; gates G1–G5 on real meetings pending (`docs/tasks/speaker-attribution/prd.md`) |

## 6. Out of scope and user responsibilities
- Voice identification (a voiceprint per person) and voice clustering (diarization): not implemented, and not planned: the people in the user's meetings change constantly. Speaker attribution from the Teams window **ships on macOS** (2026-10-17): the names come from the meeting window, the user's lines from the microphone track; where the window cannot be read (no permission, covered window, Windows) the lines stay unlabelled and the model infers speakers from context as before. Windows parity (UI Automation) is a separate, later task.
- Notifying participants and complying with company policy and LGPD (Brazil's data protection law): the user's responsibility. The project offers a sensitive-term filter only as a future improvement (risk R5 in `docs/REQUIREMENTS-AND-ARCHITECTURE.md`).
- Integration with Microsoft To Do, Obsidian or the calendar: deferred until after phase 7.
