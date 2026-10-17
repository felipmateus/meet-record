---
status: completed
title: "Task 6: Labelling at transcription and the daily notice"
type: feature
complexity: medium
---

# Task 6: Labelling at transcription and the daily notice

## Overview

Puts names on the transcript: after whisper (and the retry, when there is one), `TranscribeMeeting` reads the speaker log and the energy, labels the segments with the domain rules, stores the summary with the transcript and raises the day's single notification when a wired observer produced nothing. This is where the Motivating Problem becomes visible in `transcript.txt`.

## Shippable Outcome

- Outcome: `trec transcribe` on a meeting with events and energy writes `transcript.json` with `speaker` on the labelled segments and a `speakers` summary, and `transcript.txt` with `[HH:MM:SS] Name: text` lines; a meeting whose observer was wired but produced nothing raises one notification per day with the reason.
- Verify in this task: UT-040–UT-047 on the fakes and IT-001 on the file repository.
- Integration verification: E2E-001 (task 9).

## Requirements

- Contracts: `_spec.md` › Core Interfaces (`TranscribeMeeting.clock`, `user_name`), › Label rules, › Data Models (reason codes and which notify), safety invariants 7 and 9; `_dx.md` › Files (the reason table) and › Notification.
- Labelling: `log = repo.load_speaker_log(id, fallback_epoch=meeting.started_at.timestamp(), end=duration or last segment end)`, `energy = repo.load_energy(id)`, `label = user_label(user_name, log, Minutes.SPEAKER_USER_FALLBACK)`, `transcript = label_segments(...)`; any `RepositoryError`/`OSError`/`ValueError` → `Log.SPEAKERS_LABEL_FAILED`, the transcript saved unlabelled (no summary); success → `Log.SPEAKERS_LABELLED` with labelled, eligible and the names.
- Notice: only when `clock` is set, the events file exists (`log is not None`), `labels.labelled == 0` and the reason is one of `binary-missing`, `permission-missing`, `start-failed`, `observer-died`, `no-window`; `repo.last_notice_day(Speakers.NOTICE_KEY) != clock.now().date()` → `Notify.NO_SPEAKER_LABELS` with the body of the reason, then `repo.save_notice_day`; otherwise `Log.NO_SPEAKER_LABELS` only. `no-match` logs only; `no-observer` neither notifies nor warns.
- `Container.transcribe_meeting` passes `clock` and `user_name`.
- Texts in `messages.py` (`Notify.NO_SPEAKER_LABELS`, the bodies per reason, the `Log` templates).

## Subtasks

- [x] 6.1 Labelling in `TranscribeMeeting.execute` after the health/retry logic and before `save_transcript`.
- [x] 6.2 The daily notice with the reason table and the marker.
- [x] 6.3 Container wiring; tests UT-040–UT-047 and IT-001.

## Implementation Details

### Relevant Files

- `src/teams_recorder/application/use_cases/processing.py:35-110` — `TranscribeMeeting.execute`, where labelling and the notice go.
- `src/teams_recorder/domain/speakers.py` (task 1) — `label_segments`, `user_label`, `no_label_reason`.
- `src/teams_recorder/container.py:110-115` — `transcribe_meeting`.
- `tests/unit/test_processing_use_cases.py` — the `TranscribeMeeting` test patterns.
- `tests/integration/test_repository_fs.py` — the file repository fixtures for IT-001.
- `_dx.md` › Files — the `speakers.jsonl` example IT-001 uses.

### Dependent Files

- `src/teams_recorder/adapters/inbound/cli.py` — `trec transcribe` prints the summary (task 8).

### Related ADRs

- [ADR-002](adrs/adr-002.md) — the user's lines by energy.

## Deliverables

- The labelling and notice logic, the messages, the tests.

## Tests

- [x] UT-040, UT-041 — labelling failure keeps the transcript; success labels and logs.
- [x] UT-042, UT-043, UT-044, UT-045, UT-046, UT-047 — the daily notice: first of the day, already sent, unreadable marker, labels present, the reason table, no clock.
- [x] IT-001 — the `_dx.md` events and an `energy.json` through `FsMeetingRepository` and `TranscribeMeeting`: the expected `speaker` values and `transcript.txt` lines.

## Success Criteria

- Re-running `trec transcribe` on the same meeting yields identical labels (invariant 7).
- A meeting without `speakers.jsonl` transcribes exactly as before this feature, with no notification.

## Completion Notes (2026-10-16)

- Done; nothing committed. `pytest` 622 passed, 8 skipped (baseline 604 + 18 new); `mypy` clean; `tests/unit/test_no_hardcoded_strings.py` green.
- Tests: `tests/unit/test_transcribe_speakers.py` (UT-040-UT-047, plus the fallback label, the relabelling and the no-observer cases), `test_it001_*` in `tests/integration/test_repository_fs.py`, and a wiring assertion in `tests/unit/test_container_platforms.py`.
- Texts: `Notify.NO_SPEAKER_LABELS`, `NO_SPEAKER_LABELS_BODY`, `NO_SPEAKER_LABELS_REASON` (per reason), and `Log.SPEAKERS_LABELLED`, `SPEAKERS_LABEL_FAILED`, `NO_SPEAKER_LABELS`, `SPEAKERS_NOTICE_FAILED` in `messages.py`.
- Consequence for existing tests: the use case now returns the labelled copy of the transcript, so four retry tests in `test_processing_use_cases.py` compare `segments` instead of object identity.
- Not done here (task 8): the `trec transcribe` Speakers line and the reason table for the CLI.
