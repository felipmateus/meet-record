---
status: completed
title: "Task 5: The curation use case"
type: feature
complexity: high
---

# Task 5: The curation use case

## Overview

`CurateMeetings` runs a pass end to end: under the store lock it reads the document (creating the skeleton on first use), the base and the user's edits, builds the curator input with each meeting's analysis and transcript excerpts, calls the curator, re-reads the file, applies the edits, sends failures to one repair round, renders the box and links, rescues lines the user typed in the box, and commits; it notifies when the pass concerns the user, records failures without touching the meeting status, isolates a failed batch before counting attempts, and answers which meetings still need a pass. This is the heart of the Motivating Problem: after it, one document holds everything still open.

## Shippable Outcome

- Outcome: `CurateMeetings.execute(ids)` produces a committed `atividades.md` whose box, sections and link block follow `_dx.md`, never drops or changes a checkbox outside `archive`, keeps every user edit made before or during the call, and writes `curation_error.txt` plus a failure notification when a single-meeting pass fails; `pending()` and `not_curated()` list the meetings that need a pass.
- Verify in this task: the unit cases on fakes and the integration cases on `FsActivityStore` listed below.
- Integration verification: task_06 (IT-001, IT-002, IT-008: through the pipeline and the real adapter); task_07 (E2E-001, E2E-002 through the CLI).

## Requirements

- Contracts: `_spec.md` › System Architecture (the `CurateMeetings` flow, step by step), › Core Interfaces (`application/use_cases/activities.py` block: `NotCurated`, `PassResult`, `CurateMeetings`), › Business Rules (Batching, Recovery, Empty analysis, Notification, Typed in the box), › Key Decisions (base.md = the curator's output without rescue lines plus `during_edits`; a failed batch is isolated before it is counted; recovery by window), Safety Invariants 1, 3, 4, 8, 9, 11, 12; `_dx.md` › Notifications, › Errors (pass rows).
- `user_edits` = the last meeting/undo record's `during_edits` + `unified_diff(body(base), body(document))`; `""` on the first pass. `during_edits = unified_diff(body(F), body(F'))`. `base = render_links(render_box(W, …, stamp=version))` without rescue lines; rescue lines go to the document only.
- `MeetingContext.excerpts` is built with `domain.excerpts.excerpt_window` (±60 s around each status update's `at`, merged, speaker labels) — the `CurateMeetings` clause of UT-053 (task_01); assert it in this task's input checks.
- Skeleton from `messages.ActivityDoc`, its closing marker carrying `Activities.SKELETON_STAMP`.
- Batches of at most 4, oldest first; a failed multi-meeting pass re-runs each meeting alone; only a failed single-meeting pass is that meeting's failure (error file, attempt, notification).
- `pending(max_attempts=2, working_days=2)` and `not_curated(working_days=10)` count today as day 0 via `working_days_ago`. The window is decided by the meeting's own date (`Meeting.day`) with `derive_status == ANALYZED` (settled in `_spec.md` › Business Rules › Recovery).
- `execute(…, wait, on_wait)`: tries the lock without blocking first; when busy and `wait=True`, calls `on_wait()` once, then blocks.
- Notification: one `Activities updated` with the curator's summary when the curator says `notify` and `[activities] notify` (the `notify` field) is true; failures always notify (`Activity curation failed`). Texts in `messages.Notify`, errors in `messages.Err`, logs in `messages.Log`; defaults (batch size, windows, attempts, archive entries sent = 60, excerpt window) in `constants.Activities`.
- Never writes `error.txt`, never changes `derive_status`.

## Subtasks

- [x] 5.1 Input building: skeleton, base/document/user edits, box lines, recent archive, last summary, calendar, `MeetingContext` with excerpts; empty-analysis skip.
- [x] 5.2 Apply, repair once, render box and links, rescue box lines, commit with the `PassRecord`; archive and `user_removed` entries.
- [x] 5.3 Failure path (failed record, error file, notification), success path (clear error file, notification rules).
- [x] 5.4 Batching and the one-at-a-time re-run of a failed batch; `wait` / `on_wait`.
- [x] 5.5 `pending()` and `not_curated()`.
- [x] 5.6 Tests on fakes and on `FsActivityStore`.

## Implementation Details

### Relevant Files

- `src/teams_recorder/application/use_cases/activities.py` — `doc_format()` from task_02; add the use case here.
- `src/teams_recorder/application/use_cases/processing.py:164-185` — `AnalyzeMeeting`, how analyses and health are loaded.
- `src/teams_recorder/application/use_cases/planning.py:45-70` — `BuildDailyPlan`'s selection of a day's analyzed meetings (precedent for the window).
- `src/teams_recorder/domain/activities.py`, `src/teams_recorder/domain/excerpts.py` — the functions this use case composes.
- `tests/fakes/__init__.py` — `FakeActivityCurator`, `InMemoryActivityStore`, repository/notifier/clock fakes.

### Dependent Files

- `src/teams_recorder/container.py`, `adapters/inbound/daemon.py` (task_06), `adapters/inbound/cli.py` (task_07), `UndoLastPass` (task_09).

### Related ADRs

- [ADR-001](adrs/adr-001.md) — one rule enforced edit by edit; one repair round.
- [ADR-003](adrs/adr-003.md) — what the pass hands to `commit`.

## Deliverables

- `CurateMeetings`, `PassResult`, `NotCurated`, the message and constant entries, Portuguese fixtures, tests.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [x] UT-030, UT-031, UT-032, UT-033, UT-035 — a pass, the skeleton, the empty analysis, box lines and `user_edits` in the input.
- [x] UT-034, UT-036, UT-037, UT-104 — rule failure after repair, one repair call, transport error, a rule failure repaired.
- [x] UT-046, UT-047, UT-048, UT-049, UT-100, UT-123 — edits during the call, box rescue, base built from the written text, each user edit seen once.
- [x] UT-038, UT-039, UT-101, UT-106 — `pending()`, error file cleared, the working-day window, `not_curated()`.
- [x] UT-040, UT-041 — archive entries (rendered by the store) and `removido por você`.
- [x] UT-042, UT-102, UT-105 — four per pass, failed batch isolated, `on_wait`.
- [x] UT-043, UT-044 — notification rules.
- [x] IT-003, IT-004, IT-005, IT-010, IT-016 — rerun, a tick rejected, a user edit during the call, concurrent passes serialised, deletion and box line during the call, on `FsActivityStore`.
- [x] IT-013, IT-019 — interrupted commits reconciled by the stamp, seen through the next pass.

## Success Criteria

- `pytest` (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green.
- No path of `CurateMeetings` writes `error.txt` or raises out of a failed pass (the result carries it).
