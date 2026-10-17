---
status: completed
title: "Task 1: Domain and persistence of speaker labels"
type: feature
complexity: medium
---

# Task 1: Domain and persistence of speaker labels

## Overview

Gives the pipeline the vocabulary and the files of speaker attribution: a `speaker` on each transcript segment, the labelling summary and roster on the transcript, the pure rules that turn observer events and track levels into labels, and the repository methods that read and write `speakers.jsonl`, `energy.json` and the daily-notice marker. Every later task builds on these types; nothing user-visible changes yet, and every file written before this task loads unchanged.

## Shippable Outcome

- Outcome: `label_segments` turns a transcript, a `SpeakerLog` and two `EnergyTimeline`s into a transcript whose lines carry names, rendered as `[HH:MM:SS] Name: text`; old `transcript.json` and `current_recording.json` files load exactly as before.
- Verify in this task: the unit suites on `domain/speakers.py`, `domain/models.py`, the codec and the repository (UT-001–UT-027), plus the existing `tests/integration/test_repository_fs.py` still green.
- Integration verification: IT-001 is owned by task 6, which wires the rules into `TranscribeMeeting`.

## Requirements

- Contracts: `_spec.md` › Core Interfaces (`Segment.speaker`, `Transcript.roster/user_label/labels`, `LabelSummary`, `SpeakerEvent`, `SpeakerTurn`, `SpeakerLog` with `ended`, `EnergyTimeline`, `LabelRules`, `turns_from_events`, `label_segments`, `user_label`, `no_label_reason`, `is_speech` moved into `models.py`, the `MeetingRepository` additions) and › Label rules (eligibility, positive overlap, power mean, windows by midpoint, tie-break, the copy returned with roster, user label and summary).
- Data: `_spec.md` › Data Models (the `speakers` object in `transcript.json`, the events and their fields, the reason codes, the marker at `<data_dir>/notices/<key>`); file names in `domain/status.py` (`SPEAKERS = "speakers.jsonl"`, `ENERGY = "energy.json"`); reason codes and defaults in a `Speakers` class of `constants.py`; the fallback label in `messages.Minutes`.
- Codec: event times relative to the `start` event's `epoch`, the meeting start only as fallback; an `unavailable` line wins over anything else; malformed lines skipped and counted; `speaker` and `speakers` omitted when absent so old files round-trip byte-for-byte.
- Compatibility: `_spec.md` › Impact Analysis (lossless, additive; no shim).
- `domain/health.py` keeps exporting `is_speech` (it imports `models`, so `models` hosts the predicate).
- `SpeakersUnavailable(CaptureError)` with a `reason` code in `domain/errors.py`.

## Subtasks

- [x] 1.1 Add `Segment.speaker`, the `Transcript` fields and `LabelSummary`, `is_speech` in `models.py` (re-exported by `health.py`), `clock_time` unchanged; render labels in `as_timestamped_text`; `Transcript.speakers`.
- [x] 1.2 Write `domain/speakers.py`: the dataclasses, `turns_from_events`, `label_segments`, `user_label`, `no_label_reason`, with the rules of the spec; export from `domain/__init__.py`.
- [x] 1.3 Add `SpeakersUnavailable`, the file names, the `Speakers` constants (reason codes, `SILENCE_DB`, defaults of `LabelRules`, the notice key) and the Portuguese fallback label.
- [x] 1.4 Codec: `speaker_log_from_lines`, `energy_to_dict` / `energy_from_dict`, `transcript_to_dict` / `transcript_from_dict` with the new fields; `ActiveRecording` pointer with an optional `speakers_handle`.
- [x] 1.5 Repository: `write_speakers_unavailable`, `load_speaker_log`, `save_energy`, `load_energy`, `last_notice_day`, `save_notice_day`; `InMemoryMeetingRepository` counterparts that record calls.
- [x] 1.6 Unit tests UT-001–UT-027 and a compatibility pass over the fixtures in `tests/fixtures/sample_transcript.json`.

## Implementation Details

### Relevant Files

- `src/teams_recorder/domain/models.py:45-120` — `Segment`, `Transcript`, `clock_time`; the new fields and rendering go here.
- `src/teams_recorder/domain/health.py:42-45` — `is_speech`, to move and re-export.
- `src/teams_recorder/domain/errors.py` — `CaptureError` to subclass.
- `src/teams_recorder/domain/status.py` — meeting file names (the domain's state).
- `src/teams_recorder/adapters/outbound/codec.py:70-125` — transcript and health codec, the pattern for defaults on old files.
- `src/teams_recorder/adapters/outbound/repository_fs.py:154-190,213-245` — the active-recording pointer and the artifact loaders (`_decoded`, atomic writes) to extend.
- `src/teams_recorder/application/ports.py:28-75,149-192` — `CaptureHandle`, `ActiveRecording`, `MeetingRepository`.
- `src/teams_recorder/constants.py`, `src/teams_recorder/messages.py` — where the new identifiers and the fallback label go.
- `tests/fakes/__init__.py` — `InMemoryMeetingRepository` to extend.
- `tests/unit/test_models.py:40-50`, `tests/integration/test_repository_fs.py` — existing coverage of rendering and files.

### Dependent Files

- `src/teams_recorder/application/use_cases/processing.py`, `recording.py` — consumers in tasks 5 and 6.
- `src/teams_recorder/adapters/outbound/llm_schema.py`, `verifier_claude.py` — read the new transcript fields in task 7.

### Related ADRs

- [ADR-002: The user's own lines from the two tracks' energy](adrs/adr-002.md) — the power-mean rule and the margin this task implements.

## Deliverables

- `domain/speakers.py`, the model, error, status, constants and messages additions, the codec and repository methods, the fake's counterparts.
- Unit tests for UT-001–UT-027.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [x] UT-001, UT-002, UT-003, UT-004, UT-005, UT-007 — `turns_from_events`: open/close, open at end, short turns, window lost, union across windows, same name twice.
- [x] UT-006, UT-008, UT-009, UT-010, UT-011, UT-012, UT-012b, UT-013, UT-013b, UT-014, UT-015, UT-016, UT-016b, UT-017, UT-018 — `label_segments`, `user_label`, `no_label_reason`, eligibility, power mean, window selection, boundaries.
- [x] UT-019 — `Transcript.as_timestamped_text` with and without labels.
- [x] UT-020, UT-021, UT-022, UT-023, UT-024, UT-025, UT-026, UT-027 — codec: speaker log (time origin, `unavailable` wins, malformed lines, subjects), transcript round trip, energy round trip and shape errors.

## Success Criteria

- `pytest` and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` passes with the new modules.
- A transcript written by the previous version renders and re-serializes identically.

## Completion Notes (2026-10-16)

- Done; nothing committed. `pytest` 604 passed, 8 skipped; `mypy` clean; `tests/unit/test_no_hardcoded_strings.py` green.
- Tests: `tests/unit/test_speakers.py` (UT-001–UT-019), `tests/unit/test_speakers_codec.py` (UT-020–UT-027 plus the repository methods and the active-recording pointer).
- Deviations from the spec, recorded there: the reason codes are `domain.SpeakerReason` (a `StrEnum` with `notifies`), not `constants.Speakers.Reason`, because the domain imports nothing outside itself; `SILENCE_DB` lives in `domain/speakers.py` for the same reason. `SpeakerLog` gained `skipped` (malformed lines). `window_subject(title, compact)` derives the subject from a window title when the helper wrote no `title` event. `ActiveRecording.speakers_handle` landed in `application/ports.py` with this task, since the repository persists it.
- `_tests.md` UT-013b's example was corrected: window i covers `[0.1·i, 0.1·(i+1))`, so the midpoint of window 3 is 0.35, not 0.30.
