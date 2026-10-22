---
status: completed
title: "Task 3: Detection in the transcription and its wiring"
type: feature
complexity: medium
---

# Task 3: Detection in the transcription and its wiring

## Overview

This task solves the Motivating Problem. `TranscribeMeeting` gets the samples from the detector, chooses the language and transcribes in it, retry included. It then stores the detection record with the transcript. The container builds the whisper.cpp detector in `"auto"` mode, so the daemon and `trec transcribe` transcribe an English meeting in English. Any detection failure falls back to the first allowed language.

## Shippable Outcome

- Outcome:
  - with `language = "auto"`, `trec transcribe <id>` (and the daemon) runs whisper with `-l en` on a meeting whose samples heard English, and with `-l pt` on a Portuguese one;
  - `transcript.json` carries `language` and `language_detection`;
  - a detector failure gives a transcript in `pt` with `reason: "detection-failed"` and a warning log, never `error.txt`;
  - with a fixed code, no detector is built and the whisper command is today's.
- Verify in this task: the use-case tests on fakes, the container tests, and IT-002 over the real adapter with the scripted whisper.
- Integration verification: E2E-001 and E2E-002 (task 5); gates G1 and G2 (task 6).

## Requirements

- Contracts:
  - `_spec.md` › Core Interfaces: the `TranscribeMeeting` additions, `_language`, the paragraph on `self.language` as the only fallback source, and the order in `execute`.
  - `_spec.md` › System Architecture: the `Container.language_detector` field.
  - `_spec.md` › Business Rules: Fail-soft, Same decoding, Record.
  - `_spec.md` › Monitoring and Observability: the three `Log` lines.
  - `_spec.md` › Key Decisions: detection inside the meeting lock, and the purge race.
  - `_spec.md` › Safety Invariants 1–4.
  - US-001, US-002, US-003, US-008.AC-2/AC-4.
- Order in `execute`:
  - `_language` runs after `_rate_mismatch` and before `_transcribe`, inside the meeting lock;
  - `_transcribe` and `_checked` take the language as a parameter, and `_checked` sets `transcript.language = language`;
  - `execute` sets `transcript.language_detection` before `_label` and `save_transcript`.
- Every exception from `detect` is caught (`noqa: BLE001` with the reason, as the retry does) and logged as `Log.LANGUAGE_DETECTION_FAILED` at warning level, with the meeting id and the exception. No notification is sent.
- Container:
  - the field is `language_detector`; the name `detector` stays the Teams call detector;
  - `build_language_detector(settings)` uses the model path, whisper-cli, ffmpeg and threads of the settings, and returns None when `settings.detects_language` is false;
  - `transcribe_meeting()` passes `language_detector`, `languages` and `fallback_language` (the last from task 1).

## Subtasks

- [x] 3.1 `TranscribeMeeting`: the new fields, `_language`, the language parameter in `_transcribe` and `_checked`, the record on the transcript, the log lines.
- [x] 3.2 The container: `Container.language_detector`, `build_language_detector`, and the `transcribe_meeting()` wiring.
- [x] 3.3 IT-002 through the real adapter.

## Implementation Details

### Relevant Files

- `src/teams_recorder/application/use_cases/processing.py:29-161` — `TranscribeMeeting.execute`, `_checked`, `_transcribe` and the retry.
- `src/teams_recorder/container.py:129-131, 215-265` — `transcribe_meeting()`, and `build_retry_transcriber`, the pattern for `build_language_detector`.
- `src/teams_recorder/messages.py` — `Log`, where the three lines go.
- `tests/unit/test_processing_use_cases.py` — the `TranscribeMeeting` test patterns.
- `tests/unit/test_container_platforms.py` — container assertions.
- `tests/integration/test_language_whispercpp.py` (task 2) — the scripted detector for IT-002.

### Dependent Files

- `src/teams_recorder/adapters/inbound/cli.py` (task 5) — prints the record.
- `src/teams_recorder/application/use_cases/retention.py:18-26` — the purge, unchanged. Its race with a re-transcription is fail-soft (`_spec.md` › Key Decisions).

### Related ADRs

- [ADR-001](adrs/adr-001.md) — the vote and its fallback.

## Deliverables

- The detection step, the wiring, the log lines, and the tests.

## Tests

- [x] UT-030, UT-031, UT-038 — the detected language reaches the transcriber, with the offsets and window the detector receives; Portuguese is unchanged.
- [x] UT-032 — the first pass and the retry use the same language.
- [x] UT-033, UT-034 — a `TranscriptionError` or a bug in the detector falls back, logs the warning and sends no notification.
- [x] UT-035, UT-036, UT-037 — unknown duration, rate mismatch, and a transcription failure after detection.
- [x] UT-039, UT-040, UT-044 — a fixed language builds no detector. In `"auto"`, the container builds the whisper.cpp detector, and whisper never gets `"auto"`, even when the detector raises.
- [x] IT-002 — whisper failures and the missing answer line, through the real adapter and `TranscribeMeeting`.

## Success Criteria

- `tests/unit/test_pipeline.py` passes unchanged: the daemon path reaches the new step through `Pipeline` (`_tests.md` › Coverage Decisions).
- With `language = "pt"`, the transcriber and the retry receive `"pt"` and no detector exists (Safety Invariant 3).
