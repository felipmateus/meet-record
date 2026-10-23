---
status: completed
title: "Task 1: Speech domain, transcript record and the speech_check key"
type: feature
complexity: low
---

# Task 1: Speech domain, transcript record and the speech_check key

## Overview

This task lays down what every later task reads:

- the pure rules that decide "no speech" and measure speech inside a window;
- the `speech` record on the transcript and in `transcript.json`;
- the `[transcription] speech_check` key.

Nothing calls them yet. Every meeting is still transcribed as today until task 3 wires the check.

## Shippable Outcome

- Outcome:
  - `trec` loads the repository's `config.toml` with `speech_check = true`; a config without the key also means `true`.
  - A `transcript.json` loads with or without `speech`. A damaged `speech` is reported as `RepositoryError` naming the file.
  - Transcription behavior is unchanged.
- Verify in this task: the assigned unit tests, `mypy`, and the existing suite unchanged.
- Integration verification: E2E-001 (task 6).

## Requirements

- Contracts:
  - `_spec.md` › Business Rules › No speech and Language samples (the 2.0 s and 3.0 s thresholds).
  - `_spec.md` › Core Interfaces › `domain/speech.py`.
  - `_spec.md` › Data Models: the `speech` JSON shape, the strict decoder checks, the config key and `Settings.speech_model_path`.
  - `_dx.md` › Config and › Files.
- `domain/speech.py` is pure: it imports only the standard library and `domain` (`_spec.md` › Architectural Boundaries).
- The `speech` decoder checks types and never coerces, unlike the `language_detection` decoder:
  - the record is a `dict`;
  - `found` is a `bool`;
  - `segments` is an `int` and not a `bool`;
  - the seconds are finite `int` or `float` values, not `bool`, reusing `_finite`.
  - Each failure raises `TypeError`, which `repository_fs._decode` turns into `RepositoryError`.
- The encoder writes `speech` only when it is set. The 28 stored transcripts load unchanged (UT-022).
- `speech_check` is parsed with `bool(...)`, like `vad` and `retry_vad`.
- `Settings.speech_model_path` is `models_dir / ggml_model_file(vad_model)` when `speech_check` is set, else None.
- The repository's `config.toml` gets the key with the comment from `_dx.md` › Config.
- New texts go in `messages.py`. New constants go in `constants.py` (`Bin.WHISPER_VAD`, `Proc.SPEECH_CHECK_TIMEOUT`, and so on, as `_spec.md` › Impact Analysis lists them). Add the ones later tasks need only when they are shared contract; leave the rest to their tasks.

## Subtasks

- [x] 1.1 `domain/speech.py`: `SpeechRules`, `SpeechActivity` (`speech_seconds`, `speech_between`), `SpeechCheck`, `check_speech`, `samples_with_speech`, exported from `domain/__init__.py`.
- [x] 1.2 `Transcript.speech` and its codec, tested through the file repository.
- [x] 1.3 The `speech_check` key, `Settings.speech_check` and `Settings.speech_model_path`, and the repository's `config.toml`.

## Implementation Details

### Relevant Files

- `src/teams_recorder/domain/models.py:97-163` — `Transcript`, which gains `speech`.
- `src/teams_recorder/domain/language.py` — the shape of a pure domain module to mirror.
- `src/teams_recorder/adapters/outbound/codec.py:140-200` — `transcript_to_dict`, the coercing `language_detection` decoder (not to copy), and `_finite`.
- `src/teams_recorder/adapters/outbound/repository_fs.py:58-73` — how a decoding error becomes `RepositoryError`.
- `src/teams_recorder/config.py:50-61, 81-146, 280-315` — `Settings` and the `[transcription]` parsing.
- `src/teams_recorder/constants.py`, `src/teams_recorder/messages.py` — where the texts and constants go.
- `config.toml` — the `[transcription]` section.

### Dependent Files

- `src/teams_recorder/adapters/outbound/speech_whispercpp.py` (task 2) — returns `SpeechActivity`.
- `src/teams_recorder/application/use_cases/processing.py` (tasks 3 and 4) — calls `check_speech` and `samples_with_speech`.

### Related ADRs

- [ADR-001](adrs/adr-001.md) — whole-audio VAD before transcription.

## Deliverables

- The domain module, the transcript field and codec, the config key, the texts and constants, and the tests.

## Tests

- [x] UT-001, UT-002, UT-003, UT-004, UT-005, UT-006, UT-007 — `domain/speech.py` (`tests/unit/test_speech.py`, new).
- [x] UT-020, UT-021, UT-022, UT-023 — the `speech` codec, damaged shapes through `FsMeetingRepository`.
- [x] UT-025 — the config key and `speech_model_path` (`tests/unit/test_config.py`).

## Success Criteria

- `pytest` and `mypy` are green, and no existing test changed.
