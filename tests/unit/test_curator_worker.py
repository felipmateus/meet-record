"""The daemon's curator worker and how the Daemon owns it: ordering and de-duplication of a round (UT-045), the stop contract
(UT-120), the queue rebuilt at daemon start and the switch that builds no worker (UT-107), the hook wiring (UT-108)."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from teams_recorder.adapters.inbound.daemon import CuratorWorker, Daemon
from teams_recorder.application.pipeline import Pipeline
from teams_recorder.application.use_cases.activities import CurateMeetings, PassResult
from teams_recorder.application.ports import CallState
from teams_recorder.domain import MeetingStatus, PassKind, derive_status
from teams_recorder.messages import Log
from tests.fakes import FakeActivityCurator, FakeCallDetector, FakeMicCapture, FakeProcessCapture, InMemoryActivityStore
from tests.fixtures.curation import answer, build, rec, seed
from tests.unit.test_daemon import FakeContainer

DAY = datetime(2026, 10, 19, 9, 30)
A, B, C, D, E, F = (f"2026-10-19_09-{minute:02d}-00" for minute in (10, 20, 30, 40, 50, 55))
EMPTY = PassResult((), (), (), None, 0)


class StubCurate:
    """`CurateMeetings` as the worker sees it: `pending()`, `uncurated(ids)` and `execute(ids, wait, on_wait)`. `during` runs inside a
    call. A call that returns counts its ids as curated, as the pass log would; a call that raises does not."""

    def __init__(self, pending: list[list[str]] | None = None, during=None, fail: Exception | None = None) -> None:
        self.pending_answers = list(pending or [])
        self.calls: list[list[str]] = []
        self.waits: list[bool] = []
        self.during = during
        self.fail = fail
        self.done: set[str] = set()

    def uncurated(self, ids: list[str]) -> list[str]:
        return [meeting_id for meeting_id in ids if meeting_id not in self.done]

    def pending(self) -> list[str]:
        return self.pending_answers.pop(0) if self.pending_answers else []

    def execute(self, ids: list[str], wait: bool = True, on_wait=None) -> PassResult:
        self.calls.append(list(ids))
        self.waits.append(wait)
        if self.during is not None:
            self.during(len(self.calls))
        if self.fail is not None:
            raise self.fail
        self.done.update(ids)
        return EMPTY


def worker_of(stub: StubCurate) -> CuratorWorker:
    return CuratorWorker(stub)  # type: ignore[arg-type]


def step_soon(worker: CuratorWorker) -> None:
    """One round on a helper thread, so a test whose hook never reached the queue fails instead of hanging."""
    thread = threading.Thread(target=worker.step, daemon=True)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive(), "the worker's queue was empty"


# --- UT-045: ordering and de-duplication -------------------------------------------------------------------------------
def test_ut045_ids_enqueued_while_a_pass_runs_go_together_with_the_pending_ones_in_the_next_call():
    def while_the_first_pass_runs(n: int) -> None:
        if n == 1:
            for meeting_id in (D, B, C, B):   # three ids, one of them twice
                worker.enqueue(meeting_id)

    stub = StubCurate(pending=[[], [A]], during=while_the_first_pass_runs)
    worker = worker_of(stub)
    worker.enqueue(E)

    assert worker.step() and worker.step()

    assert stub.calls == [[E], [A, B, C, D]]   # one call each: the oldest first, an id queued twice once, the pending id added
    assert stub.waits == [True, True]          # a pass waits for the document lock rather than skipping the meeting


def test_ut045_an_id_that_is_also_pending_is_curated_once():
    stub = StubCurate(pending=[[A, B]])
    worker = worker_of(stub)
    worker.enqueue(B)
    worker.enqueue(C)
    worker.step()
    assert stub.calls == [[A, B, C]]


def test_ut045_a_round_takes_the_woken_id_and_three_more_and_runs_what_is_over_four_as_the_next_pass():
    stub = StubCurate(pending=[[F]])
    worker = worker_of(stub)
    for meeting_id in (D, C, B, A, E):
        worker.enqueue(meeting_id)

    worker.step()
    assert stub.calls == [[A, B, C, D], [F]]   # D, C, B, A: the id it woke up for and three more; E waits for the next round
    worker.step()
    assert stub.calls[2:] == [[E]]


def test_ut045_ids_queued_at_start_are_curated_once_across_rounds_even_when_pending_ran_them_first():   # review 006, issue 002
    ids = [A, B, C, D, E, F]
    stub = StubCurate(pending=[ids, []])   # daemon start: six meetings without a pass; once round 1 has run them, none
    worker = worker_of(stub)
    for meeting_id in ids:                 # Daemon._enqueue_pending
        worker.enqueue(meeting_id)

    worker.step()
    assert stub.calls == [[A, B, C, D], [E, F]]   # pending() absorbed E and F in round 1 ...
    worker.step()                                 # ... the ids still queued wake round 2
    assert stub.calls == [[A, B, C, D], [E, F]]   # which has nothing left to run
    assert sorted(meeting_id for call in stub.calls for meeting_id in call) == ids   # every id reached execute exactly once


def test_ut045_a_queued_id_curated_meanwhile_is_dropped_and_logged(caplog):
    stub = StubCurate(pending=[[], []])
    worker = worker_of(stub)
    worker.enqueue(A)
    worker.enqueue(B)
    stub.done.add(A)   # A was curated meanwhile (by a CLI run, say), B was not
    with caplog.at_level("INFO"):
        worker.step()
    assert stub.calls == [[B]] and Log.WORKER_QUEUE_DONE % (1, A) in caplog.text


def test_ut045_a_pass_log_that_cannot_be_read_does_not_stop_the_queued_ids(caplog):
    stub = StubCurate()

    def broken(ids: list[str]) -> list[str]:
        raise OSError("disk")

    stub.uncurated = broken  # type: ignore[method-assign]
    worker = worker_of(stub)
    worker.enqueue(A)
    with caplog.at_level("WARNING"):
        worker.step()
    assert stub.calls == [[A]] and Log.WORKER_QUEUE_FILTER_FAILED % "disk" in caplog.text


def test_ut045_a_failing_pass_does_not_stop_the_thread_or_the_passes_after_it(caplog):
    stub = StubCurate(pending=[[A, B, C, D, E]], fail=RuntimeError("claude is down"))
    worker = worker_of(stub)
    worker.enqueue(F)

    with caplog.at_level("ERROR"):
        assert worker.step() is True

    assert stub.calls == [[A, B, C, D], [E, F]]
    assert caplog.text.count(Log.WORKER_PASS_FAILED % f"{A}, {B}, {C}, {D}") == 1 and "claude is down" in caplog.text


def test_ut045_pending_that_cannot_be_listed_still_curates_the_queued_ids(caplog):
    stub = StubCurate()

    def broken() -> list[str]:
        raise OSError("disk")

    stub.pending = broken  # type: ignore[method-assign]
    worker = worker_of(stub)
    worker.enqueue(A)
    with caplog.at_level("WARNING"):
        worker.step()
    assert stub.calls == [[A]] and "disk" in caplog.text


def test_ut045_the_round_is_logged_with_its_size_and_every_pass(caplog):
    stub = StubCurate(pending=[[A]])
    worker = worker_of(stub)
    worker.enqueue(B)
    with caplog.at_level("INFO"):
        worker.step()
    assert Log.WORKER_QUEUE % (2, 1, 1, f"{A}, {B}") in caplog.text
    assert Log.WORKER_PASS_START % (1, 1, f"{A}, {B}") in caplog.text
    assert Log.WORKER_PASS_END % (f"{A}, {B}", 0, 0, 0, 0) in caplog.text


# --- UT-120: the stop contract -----------------------------------------------------------------------------------------
def test_ut120_an_idle_worker_returns_within_a_second_of_the_stop_and_its_thread_is_a_daemon_thread():
    worker = worker_of(StubCurate())
    worker.start()
    assert worker.thread is not None and worker.thread.daemon and worker.thread.is_alive()

    worker.request_stop()
    worker.thread.join(timeout=1)

    assert not worker.thread.is_alive()


def test_ut120_an_id_enqueued_after_the_stop_is_not_started():
    stub = StubCurate()
    worker = worker_of(stub)
    worker.request_stop()
    worker.enqueue(A)
    assert worker.step() is False
    assert stub.calls == []


def test_ut120_ids_queued_before_the_stop_are_not_started_either():
    stub = StubCurate()
    worker = worker_of(stub)
    worker.enqueue(A)
    worker.request_stop()
    assert worker.step() is False and stub.calls == []


def test_ut120_the_stop_between_two_passes_of_a_round_starts_no_new_pass():
    stub = StubCurate(pending=[[A, B, C, D, E]], during=lambda n: worker.request_stop())
    worker = worker_of(stub)
    worker.enqueue(F)
    assert worker.step() is False
    assert stub.calls == [[A, B, C, D]]


def test_ut120_shutdown_does_not_wait_for_a_pass_in_flight_and_pending_returns_the_abandoned_meeting(repo, notifier, clock):
    released = threading.Event()
    in_flight = threading.Event()

    def thinking() -> None:
        in_flight.set()
        released.wait(timeout=30)

    mid = seed(repo, DAY)
    store = InMemoryActivityStore()
    use, _, _ = build(repo, store, FakeActivityCurator([answer()], during_call=thinking), now=datetime(2026, 10, 19, 10, 12))
    daemon = _daemon(repo, notifier, clock, use)
    worker = daemon.curator_worker
    assert worker is not None
    worker.start()
    worker.enqueue(mid)
    assert in_flight.wait(timeout=5)

    started = time.monotonic()
    daemon.shutdown()
    elapsed = time.monotonic() - started

    try:
        assert elapsed < 1 and worker.thread is not None and worker.thread.is_alive()   # the pass is still running
        assert use.pending() == [mid]   # nothing was committed: the next start rebuilds it
    finally:
        released.set()
        assert worker.thread is not None
        worker.thread.join(timeout=10)
    assert not worker.thread.is_alive()
    assert [r.kind for r in store.passes()] == [PassKind.MEETING]   # the abandoned pass ended by itself once it was released


# --- UT-107, UT-108: the Daemon owns the worker -------------------------------------------------------------------------
class CuratingContainer(FakeContainer):
    """The daemon's FakeContainer plus what the daemon reads when `[activities]` is on: `curate_meetings()`."""

    def __init__(self, *args, curate: CurateMeetings, enabled: bool = True, **kw) -> None:
        super().__init__(*args, **kw)
        self.curate = curate
        self.settings = SimpleNamespace(capture_log=Path("/fake/log/capture.log"), speakers_log=Path("/fake/log/speakers.log"), activities_enabled=enabled)
        self.hooks: list[object] = []
        self.built = 0

    def curate_meetings(self) -> CurateMeetings:
        self.built += 1
        return self.curate

    def pipeline(self, after_analysis=None) -> Pipeline:
        self.hooks.append(after_analysis)
        return super().pipeline(after_analysis)


def _daemon(repo, notifier, clock, curate: CurateMeetings, states=(), enabled: bool = True) -> Daemon:
    container = CuratingContainer(repo, FakeCallDetector(list(states)), notifier, clock, FakeProcessCapture(), FakeMicCapture(),
                                  curate=curate, enabled=enabled)
    return Daemon(container, poll_seconds=0, start_after=2, stop_after=3, sleep=lambda s: None, run_in_background=lambda fn: fn())


def _use(repo, clock, store=None, curator=None) -> tuple[CurateMeetings, InMemoryActivityStore, FakeActivityCurator]:
    store = store or InMemoryActivityStore()
    curator = curator or FakeActivityCurator([answer()])
    use, _, _ = build(repo, store, curator, now=clock.now())
    use.clock = clock
    return use, store, curator


def test_ut107_start_queues_an_analyzed_meeting_that_has_no_pass_record(repo, notifier, clock):
    mid = seed(repo, clock.now().replace(hour=9, minute=30))   # analyzed this morning, the queue was lost to a restart
    use, store, curator = _use(repo, clock)
    daemon = _daemon(repo, notifier, clock, use)
    worker = daemon.curator_worker
    assert worker is not None
    queued: list[str] = []
    real_enqueue = worker.enqueue
    worker.enqueue = lambda meeting_id: (queued.append(meeting_id), real_enqueue(meeting_id))[1]   # type: ignore[method-assign]

    daemon._resume_pending()

    assert queued == [mid]
    step_soon(worker)   # the worker receives it: one pass, one record
    assert [(r.kind, r.meetings) for r in store.passes()] == [(PassKind.MEETING, (mid,))] and len(curator.inputs) == 1


def test_ut107_a_meeting_that_already_has_a_pass_is_not_queued_again(repo, notifier, clock):
    mid = seed(repo, clock.now().replace(hour=9, minute=30))
    store = InMemoryActivityStore()
    store.records.append(rec(PassKind.MEETING, mid))
    use, _, _ = _use(repo, clock, store=store)
    daemon = _daemon(repo, notifier, clock, use)
    assert daemon.curator_worker is not None
    queued: list[str] = []
    daemon.curator_worker.enqueue = queued.append   # type: ignore[method-assign]

    daemon._resume_pending()

    assert queued == []


def test_ut107_with_activities_disabled_no_worker_is_built_and_nothing_is_enqueued(repo, notifier, clock):
    seed(repo, clock.now().replace(hour=9, minute=30))
    use, store, curator = _use(repo, clock)
    daemon = _daemon(repo, notifier, clock, use, enabled=False)

    daemon._resume_pending()
    daemon.shutdown()

    assert daemon.curator_worker is None and daemon._after_analysis() is None
    assert daemon.container.built == 0 and daemon.container.hooks == [None]   # type: ignore[attr-defined]
    assert store.passes() == [] and curator.inputs == []


def test_ut107_a_container_without_a_curator_builds_no_worker(repo, notifier, clock):
    daemon = Daemon(FakeContainer(repo, FakeCallDetector([]), notifier, clock, FakeProcessCapture(), FakeMicCapture()), poll_seconds=0)
    assert daemon.curator_worker is None and daemon._after_analysis() is None


def test_ut107_a_failing_pending_listing_does_not_stop_the_pipeline_from_resuming(repo, notifier, clock, caplog):
    use, _, _ = _use(repo, clock)
    daemon = _daemon(repo, notifier, clock, use)

    def broken(*args: object, **kwargs: object) -> list[str]:
        raise OSError("disk")

    use.pending = broken   # type: ignore[method-assign]
    with caplog.at_level("WARNING"):
        daemon._resume_pending()
    assert "disk" in caplog.text and len(daemon.container.hooks) == 1   # type: ignore[attr-defined]


def test_ut108_a_call_that_ends_hands_the_analyzed_meeting_to_the_worker_through_the_pipeline_hook(repo, notifier, clock):
    use, store, curator = _use(repo, clock)
    states = [CallState.IDLE, CallState.IN_CALL, CallState.IN_CALL, CallState.IN_CALL, CallState.IDLE, CallState.IDLE, CallState.IDLE]
    daemon = _daemon(repo, notifier, clock, use, states)
    worker = daemon.curator_worker
    assert worker is not None

    for _ in states:
        daemon.tick()
        clock.advance(seconds=3)

    [meeting] = repo.list_meetings()
    assert derive_status(repo.files(meeting.id)) == MeetingStatus.ANALYZED
    assert daemon.container.hooks == [worker.enqueue]   # type: ignore[attr-defined]   # _finish_call passes worker.enqueue
    assert store.passes() == []
    step_soon(worker)
    assert [r.meetings for r in store.passes()] == [(meeting.id,)]   # the meeting reached the worker


def test_ut108_resume_pending_passes_the_worker_hook_too_and_the_meetings_it_analyzes_reach_the_worker(repo, notifier, clock):
    from teams_recorder.domain import Meeting
    from teams_recorder.domain.status import AUDIO, TRANSCRIPT_JSON
    from tests.fakes import FakeTranscriber

    recorded = Meeting.start(clock.now().replace(hour=9, minute=30))
    repo.seed(recorded, {AUDIO, TRANSCRIPT_JSON}, transcript=FakeTranscriber().transcript)
    use, store, _ = _use(repo, clock)
    daemon = _daemon(repo, notifier, clock, use)
    worker = daemon.curator_worker
    assert worker is not None

    daemon._resume_pending()

    assert daemon.container.hooks == [worker.enqueue]   # type: ignore[attr-defined]
    step_soon(worker)
    assert [r.meetings for r in store.passes()] == [(recorded.id,)]


def test_ut108_importing_the_container_does_not_import_the_daemon():
    code = "import sys, teams_recorder.container; sys.exit(1 if 'teams_recorder.adapters.inbound.daemon' in sys.modules else 0)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
