# AGENTS.md

Guidance for coding agents working in this repository. Humans: see `README.md`, `docs/REQUIREMENTS-AND-ARCHITECTURE.md` (requirements + architecture) and `prd/` (product requirements).

## What this is

`teams-recorder` is a macOS background tool that records Microsoft Teams calls (Teams audio + microphone), transcribes them locally with whisper.cpp, extracts decisions/actions with Claude, and will build a daily plan. Python 3.11 orchestrates; a small Swift binary (`native/teams-tap`) does the Core Audio capture. There is no database: **the state of a meeting is the set of files in its folder** (`src/teams_recorder/domain/status.py`).

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

scripts/install.sh [--dry-run]         # idempotent installer (deps, .venv, teams-tap, model, config, LaunchAgents); install.command wraps it for Finder
scripts/uninstall.sh [--all]           # removes this copy's LaunchAgents (+ .venv/build with --all); never data
scripts/build-native.sh                # swift build -c release → native/teams-tap/.build/release/teams-tap
scripts/build-native-windows.sh        # dotnet publish → native/teams-tap-win/bin/Release/net8.0/win-x64/publish/teams-tap.exe (Windows port, same CLI; untested)
scripts/download-model.sh [name]       # ggml models into data/models (default large-v3-turbo-q5_0; silero-v5.1.2 for VAD)

trec doctor | status | start | stop | cancel | transcribe [id] | analyze [id] | minutes [id] [--all] | plan [--date] | purge
trec daemon --once                     # one detector reading
trec status                            # also prints the data dir (paths.data_dir in config.toml; currently ./data)
trec agent install|restart|status|uninstall   # LaunchAgent local.teams-recorder.daemon
native/teams-tap/.build/release/teams-tap --list   # which processes are Core Audio clients right now
```

Rules that bite:
- **After changing Python code, run `trec agent restart`** or the running daemon keeps the old code. The Swift binary is re-spawned per recording, so a rebuild is enough.
- Do not run two pytest sessions at once; subprocess-based tests time out under contention.
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

Import direction is strict: `domain ← application ← adapters/container`. Adapters never import each other's internals except the LLM stack: `llm_schema` (output schema + prompt helpers) is used by `llm_transport` (API / Claude Code request shape, error mapping, usage log), `llm_claude` (analyzer) and `planner_claude` (planner); and `codec` (JSON ↔ domain) is used by `repository_fs`.

Ports and their adapters (`application/ports.py`):

| Port | Adapter(s) |
|---|---|
| `MeetingRepository` | `repository_fs.FsMeetingRepository` (folder per meeting, atomic writes, `.lock`, `current_recording.json`) |
| `ProcessAudioCapture` | `capture_coreaudio.CoreAudioTapCapture` → `teams-tap --pid` (target + descendant audio clients; Teams' main process emits no audio) |
| `MicCapture` | `capture_mic_coreaudio` (default, `teams-tap --mic`, survives device reconfiguration) or `capture_mic_ffmpeg` |
| `AudioMixer` | `mixer_ffmpeg` (per-track highpass+afftdn, amix, loudnorm, limiter; keeps raw tracks in `debug/` on anomaly) |
| `Transcriber` | `transcriber_whispercpp` (ffmpeg → 16 kHz WAV → whisper-cli `-oj`; optional Silero VAD) |
| `MeetingAnalyzer` | `llm_claude.ClaudeAnalyzer` over a `StructuredTransport`: `llm_transport.ApiTransport` (structured output, cached system prompt, server-side fallback) or `llm_transport.ClaudeCodeTransport` (`claude -p`, subscription), chosen by `llm.provider`; the same transport instance serves the planner |
| `CallDetector` | `detector_pmset` (parses `pmset -g assertions` for the Teams process) |
| `Notifier`, `Clock` | `notifier_macos` (osascript / log), `clock` |
| `MinutesRenderer` | `minutes_markdown.MarkdownMinutesRenderer` (minutes.md from the analysis, no LLM call; labels in `messages.Minutes`) |
| `Planner` | `planner_claude.ClaudePlanner` over the same `StructuredTransport` (new/overdue actions computed in code; the model writes markdown, priorities and completed ids) |

Every port has a fake in `tests/fakes/__init__.py`; use-case tests run entirely on fakes. Subprocess adapters are tested with scripted stand-ins in `tests/fixtures/` (`fake_recorder.py`, `fake_whisper_cli.py`, `fake_claude_cli.py`) that wait for a readiness file instead of assuming startup time.

Strings and identifiers live in two modules, never inline:
- `src/teams_recorder/messages.py` — every user-facing text: CLI output and help (`Cli`), notifications (`Notify`), exception messages (`Err`), log templates (`Log`, printf-style). Tests assert on these constants, so changing a wording is a one-line change.
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
5. Surface it in `trec doctor` when it depends on an external binary or model, update `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 notes and the relevant `prd/` page.

## Working conventions

- **English only.** Everything written into this repository is in English: code, identifiers, comments, docstrings, log messages, CLI output, notifications, tests, documentation, PRD, run logs and commit messages. The only Portuguese allowed is data and user-facing documents built from LLM content (the labels of `minutes.md` in `messages.Minutes` and the daily-plan section names in the prompt): sample transcripts and analyses used as test fixtures, and the content the LLM produces for the user (meetings are held in Brazilian Portuguese, so prompts must keep asking for Portuguese output while being written in English). Commits before 2026-10-05 are in Portuguese and were not rewritten.
- **Ask before committing or pushing.** Edit, test and show the diff; commit only with explicit approval.
- Commits are grouped in **waves** per phase, one commit per layer in dependency order (`docs`, `feat(domain)`, `feat(application)`, `feat(adapters)`, `feat(native)`, `feat(cli)`, `test`), imperative English messages with a body explaining the decision. See `docs/COMMITS.md`. Each commit must leave the tree importable.
- Never commit `.env`, `data/`, `native/teams-tap/.build/`, `native/teams-tap-win/bin|obj/` or `.venv/` (already ignored). `.env` holds `ANTHROPIC_API_KEY`; never read or print its value.
- Ask before: installing/uninstalling/restarting the LaunchAgent on the user's Mac, deleting anything under `data/recordings`, changing macOS permissions, or running tests that spend API credit. The daemon is installed and running on the development machine and records the user's real meetings.
- Keep `docs/REQUIREMENTS-AND-ARCHITECTURE.md` §10 (phase status + notes) and `prd/` in sync when a phase or a behavior changes.
- When a skill is run, the organization requires a `RUN_LOG-<user>-<date>.md` in `docs/run-logs/` listing questions asked and answers given.

## Environment quirks (dev Mac)

Never place the project (or its `data/`) under `~/Documents`, `~/Desktop` or `~/Downloads`: macOS TCC blocks the launchd daemon there ("[Errno 11] Resource deadlock avoided"), first intermittently and then persistently — on 2026-10-05 it stopped recordings entirely, so the project moved to `~/Projetos/Pessoal/teams-recorder`. File I/O still goes through `adapters/outbound/fs_retry.retry_io` and process spawns through `process_control`, both retrying transient errnos; use them for any new file access the daemon performs.

First open of any newly written file (including `.pyc`) can take seconds per file due to endpoint security scanning; a cold `pytest` after large edits may hang for minutes with 0% CPU, then run in ~10 s. Free disk and swap were tight; the macOS kernel has SIGKILLed test subprocesses under memory pressure. Coverage is opt-in for that reason.
