---
status: completed
title: "Task 8: CLI lines: doctor, status, transcribe, start"
type: feature
complexity: low
---

# Task 8: CLI lines: doctor, status, transcribe, start

## Overview

Shows the feature's state where the operator looks: `trec doctor` reports the helper's build and permission and compares them with the last recording's outcome, `trec status` and `trec transcribe` show how much of each transcript is labelled and why not, and `trec start` prints the observer line. No new verbs; the lines are the ones frozen in `_dx.md`.

## Shippable Outcome

- Outcome: the exact `trec doctor`, `trec status`, `trec transcribe` and `trec start` lines of `_dx.md`, including `· speakers 0% (<reason>)` for a transcript labelling ran on without result and the `[WARNING]` mismatch line.
- Verify in this task: UT-061–UT-065 and IT-005 through Typer's runner with stand-ins.
- Integration verification: `trec doctor` on the development Mac after task 9's build (E2E-001).

## Requirements

- Contracts: `_dx.md` › CLI (`trec doctor`, `trec transcribe`, `trec status`, `trec start` / `trec stop`) and › Errors; `_spec.md` › Agent Manageability Plan.
- `doctor`: a `speaker labels` line that never fails the doctor: off (`[speakers] enabled = false`), not built, permission missing (with the exact `--check --prompt` command and the identity decided in task 3), or ok; append the last recording's observer outcome read from the latest transcript's summary (`observer ran, NN% of lines labelled`) and print the `[WARNING]` line when `problems()` is empty but that summary's reason is `permission-missing`.
- `transcribe`: after the health line, `Speakers: NN% of M lines labelled (names)` or `Speakers: no labels (<reason text>)` from the transcript's summary (the seven reasons of the `_dx.md` table).
- `status`: `· speakers NN%` when `labels` is present, with `(reason text)` when `labelled == 0`; nothing for transcripts without a summary.
- `start`: the `Speakers:` track line with the observer pid, or `not running (<reason>; see trec doctor)`; `stop` stops the observer through the persisted handle (task 5).
- All texts in `messages.Cli`; reason texts shared with task 6's notification bodies where they coincide.

## Subtasks

- [x] 8.1 Doctor line and the mismatch warning; the helper to read the latest transcript summary.
- [x] 8.2 Transcribe and status lines; start line.
- [x] 8.3 Tests UT-061–UT-065, IT-005.

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/inbound/cli.py:70-150,155-262,263-300` — `status`, `doctor`, `start`/`stop`/`transcribe`.
- `src/teams_recorder/messages.py` › `Cli` — the doctor/status/transcribe formats.
- `tests/unit/test_cli_helpers.py`, `tests/integration/test_cli.py` — the runner patterns.
- `_dx.md` — the frozen lines.

### Dependent Files

- `src/teams_recorder/adapters/outbound/speakers_ax.py` (`problems()`), `src/teams_recorder/domain/models.py` (`LabelSummary`).

## Deliverables

- The CLI lines, their messages, the tests.

## Tests

- [x] UT-061, UT-062, UT-063 — the doctor line in the ok, permission-missing and not-built / off states.
- [x] UT-064 — status and transcribe formats, 0% with reason, no segment for old transcripts.
- [x] UT-065 — the last-recording clause and the mismatch warning.
- [x] IT-005 — `trec doctor` through the runner with stand-ins exiting 0 and 3.

## Success Criteria

- `trec doctor` exit code is unchanged by the feature in every state; the lines match `_dx.md` character for character where they are deterministic.

## Completion Notes (2026-10-17)

- Done; nothing committed. `pytest` 732 passed, 8 skipped (baseline 704 + 28 new); `mypy` clean (58 files); `tests/unit/test_no_hardcoded_strings.py` green. Nothing touched the real project, `data/`, launchctl or the daemon: IT-005 runs the stand-in helper through the fake launchctl of `tests/integration/test_speakers_observer.py`.
- Code: `cli.py` (`_check_speakers`, `_last_labels`, `_speakers_segment`, `_speakers_line`, `_load_transcript` replacing `_transcript_health`, `_observer_not_started`, `_relative`); texts in `messages.py` (`Cli.SPEAKERS_*`, `MEETING_SPEAKERS*`, `TRACK_SPEAKERS*`); the reason table `Cli.SPEAKERS_REASON` shares the `no-window` and `observer-died` wording with `Notify.NO_SPEAKER_LABELS_REASON` through two module constants.
- Tests: `tests/unit/test_cli_speakers.py` (UT-061-UT-065 and the seven-reason table, texts written out from `_dx.md`), `tests/integration/test_cli.py` (IT-005 with stand-ins exiting 0 and 3, plus the exit-0 case, status, transcribe and start lines).
- Decision from the user's review (applied, amended in `_dx.md` › `trec status`): no speakers segment for `no-observer`; `· speakers NN%` with labels; `· speakers 0% (<reason text>)` for the other zero-label reasons.
- Amendments to `_dx.md`: the doctor `[WARNING]` no longer says "for this terminal" (the check is the helper's own launchd job, task 3), replaces the `[ok ]` line and advises recording again; the `start` line reasons; `trec transcribe` prints the `Speakers:` line after the whole health block and, being explicit, the `no-observer` text.
- Choices not in the contract: the doctor line is omitted on Windows; `trec start` prints no Speakers line when the feature is off (no observer wired); a `problems()` that raises `OSError` or a domain error becomes an `[info]` "could not be checked" line; the last-recording clause for a zero-label summary is the reason text (for example `no observer data for this meeting`, which also exposes a daemon that was not restarted).
- Follow-ups: E2E-001 on the development Mac after task 9's build; the known gap from task 5 (a persisted observer handle cannot be stopped when the feature is switched off before `trec stop`) is unchanged; README/AGENTS.md/PRD lines for these outputs belong to task 9.
