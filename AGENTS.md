# AGENTS.md

Guidance for coding agents working in this repository. Humans: see `README.md`, `docs/REQUIREMENTS-AND-ARCHITECTURE.md` (requirements + architecture) and `docs/prd/` (product requirements).

## What this is

`teams-recorder` is a macOS (and Windows, untested on real hardware) background tool that records Microsoft Teams calls (Teams audio + microphone), transcribes them locally with whisper.cpp, extracts decisions/actions (and progress reported on earlier work) with Claude, and builds a daily plan. A curator agent keeps one document, `data/activities/atividades.md`, current after each analyzed meeting: it runs in the daemon beside the planner (the shadow slice of `docs/tasks/activities-curator/`) until the user decides the planner goes. Python 3.11 orchestrates; a small Swift binary (`native/teams-tap`) does the Core Audio capture, a second one (`native/teams-speakers`) reads who is speaking from the Teams window through the Accessibility API (macOS), and a C# binary (`native/teams-tap-win`) does the WASAPI capture on Windows. `Settings.platform` (from `sys.platform`) makes `container.py` pick the macOS or Windows adapters. There is no database: **the state of a meeting is the set of files in its folder** (`src/teams_recorder/domain/status.py`).

## Commands

```bash
source .venv/bin/activate              # venv lives in the repo (ignored by git)
pytest                                 # fast suite, no coverage (~10 s warm)
pytest --cov=teams_recorder --cov-report=term-missing   # coverage is opt-in (target 70%)
pytest tests/unit/test_daemon.py -k hysteresis           # single test
mypy                                   # type check (config in pyproject.toml); keep it clean
TREC_REAL_WHISPER=1 pytest -m slow tests/integration/test_transcriber_whispercpp.py   # real whisper (loads the model)
TREC_REAL_CLAUDE=1 pytest -m slow tests/integration/test_llm_claude_real.py           # real API call (spends credit)
TREC_REAL_CLAUDE_CLI=1 pytest -m slow tests/integration/test_llm_claude_cli_real.py   # real Claude Code headless call
TREC_REAL_BACKLOG=1 pytest -m slow tests/integration/test_publisher_backlogmd_real.py # real Backlog.md CLI, throwaway board
TREC_REAL_CLAUDE_CLI=1 TREC_REAL_BACKLOG=1 pytest -m slow tests/integration/test_story_publishing_e2e_real.py  # stories end to end

scripts/wiki_corpus.py <render|process|fill|ingest|ask|score|autorun|clean>   # synthetic meetings → audio (recorder's mixer) → this pipeline → wiki → Q&A eval
scripts/fidelity_eval.py <setup|oracle|inject|defend|report|gate|stories|verify-stories|propagate|glossary|audit-wiki|review-kit>   # pipeline fidelity tests
                                       # both spend the Claude Code subscription (ask first); keep their data dirs OUTSIDE the repo (CLAUDE.md is inherited)
scripts/install.sh [--dry-run]         # idempotent installer (deps, .venv, teams-tap, model, config, LaunchAgents); install.command wraps it for Finder
scripts/uninstall.sh [--all]           # removes this copy's LaunchAgents (+ .venv/build with --all); never data
scripts\install.ps1 / uninstall.ps1    # Windows counterparts (install.cmd wraps the installer); config edits go through scripts/config_tool.py
scripts/build-native.sh                # swift build -c release → native/teams-tap/.build/release/teams-tap and native/teams-speakers/.build/release/teams-speakers (refuses a helper source that sets an accessibility attribute)
scripts/build-native-windows.sh        # dotnet publish → native/teams-tap-win/bin/Release/net8.0/win-x64/publish/teams-tap.exe (Windows port, same CLI; untested)
scripts/download-model.sh [name]       # ggml models into data/models (default large-v3-turbo-q5_0; silero-v5.1.2 for VAD)
scripts/recover-rate-mismatch.sh <meeting dir>   # audio.recovered.m4a for a meeting whose Teams track was recorded at the wrong rate (never touches audio.m4a)

trec doctor | status | start | stop | cancel | transcribe [id] | analyze [id] | minutes [id] [--all] | plan [--date] | purge
trec stories [--date] | publish [--date] [--only 1,3]  # draft stories from a plan; send drafts to the boards
trec activities [--open]               # state of the activities document: focus, counts, last pass, meetings not curated; --open also opens the file (open / os.startfile)
trec activities curate <id>… | --since YYYY-MM-DD [--yes]   # rerun the curator for analyzed meetings / bootstrap the document (asks first; one pass per day, up to 4 meetings)
trec activities undo [--yes]           # restore the document to before the last pass (previews the diff first; --yes skips only the question)
backlog board                          # the user's real board (./backlog, git-ignored); never `backlog init` here again
trec daemon --once                     # one detector reading
trec status                            # also prints the data dir (paths.data_dir in config.toml; currently ./data)
trec agent install|restart|status|uninstall   # LaunchAgent local.teams-recorder.daemon
native/teams-tap/.build/release/teams-tap --list   # which processes are Core Audio clients right now
native/teams-speakers/.build/release/teams-speakers --check   # Accessibility permission of the context it runs from (a terminal's grant, not the daemon's: trec doctor checks it as the helper's own launchd job)
```

Rules that bite:
- **After changing Python code, run `trec agent restart`** or the running daemon keeps the old code. The Swift binaries are re-spawned per recording, so a rebuild is enough. The speaker observer, the energy measurement and the `CuratorWorker` (the activities curator's thread) are Python code in the daemon: they take effect only after `trec agent restart`, which needs the user's approval (a recording may be in progress). `trec activities …` and `trec analyze` run the curator in the CLI process and need no restart.
- `teams-speakers` needs the **Accessibility** permission on the helper itself: the daemon runs it as its own launchd job (`local.teams-recorder.speakers`), because a helper spawned by the daemon's Python is judged by the Python's grant. macOS creates no list entry for a background job's request, so the user adds `native/teams-speakers/.build/release/teams-speakers` with the **+** button, and a rebuild (ad-hoc signature) may require adding it again. Changing it falls under "ask before changing macOS permissions" below; tests use `tests/fixtures/fake_speakers.py` and a fake `launchctl`, never the real launchd.
- Do not run two pytest sessions at once; subprocess-based tests time out under contention.
- Windows adapters must import and be testable on macOS: keep `ctypes`/`winreg` calls under `if sys.platform == "win32":` and inject the OS call (reader, message box, runner, kill) so tests fake it. Nothing Windows-specific has run on real Windows yet; say so when reporting.
- Env overrides for testing: `TEAMS_RECORDER_DIR` (project dir), `TREC_LLM_PROVIDER` (`api`|`claude-code`), `TREC_TEAMS_PROCESS` (process name the detector watches; `tests/fixtures/fake_call.py` simulates a Teams call under the name `python3.11`).

## Architecture (hexagonal)

```
domain/          pure Python: Meeting, Transcript, Analysis, Action, DailyPlan, MeetingStatus, derive_status(). No I/O, no deps.
application/     ports.py (Protocols) + use_cases/ + pipeline.py. Depends only on domain.
adapters/inbound/   cli.py (Typer app `trec`), daemon.py (detector loop with hysteresis)
adapters/outbound/  one file per port implementation (see below)
container.py     composition root: the ONLY place that instantiates concrete adapters, from config.Settings
config.py        config.toml + .env → frozen Settings; env overrides; data_dir = paths.data_dir (relative = inside the project; this repo uses ./data), or automatic: Application Support when the project sits in iCloud or a TCC-protected folder
```

Import direction is strict: `domain ← application ← adapters/container`. Adapters never import each other's internals except the LLM stack: `llm_schema` (output schema + prompt helpers) is used by `llm_transport` (API / Claude Code request shape, error mapping, usage log), `llm_claude` (analyzer), `planner_claude` (planner), `stories_claude` (story writer), `verifier_claude` (claim verifier) and `curator_claude` (activities curator); and `codec` (JSON ↔ domain) is used by `repository_fs`.

Ports and their adapters (`application/ports.py`):

| Port | Adapter(s) |
|---|---|
| `MeetingRepository` | `repository_fs.FsMeetingRepository` (folder per meeting, atomic writes, `.lock`, `current_recording.json`). Also owns the curation error file: `mark_curation_failed(id, message)` / `clear_curation_failed(id)` / `curation_error(id)` read and write `curation_error.txt` (`status.CURATION_ERROR`) without the meeting lock and outside `derive_status` (a curation failure never makes a meeting `failed`) |
| `ProcessAudioCapture` | `capture_coreaudio.CoreAudioTapCapture` → `teams-tap --pid` (target + descendant audio clients; Teams' main process emits no audio). Windows: `capture_wasapi.WasapiTapCapture` → `teams-tap.exe --pid --stop-file` |
| `MicCapture` | `capture_mic_coreaudio` (default, `teams-tap --mic`, survives device reconfiguration) or `capture_mic_ffmpeg`. Windows: `capture_wasapi.WasapiMicCapture` |
| `SpeakerObserver` | `speakers_ax.AxSpeakerObserver` → `teams-speakers --out speakers.jsonl --epoch T`, run as its own launchd job per recording (`start` takes about 1.5 s: the startup grace, then the job's state decides; exit 3 = `permission-missing`; `stop` boots the job out, and `stop_stale()` does the same without a handle for a job left by a start that crashed inside the grace; every `launchctl` call has a timeout; `problems()` runs `--check` as a short-lived job for `trec doctor`). Raises `SpeakersUnavailable(reason)` (`binary-missing`, `permission-missing`, `start-failed`), which `StartRecording` records as one `unavailable` line in `speakers.jsonl` and never raises. `None` when `[speakers] enabled = false` and on Windows. Labelling (`domain/speakers.py`, pure, thresholds in `LabelRules`) runs in `TranscribeMeeting` from `speakers.jsonl` + `energy.json`; every transcript carries a `speakers` summary with the reason when nothing was labelled |
| `EnergyMeter` | `energy_ffmpeg.FfmpegEnergyMeter` (RMS per 100 ms of a raw track; `StopRecording.finalize` saves both tracks as `energy.json` before deleting them, all or nothing, and a failure never blocks mixing; the user's own lines are labelled from it) |
| `AudioMixer` | `mixer_ffmpeg` (per-track highpass+afftdn, amix, loudnorm, limiter; keeps raw tracks in `debug/` on anomaly) |
| `Transcriber` | `transcriber_whispercpp` (ffmpeg → 16 kHz WAV → whisper-cli `-mc 0 -oj`; optional Silero VAD). A second instance (`container.build_retry_transcriber`: `-mc 0` + VAD) retranscribes a transcript `domain/health.py` finds degraded by a hallucination loop, except when the Teams track's capture counters show a wrong sample rate (no second pass can repair that audio) |
| `MeetingAnalyzer` | `llm_claude.ClaudeAnalyzer` over a `StructuredTransport`: `llm_transport.ApiTransport` (structured output, cached system prompt, server-side fallback) or `llm_transport.ClaudeCodeTransport` (`claude -p`, subscription), chosen by `llm.provider`; the same transport instance serves the planner. Besides decisions and actions it extracts `status_updates` (what the meeting said happened to earlier work: `done`, `in_progress`, `blocked`, `delayed`, `due_changed`, `reassigned`, `cancelled`, with who, the literal quote and the time) and `Action.for_whom`; it never sees the activities document |
| `CallDetector` | `detector_pmset` (parses `pmset -g assertions` for the Teams process). Windows: `detector_windows.MicUsageCallDetector` (registry `ConsentStore\microphone`: Teams' `LastUsedTimeStop == 0`) |
| `DiskSpace` | `disk_space.DataDirDiskSpace` (free bytes on the data volume; low-space notifications at recording start and during a call, and in `trec doctor`) |
| `Notifier`, `Clock` | `notifier_macos` (osascript / log), `clock`. Windows: `notifier_windows.ToastNotifier` (PowerShell toast) |
| `RecordingConfirmation` | `confirm_macos.DialogRecordingConfirmation` (osascript `display dialog`; keep/discard asked by the daemon when it starts a recording; `None` when `[confirmation] enabled = false` or headless). Windows: `confirm_windows.MessageBoxRecordingConfirmation` (user32 `MessageBoxTimeoutW`) |
| `ClaimVerifier` | `verifier_claude.ClaudeClaimVerifier` over a `StructuredTransport` (one call per meeting; the transcript whole, or its start plus ±60 s around each claim when long; verdict → confirmed/unconfirmed in code; a `status_update` claim reads `<change>: <about> — "<quote>"`, and the excerpt windowing is `domain/excerpts.excerpt_window`, shared with the curator). Used by `VerifyAnalysis`, which also runs the two code checks (`domain/verification.py`) and skips the verifier on an untrusted transcript (`TranscriptHealth.untrusted`). Built by `container.build_verifier` on its own transport (`[verification]` model and effort, same provider); `None` when `[verification] enabled = false` (`VerifyAnalysis` then runs the code checks only) |
| `MinutesRenderer` | `minutes_markdown.MarkdownMinutesRenderer` (minutes.md from the analysis, no LLM call; labels in `messages.Minutes`; a banner when the transcript's health is degraded, another when the Teams track was recorded at the wrong sample rate, then a line saying no item was confirmed from such a transcript; ⚠️ and the reason on each unconfirmed claim, via `domain.unconfirmed_reason`; a `🔄 Andamento informado` section after the actions lists the status updates, an unconfirmed one ending ` ⚠️ não confirmado: <reason>`) |
| `ActivityCurator` | `curator_claude.ClaudeCurator` over its own `StructuredTransport` (`container.build_curator`: `[activities] model` / `cli_model` / `effort`, same provider as `[llm]`; prompt `prompts/curate_system.md`, re-read per call). `curate(CuratorInput) -> CuratorOutput` takes the document, the new analyses (every claim as a ref `1.a1`, `1.o2`, `1.u1`, …), windowed transcript excerpts around each status update, a 14-day calendar, the user's edits since the last pass and recent archive entries; returns edit ops (`replace`, `insert_after`, `move`, `archive`) plus focus, summary and `notify`. `repair(data, current, failures)` is the one repair round for ops that did not apply. Pure edit logic (apply, the open-line rule, links, diff) is in `domain/activities.py`; `CurateMeetings` (`use_cases/activities.py`) runs a pass |
| `ActivityStore` | `activities_fs.FsActivityStore` (see below for the layout). `lock(wait)` is an OS lock (`fcntl.flock`, `msvcrt.locking` on Windows, untested there) that also reconciles a pass a hard stop interrupted; `commit(before, after, archived, base, record)` writes version files, archive entries, the document, `base.md` and, as the commit point, the pass-log line, in that order; `log_pass(record)` appends a `failed` / `skipped_empty` record and nothing else; `passes()`, `version(name)`, `recent_archive(limit)`, `truncate_archive(record)` (undo; only while the archive still has the size the pass left), `read_document()`, `read_base()`, `path()`. Built by `container.build_activity_store` (`[activities] keep_versions`) |
| `Planner` | `planner_claude.ClaudePlanner` over the same `StructuredTransport` (new/overdue actions computed in code; the model writes markdown, priorities and completed ids) |
| `StoryWriter` | Receives only `feature`/`bug` actions and unclassified ones: `DraftUserStories` routes by `Action.kind` (set by the analysis), turning `technical`/`operation` actions into task cards and leaving `management`/`communication` in the plan. `stories_claude.ClaudeStoryWriter` over the same `StructuredTransport`: drafts user stories from a plan's new actions; the user's guide (`[stories] guide`, default `prompts/user_story_guide.md`) is appended to `prompts/stories_system.md` and re-read on every call, and a missing or empty guide is an error. Invented action ids are dropped in code; uncovered actions become `skipped` |
| `StoryRenderer` | `stories_markdown.MarkdownStoryRenderer` (`plans/<day>.stories.md`, the review document; labels in `messages.StoryDoc`; a banner per source meeting whose transcript is degraded or whose Teams track was recorded at the wrong sample rate, with a line saying nothing was confirmed from it, the mark of an unconfirmed task card) |
| `StoryPublisher` | `publisher_backlogmd.BacklogMdPublisher` (`backlog task create` in the Triagem column; options before `--` and the title; `problems()` checks the binary, board, column, no auto-commit/remotes and that Git ignores the board — fails closed — and runs before every publish). Chosen by `[stories] destinations` through the `_PUBLISHERS` table in `container.py`; `PublishUserStories` fans out to every destination and skips what each already has |
| (scheduler, not a port) | `launchd.LaunchAgent` on macOS, `scheduler_windows.ScheduledTask` (schtasks XML, `pythonw -m teams_recorder.adapters.inbound.cli`) on Windows; chosen in `cli._agent()` |

The activities document (`docs/tasks/activities-curator/`, `docs/prd/pages/09-activities.md`) lives under `<data_dir>/activities/` and `<data_dir>/log/`:

```
activities/atividades.md          the document the user edits by hand (Portuguese; markers and headings in messages.ActivityDoc)
activities/arquivo/<YYYY-MM>.md   append-only archive: everything that left the document, with date and reason
activities/.curator/lock          flock target, always empty: the one lock that serialises passes, undo and the daemon's worker
activities/.curator/base.md       the document as the last pass left it (the next pass diffs the user's edits against it)
activities/.curator/versions/     <version>_{before,after,base,prevbase}.md and <version>_pass.json, the last [activities] keep_versions passes (undo)
log/activities.jsonl              one PassRecord per line (kinds meeting, undo, skipped_empty, failed); the line is the commit point of a pass
recordings/<id>/curation_error.txt   why the last pass for this meeting failed; cleared by a later success; not part of the meeting status
```

Invariants of the document: only an `archive` op (with a reason) removes a checkbox line, and only the user changes a box (checked in `domain/activities.apply_ops`, edit by edit, on the body between the box and the link block); lines no op targets are kept byte for byte; the box's closing marker carries the pass's version stamp, which tells `lock()` after a crash whether the document was replaced (roll forward) or not (roll back). A pass never writes `error.txt` and never blocks recording, transcription or analysis: `Pipeline.after_analysis` (fired once, when the analysis step ran and the meeting is `ANALYZED`) only enqueues the meeting for the daemon's `CuratorWorker`; a hook failure is logged. The worker runs rounds of up to 4 meetings per pass (the woken id, up to 3 more, and `CurateMeetings.pending()`: analyzed in the last 2 working days with no successful pass and fewer than 2 failed attempts alone), rebuilds its queue at daemon start, and is never joined on shutdown. `[activities] enabled = false` turns off only the automatic triggers (the worker and the curation step of `trec analyze`); `trec activities …` always runs.

Every port has a fake in `tests/fakes/__init__.py` (`InMemoryActivityStore`, `FakeActivityCurator` for the two above); use-case tests run entirely on fakes. Subprocess adapters are tested with scripted stand-ins in `tests/fixtures/` (`fake_recorder.py`, `fake_whisper_cli.py`, `fake_claude_cli.py` (`FAKE_CLAUDE_OUTPUT_FILE`, `FAKE_CLAUDE_SCRIPT` and `FAKE_CLAUDE_RECORD` script and record the curator's calls), `fake_backlog_cli.py`); the long-running ones wait for a readiness file instead of assuming startup time.

Strings and identifiers live in two modules, never inline:
- `src/teams_recorder/messages.py` — every user-facing text: CLI output and help (`Cli`), notifications (`Notify`), exception messages (`Err`), log templates (`Log`, printf-style), the activities document's markers, headings and labels (`ActivityDoc`, Portuguese like `Minutes`). Tests assert on these constants, so changing a wording is a one-line change.
- `src/teams_recorder/constants.py` — enums (`LlmProvider`, `MicBackend`, `Effort`), environment variables (`Env`), external binaries (`Bin`), file/folder names (`Files`), launchd labels, LLM/audio/detector/process defaults. Meeting file names stay in `domain/status.py` (they are the domain's state).
Add to these modules instead of writing a new literal. Prefer `StrEnum` over free strings for closed sets.
This is enforced: `tests/unit/test_no_hardcoded_strings.py` fails on any prose-like string literal (or f-string with literal text) outside `messages.py`, `constants.py` and `domain/status.py`. Docstrings are exempt; a literal that genuinely belongs inline (an external tool's flag, a protocol keyword) needs `# literal-ok: <reason>` on its line.

Key invariants:
- `CaptureHandle` is a concrete dataclass (pid + path), not a Protocol, because `trec stop` in another process must stop recorders started by `trec start`.
- `Pipeline.process()` derives the next step from files and stops at the first failure, writing `error.txt`; re-running clears it. One meeting's failure never blocks others.
- Analyzers short-circuit transcripts under 20 words (whisper hallucinates on silence) and never return partial analyses: refusal, truncation and schema violations are errors.
- Prompts live in `prompts/*.md`; the analyzer's JSON schema is derived from `AnalysisOut` (Pydantic) with `additionalProperties=false`.
- The `anthropic` SDK is imported lazily (inside `ClaudeAnalyzer`); do not import it at module level — it has ~1,900 modules and a cold import took 12 minutes on the dev Mac.

## Adding an adapter (the most common change)

1. If the capability is new, declare the port as a `typing.Protocol` in `application/ports.py` (methods only; no I/O types beyond `Path`). Existing ports: see the table above.
2. Implement it in `adapters/outbound/<capability>_<tech>.py`. Translate every external failure into a domain error (`CaptureError`, `TranscriptionError`, `AnalysisError`, `RepositoryError`) with a message that tells the user what to do. Keep SDK/CLI shapes in one method (e.g. `command()` / `_request()`) so tests can inspect them.
3. Add a fake in `tests/fakes/__init__.py` (in-memory, records calls) and unit tests for the adapter with a scripted stand-in if it spawns processes (`tests/fixtures/fake_*.py`, wait for a readiness file).
4. Register it in `container.py` (`build_container` or a `build_<x>()` helper) and, if selectable, add the switch to `config.toml` + `config.Settings` with a test in `tests/unit/test_config.py`.
5. Surface it in `trec doctor` when it depends on an external binary or model, update `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 notes and the relevant `docs/prd/` page.

## Working conventions

- **English only.** Everything written into this repository is in English: code, identifiers, comments, docstrings, log messages, CLI output, notifications, tests, documentation, PRD, run logs and commit messages. The only Portuguese allowed is data and user-facing documents built from LLM content (the labels of `minutes.md` in `messages.Minutes`, the labels of the story drafts in `messages.StoryDoc`, the markers, headings and labels of the activities document in `messages.ActivityDoc`, and the daily-plan section names in the prompt): sample transcripts and analyses used as test fixtures, and the content the LLM produces for the user (meetings are held in Brazilian Portuguese, so prompts must keep asking for Portuguese output while being written in English). Model-written Portuguese is echoed verbatim into otherwise English output in two places: the curator's one-line summary (notification bodies, `Last pass:` and the per-pass lines of `trec activities curate` / `trec analyze`) and the focus lines `trec activities` prints. Everything else the CLI prints is English, weekdays included (`Mon 19/10`). Commits before 2026-10-05 are in Portuguese and were not rewritten.
- **Ask before committing or pushing.** Edit, test and show the diff; commit only with explicit approval.
- Commits are grouped in **waves** per phase, one commit per layer in dependency order (`docs`, `feat(domain)`, `feat(application)`, `feat(adapters)`, `feat(native)`, `feat(cli)`, `test`), imperative English messages with a body explaining the decision. See `docs/COMMITS.md`. Each commit must leave the tree importable.
- Never commit `.env`, `data/`, `backlog/`, `backlog.config.yml`, `native/teams-tap/.build/`, `native/teams-tap-win/bin|obj/` or `.venv/` (already ignored). `backlog/` is the user's real board of stories built from meetings: never publish test stories there; tests use throwaway boards. `.env` holds `ANTHROPIC_API_KEY`; never read or print its value.
- Ask before: installing/uninstalling/restarting the LaunchAgent on the user's Mac, deleting anything under `data/recordings`, changing macOS permissions, or running tests that spend API credit. The daemon is installed and running on the development machine and records the user's real meetings.
- Keep `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 (phase status + notes) and `docs/prd/` in sync when a phase or a behavior changes.
- When a skill is run, the organization requires a `RUN_LOG-<user>-<date>.md` in `docs/run-logs/` listing questions asked and answers given.

## Environment quirks (dev Mac)

Never place the project (or its `data/`) under `~/Documents`, `~/Desktop` or `~/Downloads`: macOS TCC blocks the launchd daemon there ("[Errno 11] Resource deadlock avoided"), first intermittently and then persistently — on 2026-10-05 it stopped recordings entirely, so the project moved to `~/Projetos/Pessoal/teams-recorder`. File I/O still goes through `adapters/outbound/fs_retry.retry_io` and process spawns through `process_control`, both retrying transient errnos; use them for any new file access the daemon performs.

First open of any newly written file (including `.pyc`) can take seconds per file due to endpoint security scanning; a cold `pytest` after large edits may hang for minutes with 0% CPU, then run in ~10 s. Free disk and swap were tight; the macOS kernel has SIGKILLed test subprocesses under memory pressure. Coverage is opt-in for that reason.
