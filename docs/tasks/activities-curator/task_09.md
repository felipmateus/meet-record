---
status: completed
title: "Task 9: Undo the last pass"
type: feature
complexity: high
---

# Task 9: Undo the last pass

## Overview

`trec activities undo` shows what the last pass changed, warns about lines the user edited after it, and on confirmation restores the document to before that pass through the same journal a pass uses: the document, then `base.md` back to the base the undone pass read, then the pass-log line, and last the archive truncated only while it is exactly as that pass left it. It never waits for a running pass and refuses if another pass committed after the preview. The next pass then sees again every edit the user made before and during the undone pass.

## Shippable Outcome

- Outcome: `trec activities undo [--yes]` behaves and prints as `_dx.md` › `trec activities undo`, including busy, nothing-to-undo, stale-preview and archive-changed cases; repeated undos walk back through not-undone passes.
- Verify in this task: UT-060–UT-066, UT-118, UT-119, UT-126, IT-006, IT-007, IT-015, IT-020, IT-021, E2E-003.
- Integration verification: none beyond E2E-003 (owned here).

## Requirements

- Contracts: `_spec.md` › Core Interfaces (`UndoLastPass`, `UndoPreview`, `UndoResult`, `PassRecord.carried_edits` / `undoes`, `VersionFiles`), › Key Decisions (undo is a commit), Safety Invariants 3, 7, 12; [ADR-003](adrs/adr-003.md) (undo through the journal; the stamp of the restored text decides reconcile); `_dx.md` › `trec activities undo`, › Errors (undo rows).
- `execute(expected_version)`: non-blocking lock → `CuratorBusy`; no not-undone pass → `NothingToUndo`; last pass ≠ previewed → `UndoStale`; `store.commit(current, N.before, [], N.prevbase, undo_record)` with `kind=undo`, `undoes=N.version`, `during_edits=N.carried_edits`, `carried_edits=""`; `base=None` when N was the first pass (deletes `base.md`); then `store.truncate_archive(N)`.
- Undo records are never undone; `preview()` skips them.
- The store methods this task exercises (`commit` with `base=None`, `version()` with absent files, `truncate_archive`, reconcile of an undo set) are implemented by task_03; fix them here if these tests expose a gap, keeping task_03's tests green.
- CLI texts in `messages.Cli` / `messages.Err`; exit 1 for busy, nothing to undo and stale.

## Subtasks

- [x] 9.1 `UndoLastPass.preview` (diff now → before, lines edited after the pass, version) and `execute`.
- [x] 9.2 `trec activities undo [--yes]` in the `activities` sub-app.
- [x] 9.3 Tests on fakes and on `FsActivityStore`, including interrupted undos.

## Implementation Details

### Relevant Files

- `src/teams_recorder/application/use_cases/activities.py` — add `UndoLastPass` next to `CurateMeetings`.
- `src/teams_recorder/adapters/outbound/activities_fs.py` — `commit`, `version`, `truncate_archive`, reconcile (task_03).
- `src/teams_recorder/adapters/inbound/cli.py` — the `activities` sub-app (task_07).
- `tests/fakes/__init__.py` — `InMemoryActivityStore` busy switch and pass list.

### Related ADRs

- [ADR-003](adrs/adr-003.md) — undo is a commit; surplus archive entries, never missing ones.

## Deliverables

- `UndoLastPass`, `trec activities undo`, messages, tests.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [x] UT-060, UT-061, UT-063, UT-066 — preview, execute through `commit`, walking back, preview after an undo.
- [x] UT-062 — `truncate_archive` only at `archive_bytes_after`.
- [x] UT-064, UT-065 — busy and stale preview.
- [x] UT-118, UT-119 — the next pass sees the user's edits again; undo of the first pass deletes `base.md`.
- [x] UT-126 — `base=None`, absent `_prevbase` / `_base`, reconcile with no stamp, undo of a pass whose `_before` had no stamp.
- [x] IT-006, IT-007 — two undos on `FsActivityStore`; a child holding the `flock` (undo busy within 1 s, `CurateMeetings(wait=True)` blocks).
- [x] IT-015, IT-020, IT-021 — interrupted undos reconciled.
- [x] E2E-003 — undo after E2E-001's fixture, then nothing left.

## Success Criteria

- `pytest` (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green.
- Undo is CLI-only: no daemon restart needed. Nothing committed without the user's approval.
