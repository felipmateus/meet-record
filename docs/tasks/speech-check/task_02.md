---
status: completed
title: "Task 2: The whisper.cpp speech detector and the shared WAV conversion"
type: feature
complexity: medium
---

# Task 2: The whisper.cpp speech detector and the shared WAV conversion

## Overview

This task adds the `SpeechDetector` port and its adapter. The adapter converts the meeting's audio to a 16 kHz WAV and runs whisper.cpp's `whisper-vad-speech-segments` with Silero VAD over it. It then returns the audio's length and the speech segments.

A format change in the tool's output must read as a failed check, never as "no speech". The conversion moves to a neutral module shared with the transcriber, so neither adapter imports the other.

## Shippable Outcome

- Outcome: `WhisperCppSpeechDetector(...).activity(audio)` returns a `SpeechActivity` from the real tool. Every failure raises `TranscriptionError`, and no temporary folder is left behind.
- Verify in this task:
  - the unit cases;
  - IT-001 and IT-002 against the stand-in with real ffmpeg;
  - IT-005 with the real tool when `TREC_REAL_WHISPER=1` (it needs no Claude credit, so run it);
  - `tests/unit/test_transcriber.py::test_commands` passing as written after the extraction.
- Integration verification: IT-003 and IT-004 (task 3), E2E-001 and E2E-002 (task 6).

## Requirements

- Contracts:
  - `_spec.md` › Core Interfaces › `application/ports.py` and `adapters/outbound/speech_whispercpp.py`, including the parser rules.
  - `_spec.md` › Integration Points.
  - `_spec.md` › Safety Invariant 3 (no file in the meeting folder; temp dir `trec-speech-`, removed on success and failure).
  - `_dx.md` › Errors.
- `vad_command(wav)` is exactly `[tool, "-vm", model, "-f", wav, "-np", "-t", threads, *Audio.VAD_ARGS]` (UT-030).
- `parse_speech_segments`:
  - reads `Detected <n> speech segments:` and the n `Speech segment <i>: start = <cs>, end = <cs>` lines, in centiseconds;
  - raises `TranscriptionError(Err.VAD_BAD_OUTPUT)`, with the output tail, when the count line is missing or n differs from the lines read;
  - regexes go in `constants.Parse`.
- The audio length comes from the converted WAV (`frames / rate`), not from `meta.json`.
- The model and the audio are checked before any process starts (`Err.MODEL_MISSING`, `Err.AUDIO_MISSING`).
- Process errors map like `language_whispercpp.py`: `Err.EXECUTABLE_MISSING`, `Err.TIMED_OUT`, `Err.STEP_FAILED_CODE` with the tail. Spawns use `creationflags=NO_WINDOW`.
- `adapters/outbound/audio_convert.py` holds `wav_convert_command(ffmpeg, audio, wav)`, which returns today's argv and imports only `constants`. `WhisperCppTranscriber.convert_command` delegates to it unchanged.
- `tests/fixtures/fake_whisper_vad.py` prints the real tool's format, with these flags: `--segments`, `--none`, `--garbled`, `--mismatch`, `--fail`, `--log`. `ScriptedSpeechDetector` appends them to `vad_command`, as `ScriptedLanguageDetector` does.
- `FakeSpeechDetector` goes in `tests/fakes/__init__.py`. It returns a scripted activity or a per-audio mapping, or raises a scripted exception, and records the audio paths it was given (`_tests.md` › Strategy).

## Subtasks

- [x] 2.1 `audio_convert.wav_convert_command`, and the transcriber delegating to it.
- [x] 2.2 The `SpeechDetector` port and `FakeSpeechDetector`.
- [x] 2.3 `WhisperCppSpeechDetector`, `parse_speech_segments`, and their texts and constants.
- [x] 2.4 The `fake_whisper_vad.py` stand-in, the adapter tests and the opt-in real test.

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/outbound/language_whispercpp.py` — the adapter pattern to mirror (temp dir, `_run`, errors as `TranscriptionError`, output tail).
- `src/teams_recorder/adapters/outbound/transcriber_whispercpp.py:43-60` — `convert_command` and the use of `Audio.VAD_ARGS`.
- `src/teams_recorder/application/ports.py` — where the port goes, next to `LanguageDetector`.
- `tests/fixtures/fake_whisper_cli.py`, `tests/integration/test_language_whispercpp.py` — the stand-in and `Scripted…` patterns.
- `tests/fakes/__init__.py` — `FakeLanguageDetector`, the model for `FakeSpeechDetector`.

### Dependent Files

- `src/teams_recorder/container.py` (task 3) — builds the detector.
- `tests/unit/test_transcriber.py::test_commands` — must pass unchanged.

### Related ADRs

- [ADR-001](adrs/adr-001.md) — why whisper.cpp's separate VAD tool.

## Deliverables

- The port, the fake, the adapter and parser, the conversion module, the stand-in, and the tests.

## Tests

- [x] UT-030, UT-031, UT-032, UT-033, UT-034, UT-035, UT-036 — command, parser, missing inputs, process errors (`tests/unit/test_speech_whispercpp.py`, new).
- [x] IT-001, IT-002 — the adapter with the stand-in and real ffmpeg (`tests/integration/test_speech_whispercpp.py`, new).
- [x] IT-005 — the real tool on silence and on `say` speech (slow, `TREC_REAL_WHISPER=1`).

## Success Criteria

- No `trec-speech-` folder is left in the temp dir after any test.
- `pytest` and `mypy` are green.
