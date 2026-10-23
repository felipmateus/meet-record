---
status: completed
title: "Task 3: Speech check in the transcription, its wiring and the transcribe lines"
type: feature
complexity: medium
---

# Task 3: Speech check in the transcription, its wiring and the transcribe lines

## Overview

This task solves the Motivating Problem. Before the language detection and whisper, `TranscribeMeeting` asks the speech detector how much speech the recording holds. Under 2.0 s, whisper, the language detection, the retry and the speaker labelling do not run. The transcript is saved empty with the `speech` record, a warning is logged, and a recording of 60 s or more notifies.

With speech, the transcription runs as with the check off, and the record says `found`. The container builds the detector when `speech_check` is on. `trec transcribe` prints the `Speech:` line and, for no speech, the warning block.

## Shippable Outcome

- Outcome:
  - `trec transcribe <id>` (and the daemon) on a silent recording saves an empty transcript marked "no speech", prints the `_dx.md` no-speech block and never calls whisper.
  - On a recording with speech, it runs the whisper commands that `speech_check = false` gives and prints `Speech: …` before `Health:`.
  - A failed check is a warning, and the transcription then runs without it.
- Verify in this task: the use-case cases on fakes, the container case, IT-003 and IT-004 over the stand-in, and the `trec transcribe` unit cases.
- Integration verification: E2E-001 and E2E-002 (task 6).

## Requirements

- Contracts:
  - `_spec.md` › Business Rules: No speech, What a no-speech recording gets, Notification, A recording with speech, Check off or failed.
  - `_spec.md` › Core Interfaces › `processing.py`, with the `execute()` order, steps 1–5 and 8–9. Steps 6–7 (the duration stand-in and the sample filter) are task 4.
  - `_spec.md` › Monitoring and Observability (the log lines).
  - `_spec.md` › Safety Invariants 1, 2, 4, 5, 6 and 8.
  - `_dx.md` › CLI › `trec transcribe`, › Notification, › Errors.
- `TranscribeMeeting` gains `speech_detector: SpeechDetector | None = None` and `speech_rules`, appended after `language_rules`.
- The check runs under the meeting lock, after `_rate_mismatch` and before `_language`.
- A detector failure of any kind is caught (`noqa: BLE001` with the reason). It produces one `Log.SPEECH_CHECK_FAILED` warning and never an `error.txt` or a notification.
- The no-speech transcript:
  - has `segments == []` and `language = self.language` (the fallback);
  - has no health, no `language_detection` and no labels, and does not run `_label`;
  - carries `speech = check`, and its warning is `Log.NO_SPEECH`.
- The no-speech notification is sent outside the lock, only when `check.audio_seconds >= 60.0`, with no daily de-duplication. Its exceptions are caught and logged as `Log.NO_SPEECH_NOTIFY_FAILED`, and `execute` still returns the saved transcript. The existing degraded and rate-mismatch notifications stay as they are.
- `container.py`:
  - `build_speech_detector(settings)` uses `find_tool(Bin.WHISPER_VAD, project_dir)`, `settings.speech_model_path`, ffmpeg and threads, and returns None when `speech_check` is false;
  - `Container.speech_detector` holds it;
  - `transcribe_meeting()` passes it.
- `cli.py transcribe`:
  - the `Speech:` line comes right after ` ok (…)`, in the three forms of `_dx.md`;
  - for no speech, the `WARNING:` line naming the id, and no `Health:`, `Language:` or `Speakers:` line.
  - `tests/integration/test_cli.py` and `tests/unit/test_cli_language.py` cases that assert line positions are updated where the new line shifts them.

## Subtasks

- [x] 3.1 `TranscribeMeeting`: `_speech`, `_no_speech`, the early return, the guarded notification, and `transcript.speech` on the normal path.
- [x] 3.2 Container wiring and `build_speech_detector`.
- [x] 3.3 `trec transcribe`: the `Speech:` line and the no-speech block.
- [x] 3.4 IT-003 and IT-004 over the stand-in with the file repository.

## Implementation Details

### Relevant Files

- `src/teams_recorder/application/use_cases/processing.py:32-205` — `TranscribeMeeting`, with `execute` (`:77`), `_language` (`:102`), `_transcribe` (`:179`) and the notifications (`:93-99`).
- `src/teams_recorder/container.py:132-136, 214-285` — `transcribe_meeting()`, `build_container`, `build_language_detector`.
- `src/teams_recorder/adapters/inbound/cli.py:472-512` — `transcribe`, and the `_language_line` helper at `:205`.
- `src/teams_recorder/adapters/outbound/llm_schema.py:23-33` — `trivial_analysis`, which already handles the empty transcript.
- `src/teams_recorder/adapters/outbound/repository_fs.py:189-192` — `save_transcript` (one newline for an empty `transcript.txt`).
- `tests/unit/test_processing_use_cases.py`, `tests/unit/test_cli_language.py`, `tests/integration/test_cli.py` — the suites to extend.

### Dependent Files

- `src/teams_recorder/adapters/inbound/cli.py` `status` and `doctor` (task 6) — read `transcript.speech`.

### Related ADRs

- [ADR-001](adrs/adr-001.md) — the check runs once, before everything else.

## Deliverables

- The use-case step, the container wiring, the `trec transcribe` lines, the texts and log lines, and the tests.

## Tests

- [x] UT-040, UT-041, UT-042, UT-043, UT-047, UT-048, UT-049, UT-050, UT-051, UT-052 — `TranscribeMeeting` on fakes (`tests/unit/test_processing_use_cases.py` or a new `tests/unit/test_transcribe_speech.py`).
- [x] UT-053 — the container, on and off.
- [x] UT-060, UT-061, UT-062 — the `trec transcribe` lines.
- [x] IT-003, IT-004 — the use case wired to the adapter on the stand-in, with the file repository.

## Success Criteria

- With `speech_check = false`, every existing transcription test passes unchanged.
- `pytest` and `mypy` are green.
