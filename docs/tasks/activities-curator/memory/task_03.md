# task_03 memory

Status: implemented and verified; changes left uncommitted.

Evidence: `pytest -q` (one session, whole fast suite) green, `mypy` clean (62 files), `tests/unit/test_no_hardcoded_strings.py` green (inside the full run, no module allowance).
New tests: `tests/integration/test_activities_store.py` (UT-125, IT-012, IT-014, lock contention with a child process, rotation, commit order and failure at each step, reconcile forward/back, archive entries, `truncate_archive`), `tests/unit/test_activity_fakes.py`; edited `tests/integration/test_repository_fs.py` (UT-109) and `tests/unit/test_fs_retry.py` (`atomic_write`).
Windows `msvcrt.locking` branch is untested (not run on Windows).

Decisions for later tasks:
- `FsActivityStore(data_dir, fmt: DocFormat, keep_versions=50, *, write=atomic_write, append=append_text, sleep=time.sleep)`. `write`/`append` are the only content writers, so tests inject a failing writer; a stop is simulated by raising a `BaseException` (the in-process rollback catches `Exception` only).
- `commit` fills `archive_file` (`arquivo/<YYYY-MM>.md`, relative to `activities/`), `archive_bytes_before`, `archive_bytes_after` on the record itself when `archived` is non-empty (month of `record.ts`); with `archived == []` the record's own archive fields are kept (None). The caller does not know the sizes.
- `version` strings must be unique per pass (files are named `<version>_<part>`; the timestamp has second resolution): an undo record needs its own version, never the undone pass's.
- `lock()` reconciles every version set with no pass-log line; roll forward when `_pass.json`, `_after` exist and `box_stamp(document)` is not None and equals `box_stamp(_after)`. A set with no `_base` file rolls forward by deleting `base.md`. A pass-log tail left cut short is dropped (or its newline completed) before the next line is appended.
- After the document replace, `base.md` and the log line are retried `Activities.COMMIT_ATTEMPTS` times, then `RepositoryError` (`Err.ACTIVITY_COMMIT_INCOMPLETE`); the document is replaced and the next `lock()` completes the pass.
- `truncate_archive` returns True when the pass archived nothing, False (logged) when the size is not `archive_bytes_after`; a file left empty is deleted (also by rollback).
- `recent_archive(limit)`: oldest first among the last `limit` entries, each `"### dd/mm/aaaa — reason\n<first text line>"`.
- `fs_retry.atomic_write` writes bytes (newlines untouched, also on Windows) and removes its temp file on failure; `repository_fs._write_atomic` is gone.
- `InMemoryActivityStore` (busy switch, `fail_commit`, `commits`, `locks`, `truncated`), `FakeActivityCurator(outputs, repairs, fail, during_call)`, repo fake `curation_errors`.
- `derive_status` unchanged; `status.CURATION_ERROR` is in the same module as the other file names.

Left to others: `keep_versions` setting (task_06), container wiring (task_06), pass-level reconcile journeys IT-013/IT-019 (task_05), undo paths (task_09), `trec doctor`/docs of the store (task_11).
