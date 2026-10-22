---
status: completed
title: "Task 1: Language domain, settings, transcript record and the never-auto guard"
type: feature
complexity: medium
---

# Task 1: Language domain, settings, transcript record and the never-auto guard

## Overview

This task lays down what every later task reads:

- the pure rules that place the samples and choose the language;
- the two `[transcription]` keys and their validation;
- the `language_detection` record on the transcript and in `transcript.json`.

It also changes the default to `"auto"`. To keep that safe, the container passes the fallback language and `TranscribeMeeting` refuses `"auto"`, so every meeting is still transcribed in Portuguese until the detector is wired in task 3.

## Shippable Outcome

- Outcome:
  - `trec` loads the repository's `config.toml` with `language = "auto"` and `languages = ["pt", "en"]`, and rejects invalid values with the `_dx.md` › Errors messages.
  - `trec transcribe` still runs whisper with `-l pt`.
  - A `transcript.json` loads with or without `language_detection`; a damaged one is reported as `RepositoryError` naming the file.
- Verify in this task: the assigned unit tests. The existing transcription and container tests stay green with the new default.
- Integration verification: E2E-001 (task 5).

## Requirements

- Contracts:
  - `_spec.md` › Business Rules: Samples, Counted samples, Decision, Validation.
  - `_spec.md` › Core Interfaces: `domain/language.py`, and `TranscribeMeeting.language` with `__post_init__`.
  - `_spec.md` › Data Models: fields, JSON shape, codec rules, config keys, `Settings`, constants, language names.
  - `_spec.md` › Safety Invariant 6.
  - `_dx.md` › Config and › Errors.
- `domain/language.py` is pure: it imports only the standard library and `domain` (`_spec.md` › Architectural Boundaries). Offsets are rounded to 0.1 s (UT-001).
- `languages`:
  - it is validated in both modes, and used only when `language` is `"auto"`;
  - a single string is read as a list of one;
  - duplicates are dropped, and the first occurrence keeps its place.
- Decoder of `language_detection`:
  - it checks the object and each sample with `isinstance(…, dict)`, raising `TypeError(Err.BAD_LANGUAGE_DETECTION…)`;
  - an unknown reason raises `ValueError` from `LanguageReason(…)`;
  - it never calls `.get` on an unchecked value, because `repository_fs.py:58-73` lets `AttributeError` through.
- The never-auto guard:
  - `Container.transcribe_meeting()` passes `language=settings.fallback_language`, never `settings.language` (today `container.py:130` passes `settings.language` positionally);
  - `TranscribeMeeting.__post_init__` raises `ValueError` when `language` is not a code.
- The repository's `config.toml` gets both keys with the comment shown in `_dx.md` › Config.
- New texts go in `messages.py`: `Err.INVALID_LANGUAGE`, `Err.INVALID_LANGUAGES`, `Err.BAD_LANGUAGE_DETECTION`, `Prompt.LANGUAGE_NAMES`, `Minutes.LANGUAGE_NAMES`.
- New constants go in `constants.py`: `Transcription.AUTO`, `LANGUAGES`, `LANGUAGE_CODE`.

## Subtasks

- [x] 1.1 `domain/language.py`: `LanguageRules`, `LanguageSample`, `LanguageReason`, `LanguageDetection`, `sample_offsets`, `choose_language`, `counted_tally`.
- [x] 1.2 `Transcript.language_detection` and its codec, tested through the file repository.
- [x] 1.3 Config keys, validation, `Settings.detects_language` / `fallback_language`, and the repository's `config.toml`.
- [x] 1.4 The never-auto guard: `TranscribeMeeting.__post_init__` and the container's `fallback_language`.

## Implementation Details

### Relevant Files

- `src/teams_recorder/domain/models.py:136-160` — `Transcript`, which gains `language_detection`.
- `src/teams_recorder/adapters/outbound/codec.py:85-150` — transcript (de)serialization, and the `isinstance` check on `speakers` to mirror.
- `src/teams_recorder/adapters/outbound/repository_fs.py:58-73` — how a decoding error becomes `RepositoryError`.
- `src/teams_recorder/config.py:63-110, 236-335` — `Settings` and `load_settings`, with `_parse_share` and `_as_list` as validation patterns.
- `src/teams_recorder/constants.py:188-280` — `Audio` and `Transcription`, where the constants go.
- `src/teams_recorder/application/use_cases/processing.py:29-60` — `TranscribeMeeting` fields.
- `src/teams_recorder/container.py:129-131` — `transcribe_meeting()`.
- `config.toml` — the `[transcription]` section.

### Dependent Files

- `src/teams_recorder/adapters/outbound/language_whispercpp.py` (task 2) — returns `LanguageSample`.
- `src/teams_recorder/adapters/inbound/cli.py` (task 5) — reads `LanguageDetection` and `counted_tally`.

### Related ADRs

- [ADR-001](adrs/adr-001.md) — samples spread over the meeting, allow-list vote.

## Deliverables

- The domain module, the transcript field and codec, the config keys and validation, the guard, the texts and constants, and the tests.

## Tests

- [x] UT-001, UT-002, UT-003, UT-004, UT-005, UT-006 — `sample_offsets`: spacing, caps, bounds (`tests/unit/test_language.py`, new).
- [x] UT-007, UT-008, UT-009, UT-010, UT-011, UT-012, UT-012a, UT-012b, UT-012c — `choose_language` and `counted_tally` (same suite).
- [x] UT-020, UT-021, UT-022, UT-023, UT-024, UT-025, UT-025a, UT-026 — config keys and validation (`tests/unit/test_config.py`).
- [x] UT-041, UT-042, UT-043 — the codec: a round trip, an absent record, damaged records through `FsMeetingRepository`.
- [x] UT-045 — `TranscribeMeeting(…, language="auto")` raises `ValueError` (`tests/unit/test_processing_use_cases.py`).

## Success Criteria

- The 27 stored transcripts load unchanged, and `transcript_to_dict` writes no `language_detection` key for them (UT-042).
- Under the new default, `trec transcribe` still invokes whisper with `-l pt`, as the existing transcriber and container tests show.
