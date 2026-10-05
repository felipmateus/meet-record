# teams-recorder — Requirements and Architecture

Date: 2026-10-04 · Author: Felipe Mateus de Carvalho (interview conducted with Claude)

## 1. Goal

Automatically record the audio of every Microsoft Teams meeting on the MacBook, transcribe it locally, extract actions and decisions with an LLM, and generate a daily activity plan. Everything runs in the background, with no user intervention, at near-zero cost.

## 2. Interview decisions

| # | Topic | Decision | Note |
|---|-------|----------|------|
| 1 | Project folder | `~/Documents/teams-recorder`, moved to `~/Projetos/Pessoal/teams-recorder` on 2026-10-05 | See risk R1 (iCloud) and the TCC note at the end |
| 2 | Languages | Python 3.11 + minimal Swift | Swift only in the capture binary |
| 3 | Teams capture | Core Audio Process Tap | No BlackHole, no routing changes |
| 4 | LLM | Claude API (Opus 5.5) | No local fallback in this phase |
| 5 | Code organization | Hexagonal architecture | Isolated domain, ports and adapters |
| 6 | State and communication | Files only | Status derived from which files exist |
| 7 | Configuration and secrets | `.env` file | See risks R1 and R2 |
| 8 | Tests | pytest with fixtures, 70% target | Fake adapters for LLM and audio |
| 9 | Call detection | System heuristic (pmset + microphone) | No calendar access |
| 10 | Audio retention | Delete after 30 days | Transcript and analysis are kept |
| 11 | Plan output | Local Markdown | Integrations deferred to phase 2 |
| 12 | Language | Portuguese only (pt-BR) | Whisper pinned to `pt` |

## 3. Functional requirements

| ID | Requirement |
|----|-------------|
| FR01 | Detect the start and end of a Teams call without user action, within 10 s of the real event. |
| FR02 | Capture the audio emitted by the Teams process (participants) and the microphone (user) as separate tracks. |
| FR03 | Mix the two tracks into a single M4A file (AAC, 64 kbps, mono) at the end of the call. |
| FR04 | Allow cancelling an in-progress recording via a CLI command; partial audio is discarded. |
| FR05 | Transcribe the audio in Portuguese with per-segment timestamps, producing `transcript.txt` and `transcript.json`. |
| FR06 | Send the transcript to the Claude API and receive a structured analysis: summary, decisions, the user's actions, third-party actions to follow up on, deadlines, open questions, upcoming meetings. |
| FR07 | Generate, once a day at a configurable time, a Markdown plan consolidating the day's analyses, the previous plan and the still-open actions. |
| FR08 | Maintain an accumulated list of open actions in `plans/open_actions.json`, updated with each plan. |
| FR09 | Notify via the macOS Notification Center at the start and end of a recording and when the daily plan is ready. |
| FR10 | Reprocess any stage via a CLI command from the existing files (`trec transcribe`, `trec analyze`, `trec plan`). |
| FR11 | Delete `audio.m4a` of meetings older than 30 days that already have a transcript. |
| FR12 | Show status via CLI: daemon running, last meeting, pending stages, API key validity. |
| FR13 | Log every stage with date, meeting and result. |

## 4. Non-functional requirements

| ID | Requirement |
|----|-------------|
| NFR01 | Audio and transcript never leave the Mac; only the text transcript is sent to the Claude API. |
| NFR02 | No changes to the audio output device or to the user's volume control. |
| NFR03 | The daemon uses less than 1% CPU while idle and less than 100 MB of RAM. |
| NFR04 | Transcribing a 1 h meeting takes at most 15 min on Apple Silicon (large-v3-turbo model). |
| NFR05 | A failure in one stage does not block other meetings nor delete files already produced. |
| NFR06 | Domain with no dependency on external libraries; adapters replaceable by tests. |
| NFR07 | 70% test coverage in the domain and application modules. |
| NFR08 | Compatible with macOS 14.2+ (process tap API); tested on macOS 26. |
| NFR09 | API cost below US$ 10/month for 40 one-hour meetings. |
| NFR10 | Full installation via a single script (`scripts/install.sh`). |

## 5. Hexagonal architecture

```
                     ┌──────────────────────────────────────────────┐
  inbound            │                 APPLICATION                  │        outbound
                     │  use cases + ports (Protocol)                │
 ┌───────────┐       │                                              │       ┌────────────────────┐
 │ daemon    │──────▶│  StartRecording   StopRecording              │──────▶│ CoreAudioTapCapture│ (Swift)
 │ (launchd) │       │  TranscribeMeeting AnalyzeMeeting            │──────▶│ FfmpegMicCapture   │
 └───────────┘       │  BuildDailyPlan   PurgeOldAudio              │──────▶│ FfmpegMixer        │
 ┌───────────┐       │                                              │──────▶│ WhisperCppTranscr. │
 │ CLI trec  │──────▶│           ┌──────────────────┐               │──────▶│ ClaudeAnalyzer     │
 └───────────┘       │           │      DOMAIN      │               │──────▶│ ClaudePlanner      │
 ┌───────────┐       │           │ Meeting, Action, │               │──────▶│ FsMeetingRepository│
 │ scheduler │──────▶│           │ Analysis, Plan   │               │──────▶│ MacOSNotifier      │
 │ (launchd) │       │           └──────────────────┘               │──────▶│ PmsetCallDetector  │
 └───────────┘       └──────────────────────────────────────────────┘       └────────────────────┘
```

### 5.1 Domain (`domain/`)
Pure Python, no I/O.

- `Meeting`: id (timestamp), start, end, folder path, derived status.
- `Transcript`: list of `Segment(start, end, text)`.
- `Analysis`: `summary`, `decisions[]`, `my_actions[]`, `others_actions[]`, `deadlines[]`, `open_questions[]`, `next_meetings[]`.
- `Action`: description, owner, optional deadline, origin (meeting id), status.
- `DailyPlan`: date, priorities, new actions, completed, overdue, Markdown text.
- `MeetingStatus`: enum derived from which files exist (`RECORDING`, `RECORDED`, `TRANSCRIBED`, `ANALYZED`, `FAILED`).

### 5.2 Ports (`application/ports.py`)

| Port | Methods | Implementation |
|------|---------|----------------|
| `CallDetector` | `poll() -> CallState` | `PmsetCallDetector` |
| `ProcessAudioCapture` | `start(pid, out) -> Handle`, `stop(Handle)` | `CoreAudioTapCapture` (Swift subprocess) |
| `MicCapture` | `start(device, out) -> Handle`, `stop(Handle)` | `FfmpegMicCapture` |
| `AudioMixer` | `mix(tracks, out)` | `FfmpegMixer` |
| `Transcriber` | `transcribe(audio, lang) -> Transcript` | `WhisperCppTranscriber` |
| `MeetingAnalyzer` | `analyze(transcript, ctx) -> Analysis` | `ClaudeAnalyzer` |
| `Planner` | `plan(analyses, prev, open) -> DailyPlan` | `ClaudePlanner` |
| `MeetingRepository` | `create`, `save_*`, `load_*`, `list(status)` | `FsMeetingRepository` |
| `Notifier` | `notify(title, body)` | `MacOSNotifier` |
| `Clock` | `now()` | `SystemClock` / `FakeClock` |

Every port has a fake adapter in `tests/fakes/` so tests run without hardware or network.

### 5.3 Use cases (`application/use_cases/`)

- `StartRecording`: creates the folder, writes `meta.json`, starts the tap and the microphone, notifies.
- `StopRecording`: stops the captures, mixes, writes `audio.m4a`, removes the raw tracks, notifies, enqueues transcription.
- `TranscribeMeeting`: reads `audio.m4a`, produces `transcript.txt` and `transcript.json`.
- `AnalyzeMeeting`: reads the transcript, calls the analyzer, writes `analysis.json`.
- `BuildDailyPlan`: reads the day's analyses, the previous plan and the open actions; writes `plans/AAAA-MM-DD.md` and updates `open_actions.json`.
- `PurgeOldAudio`: deletes `audio.m4a` older than 30 days when a transcript is present.
- `Pipeline`: chains Stop → Transcribe → Analyze with per-stage error handling.

### 5.4 Inbound adapters (`adapters/inbound/`)

- `daemon.py`: detection loop every 3 s; starts recording after 2 consecutive positive readings and stops after 5 negative ones (15 s), avoiding false positives from flapping.
- `cli.py` (Typer): `trec start|stop|cancel|transcribe|analyze|plan|purge|status|doctor`.
- Scheduler: launchd entry that calls `trec plan` at the configured time.

### 5.5 Outbound adapters (`adapters/outbound/`)

**`CoreAudioTapCapture`** runs the `native/teams-tap` binary (Swift) as a subprocess:
`teams-tap --pid <pid> --out tap.wav`; captures via `AudioHardwareCreateProcessTap` + aggregate device, 48 kHz, shuts down cleanly on SIGTERM.

**`FfmpegMicCapture`**: `ffmpeg -f avfoundation -i ":<idx>" mic.wav`, configurable device.

**`FfmpegMixer`**: `amix` of the two tracks, light normalization, AAC 64 kbps mono output.

**`WhisperCppTranscriber`**: `whisper-cli -m ggml-large-v3-turbo.bin -l pt -oj -otxt`; parses the JSON into a `Transcript`.

**`ClaudeAnalyzer` / `ClaudePlanner`** (`anthropic` SDK 1.x):
- model `claude-opus-5-5`; adaptive thinking (model default); configurable `output_config.effort`, default `high` for analysis;
- structured output via `client.messages.parse(..., output_format=<Pydantic>)`; the Pydantic schema lives in the adapter and is converted to the domain;
- streaming for long transcripts, `max_tokens` 16000;
- `cache_control` on the system prompt (fixed, in `prompts/*.md`);
- server-side fallback enabled (`betas=["server-side-fallback-2026-07-01"]`, `fallbacks="default"`) for occasional classifier refusals;
- handling of `stop_reason == "refusal"` and of the exception chain `RateLimitError → APIStatusError → APIConnectionError`, with its own retry on top of the SDK's.

**`FsMeetingRepository`**: layout below; atomic writes (temporary file + rename); `.lock` while a stage is running.

**`MacOSNotifier`**: `osascript -e 'display notification ...'`.

**`PmsetCallDetector`**: parses `pmset -g assertions` looking for assertions held by the Teams process; optional secondary signal from microphone usage, to be validated during implementation.

### 5.6 Composition root (`container.py`)
The only place that instantiates concrete adapters from `config.py`. Tests swap in fakes here.

## 6. Data file layout (state = files)

```
~/Projetos/Pessoal/teams-recorder/data/
├── recordings/
│   └── 2026-10-06_14-00-12/
│       ├── meta.json          # start, end, pid, pipeline version
│       ├── tap.wav            # temporary, deleted after mixing
│       ├── mic.wav            # temporary, deleted after mixing
│       ├── audio.m4a          # deleted after 30 days
│       ├── transcript.txt
│       ├── transcript.json
│       ├── analysis.json
│       ├── .lock              # present only while processing
│       └── error.txt          # present only if some stage failed
├── plans/
│   ├── 2026-10-06.md
│   └── open_actions.json
└── log/
    └── teams-recorder.log     # daily rotation, 30 days
```

A meeting's status is derived: `audio.m4a` without `transcript.json` → pending transcription, and so on. `trec status` and the `Pipeline` use this rule to resume whatever is missing.

## 7. Code layout

```
teams-recorder/
├── pyproject.toml              # teams_recorder package, trec CLI, deps: anthropic, pydantic, typer, python-dotenv
├── .env.example                # ANTHROPIC_API_KEY=
├── .gitignore                  # .env, data/, native/.build
├── config.toml                 # mic device, plan time, whisper model, retention, effort
├── README.md
├── docs/
│   └── REQUIREMENTS-AND-ARCHITECTURE.md
├── prompts/
│   ├── analyze_system.md
│   └── plan_system.md
├── native/teams-tap/           # Swift Package
│   ├── Package.swift
│   └── Sources/teams-tap/main.swift
├── src/teams_recorder/
│   ├── domain/
│   │   ├── models.py
│   │   ├── status.py
│   │   └── errors.py
│   ├── application/
│   │   ├── ports.py
│   │   ├── pipeline.py
│   │   └── use_cases/
│   │       ├── start_recording.py
│   │       ├── stop_recording.py
│   │       ├── transcribe_meeting.py
│   │       ├── analyze_meeting.py
│   │       ├── build_daily_plan.py
│   │       └── purge_old_audio.py
│   ├── adapters/
│   │   ├── inbound/
│   │   │   ├── cli.py
│   │   │   └── daemon.py
│   │   └── outbound/
│   │       ├── detector_pmset.py
│   │       ├── capture_coreaudio.py
│   │       ├── capture_mic_ffmpeg.py
│   │       ├── mixer_ffmpeg.py
│   │       ├── transcriber_whispercpp.py
│   │       ├── llm_claude.py
│   │       ├── repository_fs.py
│   │       ├── notifier_macos.py
│   │       └── clock.py
│   ├── config.py
│   └── container.py
├── tests/
│   ├── fakes/                  # one fake per port
│   ├── fixtures/               # short pt-BR audio, sample transcript, sample analysis
│   ├── unit/                   # domain and use cases
│   └── integration/            # real whisper (marked slow), repository in tmp_path
├── launchd/
│   ├── com.felipe.teams-recorder.plist   # daemon at login, KeepAlive
│   └── com.felipe.teams-planner.plist    # StartCalendarInterval 18:00, Mon–Fri
└── scripts/
    ├── install.sh              # brew whisper-cpp, model, pip -e ., swift build, launchctl load
    └── status.sh
```

## 8. Stack and versions on the target Mac

| Component | Version | Source |
|-----------|---------|--------|
| macOS | 26.6.2 | — |
| Python | 3.11.5 | pyenv |
| Swift | 6.1 | Command Line Tools |
| ffmpeg | 9.0.1 | Homebrew |
| whisper.cpp | 1.9.4 | Homebrew (to be installed) |
| anthropic SDK | 1.x | pip (to be installed) |
| pydantic | 2.x | pip |
| typer | 0.x | pip |
| pytest | 8.x | pip |

## 9. Risks and mitigations

| ID | Risk | Mitigation |
|----|------|------------|
| R1 | `~/Documents` may sync with iCloud, pushing `.env` (API key) and `data/` (audio and transcripts) to the cloud. | `install.sh` checks whether Documents is in iCloud and, if so, creates `data/` in `~/Library/Application Support/teams-recorder` and warns. Alternative: `chflags nosync` on the folders, or move the project. |
| R2 | API key in plain text in `.env`. | `chmod 600 .env`, `.gitignore`, and `trec doctor` warns. Migration to Keychain is documented as an improvement. |
| R3 | The `pmset` heuristic may break with a Teams update. | Detector isolated behind a port; manual `trec start/stop` always available; smoke test in `trec doctor`. |
| R4 | The process tap API may change between macOS versions. | Isolated Swift binary; an alternative BlackHole adapter can be added without touching the domain. |
| R5 | Transcripts containing client content sent to the API. | Optional filter of sensitive terms before sending (`config.toml: redact = [...]`); Radix policy to be confirmed. |
| R6 | Detector false positive (Teams prevents sleep without being in a call). | Require 2 consecutive readings and, when available, the microphone signal. |
| R7 | API cost above forecast. | Log `usage` per call; `trec status` shows the month's estimated spend. |

## 10. Implementation plan

| Phase | Deliverable | Acceptance criterion | Status |
|-------|-------------|----------------------|--------|
| 1 | Package skeleton, domain, ports, fakes, empty CLI, domain tests | `pytest` green; `trec --help` works | Completed on 2026-10-04 (use cases and file-based repository landed in this phase) |
| 2 | `teams-tap` in Swift + `CoreAudioTapCapture` + `FfmpegMicCapture` + `FfmpegMixer`; manual `trec start/stop` | A test call produces an audible `audio.m4a` with both sides | Completed on 2026-10-04. Pending from the user: grant "System Audio Recording" to `teams-tap` |
| 3 | `WhisperCppTranscriber`; `trec transcribe` | Portuguese transcript of the phase 2 audio with acceptable errors | Completed on 2026-10-04. Synthesized speech (Luciana voice) transcribed with no errors using `large-v3-turbo-q5_0` |
| 4 | `ClaudeAnalyzer`; `trec analyze`; prompts | Valid `analysis.json` with real actions from the test meeting | Completed on 2026-10-05 |
| 5 | `PmsetCallDetector` + daemon + launchd + notifications | Real meeting recorded without touching the keyboard | Completed on 2026-10-05 with a simulated call (a process that holds a power assertion and is an audio client) under launchd. Validation with real Teams pending the next meeting |
| 6 | `ClaudePlanner`; `trec plan`; scheduler; `PurgeOldAudio` | Markdown plan generated at 18:00 with accumulated actions | Completed on 2026-10-05; validation with real content pending the first real meeting |
| 7 | `install.sh`, `trec doctor/status`, README | Installation from scratch for another user of the Mac works | |

### Phase 2 notes

- `CaptureHandle` became a concrete dataclass (PID + file) instead of a Protocol: it has to be written to `data/current_recording.json` so that `trec stop`, in another process, can terminate the recorders started by `trec start`.
- `teams-tap` embeds an `Info.plist` (via the linker) with `NSAudioCaptureUsageDescription`, so that TCC can identify the utility when asking for permission.
- The end-to-end test (test tone + microphone) produced a mono AAC 48 kHz `audio.m4a`. The Teams track is silent until the system audio permission is granted; the mixer tolerates empty tracks.
- The environment is slow when opening new files for the first time (corporate antivirus); subprocess tests wait for a readiness signal instead of assuming a startup time.

### Phase 3 notes

- Default model switched from `large-v3-turbo` (1.6 GB) to `large-v3-turbo-q5_0` (574 MB, quantized): the target Mac's disk had 3.8 GB free. Portuguese quality proved equivalent in the test; the model name is configurable in `config.toml`.
- whisper-cli reads WAV/FLAC/MP3/OGG; the adapter converts the M4A to 16 kHz mono WAV with ffmpeg in a temporary folder before transcribing.
- Output via `-oj`: segments with `offsets` in milliseconds. Blank segments are discarded.
- `trec transcribe` with no argument processes every meeting in the RECORDED state; failures become `error.txt` and do not interrupt the others (NFR05).

### Phase 4 notes

- Structured output via a JSON Schema derived from an adapter-side Pydantic model (`AnalysisOut`), with `additionalProperties=false` and all fields required; Pydantic validates again on the client side before converting to the domain. Dates come in ISO format and relative expressions ("quarta-feira") are resolved by the model from the meeting date given in the message.
- Fixed system prompt marked with `cache_control`; meeting metadata and the transcript go in the user message, preserving the cached prefix across meetings.
- Server-side fallback (`fallbacks: "default"`) enabled by default; a final refusal is still treated as `AnalysisError` and becomes `error.txt`.
- Truncated responses (`max_tokens`) and off-schema responses are explicit errors, never partial analyses.
- Token usage per call in `data/log/llm_usage.jsonl` (risk R7); `trec status` will start summing the estimated spend in phase 7.
- The real test against the API is opt-in (`TREC_REAL_CLAUDE=1`), since it spends credits; the default suite uses a mocked client.
- Second transport for the same `MeetingAnalyzer` port: `ClaudeCodeTransport` calls Claude Code in headless mode (`claude -p --output-format json --json-schema …`) and uses the user's subscription instead of API credit. Selection is by `llm.provider` in `config.toml` or `TREC_LLM_PROVIDER`. Trade-offs: no refusal fallback, cache managed by Claude Code, depends on a logged-in session (relevant for the launchd daemon). Originally implemented as a separate `ClaudeCliAnalyzer`; unified on 2026-10-05 (see phase 6 notes).

### Data folder back inside the project (2026-10-05)

- User decision: `paths.data_dir = "data"` in `config.toml`; relative values now resolve against the project folder. The 549 MB of recordings, plans, models and logs were moved from Application Support back to `./data` (git-ignored); the automatic Application Support default remains for an empty `data_dir`.
- Known risk (accepted): the daemon runs under launchd and `./data` sits in `~/Documents`, where TCC has caused transient `EDEADLK`. It was observed even before the move, when the daemon read `prompts/analyze_system.md` (meeting 2026-10-05_17-28-06 failed at analysis and was re-run manually). Mitigation: `fs_retry.retry_io` retries transient errnos for prompt reads, repository reads/writes, locks and the LLM usage log, alongside the existing retries for process spawns.

### Project moved out of ~/Documents (2026-10-05)

- With `data/` back inside the project and the project in `~/Documents`, TCC stopped being intermittent: on a test call at 17:51 the daemon failed to execute `teams-tap` 48 times in a row and the call was not recorded; tracebacks even lacked source lines because Python could not read its own files. User decision: keep the data inside the project and move the project to `~/Projetos/Pessoal/teams-recorder` (outside TCC-protected folders, not in iCloud). The virtualenv was recreated, `teams-tap` rebuilt and both LaunchAgents reinstalled with the new paths. The retry helpers stay as defense in depth.

