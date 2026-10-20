---
status: completed
title: "Task 3: Ports, fakes and the file-backed activity store"
type: feature
complexity: critical
---

# Task 3: Ports, fakes and the file-backed activity store

## Overview

Defines the shared contracts of the feature (`ActivityCurator`, `ActivityStore`, `VersionFiles`, the `MeetingRepository` error-file methods, the new domain errors) and implements `FsActivityStore`: the OS lock that serialises passes, the recoverable commit order of ADR-003 (version files → archive → document carrying the stamp → `base.md` → pass-log line as commit point), in-process rollback, reconciliation of an interrupted commit at the next `lock()`, version rotation and the pass log. This is the riskiest file-system work of the feature: it owns the document the user edits by hand.

## Shippable Outcome

- Outcome: `FsActivityStore` under `<data_dir>/activities/` commits a pass all or nothing, and after a hard stop the next `lock()` rolls it forward or back by the box stamp; the meeting repository writes and clears `recordings/<id>/curation_error.txt`; the fakes let use-case tests run without files.
- Verify in this task: UT-109, UT-125, IT-012, IT-014, plus the store cases listed inline below.
- Integration verification: task_05 owns the pass-level reconcile journeys (IT-013, IT-019) and the archive-entry rendering check (UT-040); task_09 owns the undo paths through this store (UT-062, UT-126, IT-015, IT-020, IT-021).

## Requirements

- Contracts: `_spec.md` › Core Interfaces (`application/ports.py` block, `domain/errors.py` block), › Data Models › Files (paths, archive entry shape, `_pass.json`, `log/activities.jsonl`), › Key Decisions (lock held through the call, flock over a PID file, commit order, undo is a commit, atomic write helper), Safety Invariants 2, 3, 6; [ADR-003](adrs/adr-003.md) in full.
- Implement the whole `ActivityStore` port as specified, including `commit(…, base=None, …)`, `version()` returning `None` for absent files, `_prevbase`, `truncate_archive` and `archive_bytes_after`; undo consumes them in task_09.
- Reconcile rule: roll forward only when `box_stamp(document)` is not None and equals `box_stamp(_after)`; otherwise roll back (a missing stamp is never "replaced"). `PassRecord.version` is never compared with a stamp. A set with no `_base` file rolls forward by deleting `base.md`.
- `passes()` treats a torn last JSONL line as absent.
- Archive entries `### dd/mm/aaaa — <reason>` + verbatim text + link definitions with `../../recordings/…`, appended to `arquivo/<AAAA-MM>.md` after recording each file's size; sizes before/after go into `_pass.json` before the append.
- Keep `keep_versions` passes (default 50; the setting arrives in task_06, take it as a constructor argument).
- Lock: `fcntl.flock` on `activities/.curator/lock`; `lock(wait=False)` yields False when busy. Windows: `msvcrt.locking` in a retry loop under `if sys.platform == "win32":` (untested on Windows; say so when reporting).
- `repository_fs._write_atomic` moves to `fs_retry.atomic_write`, used by both repositories (internal hard cut); all file I/O goes through `fs_retry.retry_io`.
- `domain/status.py`: `CURATION_ERROR = "curation_error.txt"  # not part of status`; `derive_status` unchanged. The error file is written atomically without the meeting `.lock`.
- New file and folder names in `constants.Files`; log templates in `messages.Log`.
- Fakes in `tests/fakes/__init__.py`: `InMemoryActivityStore` (busy switch for `lock(wait=False)`, records commits, passes, versions), `FakeActivityCurator` (scripted `CuratorOutput`s and repair answers, records inputs, a hook that runs between the snapshot and the re-read so tests can edit the document "during the call"), the repository fake's error-file methods.

## Subtasks

- [x] 3.1 Ports, `VersionFiles`, domain errors (`CuratorBusy`, `NothingToUndo`, `UndoStale`), `status.CURATION_ERROR`.
- [x] 3.2 `fs_retry.atomic_write` (moved) and the repository's error-file methods.
- [x] 3.3 `FsActivityStore`: paths, lock, reads, `recent_archive`, `passes`, `version`, `path`.
- [x] 3.4 `commit` in the recoverable order with in-process rollback; version rotation.
- [x] 3.5 Reconciliation on `lock()` entry; `truncate_archive`.
- [x] 3.6 Fakes and tests.

## Implementation Details

### Relevant Files

- `src/teams_recorder/application/ports.py:149-192` — `MeetingRepository`; new Protocols go alongside.
- `src/teams_recorder/adapters/outbound/repository_fs.py:43-47,150-159` — atomic write and the meeting lock pattern.
- `src/teams_recorder/adapters/outbound/fs_retry.py` — `retry_io`; receives `atomic_write`.
- `src/teams_recorder/adapters/outbound/codec.py` — where a `PassRecord` ↔ JSON codec fits.
- `src/teams_recorder/domain/status.py:11-23`, `src/teams_recorder/domain/errors.py`.
- `tests/fakes/__init__.py`, `tests/integration/test_repository_fs.py`, `tests/unit/test_fs_retry.py`.

### Dependent Files

- `src/teams_recorder/container.py` builds the store in task_06.
- `application/use_cases/activities.py` (task_05, task_09) and `use_cases/stories.py` (task_13) take the lock.

### Related ADRs

- [ADR-003](adrs/adr-003.md) — commit order, stamp-based reconcile, undo through the same journal.

## Deliverables

- `src/teams_recorder/adapters/outbound/activities_fs.py`, the port and error additions, the repository methods, the moved atomic write, the fakes and tests.

## Tests

Cases assigned from `_tests.md` — read each assigned definition before editing.

- [x] UT-109 — `curation_error.txt` round trip without the meeting `.lock`; `derive_status` unchanged.
- [x] UT-125 — torn last pass-log line.
- [x] IT-012 — the document replace raises: everything as before, error re-raised, no pass-log line.
- [x] IT-014 — stop after the archive append, before the replace: rolled back at the next `lock()`.

Store cases not in `_tests.md` (from `_spec.md` › Testing Approach), owned here:
- [x] `lock(wait=False)` yields False while a child process holds the `flock`, True after it exits.
- [x] After `keep_versions + 1` committed passes only the newest `keep_versions` version sets remain.
- [x] A commit writes `_before`, `_after`, `_base`, `_prevbase` (absent when there was no `base.md`) and `_pass.json` with `archive_bytes_before` / `archive_bytes_after`, then the archive, document, `base.md` and the pass-log line, in that order (observable through an injected failing writer at each step).

## Success Criteria

- `pytest` (one session) and `mypy` green; `tests/unit/test_no_hardcoded_strings.py` green.
- `tests/integration/test_repository_fs.py` green after the atomic-write move.
