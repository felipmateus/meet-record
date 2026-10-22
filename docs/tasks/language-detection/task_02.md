---
status: completed
title: "Task 2: The whisper.cpp language detector"
type: feature
complexity: high
---

# Task 2: The whisper.cpp language detector

## Overview

This task builds the `LanguageDetector` port and its whisper.cpp adapter. The adapter cuts one 30-second WAV per offset with ffmpeg, runs a single `whisper-cli -l auto -dl` call over all of them, and binds each `auto-detected language` line to its clip by basename. whisper's output format is the riskiest external contract of the feature, so the adapter is tested against a scripted stand-in and, opt-in, against the real whisper.

## Shippable Outcome

- Outcome:
  - given an audio file and offsets, the real adapter returns one `LanguageSample` per offset, in order;
  - a clip past the end of the audio, or a clip with no answer, gives `None`;
  - a failure to run raises `TranscriptionError` with an `Err` message.
- Verify in this task:
  - the adapter unit tests;
  - IT-001 and IT-003, with the scripted whisper and real ffmpeg;
  - IT-004, with the real whisper (`TREC_REAL_WHISPER=1`); it runs where whisper-cli, the model and `say` are present, as on the dev Mac.
- Integration verification:
  - IT-002 (task 3) runs the adapter's failure through `TranscribeMeeting`;
  - E2E-001 (task 5) uses `ScriptedLanguageDetector`.

## Requirements

- Contracts:
  - `_spec.md` › Core Interfaces: `LanguageDetector`, `WhisperCppLanguageDetector`, `parse_detection`.
  - The bullets under Core Interfaces: the temp dir, the 1-second clip rule, the `c<i>.wav` names, the basename binding, errors and `Err.WHISPER_NO_LANGUAGE`, full paths, the `constants.Parse` regexes.
  - `_spec.md` › Architectural Boundaries and › Integration Points; Safety Invariant 4.
- Never pass `-np`: it hides the answer line. Commands use `subprocess.run` with `creationflags=NO_WINDOW`. The adapter does not import the transcriber's module.
- Errors:
  - a missing model or executable, a timeout (`Proc.LANGUAGE_DETECT_TIMEOUT = 300.0`) and a non-zero exit each raise `TranscriptionError`;
  - when whisper exits 0 and no clip gets an answer, it raises `Err.WHISPER_NO_LANGUAGE` with the output tail;
  - some clips without an answer is not an error.
- Test support (`_tests.md` › Strategy):
  - `tests/fixtures/fake_whisper_cli.py` gains a `-dl` mode. It takes `--langs code:p,…`, with `-` for no answer, and prints `main: processing '<path>' (…)` and the answer line to stderr. `--fail` and `--log` keep working.
  - `ScriptedLanguageDetector` lives next to `ScriptedTranscriber`.
  - `FakeLanguageDetector` goes in `tests/fakes/__init__.py`. Its script is a list of answers, or a mapping from audio path to answers. It records calls and can raise.

## Subtasks

- [x] 2.1 The `LanguageDetector` protocol in `application/ports.py`.
- [x] 2.2 `WhisperCppLanguageDetector` (`clip_command`, `detect_command`, `detect`, `parse_detection`, error mapping), with its `Parse`, `Proc` and `Err` entries.
- [x] 2.3 The stand-in's `-dl` mode, `ScriptedLanguageDetector` and `FakeLanguageDetector`.
- [x] 2.4 The real-whisper test with `say` clips.

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/outbound/transcriber_whispercpp.py:22-102` — the adapter shape to mirror: constructor, public `*_command`, `_run` error mapping, `NO_WINDOW`.
- `src/teams_recorder/application/ports.py:100-101` — the `Transcriber` port the new protocol sits next to.
- `src/teams_recorder/constants.py:188-280` — `Bin`, `Audio`, `Proc`, `Parse`.
- `tests/fixtures/fake_whisper_cli.py` — the stand-in to extend.
- `tests/integration/test_transcriber_whispercpp.py:25-40` — the `ScriptedTranscriber` wrapping to mirror.
- `tests/fakes/__init__.py:176-191` — `FakeTranscriber`, the model for `FakeLanguageDetector`.

### Dependent Files

- `src/teams_recorder/application/use_cases/processing.py` (task 3) — calls `detect`.
- `src/teams_recorder/container.py` (task 3) — builds the adapter.

### Related ADRs

- [ADR-001](adrs/adr-001.md) — one `-dl` call over sampled clips; non-allowed answers are kept and do not count.

## Deliverables

- The port, the adapter, the constants and messages, the stand-in mode, the two test doubles, and the tests (`tests/unit/test_language_whispercpp.py` and `tests/integration/test_language_whispercpp.py`, both new).

## Tests

- [x] UT-013, UT-014 — `clip_command` and `detect_command`: fast seek, no `-np`, full paths.
- [x] UT-015, UT-015a, UT-016 — `parse_detection`: three answers, an apostrophe in the directory, bare names, missing answers bound by file.
- [x] UT-017 — a missing model raises before anything is spawned.
- [x] IT-001 — three scripted answers bound to their offsets in one whisper call.
- [x] IT-003 — a clip past the end of a 60-second file is left out and gives `None`.
- [x] IT-004 — real whisper on English and Portuguese `say` clips (slow, opt-in).

## Success Criteria

- `--log` shows a single whisper call per `detect`, and no command carries `-np`.
- The temporary directory is gone after `detect` returns or raises (Safety Invariant 4).
