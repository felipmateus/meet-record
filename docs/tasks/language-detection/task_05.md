---
status: completed
title: "Task 5: Language lines in transcribe, status, doctor and the minutes"
type: feature
complexity: low
---

# Task 5: Language lines in transcribe, status, doctor and the minutes

## Overview

This task makes the language visible where the user and the operator look:

- the `Language:` line of `trec transcribe`, in its six forms;
- the `· en` marker in `trec status`;
- the `language:` line of `trec doctor`;
- the `🗣️ **Idioma:**` line of the minutes.

It also carries the two end-to-end journeys that prove the whole path through the CLI.

## Shippable Outcome

- Outcome: an English meeting shows `Language: en (…)` in `trec transcribe`, `· en` in `trec status` and `🗣️ **Idioma:** inglês` in `minutes.md`. `trec doctor` prints the mode right after the retry line. A Portuguese meeting shows no marker and no minutes line.
- Verify in this task: the CLI and minutes unit tests, and E2E-001 and E2E-002 through `tests/integration/test_cli.py`.
- Integration verification: none. The gates in task 6 reuse this evidence for the CLI.

## Requirements

- Contracts:
  - `_dx.md` › CLI (`trec transcribe`: the six forms and the line's place; `trec status`; `trec doctor`: right after `retry of a degraded transcript:`) and › Files (the minutes line).
  - `_spec.md` › Impact Analysis: the `MinutesRenderer` / `minutes_markdown` / `AnalyzeMeeting` / `RenderMinutes` / `FakeMinutesRenderer` row, and the `cli.py` row.
  - `_spec.md` › Monitoring and Observability: why the failure line says `see the warning above`.
  - US-005, US-006, US-007.
- `MinutesRenderer.render(…, language=None)` is a keyword. `AnalyzeMeeting` passes `transcript.language`. `RenderMinutes` passes the language of the transcript it already loads, and `None` when there is none. `FakeMinutesRenderer.render` gains the keyword and records it in `languages`, or every use-case test that uses it raises `TypeError`.
- The `Language:` line goes after the health block (the `Health:` line and any `WARNING:` lines under it) and before `Speakers:` and `Text:`. The `no majority` and `too few votes` forms use `counted_tally` (task 1).
- `FakeTranscriber` gains `by_audio: dict[Path, Transcript]` for E2E-002 (`_tests.md` › Strategy).
- Texts go in `messages.Cli` and `messages.Minutes`.

## Subtasks

- [x] 5.1 `trec transcribe`: the `Language:` line in its six forms.
- [x] 5.2 `trec status` marker and the `trec doctor` line.
- [x] 5.3 The minutes line: the renderer keyword, `AnalyzeMeeting`, `RenderMinutes` and `FakeMinutesRenderer`.
- [x] 5.4 E2E-001 and E2E-002, with `FakeTranscriber.by_audio`.

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/inbound/cli.py:85-115, 210-300, 432-472` — `status`, `doctor` (`_check_transcript_health`, whose retry line is the anchor) and `transcribe`.
- `src/teams_recorder/application/ports.py:123` — `MinutesRenderer.render`.
- `src/teams_recorder/adapters/outbound/minutes_markdown.py`, `src/teams_recorder/messages.py:720-750` — the minutes header lines.
- `src/teams_recorder/application/use_cases/processing.py:188-202` — `RenderMinutes`.
- `tests/fakes/__init__.py:176-191, 432-437` — `FakeTranscriber` and `FakeMinutesRenderer`.
- `tests/unit/test_cli_speakers.py` — the pattern for CLI line tests.
- `tests/unit/test_minutes_markdown.py`, `tests/integration/test_cli.py` — the owning suites.

### Dependent Files

- `docs/guide/commands.md` (task 6) — the `trec transcribe` row names the new line.

## Deliverables

- The CLI, status, doctor and minutes lines, the fake changes, and the tests.

## Tests

- [x] UT-060, UT-061, UT-062, UT-062a, UT-063, UT-064 — the `Language:` line in its six forms. UT-063 asserts the stdout line through `CliRunner` and the WARNING record with `caplog`.
- [x] UT-065, UT-066 — the status marker.
- [x] UT-067, UT-068 — the doctor line, its place after the retry line, and an unchanged exit code.
- [x] UT-070, UT-071, UT-072 — the minutes line for `en`, `pt`/None and `es`.
- [x] UT-073 — both use cases pass the language to the renderer.
- [x] E2E-001 — an English meeting through `trec transcribe` and `trec status`, with the scripted detector.
- [x] E2E-002 — two meetings with different languages, one of them degraded: one `Language:` line per meeting, in place.

## Success Criteria

- `trec minutes --all` on the stored meetings renders minutes identical to today's (all `pt`, US-006.EC-2).
- The existing CLI and minutes tests pass unchanged, apart from the `FakeMinutesRenderer` signature.
