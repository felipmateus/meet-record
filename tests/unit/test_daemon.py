"""Daemon state machine with all ports faked."""
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from teams_recorder.adapters.inbound.daemon import Daemon
from teams_recorder.application.ports import CallState, ConfirmAnswer
from teams_recorder.application.use_cases import AnalyzeMeeting, CancelRecording, StartRecording, StopRecording, TranscribeMeeting
from teams_recorder.application.pipeline import Pipeline
from teams_recorder.domain import Meeting, MeetingStatus, derive_status
from teams_recorder.domain.status import AUDIO, MIC_TRACK, TAP_TRACK
from tests.fakes import FakeAnalyzer, FakeCallDetector, FakeMicCapture, FakeMixer, FakeProcessCapture, FakeTranscriber


@dataclass
class FakeContainer:
    """Only what the Daemon uses from the real Container."""
    repo: object
    detector: object
    notifier: object
    clock: object
    proc: FakeProcessCapture
    mic: FakeMicCapture
    settings: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(capture_log=Path("/fake/log/capture.log")))
    confirmation: object = None
    disk: object = None

    @property
    def process_capture(self):
        return self.proc

    @property
    def mic_capture(self):
        return self.mic

    def start_recording(self):
        return StartRecording(self.repo, self.proc, self.mic, self.notifier, self.clock, "mic")

    def stop_recording(self):
        repo = self.repo

        class MixerThatWrites(FakeMixer):
            def mix(self, tracks, out):
                repo.touch(out.parent.name, AUDIO)
                return super().mix(tracks, out)

        return StopRecording(self.repo, self.proc, self.mic, MixerThatWrites(), self.notifier, self.clock)

    def cancel_recording(self):
        return CancelRecording(self.repo, self.proc, self.mic, self.notifier)

    def pipeline(self):
        return Pipeline(self.repo, self.notifier, self.stop_recording(), TranscribeMeeting(self.repo, FakeTranscriber()), AnalyzeMeeting(self.repo, FakeAnalyzer()))


def _inline(fn):
    fn()  # synchronous background work in tests


def _daemon(repo, notifier, clock, states, confirmation=None, runner=_inline, **kw):
    c = FakeContainer(repo, FakeCallDetector(states), notifier, clock, FakeProcessCapture(), FakeMicCapture(), confirmation=confirmation)
    return Daemon(c, poll_seconds=0, start_after=2, stop_after=3, sleep=lambda s: None, run_in_background=runner, **kw), c


class FakeConfirmation:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.asked = []

    def ask(self, meeting):
        self.asked.append(meeting.id)
        answer = self.answers.pop(0) if self.answers else ConfirmAnswer.NO_ANSWER
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_full_call_cycle(repo, notifier, clock):
    states = [CallState.IDLE, CallState.IN_CALL, CallState.IN_CALL, CallState.IN_CALL, CallState.IDLE, CallState.IDLE, CallState.IDLE]
    d, c = _daemon(repo, notifier, clock, states)

    for _ in range(len(states)):
        d.tick()
        clock.advance(seconds=3)

    meetings = repo.list_meetings()
    assert len(meetings) == 1
    assert derive_status(repo.files(meetings[0].id)) == MeetingStatus.ANALYZED
    assert d.active is None
    titles = [t for t, _ in notifier.messages]
    assert titles[:2] == ["Recording started", "Recording stopped"]


def test_hysteresis_ignores_short_blips(repo, notifier, clock):
    states = [CallState.IN_CALL, CallState.IDLE, CallState.IN_CALL, CallState.IDLE]
    d, _ = _daemon(repo, notifier, clock, states)
    for _ in states:
        d.tick()
    assert repo.list_meetings() == [] and d.active is None


def test_short_idle_gap_does_not_stop_recording(repo, notifier, clock):
    states = [CallState.IN_CALL, CallState.IN_CALL, CallState.IDLE, CallState.IDLE, CallState.IN_CALL, CallState.IDLE]
    d, _ = _daemon(repo, notifier, clock, states)
    for _ in states:
        d.tick()
    assert d.active is not None
    assert len(repo.list_meetings()) == 1 and AUDIO not in repo.files(d.active.meeting.id)


def test_unknown_readings_are_neutral(repo, notifier, clock):
    states = [CallState.IN_CALL, CallState.UNKNOWN, CallState.UNKNOWN, CallState.IN_CALL]
    d, _ = _daemon(repo, notifier, clock, states)
    for _ in states:
        d.tick()
    assert d.active is not None  # the two UNKNOWN readings did not reset the count


def test_adopts_manual_recording_instead_of_starting_another(repo, notifier, clock):
    d, c = _daemon(repo, notifier, clock, [CallState.IN_CALL, CallState.IN_CALL])
    manual = c.start_recording().execute(pid=1)
    for _ in range(2):
        d.tick()
    assert d.active is not None and d.active.meeting.id == manual.meeting.id
    assert len(repo.list_meetings()) == 1


def test_recover_finishes_orphan_recording(repo, notifier, clock):
    d, c = _daemon(repo, notifier, clock, [])
    orphan = c.start_recording().execute(pid=1)
    repo.touch(orphan.meeting.id, TAP_TRACK)
    repo.touch(orphan.meeting.id, MIC_TRACK)

    d.recover()                                    # stops and releases at once; mixing is left for later
    assert repo.load_active() is None
    assert AUDIO not in repo.files(orphan.meeting.id)

    d._resume_pending()                            # runs in the background on startup
    assert derive_status(repo.files(orphan.meeting.id)) == MeetingStatus.ANALYZED


def test_recover_clears_pointer_without_tracks(repo, notifier, clock):
    d, c = _daemon(repo, notifier, clock, [])
    c.start_recording().execute(pid=1)  # no tracks recorded
    d.recover()
    assert repo.load_active() is None


def test_shutdown_finishes_active_call(repo, notifier, clock):
    d, _ = _daemon(repo, notifier, clock, [CallState.IN_CALL, CallState.IN_CALL])
    d.tick(); d.tick()
    assert d.active is not None
    d.shutdown()
    assert d.active is None
    assert derive_status(repo.files(repo.list_meetings()[0].id)) == MeetingStatus.ANALYZED


def test_tick_without_detector_raises(repo, notifier, clock):
    d, c = _daemon(repo, notifier, clock, [])
    c.detector = None
    with pytest.raises(Exception, match="without a configured detector"):
        d.tick()


def test_dead_capturer_is_logged_once(repo, notifier, clock, caplog):
    import logging
    d, c = _daemon(repo, notifier, clock, [CallState.IN_CALL] * 5)
    d.tick(); d.tick()
    assert d.active is not None
    c.proc.died = {d.active.process_handle.pid}
    with caplog.at_level(logging.WARNING):
        d.tick(); d.tick()
    warnings = [r for r in caplog.records if "died during call" in r.getMessage()]
    assert len(warnings) == 1 and "teams-tap" in warnings[0].getMessage()


# --- keep-recording question ------------------------------------------------------
IN, IDLE = CallState.IN_CALL, CallState.IDLE


def _run(d, clock, n):
    for _ in range(n):
        d.tick()
        clock.advance(seconds=1)


def test_discard_cancels_and_ignores_the_rest_of_the_call(repo, notifier, clock):
    confirm = FakeConfirmation(ConfirmAnswer.DISCARD)
    d, _ = _daemon(repo, notifier, clock, [IN] * 6, confirmation=confirm)
    _run(d, clock, 6)
    assert d.active is None and repo.list_meetings() == []
    assert confirm.asked and len(confirm.asked) == 1          # not asked again while the call goes on
    assert ("Recording cancelled", f"Meeting {confirm.asked[0]} discarded") in notifier.messages


def test_after_a_discarded_call_ends_the_next_call_is_recorded(repo, notifier, clock):
    confirm = FakeConfirmation(ConfirmAnswer.DISCARD, ConfirmAnswer.KEEP)
    d, _ = _daemon(repo, notifier, clock, [IN, IN, IN, IDLE, IDLE, IDLE, IN, IN], confirmation=confirm)
    _run(d, clock, 8)
    assert d.active is not None and len(confirm.asked) == 2
    assert [m.id for m in repo.list_meetings()] == [d.active.meeting.id]


@pytest.mark.parametrize("answer", [ConfirmAnswer.KEEP, ConfirmAnswer.NO_ANSWER, RuntimeError("osascript broke")])
def test_keep_no_answer_or_failure_keeps_the_recording(repo, notifier, clock, answer):
    d, _ = _daemon(repo, notifier, clock, [IN, IN, IN, IDLE, IDLE, IDLE], confirmation=FakeConfirmation(answer))
    _run(d, clock, 6)
    meetings = repo.list_meetings()
    assert len(meetings) == 1 and derive_status(repo.files(meetings[0].id)) == MeetingStatus.ANALYZED


def test_no_question_for_an_adopted_manual_recording(repo, notifier, clock):
    confirm = FakeConfirmation(ConfirmAnswer.DISCARD)
    d, c = _daemon(repo, notifier, clock, [IN, IN], confirmation=confirm)
    c.start_recording().execute(pid=1)
    _run(d, clock, 2)
    assert confirm.asked == [] and d.active is not None


def _call_ends_before_the_answer(repo, notifier, clock, answer):
    """The call ends while the dialog is open: capture stops at hang-up, then the answer decides."""
    import threading
    import time

    jobs = []
    gate = threading.Event()

    class SlowConfirmation(FakeConfirmation):
        def ask(self, meeting):
            gate.wait(5)
            return super().ask(meeting)

    d, c = _daemon(repo, notifier, clock, [IN, IN, IDLE, IDLE, IDLE], confirmation=SlowConfirmation(answer), runner=jobs.append, confirm_wait=5)
    _run(d, clock, 5)
    ask_job, finish_job = jobs
    meeting_id = repo.list_meetings()[0].id
    # At hang-up the recorders are stopped and the pointer released, before the answer and before mixing.
    assert repo.load_active() is None and c.proc.stopped and AUDIO not in repo.files(meeting_id)
    asker = threading.Thread(target=ask_job)
    finisher = threading.Thread(target=finish_job)
    asker.start(); finisher.start()
    time.sleep(0.05)
    assert AUDIO not in repo.files(meeting_id)     # nothing is mixed while the question is open
    gate.set()
    asker.join(5); finisher.join(5)
    return meeting_id


def test_discard_after_the_call_ended_deletes_the_recording(repo, notifier, clock):
    meeting_id = _call_ends_before_the_answer(repo, notifier, clock, ConfirmAnswer.DISCARD)
    assert repo.list_meetings() == []
    assert ("Recording cancelled", f"Meeting {meeting_id} discarded") in notifier.messages


def test_keep_after_the_call_ended_processes_the_recording(repo, notifier, clock):
    meeting_id = _call_ends_before_the_answer(repo, notifier, clock, ConfirmAnswer.KEEP)
    assert derive_status(repo.files(meeting_id)) == MeetingStatus.ANALYZED


# --- long meetings and back-to-back calls ----------------------------------------------
def test_call_starting_while_the_previous_one_is_mixing_is_recorded(repo, notifier, clock):
    """2026-10-06 20:15: a call that began 25 s after the previous one ended was taken for it and lost."""
    jobs = []
    d, c = _daemon(repo, notifier, clock, [IN, IN, IDLE, IDLE, IDLE, IN, IN], runner=jobs.append)
    _run(d, clock, 5)
    first = repo.list_meetings()[0].id
    assert repo.load_active() is None and len(jobs) == 1    # stopped and released; mixing still queued

    _run(d, clock, 2)                                       # the next call starts before the mix ran
    assert d.active is not None and d.active.meeting.id != first

    jobs[0]()                                               # the first meeting's mix and processing
    assert derive_status(repo.files(first)) == MeetingStatus.ANALYZED


class FakeDisk:
    def __init__(self, free):
        self.free = free

    def free_bytes(self):
        return self.free


def test_nearly_full_disk_is_warned_once_per_call(repo, notifier, clock):
    d, c = _daemon(repo, notifier, clock, [IN] * 6)
    c.disk = FakeDisk(500_000_000)
    _run(d, clock, 6)
    assert [t for t, _ in notifier.messages].count("Disk almost full") == 1


def test_enough_disk_is_not_warned(repo, notifier, clock):
    d, c = _daemon(repo, notifier, clock, [IN] * 4)
    c.disk = FakeDisk(50_000_000_000)
    _run(d, clock, 4)
    assert "Disk almost full" not in [t for t, _ in notifier.messages]
