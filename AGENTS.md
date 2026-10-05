# AGENTS.md

Guidance for coding agents working in this repository. Humans: see `README.md`, `docs/REQUISITOS-E-ARQUITETURA.md` (requirements + architecture, Portuguese) and `prd/` (product requirements).

## What this is

`teams-recorder` is a macOS background tool that records Microsoft Teams calls (Teams audio + microphone), transcribes them locally with whisper.cpp, extracts decisions/actions with Claude, and will build a daily plan. Python 3.11 orchestrates; a small Swift binary (`native/teams-tap`) does the Core Audio capture. There is no database: **the state of a meeting is the set of files in its folder** (`src/teams_recorder/domain/status.py`).

## Commands

```bash
source .venv/bin/activate              # venv lives in the repo (ignored by git)
pytest                                 # fast suite, no coverage (~10 s warm)
pytest --cov=teams_recorder --cov-report=term-missing   # coverage is opt-in (target 70%)
pytest tests/unit/test_daemon.py -k hysteresis           # single test
TREC_REAL_WHISPER=1 pytest -m slow tests/integration/test_transcriber_whispercpp.py   # real whisper (loads the model)
TREC_REAL_CLAUDE=1 pytest -m slow tests/integration/test_llm_claude_real.py           # real API call (spends credit)
TREC_REAL_CLAUDE_CLI=1 pytest -m slow tests/integration/test_llm_claude_cli_real.py   # real Claude Code headless call

scripts/build-native.sh                # swift build -c release → native/teams-tap/.build/release/teams-tap
scripts/download-model.sh [name]       # ggml models into data/models (default large-v3-turbo-q5_0; silero-v5.1.2 for VAD)

trec doctor | status | start | stop | cancel | transcribe [id] | analyze [id] | purge
trec daemon --once                     # one detector reading
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
config.py        config.toml + .env → frozen Settings; env overrides; iCloud-aware data_dir
```

Import direction is strict: `domain ← application ← adapters/container`. Adapters never import each other's internals except `llm_claude_cli` reusing schema/prompt helpers from `llm_claude`, and `codec` (JSON ↔ domain) used by `repository_fs`.

Ports and their adapters (`application/ports.py`):

| Port | Adapter(s) |
|---|---|
| `MeetingRepository` | `repository_fs.FsMeetingRepository` (folder per meeting, atomic writes, `.lock`, `current_recording.json`) |
| `ProcessAudioCapture` | `capture_coreaudio.CoreAudioTapCapture` → `teams-tap --pid` (target + descendant audio clients; Teams' main process emits no audio) |
| `MicCapture` | `capture_mic_coreaudio` (default, `teams-tap --mic`, survives device reconfiguration) or `capture_mic_ffmpeg` |
| `AudioMixer` | `mixer_ffmpeg` (per-track highpass+afftdn, amix, loudnorm, limiter; keeps raw tracks in `debug/` on anomaly) |
| `Transcriber` | `transcriber_whispercpp` (ffmpeg → 16 kHz WAV → whisper-cli `-oj`; optional Silero VAD) |
| `MeetingAnalyzer` | `llm_claude.ClaudeAnalyzer` (API, structured output, cache, server fallback) or `llm_claude_cli.ClaudeCliAnalyzer` (`claude -p`), chosen by `llm.provider` |
| `CallDetector` | `detector_pmset` (parses `pmset -g assertions` for the Teams process) |
| `Notifier`, `Clock` | `notifier_macos` (osascript / log), `clock` |
| `Planner` | not yet implemented (phase 6) |

Every port has a fake in `tests/fakes/__init__.py`; use-case tests run entirely on fakes. Subprocess adapters are tested with scripted stand-ins in `tests/fixtures/` (`fake_recorder.py`, `fake_whisper_cli.py`, `fake_claude_cli.py`) that wait for a readiness file instead of assuming startup time.

Key invariants:
- `CaptureHandle` is a concrete dataclass (pid + path), not a Protocol, because `trec stop` in another process must stop recorders started by `trec start`.
- `Pipeline.process()` derives the next step from files and stops at the first failure, writing `error.txt`; re-running clears it. One meeting's failure never blocks others.
- Analyzers short-circuit transcripts under 20 words (whisper hallucinates on silence) and never return partial analyses: refusal, truncation and schema violations are errors.
- Prompts live in `prompts/*.md`; the analyzer's JSON schema is derived from `AnalysisOut` (Pydantic) with `additionalProperties=false`.
- The `anthropic` SDK is imported lazily (inside `ClaudeAnalyzer`); do not import it at module level — it has ~1,900 modules and a cold import took 12 minutes on the dev Mac.

## Working conventions

- **Ask before committing or pushing.** Edit, test and show the diff; commit only with explicit approval.
- Commits are grouped in **waves** per phase, one commit per layer in dependency order (`docs`, `feat(domain)`, `feat(application)`, `feat(adapters)`, `feat(native)`, `feat(cli)`, `test`), imperative Portuguese messages with a body explaining the decision. See `docs/COMMITS.md`. Each commit must leave the tree importable.
- Never commit `.env`, `data/`, `native/teams-tap/.build/` or `.venv/` (already ignored). `.env` holds `ANTHROPIC_API_KEY`; never read or print its value.
- Ask before: installing/uninstalling/restarting the LaunchAgent on the user's Mac, deleting anything under `data/recordings`, changing macOS permissions, or running tests that spend API credit. The daemon is installed and running on the development machine and records the user's real meetings.
- Keep `docs/REQUISITOS-E-ARQUITETURA.md` §10 (phase status + notes) and `prd/` in sync when a phase or a behavior changes.
- When a skill is run, the organization requires a `RUN_LOG-<user>-<date>.md` in `docs/run-logs/` listing questions asked and answers given.

## Environment quirks (dev Mac)

First open of any newly written file (including `.pyc`) can take seconds per file due to endpoint security scanning; a cold `pytest` after large edits may hang for minutes with 0% CPU, then run in ~10 s. Free disk and swap were tight; the macOS kernel has SIGKILLed test subprocesses under memory pressure. Coverage is opt-in for that reason.
