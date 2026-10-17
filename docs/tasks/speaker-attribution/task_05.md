---
status: completed
title: "Task 5: Observer and energy in the recording use cases"
type: feature
complexity: high
---

# Task 5: Observer and energy in the recording use cases

## Overview

Makes every recording produce the two inputs of labelling without ever depending on them: the observer starts after both recorders and its failure is recorded as an `unavailable` line; the energy of both tracks is measured before they are deleted; the window's subject names an untitled meeting; `trec stop`, cancel, the daemon's watch and its crash recovery all know the observer. This is the riskiest task because it touches the path that records the user's real meetings.

## Shippable Outcome

- Outcome: after a recorded call, the meeting folder holds `speakers.jsonl` (events, or one `unavailable` line) and `energy.json`, `meta.json` carries the window's subject as the title when none was given, and no observer failure ever stops or delays the recording, the mixing or the next call.
- Verify in this task: UT-030–UT-039 and UT-036b on the fakes; the daemon tests still green.
- Integration verification: E2E-001 (task 9) on a live call.

## Requirements

- Contracts: `_spec.md` › System Architecture (use cases), safety invariants 1, 2, 3, 5, 6, 10; `_dx.md` › Files (the `unavailable` line) and › Errors (log lines for start failure, death, energy failure).
- `StartRecording`: optional `speakers: SpeakerObserver | None`; start it after both captures with `out = path(SPEAKERS)` and the meeting epoch; on `SpeakersUnavailable(reason)` → `repo.write_speakers_unavailable(id, reason)` and `Log.SPEAKERS_UNAVAILABLE`; on any other exception → reason `start-failed`; persist `speakers_handle` in the active pointer before notifying; never raise.
- `StopRecording.stop_capture`: stop the observer first (best effort, `Log.SPEAKERS_STOP_FAILED`), then the recorders; after the pointer is cleared, read the subject through `repo.load_speaker_log` and set `meeting.title` when it is None (`Log.TITLE_FROM_WINDOW`); `finalize`: measure both tracks with the `EnergyMeter` before mixing, save `energy.json` atomically, `Log.ENERGY_MEASURED` / `Log.ENERGY_FAILED`, then mix and delete as today.
- `CancelRecording`: stops the observer too. `Daemon._watch_capturers`: watches the observer handle (`Log.CAPTURER_SPEAKERS = "teams-speakers"`), once per call; `Daemon.recover`: stops the observer with the recorders. Use `getattr(self.container, "speakers", None)` so the daemon's `FakeContainer` in tests needs no change.
- `trec stop` from another process stops the observer through the persisted handle (pid only).

## Subtasks

- [x] 5.1 `StartRecording` with the observer, the `unavailable` write and the persisted handle.
- [x] 5.2 `StopRecording.stop_capture` / `finalize` with the observer stop, the title from the subject and the energy before deletion; `CancelRecording`.
- [x] 5.3 Daemon watch and recovery; `Container.start_recording/stop_recording/cancel_recording` pass the new collaborators.
- [x] 5.4 Tests UT-030–UT-039, UT-036b; log templates in `messages.Log`.

## Implementation Details

### Relevant Files

- `src/teams_recorder/application/use_cases/recording.py` — `StartRecording.execute`, `StopRecording.stop_capture/finalize`, `CancelRecording`.
- `src/teams_recorder/adapters/inbound/daemon.py:118-134,200-230` — `_watch_capturers`, `recover`, `_last_write`.
- `src/teams_recorder/container.py:110-130` — the use-case factories.
- `src/teams_recorder/application/pipeline.py` — unchanged; the failure isolation to respect.
- `tests/unit/test_recording_use_cases.py`, `tests/unit/test_daemon.py` — the patterns and the `FakeContainer`.
- `_spec.md` › Safety Invariants — 1, 2, 3, 5, 6, 10.

### Dependent Files

- `src/teams_recorder/adapters/inbound/cli.py` — `trec start` prints the observer line and `trec stop` stops it (task 8).

### Related ADRs

- [ADR-002](adrs/adr-002.md) — why the energy is measured before deletion.

## Deliverables

- The three use cases and the daemon changes, the log templates, the tests.

## Tests

- [x] UT-030, UT-031, UT-032 — the title from the window subject: set, kept, absent.
- [x] UT-033, UT-034, UT-035, UT-037, UT-038, UT-039 — observer started after the captures and persisted; `SpeakersUnavailable` and other failures recorded without raising; `speakers=None`; stop and cancel stop it; recovery and the watch.
- [x] UT-036, UT-036b — energy failure leaves mixing untouched; energy measured before deletion and saved.

## Success Criteria

- With `FakeSpeakerObserver(fail=…)` in every failure mode, `StartRecording` still returns an active recording and `StopRecording` still produces `audio.m4a`.
- The existing recording and daemon tests pass unchanged except for the new collaborators.
