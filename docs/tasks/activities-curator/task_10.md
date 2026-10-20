---
status: completed
title: "Task 10: Not-curated meetings in `trec doctor` and `trec status`"
type: feature
complexity: low
---

# Task 10: Not-curated meetings in `trec doctor` and `trec status`

## Overview

Makes the document's health visible where the operator already looks: `trec doctor` gains the `Activities document` line (ok with the last pass, not created yet, or N meetings not curated), `trec status` replaces `Open actions: N` with the document's counts, and `trec activities` lists both kinds of meetings without a successful pass (failed with their error, never attempted) with their retry command. Together with the queue rebuilt at daemon start (task_06), a pass lost to a restart is either redone or shown.

## Shippable Outcome

- Outcome: `trec doctor` and `trec status` print the lines of `_dx.md` › `trec doctor` (new line) and › `trec status` (replaced line); `trec activities` lists failed and never-attempted meetings of the last 10 working days with `trec activities curate <id>`.
- Verify in this task: UT-087, E2E-005, and the status case listed inline.
- Integration verification: none.

## Requirements

- Contracts: `_dx.md` › `trec doctor` (new line), › `trec status` (replaced line), › `trec activities` (`Not curated` rules); `_spec.md` › Business Rules › Recovery (listing window of 10 working days, today is day 0).
- Reuse `ActivitiesSummary` (task_07) and `CurateMeetings.not_curated()` (task_05); no new query.
- `trec status` stops reading `open_actions.json` for this line (the planner keeps writing it until task_14).
- Texts in `messages.Cli`.

## Subtasks

- [x] 10.1 `trec doctor` line (three states).
- [x] 10.2 `trec status` line.
- [x] 10.3 The `Not curated` listing of `trec activities` (printed by task_07 from `not_curated()`) shows both reasons (`<error text>` / `not attempted yet`); fix it here if UT-087 finds a gap.
- [x] 10.4 Tests and E2E-005 (fake detector, `run_in_background` hooks).

## Implementation Details

### Relevant Files

- `src/teams_recorder/adapters/inbound/cli.py:75-140` — `status` (the `Open actions` line at `Cli.OPEN_ACTIONS`).
- `src/teams_recorder/adapters/inbound/cli.py:189-260` — `doctor`.
- `tests/unit/test_daemon.py` — `FakeContainer`, `run_in_background` hooks for E2E-005.

## Deliverables

- The doctor and status lines, the listing, tests.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [x] UT-087 — `Not curated:` lists a failed and a never-attempted meeting with retry commands; `trec doctor` counts both.
- [x] E2E-005 — daemon start on a Monday curates Friday's pending meeting; nothing listed; doctor ok.

Status case not in `_tests.md`, owned here:
- [x] `trec status` with a document of 7 open own items and 3 waiting, last pass Mon 19/10 10:12 → `Activities: 7 yours · 3 waiting on others (last pass Mon 19/10 10:12)`; no `Open actions:` line.

## Success Criteria

- `pytest` (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green.
- CLI-only change: no daemon restart needed.
