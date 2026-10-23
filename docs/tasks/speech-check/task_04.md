---
status: completed
title: "Task 4: Language samples only where there is speech, and the duration stand-in"
type: feature
complexity: medium
---

# Task 4: Language samples only where there is speech, and the duration stand-in

## Overview

With the check's result in hand, the language detection stops voting on silence:

- a planned 30-second sample with under 3.0 s of speech is not cut or sent;
- one surviving sample of several planned can no longer decide the language alone;
- a meeting without a recorded length plans its samples over the audio length the check measured.

## Shippable Outcome

- Outcome: in auto mode, `trec transcribe` on a meeting with silent windows sends only the windows with speech to the language detector and logs how many were dropped. The record lists only the samples sent.
- Verify in this task: the use-case cases on fakes and the `choose_language` boundary case.
- Integration verification: E2E-002 (task 6); gate G2 (task 7) on the stored recordings.

## Requirements

- Contracts:
  - `_spec.md` › Business Rules › Language samples, including the one-vote exception that follows the planned count.
  - `_spec.md` › Core Interfaces › `execute()` order steps 6–7.
  - `_spec.md` › Monitoring (`Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH`).
  - `_spec.md` › Safety Invariant 4.
- `choose_language` gains `planned: int | None = None`. None means today's behavior, so the existing language tests and callers pass unchanged. The use case passes `planned=len(offsets)`.
- `duration = meta.duration_seconds or (activity.audio_seconds if activity else None)`. The same duration feeds `sample_offsets` and the transcript health.
- With no activity (check off or failed), the samples are planned and sent exactly as today.
- When no planned sample holds speech, the result is `no-usable-sample` with the fallback, and the detector is not called.

## Subtasks

- [x] 4.1 `choose_language(..., planned=...)` in `domain/language.py`.
- [x] 4.2 `TranscribeMeeting._language` takes the activity, filters with `samples_with_speech`, logs the dropped count and passes `planned`. Add the duration stand-in in `execute`.

## Implementation Details

### Relevant Files

- `src/teams_recorder/domain/language.py:13-92` — `sample_offsets` (`:52`) and `choose_language` (`:77`). `needed = 1 if len(kept) == 1` at `:87` is where `planned` goes.
- `src/teams_recorder/application/use_cases/processing.py:77-130` — `execute` and `_language`.
- `src/teams_recorder/domain/speech.py` (task 1) — `samples_with_speech`.
- `tests/unit/test_language.py`, `tests/unit/test_processing_use_cases.py` — the suites to extend.

### Related ADRs

- [ADR-001](adrs/adr-001.md) — the check feeds the language samples.

## Deliverables

- The `planned` keyword, the filter and the stand-in in the use case, the log line, and the tests.

## Tests

- [x] UT-008 — `choose_language` with `planned` (`tests/unit/test_language.py`).
- [x] UT-044, UT-045, UT-046, UT-055, UT-056 — the filter, the stand-in, no usable sample, one sample of several, and auto mode changing only `-l`.

## Success Criteria

- Every existing language-detection test passes unchanged.
- `pytest` and `mypy` are green.
