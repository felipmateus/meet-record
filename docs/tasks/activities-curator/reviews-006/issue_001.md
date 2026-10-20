---
provider: manual
pr:
round: 6
round_created_at: 2026-10-20T12:34:07Z
status: resolved
file: src/teams_recorder/application/use_cases/activities.py
line: 360
severity: high
author: claude-code
provider_ref:
---

# Issue 001: Incomplete commit is logged as failed and never reconciled

## Review Comment

Round 6 is the first review of the implementation (slice 1). Rounds 001–005 reviewed the spec document.

`FsActivityStore.commit` raises `RepositoryError(ACTIVITY_COMMIT_INCOMPLETE)` when the document was already replaced but `base.md` or the pass-log line could not be written after `COMMIT_ATTEMPTS` tries (`activities_fs.py` `_finish` / `_retried`). The message says "the next pass completes it", and the store test `test_a_persistent_failure_after_the_replace_is_reported_and_completed_by_the_next_lock` covers that at the store level. `CurateMeetings` breaks it:

1. `_pass` catches the error as an ordinary pass failure and `_failed` logs a `failed` record. `_logged_record` names that record with `free_version(store, clock.now())`. `free_version` only looks at versions that already have a log line, and the committed set has none yet. Within the same second, the `failed` record gets **the same version string as the version set that was just committed**.
2. At the next `lock()`, `_reconcile` builds `logged = {record.version for record in passes()}`. That set now contains the orphan's version, so the set is skipped forever. It is neither rolled forward nor back, and `base.md` is never brought up to date.
3. The meeting gets `curation_error.txt`, a failure notification and a counted attempt, even though its edits are in the document. `pending()` keeps listing it, so it is curated a second time.
4. The next pass's `user_edits` holds `diff(body(stale base), body(document))`. That diff shows the curator's own lines as **user edits**, which breaks Safety Invariant 12 ("nothing the curator or code wrote"). The prompt's "user's hand wins" rule then freezes those lines.

Reproduced with the repo's own helpers (`tests/integration/test_activities_store.Faults(fail_at="base", times=Activities.COMMIT_ATTEMPTS)`, `World`, `FakeActivityCurator`). Script: `/private/tmp/claude-501/-Users-felipemateusdecarvalho-Projetos-Pessoal-teams-recorder/38833900-8373-4b20-8322-07dcc789a48c/scratchpad/commit_repro.py`. Output:

```
document has the pass's line: True
records: [('meeting', '20261016-174000'), ('failed', '20261019-101200')]
version sets on disk: ['20261016-174000', '20261019-101200']
curation_error.txt: Activity curation failed: the activities pass 20261019-101200 replaced the document but could not finish (base.md: [Errno 5] disk full); the next pass completes it
next pass sees the curator's own line as a user edit: True
pending(): ['2026-10-19_09-30-00']
```

There is a second path in a batch of more than one meeting, when logging the `failed` record also fails. `_locked` then runs the isolation re-runs **inside the same lock**, without reconciling the orphan set first. They commit new sets that append to the same archive month file. At the next `lock()`, the orphan's stamp no longer matches the document, so it is rolled back, and `_undo_writes` truncates the archive to the orphan's `archive_bytes_before`. That deletes the archive entries the re-runs appended, and the orphan's own entries for lines that are already gone from the document. This breaks the "never delete" rule and Safety Invariant 6.

Common trigger: ENOSPC or a persistent EDEADLK on `base.md` or `log/activities.jsonl` right after the document write succeeded. The docs say disk space is tight on the dev Mac.

Suggested fix:
- Treat `ACTIVITY_COMMIT_INCOMPLETE` (a dedicated error subclass) as "committed, finish pending". Do not log a `failed` record, write no error file and send no failure notification. Stop the round and let the next `lock()` reconcile.
- Make `free_version` also skip versions that have files in `versions/`, through a store method, so no record can claim an unreconciled set.
- Add a use-case or fs test: a persistent `base.md` failure, then the next pass. Assert `user_edits == ""`, a `meeting` record for the meeting, and no `curation_error.txt`.

## Triage

- Decision: `VALID`
- Notes: Root cause confirmed with the reviewer's script. `FsActivityStore._retried` raised a plain `RepositoryError` after the document replace; `CurateMeetings._pass` handled it like any failure (a `failed` record named by `free_version`, which ignored version sets without a log line, so it took the committed set's version; reconcile then skipped that set forever), and a batch re-ran meeting by meeting inside the same lock on top of the unfinished set. Fix: new `CommitIncomplete(RepositoryError)` (`domain/errors.py`); `_curate` catches it around `commit` and returns an unfinished attempt (no failed record, no error file, no failure notification, no isolation; `PassResult.unfinished`, and `trec` prints `Cli.CURATION_UNFINISHED`); the next `lock()` reconciles. `free_version` also skips names from the new port method `ActivityStore.version_names()` (fs store, fake, port). Spec clarified in `_spec.md` (commit order paragraph, `render_box` signature) and `_tests.md`. Regression tests: `tests/integration/test_curate_meetings_fs.py::test_a_persistent_failure_after_the_replace_is_unfinished_not_failed_and_the_next_pass_completes_it` (base and log steps; asserts `user_edits == ""`, a `meeting` record, no error file, pending empty), `::test_an_unfinished_pass_of_several_meetings_is_not_rerun_one_meeting_at_a_time` (archive entries kept), unit `test_a_commit_left_unfinished_is_neither_a_failed_pass_nor_isolated`, `test_a_new_pass_never_takes_the_name_of_a_version_set_that_is_on_disk`, store `test_version_names_...`, CLI `test_a_commit_left_unfinished_is_said_after_the_ok_line_and_keeps_exit_0`. Existing store test updated to expect `CommitIncomplete`.
- Reopened (round 7): the main path is fixed. `commit_repro.py` re-run against the fix prints `result failed: ()`, `curation_error.txt: None`, `next pass sees the curator's own line as a user edit: False` and `pending(): []`, and the next lock logs "completed it". `free_version` also skips `version_names()`. The second failure mode in this issue is still open: a commit on top of an unreconciled set inside the same lock. The fix stops isolation only when the *batch* pass is unfinished. `CurateMeetings._locked` (`application/use_cases/activities.py` ~213) keeps looping over the single-meeting re-runs after one of them returns `unfinished`. Repro: `/private/tmp/claude-501/-Users-felipemateusdecarvalho-Projetos-Pessoal-teams-recorder/38833900-8373-4b20-8322-07dcc789a48c/scratchpad/isolation_unfinished_repro.py`. Setup: a batch of 2 whose first curator call raises, then `Faults(fail_at="base", times=COMMIT_ATTEMPTS)`, so the re-run of meeting A is unfinished, and the re-run of meeting B commits in the same lock. Output: `B's pass saw A's curator line as a user edit: True` (Safety Invariant 12). After the next `lock()`, A's set is "rolled back" (the document stamp is now B's), and `_undo_writes` truncates the archive to A's `archive_bytes_before`. Result: `archive has AGENDA: False ITEM: False` while `document has AGENDA: False ITEM: False`. The line A archived and the line B archived are now in neither file ("never delete", Safety Invariant 6). The log has no record for A, so `pending(): ['2026-10-19_09-30-00']` and A is curated again. Fix direction: once any attempt in `_locked` is `unfinished`, stop the round (return the tally; the remaining meetings stay pending for the next lock, which reconciles first), or reconcile before each re-run. Add an fs test for an unfinished isolated re-run followed by another meeting.
- Round 7 fix: root cause of the remaining defect: `_locked` stopped isolation only when the *batch* pass was unfinished; an isolated single-meeting re-run that returned `unfinished` did not stop the loop, so the next re-run committed on top of the unreconciled set (it saw A's line as a user edit, and the next lock's roll-back truncated the archive). Fix (`application/use_cases/activities.py`, `_locked`): after each isolated re-run, `if tally.unfinished is not None: break`. No further commit happens in that lock; the meetings not yet re-run stay in `pending()` and the next `lock()` reconciles the unfinished set first. Regression test: `tests/integration/test_curate_meetings_fs.py::test_an_isolated_rerun_left_unfinished_stops_the_round_and_the_next_lock_loses_nothing` (two-meeting batch, first curator call raises, `base.md` fails `COMMIT_ATTEMPTS` times; asserts only two curator calls, no error file, after the next lock the archive keeps A's entry once, `pending() == [B]`, then B's pass sees `user_edits == ""`, both archive entries are kept, each meeting has exactly one `meeting` record). It fails without the `break` and passes with it. Verification: `pytest -q` (whole suite) green, `mypy` clean (63 files).
- Verified (round 8): `CurateMeetings._locked` (`application/use_cases/activities.py` ~213-218) now breaks the isolation loop as soon as `tally.unfinished` is set. Re-ran `isolation_unfinished_repro.py` (with `PYTHONPATH=.`): only 2 curator calls (the failed batch and meeting A alone), records `[('failed', (A, B)), ('meeting', (A,))]`, `unfinished: True`; B's pass no longer runs in the same lock (the script's third-call probe now hits `IndexError`, which is the expected outcome). `commit_repro.py` still prints `result failed: ()`, `curation_error.txt: None`, `next pass sees the curator's own line as a user edit: False`, `pending(): []`, and the next lock logs "completed it". The new fs test `test_an_isolated_rerun_left_unfinished_stops_the_round_and_the_next_lock_loses_nothing` asserts that B has no error file, that the next `lock()` rolls A forward with its archive entry kept once, that `pending() == [B]`, that B's later pass sees `user_edits == ""`, that both archive entries survive, and that there is one `meeting` record per meeting. No regression in state: B gets no failed attempt and no failure notification, and stays in `pending()`. The daemon's next round picks B up through `pending()`. Full `pytest -q` exit 0; `mypy`: "Success: no issues found in 63 source files". One follow-up on how the skipped meeting is reported is tracked as reviews-008/issue_001 (low, non-blocking).
