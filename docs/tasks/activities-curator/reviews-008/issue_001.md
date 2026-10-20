---
provider: manual
pr:
round: 8
round_created_at: 2026-10-20T12:53:27Z
status: resolved
file: src/teams_recorder/adapters/inbound/cli.py
line: 568
severity: low
author: claude-code
provider_ref:
---

# Issue 001: Meetings skipped after an unfinished isolated re-run go unreported

## Review Comment

Follow-up to the round 7 fix for reviews-006/issue_001. The fix is correct and verified. Non-blocking.

`CurateMeetings._locked` (`application/use_cases/activities.py` ~213-218) now `break`s the isolation loop when a single-meeting re-run returns `unfinished`. The meetings after it in the batch are not re-run in this call. They appear in neither `PassResult.curated` nor `PassResult.failed`, and that is correct for the store: no error file, no attempt, and they stay in `pending()`. But no caller reports them:

- `cli._curate_passes` (`adapters/inbound/cli.py` ~557-573) prints one line for `result.curated`, the `Cli.CURATION_UNFINISHED` line ("The document was updated, but the pass could not be fully recorded: ...") and one line per `result.failed`. For `trec activities curate A B` (same day, batch fails, then A's re-run hits a persistent `base.md` failure), the output names A and the unfinished reason and says nothing about B. The exit code is 0, so a user who asked for B by name is never told B was not curated. The function's docstring promises "a line for the meetings a pass curated and one for each that failed", and B is neither.
- The daemon's `Log.WORKER_PASS_END` logs only `len(curated)` and `len(failed)`. B is recovered by `pending()` in the next round, so the daemon loses nothing, but the log does not show that B was deferred.
- `_spec.md` line 655 ("A failed batch is isolated before it is counted ... re-runs the meetings of a failed multi-meeting pass one at a time") and the commit-order paragraph (line 650, which covers only the *batch* pass being unfinished) do not state the new rule: after an unfinished isolated re-run, the rest of the batch is deferred to the next lock.

Evidence: the scenario in `tests/integration/test_curate_meetings_fs.py::test_an_isolated_rerun_left_unfinished_stops_the_round_and_the_next_lock_loses_nothing` gives `result.curated == (A,)`, `result.failed == ()` and `pending() == [B]`. Feed that `PassResult` to `_curate_passes` and no line contains B.

Suggested fix: add a `deferred: tuple[str, ...]` field to `PassResult`, set to the batch ids that were not re-run after the break. Have `_curate_passes` print one line per deferred meeting (for example "not curated yet; the next run picks it up"), and include the count in `WORKER_PASS_END`. Add one sentence to `_spec.md` line 655. Add a CLI test for the two-meeting case.

## Triage

- Decision: `VALID`
- Notes: Confirmed by reading `CurateMeetings._locked`: after the `break` the meetings not yet re-run are in neither `curated` nor `failed`, and `_curate_passes` and `WORKER_PASS_END` had nothing else to print. Root cause: `PassResult` could not carry the meetings the round skipped.
- Fix: `PassResult.deferred` (`application/use_cases/activities.py`) holds the batch ids after the one whose re-run was left unfinished. `_curate_passes` prints one `Cli.CURATION_DEFERRED` line per deferred meeting (exit code unchanged). `Log.WORKER_PASS_END` now counts deferred meetings (`daemon.py`). One sentence added to the "A failed batch is isolated before it is counted" decision in `_spec.md`.
- Verified: `tests/integration/test_cli_activities.py::test_a_meeting_deferred_by_an_unfinished_rerun_is_named_and_keeps_exit_0` (A unfinished, B deferred line, exit 0); `tests/integration/test_curate_meetings_fs.py::test_an_isolated_rerun_left_unfinished_stops_the_round_and_the_next_lock_loses_nothing` now asserts `result.deferred == (second,)`; `tests/unit/test_curator_worker.py::test_ut045_the_round_is_logged_with_its_size_and_every_pass` covers the new log template. Full `pytest -q` and `mypy` pass.
