# Development

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | Python 3.11+ (Typer CLI, Pydantic, python-dotenv), hexagonal architecture |
| Audio capture (macOS) | Swift binary `native/teams-tap`: Core Audio Process Tap (macOS 14.2+) and AVAudioEngine for the microphone |
| Speaker labels (macOS) | Swift binary `native/teams-speakers`: reads the Teams window through the Accessibility API (read-only), started by the daemon as its own launchd job |
| Audio capture (Windows) | C# binary `native/teams-tap-win`: WASAPI process loopback (.NET 8) |
| Mixing and conversion | ffmpeg |
| Transcription | whisper.cpp (`whisper-cli`), ggml models from Hugging Face, optional Silero VAD |
| Analysis, activities curator, stories | Claude Opus 5.5 (`claude-opus-5-5`) through the `anthropic` SDK, or Claude Code headless (`claude -p`) |
| Background service | launchd LaunchAgents (macOS), Task Scheduler (Windows) |
| Story board | [Backlog.md](https://github.com/MrLesk/Backlog.md) (local Markdown kanban) |
| Tests and types | pytest, pytest-cov, mypy |

## Architecture

The Python code follows a hexagonal (ports and adapters) layout with a strict import direction: `domain ← application ← adapters/container`.

```
src/teams_recorder/
├── domain/              # pure Python, no I/O: Meeting, Transcript, Analysis, Action,
│                        # MeetingStatus and derive_status() (state = files)
├── application/
│   ├── ports.py         # typing.Protocol interfaces for every external capability
│   ├── use_cases/       # recording, processing, activities (curator pass, undo), stories (drafting from tags, publishing), retention (audio purge)
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
├── teams-speakers/      # Swift package: reads who speaks from the Teams window (Accessibility API, read-only)
└── teams-tap-win/       # C# (.NET 8): WASAPI counterpart with the same CLI
prompts/                 # system prompts and the story guide
scripts/                 # installers, native builds, model download
tests/                   # unit/, integration/, fakes/, fixtures/
```

### Ports and adapters

| Port | macOS adapter | Windows adapter |
|---|---|---|
| `MeetingRepository` | `repository_fs` (folder per meeting, atomic writes, `.lock`, `curation_error.txt`, the story drafts in `plans/`) | same |
| `ProcessAudioCapture` | `capture_coreaudio` → `teams-tap --pid` | `capture_wasapi` → `teams-tap.exe --pid --stop-file` |
| `MicCapture` | `capture_mic_coreaudio` (default) or `capture_mic_ffmpeg` | `capture_wasapi.WasapiMicCapture` |
| `SpeakerObserver` | `speakers_ax` → `teams-speakers`, run as its own launchd job per recording | none (`[speakers] enabled = false` also wires none) |
| `EnergyMeter` | `energy_ffmpeg` (RMS per 100 ms of each raw track) | same |
| `AudioMixer` | `mixer_ffmpeg` | same |
| `Transcriber` | `transcriber_whispercpp` | same |
| `MeetingAnalyzer`, `StoryWriter` | `llm_claude`, `stories_claude` over one shared transport (`llm_transport.ApiTransport` or `ClaudeCodeTransport`) | same |
| `ActivityCurator` | `curator_claude` (its own transport on the same provider; `[activities]` model and effort) | same |
| `ActivityStore` | `activities_fs` (the document, archive, versions and pass log under `data/activities/` and `data/log/`, one OS lock; the story tag's replacement) | same (`msvcrt` lock, not run on Windows) |
| `MinutesRenderer`, `StoryRenderer` | `minutes_markdown`, `stories_markdown` | same |
| `StoryPublisher` | `publisher_backlogmd` | same |
| `CallDetector` | `detector_pmset` | `detector_windows` |
| `Notifier` | `notifier_macos` (osascript) | `notifier_windows` (PowerShell toast) |
| `RecordingConfirmation` | `confirm_macos` (osascript dialog) | `confirm_windows` (`MessageBoxTimeoutW`) |
| `DiskSpace`, `Clock` | `disk_space`, `clock` | same |
| Scheduler (not a port) | `launchd.LaunchAgent` (the daemon only) | `scheduler_windows.ScheduledTask` (the daemon only) |

`Settings.platform` (from `sys.platform`) decides which set `container.py` builds. Every port has an in-memory fake in `tests/fakes/`, so use cases are tested without real I/O.

### Design decisions worth knowing

- **State is files.** There is no database. `Pipeline.process()` looks at which files exist, runs the next step, and writes `error.txt` on failure. Re-running a command resumes from where it stopped.
- **The curator edits, code guards.** The model decides what is new, what matches what and where it goes; code only applies its edits to the file as it is when the answer arrives, enforces that nothing but an archive removes a checkbox line, and commits in a recoverable order (the pass-log line is the commit point). There is no task database.
- **Recording is cross-process.** `CaptureHandle` is a plain dataclass (PID and path) stored in `current_recording.json`, so `trec stop` in one terminal can stop recorders started by the daemon or by another `trec start`.
- **No hardcoded strings.** User-facing text lives in `messages.py`, and identifiers in `constants.py`. `tests/unit/test_no_hardcoded_strings.py` enforces this.
- **Lazy SDK import.** The `anthropic` SDK is imported only inside the analyzer; at module level it made cold starts very slow.
- **Fail closed when publishing.** The Backlog.md adapter checks the binary, the board, the column, the Git ignore status and the absence of auto-commit before every publish.

The full requirements, interview decisions, risks and per-phase design notes are in [`docs/REQUIREMENTS-AND-ARCHITECTURE.md`](../REQUIREMENTS-AND-ARCHITECTURE.md).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
scripts/build-native.sh        # needed only for capture tests and real recordings
trec --help
```

## Tests and type checks

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
TREC_REAL_CLAUDE_CLI=1 pytest -m slow tests/integration/test_verifier_claude_real.py  # claim verifier, Claude Code
TREC_REAL_CLAUDE_CLI=1 TREC_REAL_BACKLOG=1 pytest -m slow tests/integration/test_story_publishing_e2e_real.py  # stories end to end
pytest -m slow tests/integration/test_mixer_ffmpeg_real.py tests/integration/test_energy_ffmpeg_real.py   # real ffmpeg, no model
```

Test layout:

```
tests/
├── unit/          # use cases on fakes, adapters with scripted stand-ins, config, string policy
├── integration/   # subprocess adapters and opt-in real-tool tests
├── fakes/         # in-memory fake for every port
└── fixtures/      # fake_recorder.py, fake_whisper_cli.py, fake_claude_cli.py, fake_backlog_cli.py,
                   # fake_speakers.py, fake_call.py, sample transcripts and analyses,
                   # activities documents, the synthetic meeting corpus (wiki_corpus/)
```

Do not run two pytest sessions at once: subprocess-based tests time out under contention. Coverage is opt-in because on a machine with little free memory, macOS has killed test subprocesses.

## Simulating a call without Teams

```bash
TREC_TEAMS_PROCESS=python3.11 trec daemon --once   # while tests/fixtures/fake_call.py runs
```

## Evaluation scripts

Two scripts measure the pipeline on synthetic meetings whose dialogues say who said what (`tests/fixtures/wiki_corpus/`). Both call the model through your Claude Code subscription, so run them knowingly, and keep their data folders **outside** the repository (Claude Code reads every `CLAUDE.md` from the working directory up).

```bash
scripts/wiki_corpus.py <render|process|fill|ingest|ask|score|autorun|clean>   # dialogues → audio (the recorder's mixer) → this pipeline → Q&A eval
scripts/fidelity_eval.py <setup|oracle|inject|defend|report|gate|stories|verify-stories|propagate|glossary|audit-wiki|review-kit>
```

`fidelity_eval.py` checks whether what reaches the activities document and the stories matches what was said: it injects known errors (wrong owner, invented date, phantom participant…), measures what the code checks and the claim verifier catch, and traces one error through the curator and the stories. Results and method: [`docs/tasks/prd-llm-wiki/evaluation.md`](../tasks/prd-llm-wiki/evaluation.md) and [`docs/tasks/prd-fidelity-guard/`](../tasks/prd-fidelity-guard/).

## Adding an adapter

1. Declare the port as a `typing.Protocol` in `application/ports.py`, if it is new.
2. Implement it in `adapters/outbound/<capability>_<tech>.py`, translating every external failure into a domain error with a message that tells the user what to do.
3. Add a fake in `tests/fakes/` and tests (with a scripted stand-in in `tests/fixtures/` if it spawns processes).
4. Register it in `container.py`. If it is selectable, add the switch to `config.toml` and `config.Settings`, with a test.
5. Surface it in `trec doctor` if it depends on an external binary, and update `docs/` and `docs/prd/`.

## Conventions

- Everything in the repository is in English. The only Portuguese is user-facing content built from LLM output (minutes labels, story labels, activities document labels) and test fixtures.
- Commits are grouped per layer in dependency order (`docs`, `feat(domain)`, `feat(application)`, `feat(adapters)`, `feat(native)`, `feat(cli)`, `test`); see [`docs/COMMITS.md`](../COMMITS.md).
- **After changing Python code, run `trec agent restart`**, or the running daemon keeps the old code (the curator's worker and the daily audio purge run inside it). The Swift binaries are spawned again for each recording, so rebuilding them is enough. `trec activities`, `analyze`, `stories`, `publish` and `purge` run in their own process and need no restart.
- Coding agents: see [`AGENTS.md`](../../AGENTS.md).

## Project status

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Domain, ports, use cases, file repository, `trec status` / `doctor` | Done |
| 2 | Teams and microphone capture, mixing, `trec start` / `stop` / `cancel` | Done |
| 3 | Local transcription with whisper.cpp | Done |
| 4 | Analysis with Claude and meeting minutes | Done |
| 5 | Call detector, daemon, LaunchAgent | Done, validated with real calls |
| 6 | Daily plan at 6 pm and audio retention | Done; the daily plan was replaced by the activities document and removed on 2026-10-20, and the retention now runs in the daemon |
| 7 | Installer and uninstaller | Done |
| — | User story drafts and Backlog.md publishing | Done; stories are drafted only from items tagged `#história` (`trec stories`); publishing is manual (`publish = false`) until story quality is approved |
| — | Activities document (curator, `trec activities`) | Done; replaced the daily plan on 2026-10-20 (the user waived the full shadow week; the quality evaluations on real meetings were not run) |
| — | Windows port | Implemented and unit-tested; not yet run on Windows |

Not done yet: the month's LLM spend in `trec status`, GitHub Projects and Azure Boards destinations, reading approvals back from the board, and voice identification (a voiceprint per person, deliberately left out). Speaker labels from the Teams window ship on macOS; their gates on real meetings are pending. Calendar integration was dropped.

## Further documentation

| Document | Content |
|---|---|
| [`docs/prd/README.md`](../prd/README.md) | Product requirements: modules, flows, global rules, with one page per flow and appendices (states, integrations, data layout) |
| [`docs/REQUIREMENTS-AND-ARCHITECTURE.md`](../REQUIREMENTS-AND-ARCHITECTURE.md) | Requirements, architecture, risks and per-phase implementation notes |
| [`docs/SPEAKER-ATTRIBUTION.md`](../SPEAKER-ATTRIBUTION.md) | Investigation and spike runs behind the speaker labels; PRD in [`docs/tasks/speaker-attribution/`](../tasks/speaker-attribution/) |
| [`docs/tasks/activities-curator/`](../tasks/activities-curator/) | Specification, user stories, developer-experience contract, tests, ADRs and tasks for the activities document |
| [`docs/tasks/prd-story-publishing/`](../tasks/prd-story-publishing/) | PRD, tech spec and tasks for story publishing |
| [`docs/tasks/prd-fidelity-guard/`](../tasks/prd-fidelity-guard/) | PRD, tech spec and tasks for the transcript-loop guard, claim verification and cited story criteria |
| [`docs/tasks/prd-llm-wiki/`](../tasks/prd-llm-wiki/) | The LLM wiki of meetings, evaluated and not built (no better than giving the model all the minutes); its `evaluation.md` holds the fidelity measurements |
| [`docs/COMMITS.md`](../COMMITS.md) | Commit conventions |
| [`AGENTS.md`](../../AGENTS.md) | Guidance for coding agents |
| [`native/teams-tap-win/README.md`](../../native/teams-tap-win/README.md) | The Windows capture binary |
