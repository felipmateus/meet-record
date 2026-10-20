---
status: completed
title: "Task 7: `trec activities`, `trec activities curate` and the curation step of `trec analyze`"
type: feature
complexity: medium
---

# Task 7: `trec activities`, `trec activities curate` and the curation step of `trec analyze`

## Overview

Gives the user and the operator the CLI of the document: `trec activities [--open]` shows where it is, the focus, the open counts, the last pass and the meetings still not curated; `trec activities curate <id>… | --since` reruns a meeting or bootstraps the document from the last working days with a confirmation; `trec analyze` curates what it just analyzed. With task_06 this completes the first usable slice: the document builds itself, and the user can rebuild or inspect it by hand.

## Shippable Outcome

- Outcome: the three commands behave and print as `_dx.md` › CLI (`trec activities`, `curate`, `analyze` curation step), with the exit codes shown there.
- Verify in this task: UT-080–UT-086, UT-088, UT-089, UT-110, E2E-001, E2E-002.
- Integration verification: task_10 owns UT-087 (both kinds of not-curated meetings, and the doctor count) and E2E-005.

## Requirements

- Contracts: `_dx.md` › CLI (`trec activities [--open]`, `trec activities curate`, `trec analyze [id]` curation step), › Errors; `_spec.md` › Core Interfaces (`ActivitiesStatus`, `ActivitiesSummary`), › System Architecture (`trec analyze` does not use `Pipeline`; curation after its loop, batches of 4 oldest first; `trec activities curate` inline with blocking lock and `on_wait`), › Config Lifecycle (`enabled = false` skips only the automatic step).
- `ActivitiesSummary` (in `application/use_cases/activities.py`) reads the box focus between its markers, counts open checkboxes per `messages.ActivityDoc` heading (lines for agenda and context; a renamed heading is omitted), and takes `updated` / titles from the last meeting/undo pass record; `not_curated` from `CurateMeetings.not_curated()`.
- `--since`: confirmation wording per `llm.provider`; estimate = passes × `Activities.EST_SECONDS_PER_PASS` (160 s); `--yes` skips it; passes run chronologically, up to 4 same-day meetings per pass; a failed meeting prints `failed: <reason>` and the command exits 1 at the end.
- `curate <id>` on a meeting that is not analyzed: `Meeting <id> is <state>, not analyzed: run trec analyze <id> first.`, exit 1; unknown id: the existing `Meeting not found` message.
- `trec analyze`: a curation failure prints `Curating … failed: <reason>` and keeps exit 0 when every analysis succeeded; a failed analysis is not curated.
- `--open`: `open` on macOS, `os.startfile` on Windows (behind `sys.platform`, injected for tests).
- All texts in `messages.Cli` / `messages.Err`; the focus lines and the curator summary are printed as stored (Portuguese content).

## Subtasks

- [x] 7.1 `ActivitiesSummary` and `ActivitiesStatus`.
- [x] 7.2 `trec activities` sub-app: the status view, `--open`, the bootstrap hint.
- [x] 7.3 `trec activities curate <id>… | --since [--yes]` with `on_wait`.
- [x] 7.4 Curation step at the end of `trec analyze`.
- [x] 7.5 Tests and the E2E journeys with the API fake transport scripted for analysis and curation.

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/inbound/cli.py:453-493` — the `analyze` loop.
- `src/teams_recorder/adapters/inbound/cli.py:189-260` — `doctor` (unchanged here; task_10), `_check_llm_prerequisites`, `_fail`.
- `tests/integration/test_cli.py`, `tests/unit/test_cli_helpers.py` — Typer runner patterns.

### Dependent Files

- `trec activities undo` (task_09) joins this sub-app; `trec doctor` / `trec status` lines (task_10) reuse `ActivitiesSummary`.

## Deliverables

- `ActivitiesSummary`, the `activities` sub-app, the `analyze` curation step, messages, tests.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [x] UT-080, UT-081, UT-088, UT-089 — `curate` errors, the `--since` confirmation and estimate, `waiting for the curator…`.
- [x] UT-082, UT-083, UT-110 — `trec activities` output, no document, the summary counts and focus.
- [x] UT-084, UT-085, UT-086 — `trec analyze` curation step, its failure, `enabled = false`.
- [x] E2E-001 — `trec analyze <id>` then `trec activities` on a fixture meeting.
- [x] E2E-002 — `trec activities curate --since 2026-10-05 --yes` over three meetings on two days.

## Success Criteria

- `pytest` (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green.
- `trec activities` (status view) never takes the curator lock.
