---
provider: manual
pr:
round: 6
round_created_at: 2026-10-20T12:34:07Z
status: resolved
file: src/teams_recorder/adapters/inbound/daemon.py
line: 91
severity: medium
author: claude-code
provider_ref:
---

# Issue 002: CuratorWorker curates the same meetings twice after a restart

## Review Comment

`CuratorWorker.step` takes the woken id plus at most `WORKER_DRAIN` (3) more from the queue. It then adds `pending()` and runs **every** batch of the union. `Daemon._enqueue_pending` puts all pending ids on the queue at start. With more than four pending meetings (a Monday after the daemon was down, or a day of many meetings), round 1 already curates all of them through `pending()`. The ids still in the queue then wake round 2, which curates them **again**. `CurateMeetings.execute` does not skip meetings that already have a successful pass; it must not, because `trec activities curate <id>` reruns on purpose.

Reproduced with the worker test's own stub (`tests/unit/test_curator_worker.StubCurate`, pending = six ids, then none). Script: `/private/tmp/claude-501/-Users-felipemateusdecarvalho-Projetos-Pessoal-teams-recorder/38833900-8373-4b20-8322-07dcc789a48c/scratchpad/dup_repro.py`:

```
round 1: [[A, B, C, D], [E, F]]
round 2: [[E, F]]
```

Each extra pass is a full LLM call (minutes, subscription quota). Duplicate items are then avoided only by the prompt's repeat-safety rule (Q-002), not by code. This goes against UT-045's contract ("an id enqueued twice is curated once"). The test covers only duplicates within one round (`test_ut045_an_id_that_is_also_pending_is_curated_once`), not ids that `pending()` has already absorbed in an earlier round.

Suggested fix: in `step`, drain the whole queue, or drop queued ids that the pass log already shows as curated since they were enqueued. For example, filter `queued` against `pending()` plus ids with no successful record. Add a UT-045 case that enqueues 6 ids at start and asserts each id reaches `execute` exactly once across rounds.

## Triage

- Decision: `VALID`
- Notes: Root cause confirmed with `dup_repro.py`: ids queued at daemon start stayed in the queue after round 1's `pending()` had already curated them, and woke round 2. Fix: `CurateMeetings.uncurated(ids)` (ids with no successful pass in the log) and `CuratorWorker._uncurated`, applied to the queued ids at the start of each round (dropped ids are logged; an unreadable log keeps them all). This also covers the narrow race where the pipeline enqueues an id that `pending()` already listed. `execute` is unchanged, so `trec activities curate <id>` still reruns on purpose. Spec UT-045 extended. Regression tests in `tests/unit/test_curator_worker.py` (`test_ut045_ids_queued_at_start_are_curated_once_across_rounds_...`, `..._curated_meanwhile_is_dropped_and_logged`, `..._pass_log_that_cannot_be_read_...`) and `tests/unit/test_curate_meetings.py::test_uncurated_keeps_the_ids_with_no_successful_pass_in_the_order_given`.
- Verified (round 7): `/private/tmp/claude-501/-Users-felipemateusdecarvalho-Projetos-Pessoal-teams-recorder/38833900-8373-4b20-8322-07dcc789a48c/scratchpad/dup_repro.py` re-run against the fix prints `round 2: []` (round 1 still curates all six). `CuratorWorker.step` filters only the queued ids through `CurateMeetings.uncurated`. `uncurated` drops only ids that have a `meeting`/`skipped_empty` record, so an id whose last pass failed is kept and retried. An unreadable log keeps every id (`_uncurated` falls back to `queued`). `execute` is unchanged, so the explicit `trec activities curate <id>` still reruns. Full suite green.
