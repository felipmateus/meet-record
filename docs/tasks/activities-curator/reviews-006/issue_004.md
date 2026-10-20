---
provider: manual
pr:
round: 6
round_created_at: 2026-10-20T12:34:07Z
status: resolved
file: src/teams_recorder/adapters/inbound/cli.py
line: 562
severity: low
author: claude-code
provider_ref:
---

# Issue 004: OSError from the curator lock escapes trec analyze after analysis

## Review Comment

`_curate_passes` (used by `trec analyze` and `trec activities curate`) catches only `TeamsRecorderError` around `CurateMeetings.execute`. `FsActivityStore.lock()` raises raw `OSError` in three places, none wrapped in `RepositoryError`:
- `curator_dir.mkdir`;
- `retry_io(open(lock_file))`;
- `_reconcile` → `_complete` / `_undo_writes` → `append_text` / `_cut` / `atomic_write`.

The error raises from the `with` statement, outside `_locked`'s per-pass `try`. When any of these fails, for example ENOSPC while a reconcile rolls a set forward, `trec analyze` ends with a traceback and a non-zero exit code even though every analysis succeeded. That contradicts the code comment "a curation failure never changes the exit code" and the `_dx.md` row "Curation failed after a successful analysis → exit 0". `_check_activities` in `trec doctor` and the `trec status` line catch only `TeamsRecorderError` around `activities_summary()`, so the same applies there. `passes()` can also raise `OSError` from `retry_io`.

The daemon's `CuratorWorker._run_pass` catches `Exception`, so the daemon is not affected.

Suggested fix: translate `OSError` into `RepositoryError` at the store boundary, in `lock()` and the read methods, as AGENTS.md "Adding an adapter" step 2 requires. Alternatively, catch `OSError` next to `TeamsRecorderError` in `_curate_passes`. Add a CLI test where the store's lock raises `OSError` and assert exit 0 with a `failed:` line.

## Triage

- Decision: `VALID`
- Notes: Root cause: `FsActivityStore` let raw `OSError` out of `lock()` (mkdir, open, acquire, reconcile) and the read/commit methods; the CLI, doctor and status catch only `TeamsRecorderError`. Fix at the store boundary (AGENTS.md "Adding an adapter" step 2): `_io_boundary()` (context manager and decorator) turns `OSError` into `RepositoryError(Err.ACTIVITY_STORE_IO)` in `lock()` setup/acquire/reconcile (not around the caller's block, and the file lock is still released) and in `read_document`, `read_base`, `version`, `version_names`, `passes`, `recent_archive`, `commit`, `log_pass`, `truncate_archive`. Two existing store tests that expected a raw `OSError` from a failing `commit` now expect `RepositoryError` (message still carries the OS error, `__cause__` is the `OSError`): a contract change required by the fix, not a weakening. Regression tests: store `test_a_lock_that_cannot_be_set_up_is_a_repository_error`, `test_a_reconcile_that_cannot_complete_is_a_repository_error_and_releases_the_lock`, `test_what_the_callers_block_raises_inside_the_lock_is_not_translated`, `test_a_read_that_hits_the_file_system_error_is_a_repository_error`; CLI `test_a_store_that_cannot_lock_is_a_failed_curation_line_not_a_traceback_after_analyze` (exit 0), `..._fails_the_explicit_curate_with_exit_1_...`, `test_a_pass_log_the_file_system_cannot_read_is_reported_by_status_and_doctor_not_a_traceback`.
- Verified (round 7): `FsActivityStore.lock()` wraps only the setup (mkdir/open), `_acquire` and `_reconcile` in `_io_boundary`. Both `yield`s are outside it. Probe `/private/tmp/claude-501/-Users-felipemateusdecarvalho-Projetos-Pessoal-teams-recorder/38833900-8373-4b20-8322-07dcc789a48c/scratchpad/r7_probes.py`: an `OSError` raised by the caller's block comes out as a plain `OSError` (not translated), and so does a `RepositoryError`. In both cases a following `lock(wait=False)` gets the lock (`True`), so the flock is released. `commit` is decorated, but `CommitIncomplete` is not an `OSError` and passes through unchanged. `_rotate` still swallows its own `OSError`, so a committed pass is never reported as failed by the boundary. No caller in `application/` or `adapters/inbound/` relied on catching a raw `OSError` from the store. Full suite green.
