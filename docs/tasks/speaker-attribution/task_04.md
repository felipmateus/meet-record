---
status: completed
title: "Task 4: Ports, adapters, configuration and wiring"
type: feature
complexity: medium
---

# Task 4: Ports, adapters, configuration and wiring

## Overview

Connects the helper and the energy measurement to the application: the `SpeakerObserver` and `EnergyMeter` ports, their adapters, the `[speakers]` setting and the container wiring, with fakes and scripted stand-ins so the use cases of tasks 5 and 6 can be tested without Teams or a terminal permission. After this task `build_container` carries an observer on macOS when the feature is on and `None` on Windows or when it is off.

## Shippable Outcome

- Outcome: `AxSpeakerObserver.start(out, epoch)` checks the permission with `--check`, spawns the helper with the mandatory `--epoch`, stops it on request and reports `problems()` for the doctor; `FfmpegEnergyMeter.measure(track)` returns one level per 100 ms from a real ffmpeg run; `Settings.speakers_enabled` drives the wiring.
- Verify in this task: UT-060, UT-070–UT-075 with stand-ins, IT-002 with real ffmpeg, IT-003/IT-004 with `tests/fixtures/fake_speakers.py`.
- Integration verification: the use-case behaviour is tasks 5 and 6; the live run is E2E-001 (task 9).

## Requirements

- Contracts: `_spec.md` › Core Interfaces (`SpeakerObserver`, `EnergyMeter`, `ActiveRecording.speakers_handle`), › Integration Points (the ffmpeg filter chain; `--check` before spawning so any early exit is `start-failed`; exit 3 → `permission-missing`), › Config Lifecycle (`[speakers] enabled`, default true), › Architectural Boundaries (adapters under `adapters/outbound/`, the container as the only instantiation point, Windows passes `None`).
- **Design decided in task 3: the helper runs as its own launchd job** (`_spec.md` › Integration Points › macOS TCC, safety invariant 11). `AxSpeakerObserver` writes the job definition to `<data_dir>/run/local.teams-recorder.speakers.plist`, boots out a stale job, bootstraps it in `gui/<uid>`, waits a startup grace and reads the pid and state from `launchctl print` (the `print` parsing of `adapters/outbound/launchd.py`); exit code 3 → `SpeakersUnavailable("permission-missing")`, any other early exit → `start-failed`; `stop` boots it out and removes the definition, falling back to SIGTERM by pid (`process_control.terminate`) when launchctl fails; `is_running` asks launchctl, then the pid. `problems()` runs `--check` as the short-lived job `local.teams-recorder.speakers-check`. All launchctl calls go through an injected `runner` (as `LaunchAgent` does) so tests use a fake.
- `FfmpegEnergyMeter`: `-af aresample=16000,asetnsamples=n=1600,astats=metadata=1:reset=1,ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-` then `-f null -`; parse `pts_time` (integers print without decimals) and `RMS_level` (`-inf` → `Speakers.SILENCE_DB`); timeout and non-zero exit → `CaptureError` with the stderr tail.
- Fakes: `FakeSpeakerObserver` (records starts with `out`/`epoch`, can raise `SpeakersUnavailable(reason)`, reports stops, `problems()` configurable) and `FakeEnergyMeter` (returns a given timeline per track or fails) in `tests/fakes/__init__.py`; `tests/fixtures/fake_speakers.py` honours `--check` (exit 0 when `FAKE_SPEAKERS_TRUSTED=1`, else 3), writes a readiness file and a `start` line, appends a `stop` line on SIGTERM.
- Strings in `messages.py` (`Err.SPEAKERS_*`, the problems texts with the exact command and settings path from `_dx.md`), identifiers in `constants.py` (`Files.SPEAKERS_BINARY`, `Files.SPEAKERS_LOG`, `Bin.TEAMS_SPEAKERS`, `Speakers.INTERVAL`).

## Subtasks

- [x] 4.1 Ports and `ActiveRecording.speakers_handle`; `Container.speakers` / `Container.energy`; `_macos_adapters` / `_windows_adapters`; `config.load_settings` for `[speakers]` and `config.toml` comments.
- [x] 4.2 `adapters/outbound/speakers_ax.py` with `command`, `start` (check then spawn), `stop`, `is_running`, `problems`; the identity design from task 3.
- [x] 4.3 `adapters/outbound/energy_ffmpeg.py` with `command`, `parse_levels`, `measure`.
- [x] 4.4 Fakes and the `fake_speakers.py` stand-in; tests UT-060, UT-070–UT-075, IT-002, IT-003, IT-004.

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/outbound/capture_coreaudio.py` — the spawn/stop/is_running pattern to follow.
- `src/teams_recorder/adapters/outbound/process_control.py:48-66,94-122` — `spawn` (startup grace, early exit) and `terminate`.
- `src/teams_recorder/container.py:95-160` — `Container`, platform adapters, `build_container`.
- `src/teams_recorder/config.py:60-110,220-290` — `Settings` and `load_settings`.
- `src/teams_recorder/adapters/outbound/mixer_ffmpeg.py` — ffmpeg invocation and probing style (timeouts, stderr tails).
- `tests/fixtures/fake_recorder.py` — the stand-in pattern (readiness file, signals).
- `tests/unit/test_container_platforms.py`, `tests/unit/test_config.py` — existing wiring and config tests to extend.
- `_dx.md` › CLI › `teams-speakers` and › Errors — the exact texts `problems()` returns.

### Dependent Files

- `src/teams_recorder/application/use_cases/recording.py`, `processing.py` — consumers (tasks 5, 6).
- `src/teams_recorder/adapters/inbound/cli.py` — `doctor` reads `problems()` (task 8).

### Related ADRs

- [ADR-001](adrs/adr-001.md), [ADR-002](adrs/adr-002.md) — the two signals these adapters deliver.

## Deliverables

- The two ports, the two adapters, the setting and wiring, the fakes and the stand-in, the tests.

## Tests

- [x] UT-060 — `[speakers] enabled` default and override; macOS builds the observer only when enabled; Windows passes `None`.
- [x] UT-070, UT-070b, UT-071, UT-072 — the observer's command (mandatory `--epoch`), binary missing, `--check` exit 3, early exit after a passing check.
- [x] UT-073, UT-074, UT-075 — the ffmpeg command, `parse_levels` on the real output shape, failures.
- [x] IT-002 — real ffmpeg on two generated WAVs: levels inside and outside the tones, the segments `[0, 1.4]` and `[1.6, 3.0]`.
- [x] IT-003, IT-004 — lifecycle with the stand-in: start/readiness/stop with a `stop` event last; permission missing raises without spawning.

## Success Criteria

- `trec doctor` (task 8) can print the three states from `problems()` alone; the use cases of tasks 5 and 6 run on the fakes without changes to the adapters.

## Completion Notes (2026-10-17)

- `start` does not run a separate `--check` job first: the helper itself exits 3 before creating any file when the permission is missing, and the job's last exit code (read from `launchctl print` after the startup grace) maps 3 to `permission-missing` and any other early exit to `start-failed`; this is what UT-072 and IT-004 specify. The separate check job exists only for `problems()`.
- `problems()` texts are final (`Err.SPEAKERS_PROBLEM_*`): `teams-speakers not built → scripts/build-native.sh`; `Accessibility permission missing → run `<binary> --check --prompt` and allow teams-speakers (add it with the + button: <binary>) under System Settings > Privacy & Security > Accessibility`; `the Accessibility permission could not be checked: <detail>`. They carry the absolute binary path; the doctor (task 8) adds the `speaker labels:` prefix and level and may relativize the path.
- `launchd.py` gained `JobState`, `parse_print` and `job_domain` (shared by `LaunchAgent.status` and the observer); `LaunchAgent` behaves as before.
- `AxSpeakerObserver(binary, run_dir, log_path=None, interval, runner, sleep, startup_grace, stop_timeout, check_timeout, terminate, alive)`: `terminate` and `alive` are injected so unit tests never signal a real pid. `Container.speakers` / `Container.energy` exist and are wired; the use-case constructors in `Container` do not take them yet (task 5).
- Not done here (documentation, task 9): AGENTS.md port table rows, README and installer text.
