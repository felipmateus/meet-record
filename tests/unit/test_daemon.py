"""Daemon state machine with all ports faked."""
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest

from teams_recorder.adapters.inbound.daemon import Daemon
from teams_recorder.application.ports import CallState, ConfirmAnswer
from teams_recorder.application.use_cases import AnalyzeMeeting, CancelRecording, PurgeOldAudio, StartRecording, StopRecording, TranscribeMeeting
from teams_recorder.application.pipeline import Pipeline
from teams_recorder.domain import Meeting, MeetingStatus, derive_status
from teams_recorder.domain.status import AUDIO, MIC_TRACK, TAP_TRACK
from teams_recorder.messages import Log
from tests.fakes import FakeAnalyzer, FakeCallDetector, FakeMicCapture, FakeMixer, FakeProcessCapture, FakeSpeakerObserver, FakeTranscriber


@dataclass
class FakeContainer:
    """Only what the Daemon uses from the real Container."""
    repo: object
    detector: object
    notifier: object
    clock: object
    proc: FakeProcessCapture
    mic: FakeMicCapture
    settings: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(capture_log=Path("/fake/log/capture.log"),
                                                                              speakers_log=Path("/fake/log/speakers.log")))
    confirmation: object = None
    disk: object = None
    speakers: object = None   # the speaker observer; None: not wired (the daemon reads it with getattr)
    purge: object = None      # the audio retention the daemon schedules daily; None: PurgeOldAudio on the fake repository

    @property
    def process_capture(self):
        return self.proc

    @property
    def mic_capture(self):
        return self.mic

    def start_recording(self):
        return StartRecording(self.repo, self.proc, self.mic, self.notifier, self.clock, "mic", speakers=self.speakers)

    def stop_recording(self):
        repo = self.repo

        class MixerThatWrites(FakeMixer):
            def mix(self, tracks, out):
                repo.touch(out.parent.name, AUDIO)
                return super().mix(tracks, out)

        return StopRecording(self.repo, self.proc, self.mic, MixerThatWrites(), self.notifier, self.clock, self.speakers)

    def cancel_recording(self):
        return CancelRecording(self.repo, self.proc, self.mic, self.notifier, self.speakers)

    def purge_old_audio(self):
        return self.purge or PurgeOldAudio(self.repo, self.clock)

    def pipeline(self, after_analysis=None):
        return Pipeline(self.repo, self.notifier, self.stop_recording(), TranscribeMeeting(self.repo, FakeTranscriber()), AnalyzeMeeting(self.repo, FakeAnalyzer()),
                        after_analysis)


def _inline(fn):
    fn()  # synchronous background work in tests


def _daemon(repo, notifier, clock, states, confirmation=None, runner=_inline, fresh_day=False, **kw):
    """`fresh_day=False`: today's audio retention counts as already scheduled, so the tests of calls see only their own jobs."""
    c = FakeContainer(repo, FakeCallDetector(states), notifier, clock, FakeProcessCapture(), FakeMicCapture(), confirmation=confirmation)
    daemon = Daemon(c, poll_seconds=0, start_after=2, stop_after=3, sleep=lambda s: None, run_in_background=runner, **kw)
    daemon.purge_day = None if fresh_day else clock.now().date()
    return daemon, c


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


def _observed_daemon(repo, notifier, clock, states, speakers):
    d, c = _daemon(repo, notifier, clock, states)
    c.speakers = speakers
    return d, c


def test_ut039_recover_stops_the_observer_with_the_recorders(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    d, c = _observed_daemon(repo, notifier, clock, [], speakers)
    orphan = c.start_recording().execute(pid=1)
    repo.touch(orphan.meeting.id, TAP_TRACK)
    repo.touch(orphan.meeting.id, MIC_TRACK)
    handle = repo.load_active().speakers_handle

    d.recover()

    assert handle is not None and speakers.stopped == [handle.pid]
    assert c.proc.is_stopped(orphan.process_handle) and repo.load_active() is None


def test_ut039_recover_stops_the_observer_of_a_recording_without_tracks(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    d, c = _observed_daemon(repo, notifier, clock, [], speakers)
    c.start_recording().execute(pid=1)   # no tracks recorded
    handle = repo.load_active().speakers_handle

    d.recover()

    assert speakers.stopped == [handle.pid] and repo.load_active() is None


def test_ut039_a_failing_observer_stop_does_not_stop_recovery(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    d, c = _observed_daemon(repo, notifier, clock, [], speakers)
    c.start_recording().execute(pid=1)
    speakers.stop_error = RuntimeError("bootout failed")

    d.recover()

    assert repo.load_active() is None


def test_ut039_a_dead_observer_is_logged_once(repo, notifier, clock, caplog):
    import logging
    speakers = FakeSpeakerObserver()
    d, c = _observed_daemon(repo, notifier, clock, [CallState.IN_CALL] * 6, speakers)
    d.tick(); d.tick()
    assert d.active is not None and d.active.speakers_handle is not None
    speakers.died = {d.active.speakers_handle.pid}
    with caplog.at_level(logging.WARNING):
        d.tick(); d.tick(); d.tick()
    warnings = [r.getMessage() for r in caplog.records if "died during call" in r.getMessage()]
    assert warnings == [f"capturer teams-speakers (pid {d.active.speakers_handle.pid}) died during call {d.active.meeting.id}; "
                        "see /fake/log/speakers.log"]
    assert c.proc.is_running(d.active.process_handle)   # the recording itself carries on


def test_a_failing_observer_check_never_keeps_a_call_from_ending(repo, notifier, clock, caplog):
    """Review round 2, issue 003: launchctl failing under the observer's is_running used to leave every tick before the call-end check."""
    import logging
    speakers = FakeSpeakerObserver(check_error=OSError("launchctl: Resource temporarily unavailable"))
    states = [CallState.IN_CALL] * 3 + [CallState.IDLE] * 6
    d, c = _observed_daemon(repo, notifier, clock, states, speakers)
    with caplog.at_level(logging.WARNING):
        for _ in states:
            d.tick()                                  # no tick raises
    assert d.active is None and repo.load_active() is None
    assert len(repo.list_meetings()) == 1
    failures = [m for m in caplog.messages if "speaker observer check" in m]
    assert len(failures) == 1 and "Resource temporarily unavailable" in failures[0]   # logged once for the call, not on every tick
    assert len(speakers.stopped) == 1                                                  # and the observer was still stopped with the call


def test_a_failing_observer_check_does_not_hide_a_recorder_that_died(repo, notifier, clock, caplog):
    import logging
    speakers = FakeSpeakerObserver(check_error=RuntimeError("boom"))
    d, c = _observed_daemon(repo, notifier, clock, [CallState.IN_CALL] * 6, speakers)
    d.tick(); d.tick()
    assert d.active is not None
    c.proc.died = {d.active.process_handle.pid}
    with caplog.at_level(logging.WARNING):
        d.tick(); d.tick()
    assert len([m for m in caplog.messages if "teams-tap" in m and "died during call" in m]) == 1


def test_a_recovered_recording_without_an_observer_handle_still_boots_the_job_out(repo, notifier, clock):
    """Review round 2, issue 041: the job exists a startup grace before its handle is persisted; a crash in it leaves no handle."""
    speakers = FakeSpeakerObserver()
    d, c = _observed_daemon(repo, notifier, clock, [], speakers)
    c.start_recording().execute(pid=1)               # no tracks recorded
    active = repo.load_active()
    active.speakers_handle = None                    # the daemon died after the bootstrap, before the handle was saved
    repo.save_active(active)
    stale_before = speakers.stale_stops

    d.recover()

    assert speakers.stale_stops == stale_before + 1 and speakers.stopped == [] and repo.load_active() is None


def test_a_recovered_recording_with_tracks_and_no_observer_handle_boots_the_job_out_too(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    d, c = _observed_daemon(repo, notifier, clock, [], speakers)
    orphan = c.start_recording().execute(pid=1)
    repo.touch(orphan.meeting.id, TAP_TRACK)
    repo.touch(orphan.meeting.id, MIC_TRACK)
    active = repo.load_active()
    active.speakers_handle = None
    repo.save_active(active)
    stale_before = speakers.stale_stops

    d.recover()

    assert speakers.stale_stops == stale_before + 1 and repo.load_active() is None


def test_a_failing_stale_stop_does_not_stop_recovery(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    d, c = _observed_daemon(repo, notifier, clock, [], speakers)
    c.start_recording().execute(pid=1)
    active = repo.load_active()
    active.speakers_handle = None
    repo.save_active(active)
    speakers.stop_error = RuntimeError("bootout failed")

    d.recover()

    assert repo.load_active() is None


def test_a_recording_without_an_observer_is_not_watched_for_one(repo, notifier, clock, caplog):
    import logging
    d, c = _observed_daemon(repo, notifier, clock, [CallState.IN_CALL] * 4, FakeSpeakerObserver(reason="binary-missing"))
    with caplog.at_level(logging.WARNING):
        for _ in range(4):
            d.tick()
    assert d.active is not None and d.active.speakers_handle is None
    assert not [r for r in caplog.records if "died during call" in r.getMessage()]
    assert repo.unavailable == {d.active.meeting.id: "binary-missing"}


def test_a_full_call_with_an_observer_stops_it_and_titles_the_meeting(repo, notifier, clock):
    from teams_recorder.domain import SpeakerLog
    speakers = FakeSpeakerObserver()
    states = [CallState.IN_CALL, CallState.IN_CALL, CallState.IN_CALL, CallState.IDLE, CallState.IDLE, CallState.IDLE]
    d, c = _observed_daemon(repo, notifier, clock, states, speakers)
    d.tick(); d.tick()
    repo.seed_speakers(d.active.meeting.id, SpeakerLog(subject="Daily"))
    handle = d.active.speakers_handle
    for _ in range(4):
        d.tick()

    assert d.active is None and speakers.stopped == [handle.pid]
    assert repo.list_meetings()[0].title == "Daily"


def test_a_discarded_call_stops_the_observer(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    d, c = _observed_daemon(repo, notifier, clock, [CallState.IN_CALL] * 4, speakers)
    c.confirmation = FakeConfirmation(ConfirmAnswer.DISCARD)
    d.tick(); d.tick(); d.tick()
    assert d.active is None and d.ignoring_call
    assert len(speakers.stopped) == 1


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


# --- the daily audio retention (UT-094, UT-098) ------------------------------------------------------------------------
class SpyPurge:
    def __init__(self, error: Exception | None = None) -> None:
        self.runs = 0
        self.error = error

    def execute(self) -> list[str]:
        self.runs += 1
        if self.error is not None:
            raise self.error
        return ["m1", "m2"]


def test_the_first_tick_of_a_day_schedules_the_purge_in_the_background_once(repo, notifier, clock):    # UT-094
    spy, queued = SpyPurge(), []
    d, c = _daemon(repo, notifier, clock, [CallState.IDLE] * 4, runner=queued.append, fresh_day=True)
    c.purge = spy

    d.tick()

    assert len(queued) == 1 and spy.runs == 0       # scheduled, and the tick returned without running it
    assert d.container.detector.states == [CallState.IDLE] * 3   # the call state was read in that same tick
    d.tick()
    assert len(queued) == 1                         # same day: not scheduled again
    queued[0]()
    assert spy.runs == 1


def test_the_purge_is_scheduled_again_on_the_next_calendar_day(repo, notifier, clock):
    queued = []
    d, c = _daemon(repo, notifier, clock, [CallState.IDLE] * 4, runner=queued.append, fresh_day=True)
    c.purge = SpyPurge()
    d.tick()
    clock.advance(hours=1)
    d.tick()
    assert len(queued) == 1
    clock.advance(days=1)
    d.tick()
    assert len(queued) == 2 and d.purge_day == clock.now().date()


def test_the_purge_runs_apart_from_a_call_in_progress(repo, notifier, clock):
    queued = []
    d, c = _daemon(repo, notifier, clock, [CallState.IN_CALL, CallState.IN_CALL, CallState.IN_CALL], runner=queued.append, fresh_day=True)
    d.run_in_background = lambda fn: (queued.append(fn) if fn.__name__ == "_purge" else fn())
    c.purge = SpyPurge()
    for _ in range(3):
        d.tick()
    assert d.active is not None and len(queued) == 1      # the recording started and the purge is still only queued


def test_a_failing_purge_is_logged_and_not_retried_the_same_day(repo, notifier, clock, caplog):    # UT-098
    spy = SpyPurge(error=RuntimeError("disk gone"))
    d, c = _daemon(repo, notifier, clock, [CallState.IDLE] * 4, fresh_day=True)   # inline background
    c.purge = spy

    with caplog.at_level("ERROR"):
        d.tick()
        d.tick()

    assert spy.runs == 1                                           # recorded before scheduling: no second attempt today
    assert Log.PURGE_FAILED in caplog.text and "disk gone" in caplog.text
    clock.advance(days=1)
    d.tick()
    assert spy.runs == 2                                           # tomorrow it is tried again


def test_a_purge_that_works_logs_how_many_files_it_removed(repo, notifier, clock, caplog):
    d, c = _daemon(repo, notifier, clock, [CallState.IDLE], fresh_day=True)
    c.purge = SpyPurge()
    with caplog.at_level("INFO"):
        d.tick()
    assert Log.PURGE_DONE % 2 in caplog.text
