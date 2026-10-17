import logging

import pytest

from teams_recorder.application.use_cases import CancelRecording, StartRecording, StopRecording
from teams_recorder.domain import CaptureError, EnergyTimeline, MeetingStatus, RepositoryError, SpeakerLog, derive_status
from teams_recorder.domain.status import AUDIO, MIC_TRACK, SPEAKERS, TAP_TRACK
from tests.fakes import FakeEnergyMeter, FakeMicCapture, FakeMixer, FakeProcessCapture, FakeSpeakerObserver


def _start(repo, notifier, clock, **kw):
    proc, mic = FakeProcessCapture(**kw.get("proc", {})), FakeMicCapture(**kw.get("mic", {}))
    uc = StartRecording(repo, proc, mic, notifier, clock, mic_device="Test Mic")
    return uc, proc, mic


def test_start_recording_creates_meeting_and_starts_both_captures(repo, notifier, clock):
    uc, proc, mic = _start(repo, notifier, clock)

    active = uc.execute(pid=4242, title="Daily")

    assert repo.exists(active.meeting.id)
    assert repo.load_active() is active
    assert active.meeting.pid == 4242 and active.meeting.title == "Daily"
    assert proc.handles[0].out.name == TAP_TRACK
    assert mic.handles[0].out.name == MIC_TRACK
    # both recorders get the same epoch: the meeting start, so the tracks line up
    assert proc.epochs == mic.epochs == [active.meeting.started_at.timestamp()]
    assert notifier.messages[0][0] == "Recording started"


def test_start_recording_rolls_back_if_mic_fails(repo, notifier, clock):
    uc, proc, _ = _start(repo, notifier, clock, mic={"fail_on_start": True})

    with pytest.raises(CaptureError):
        uc.execute(pid=1)

    assert repo.list_meetings() == []
    assert proc.is_stopped(proc.handles[0])
    assert notifier.messages == []


def test_stop_recording_mixes_cleans_and_saves(repo, notifier, clock):
    start, proc, mic = _start(repo, notifier, clock)
    active = start.execute(pid=1)
    repo.touch(active.meeting.id, TAP_TRACK)
    repo.touch(active.meeting.id, MIC_TRACK)
    mixer = FakeMixer()
    clock.advance(minutes=30)

    class MixerThatWrites(FakeMixer):
        def mix(self, tracks, out):
            repo.touch(active.meeting.id, AUDIO)
            return super().mix(tracks, out)

    mixer = MixerThatWrites()
    meeting = StopRecording(repo, proc, mic, mixer, notifier, clock).execute(active)

    assert meeting.duration_seconds == 1800
    assert mixer.calls[0][1].name == AUDIO
    assert [p.name for p in mixer.calls[0][0]] == [TAP_TRACK, MIC_TRACK]
    files = repo.files(meeting.id)
    assert TAP_TRACK not in files and MIC_TRACK not in files
    assert derive_status(files) == MeetingStatus.RECORDED
    assert repo.load_meta(meeting.id).ended_at == clock.now()
    assert repo.load_active() is None
    assert notifier.messages[-1] == ("Recording stopped", "30 min. Transcribing…")


def test_cancel_recording_discards_everything(repo, notifier, clock):
    start, proc, mic = _start(repo, notifier, clock)
    active = start.execute(pid=1)

    CancelRecording(repo, proc, mic, notifier).execute(active)

    assert not repo.exists(active.meeting.id)
    assert repo.load_active() is None
    assert proc.is_stopped(proc.handles[0]) and mic.is_stopped(mic.handles[0])
    assert notifier.messages[-1][0] == "Recording cancelled"


def test_start_refuses_when_another_recording_is_active(repo, notifier, clock):
    uc, _, _ = _start(repo, notifier, clock)
    uc.execute(pid=1)
    clock.advance(minutes=1)
    with pytest.raises(RepositoryError):
        uc.execute(pid=2)
    assert len(repo.list_meetings()) == 1


def test_start_recording_rolls_back_if_process_capture_fails(repo, notifier, clock):
    uc, _, mic = _start(repo, notifier, clock, proc={"fail_on_start": True})

    with pytest.raises(CaptureError, match="Teams capture"):
        uc.execute(pid=1)

    assert repo.list_meetings() == []
    assert repo.load_active() is None
    assert mic.handles == []


class _Disk:
    def __init__(self, free):
        self.free = free

    def free_bytes(self):
        return self.free


@pytest.mark.parametrize("free, warned", [(1_000_000_000, True), (40_000_000_000, False), (None, False)])
def test_start_warns_when_little_recording_fits(repo, notifier, clock, free, warned):
    from teams_recorder.application.use_cases import StartRecording
    from tests.fakes import FakeMicCapture, FakeProcessCapture

    StartRecording(repo, FakeProcessCapture(), FakeMicCapture(), notifier, clock, "mic", _Disk(free)).execute(pid=1)
    assert ("Low disk space" in [t for t, _ in notifier.messages]) is warned


# --- speaker observer and energy (docs/tasks/speaker-attribution, task 5) ------------------------------
def _observed_start(repo, notifier, clock, speakers):
    proc, mic = FakeProcessCapture(), FakeMicCapture()
    return StartRecording(repo, proc, mic, notifier, clock, "Test Mic", speakers=speakers), proc, mic


def _subject_log(subject):
    return SpeakerLog(subject=subject, roster=("Felipe",), me="Felipe", ended=True)


def test_ut033_observer_starts_after_both_captures_and_its_handle_is_persisted(repo, notifier, clock):
    seen = {}

    class Observer(FakeSpeakerObserver):
        def start(self, out, epoch):
            seen["captures"] = (len(proc.handles), len(mic.handles))
            seen["notified"] = len(notifier.messages)
            return super().start(out, epoch)

    speakers = Observer()
    uc, proc, mic = _observed_start(repo, notifier, clock, speakers)

    active = uc.execute(pid=1)

    assert seen == {"captures": (1, 1), "notified": 0}
    assert speakers.starts == [(repo.path(active.meeting.id, SPEAKERS), active.meeting.started_at.timestamp())]
    assert active.speakers_handle is speakers.handles[0]
    assert repo.load_active().speakers_handle == speakers.handles[0]
    assert notifier.messages[0][0] == "Recording started"
    assert repo.unavailable == {}


def test_ut033_the_pointer_exists_while_the_observer_starts(repo, notifier, clock):
    """The observer's startup grace must not leave a recording the daemon could not recover."""
    during = {}

    class Observer(FakeSpeakerObserver):
        def start(self, out, epoch):
            during["active"] = repo.load_active()
            return super().start(out, epoch)

    uc, _, _ = _observed_start(repo, notifier, clock, Observer())
    active = uc.execute(pid=1)
    assert during["active"] is active


def test_ut034_unavailable_observer_is_recorded_and_never_raised(repo, notifier, clock, caplog):
    uc, proc, mic = _observed_start(repo, notifier, clock, FakeSpeakerObserver(reason="permission-missing"))

    with caplog.at_level(logging.WARNING):
        active = uc.execute(pid=1)

    assert repo.load_active() is active and active.speakers_handle is None
    assert repo.unavailable == {active.meeting.id: "permission-missing"}
    assert [r.getMessage() for r in caplog.records if "speaker observer unavailable" in r.getMessage()] == [
        f"speaker observer unavailable for {active.meeting.id}: permission-missing (permission-missing)"]
    assert not proc.stopped and not mic.stopped
    assert notifier.messages[0][0] == "Recording started"


@pytest.mark.parametrize("error", [RuntimeError("boom"), OSError("launchctl vanished"), ValueError("bad plist")])
def test_ut035_any_other_observer_failure_is_start_failed(repo, notifier, clock, error):
    uc, _, _ = _observed_start(repo, notifier, clock, FakeSpeakerObserver(error=error))

    active = uc.execute(pid=1)

    assert repo.load_active() is active and active.speakers_handle is None
    assert repo.unavailable == {active.meeting.id: "start-failed"}


def test_the_recording_survives_a_failure_to_write_the_unavailable_line(repo, notifier, clock, caplog):
    def broken(meeting_id, reason):
        raise RepositoryError("disk")

    repo.write_speakers_unavailable = broken
    uc, _, _ = _observed_start(repo, notifier, clock, FakeSpeakerObserver(reason="start-failed"))

    with caplog.at_level(logging.WARNING):
        active = uc.execute(pid=1)

    assert repo.load_active() is active
    assert any("could not be recorded" in r.getMessage() for r in caplog.records)


def test_a_started_observer_is_stopped_when_its_handle_cannot_be_persisted(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    uc, _, _ = _observed_start(repo, notifier, clock, speakers)
    saves = []
    original = repo.save_active

    def flaky(active):
        saves.append(active.speakers_handle)
        if active.speakers_handle is not None:
            raise RepositoryError("disk")
        original(active)

    repo.save_active = flaky
    active = uc.execute(pid=1)

    assert speakers.stopped == [speakers.handles[0].pid]
    assert active.speakers_handle is None
    assert repo.unavailable == {active.meeting.id: "start-failed"}


def test_a_failed_observer_start_boots_out_any_job_it_left_without_a_handle(repo, notifier, clock):
    """Review round 2, issue 041: the job exists from the bootstrap on; a start that fails after it has no handle to stop it by."""
    speakers = FakeSpeakerObserver(error=OSError("launchctl vanished after the bootstrap"))
    uc, _, _ = _observed_start(repo, notifier, clock, speakers)

    active = uc.execute(pid=1)

    assert speakers.stale_stops == 1 and speakers.stopped == [] and active.speakers_handle is None


def test_ut037_without_an_observer_nothing_is_written(repo, notifier, clock):
    uc, _, _ = _observed_start(repo, notifier, clock, None)

    active = uc.execute(pid=1)

    assert active.speakers_handle is None and repo.load_active().speakers_handle is None
    assert repo.unavailable == {}


def test_ut030_untitled_meeting_takes_the_window_subject(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    start, proc, mic = _observed_start(repo, notifier, clock, speakers)
    active = start.execute(pid=1)
    repo.seed_speakers(active.meeting.id, _subject_log("Planejamento da sprint"))
    clock.advance(minutes=5)

    meeting = StopRecording(repo, proc, mic, FakeMixer(), notifier, clock, speakers).stop_capture(active)

    assert meeting.title == "Planejamento da sprint"
    assert repo.load_meta(meeting.id).title == "Planejamento da sprint"
    assert repo.load_active() is None
    # the log is read relative to the meeting's own start, over its whole length
    assert repo.speaker_log_calls == [(meeting.id, meeting.started_at.timestamp(), 300.0)]


def test_ut031_a_given_title_is_kept(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    start, proc, mic = _observed_start(repo, notifier, clock, speakers)
    active = start.execute(pid=1, title="Daily do time")
    repo.seed_speakers(active.meeting.id, _subject_log("Planejamento da sprint"))

    meeting = StopRecording(repo, proc, mic, FakeMixer(), notifier, clock, speakers).stop_capture(active)

    assert meeting.title == "Daily do time" and repo.load_meta(meeting.id).title == "Daily do time"


@pytest.mark.parametrize("speaker_log", [None, _subject_log(None), _subject_log(""), SpeakerLog(unavailable="permission-missing")])
def test_ut032_without_a_subject_the_title_stays_empty(repo, notifier, clock, speaker_log):
    speakers = FakeSpeakerObserver()
    start, proc, mic = _observed_start(repo, notifier, clock, speakers)
    active = start.execute(pid=1)
    repo.seed_speakers(active.meeting.id, speaker_log)

    meeting = StopRecording(repo, proc, mic, FakeMixer(), notifier, clock, speakers).stop_capture(active)

    assert meeting.title is None and repo.load_meta(meeting.id).title is None


def test_an_unreadable_events_file_never_fails_the_stop(repo, notifier, clock, caplog):
    start, proc, mic = _observed_start(repo, notifier, clock, FakeSpeakerObserver())
    active = start.execute(pid=1)

    def unreadable(meeting_id, fallback_epoch, end):
        raise RepositoryError("speakers.jsonl unreadable")

    repo.load_speaker_log = unreadable
    with caplog.at_level(logging.WARNING):
        meeting = StopRecording(repo, proc, mic, FakeMixer(), notifier, clock).stop_capture(active)

    assert meeting.title is None and repo.load_active() is None
    assert any("stays untitled" in r.getMessage() for r in caplog.records)


def test_ut038_stop_capture_stops_the_observer_first_and_the_recorders_after(repo, notifier, clock):
    order = []

    class Observer(FakeSpeakerObserver):
        def stop(self, handle):
            order.append("observer")
            return super().stop(handle)

    class Proc(FakeProcessCapture):
        def stop(self, handle):
            order.append("tap")
            return super().stop(handle)

    class Mic(FakeMicCapture):
        def stop(self, handle):
            order.append("mic")
            return super().stop(handle)

    speakers = Observer()
    proc, mic = Proc(), Mic()
    active = StartRecording(repo, proc, mic, notifier, clock, "m", speakers=speakers).execute(pid=1)

    StopRecording(repo, proc, mic, FakeMixer(), notifier, clock, speakers).stop_capture(active)

    assert order == ["observer", "tap", "mic"]
    assert speakers.stopped == [active.speakers_handle.pid]


def test_ut038_a_failing_observer_stop_does_not_keep_the_recorders_running(repo, notifier, clock, caplog):
    speakers = FakeSpeakerObserver(stop_error=RuntimeError("bootout failed"))
    start, proc, mic = _observed_start(repo, notifier, clock, speakers)
    active = start.execute(pid=1)
    speakers.stop_error = RuntimeError("bootout failed")

    with caplog.at_level(logging.WARNING):
        StopRecording(repo, proc, mic, FakeMixer(), notifier, clock, speakers).stop_capture(active)

    assert proc.is_stopped(proc.handles[0]) and mic.is_stopped(mic.handles[0])
    assert repo.load_active() is None
    assert any("could not be stopped" in r.getMessage() for r in caplog.records)


def test_stop_capture_tolerates_a_recording_without_an_observer_handle(repo, notifier, clock):
    speakers = FakeSpeakerObserver(reason="binary-missing")
    start, proc, mic = _observed_start(repo, notifier, clock, speakers)
    active = start.execute(pid=1)

    StopRecording(repo, proc, mic, FakeMixer(), notifier, clock, speakers).stop_capture(active)

    assert speakers.stopped == []


def test_stop_capture_and_cancel_boot_out_a_job_whose_handle_was_never_persisted(repo, notifier, clock):
    """A `trec start` interrupted during the observer's startup grace leaves the job and no handle (issue 041)."""
    speakers = FakeSpeakerObserver()
    start, proc, mic = _observed_start(repo, notifier, clock, speakers)
    active = start.execute(pid=1)
    active.speakers_handle = None
    stale_before = speakers.stale_stops

    StopRecording(repo, proc, mic, FakeMixer(), notifier, clock, speakers).stop_capture(active)

    assert speakers.stale_stops == stale_before + 1 and speakers.stopped == []

    clock.advance(minutes=1)
    second = start.execute(pid=2)
    second.speakers_handle = None
    CancelRecording(repo, proc, mic, notifier, speakers).execute(second)

    assert speakers.stale_stops == stale_before + 2 and speakers.stopped == []
    assert not repo.exists(second.meeting.id)


def test_a_failing_stale_stop_does_not_keep_the_recorders_running(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    start, proc, mic = _observed_start(repo, notifier, clock, speakers)
    active = start.execute(pid=1)
    active.speakers_handle = None
    speakers.stop_error = RuntimeError("bootout failed")

    StopRecording(repo, proc, mic, FakeMixer(), notifier, clock, speakers).stop_capture(active)

    assert proc.is_stopped(proc.handles[0]) and mic.is_stopped(mic.handles[0])


def test_ut038_cancel_stops_the_observer_and_survives_its_failure(repo, notifier, clock):
    speakers = FakeSpeakerObserver()
    start, proc, mic = _observed_start(repo, notifier, clock, speakers)
    active = start.execute(pid=1)

    CancelRecording(repo, proc, mic, notifier, speakers).execute(active)

    assert speakers.stopped == [active.speakers_handle.pid]
    assert proc.is_stopped(proc.handles[0]) and mic.is_stopped(mic.handles[0])
    assert not repo.exists(active.meeting.id)

    failing = FakeSpeakerObserver(stop_error=RuntimeError("boom"))
    start2, proc2, mic2 = _observed_start(repo, notifier, clock, failing)
    clock.advance(minutes=1)
    active2 = start2.execute(pid=2)
    failing.stop_error = RuntimeError("boom")
    CancelRecording(repo, proc2, mic2, notifier, failing).execute(active2)
    assert proc2.is_stopped(proc2.handles[0]) and not repo.exists(active2.meeting.id)


def _timelines():
    return {TAP_TRACK: EnergyTimeline(0.1, (-60.0, -30.0)), MIC_TRACK: EnergyTimeline(0.1, (-120.0, -40.0, -35.0))}


def test_ut036b_energy_is_measured_before_mixing_and_deleting_and_saved(repo, notifier, clock):
    start, proc, mic = _observed_start(repo, notifier, clock, None)
    active = start.execute(pid=1)
    repo.touch(active.meeting.id, TAP_TRACK)
    repo.touch(active.meeting.id, MIC_TRACK)
    events = []

    class Meter(FakeEnergyMeter):
        def measure(self, track):
            events.append(("measure", track.name, track.name in repo.files(active.meeting.id)))
            return super().measure(track)

    class Mixer(FakeMixer):
        def mix(self, tracks, out):
            events.append(("mix", tuple(t.name for t in tracks), {TAP_TRACK, MIC_TRACK} <= repo.files(active.meeting.id)))
            return super().mix(tracks, out)

    saved = []
    original = repo.save_energy
    repo.save_energy = lambda meeting_id, energy: (saved.append(dict(energy)), original(meeting_id, energy))
    meter = Meter(_timelines())

    StopRecording(repo, proc, mic, Mixer(), notifier, clock, energy=meter).execute(active)

    assert events == [("measure", TAP_TRACK, True), ("measure", MIC_TRACK, True), ("mix", (TAP_TRACK, MIC_TRACK), True)]
    assert saved == [_timelines()] and repo.load_energy(active.meeting.id) == _timelines()
    assert TAP_TRACK not in repo.files(active.meeting.id) and MIC_TRACK not in repo.files(active.meeting.id)


def test_ut036_an_energy_failure_leaves_mixing_and_deletion_untouched(repo, notifier, clock, caplog):
    start, proc, mic = _observed_start(repo, notifier, clock, None)
    active = start.execute(pid=1)
    repo.touch(active.meeting.id, TAP_TRACK)
    repo.touch(active.meeting.id, MIC_TRACK)
    mixer = FakeMixer()

    with caplog.at_level(logging.WARNING):
        meeting = StopRecording(repo, proc, mic, mixer, notifier, clock, energy=FakeEnergyMeter(_timelines(), fail={MIC_TRACK})).execute(active)

    assert len(mixer.calls) == 1
    assert repo.load_energy(meeting.id) == {}   # all or nothing: half a measurement labels nothing
    assert TAP_TRACK not in repo.files(meeting.id) and MIC_TRACK not in repo.files(meeting.id)
    assert any("could not be measured" in r.getMessage() and MIC_TRACK in r.getMessage() for r in caplog.records)
    assert notifier.messages[-1][0] == "Recording stopped"


def test_an_energy_meter_that_blows_up_does_not_block_mixing(repo, notifier, clock):
    start, proc, mic = _observed_start(repo, notifier, clock, None)
    active = start.execute(pid=1)

    class Broken:
        def measure(self, track):
            raise RuntimeError("bug")

    mixer = FakeMixer()
    StopRecording(repo, proc, mic, mixer, notifier, clock, energy=Broken()).execute(active)

    assert len(mixer.calls) == 1


def test_energy_that_cannot_be_saved_does_not_block_mixing(repo, notifier, clock):
    start, proc, mic = _observed_start(repo, notifier, clock, None)
    active = start.execute(pid=1)

    def broken(meeting_id, energy):
        raise RepositoryError("disk")

    repo.save_energy = broken
    mixer = FakeMixer()
    StopRecording(repo, proc, mic, mixer, notifier, clock, energy=FakeEnergyMeter(_timelines())).execute(active)

    assert len(mixer.calls) == 1


@pytest.mark.parametrize("speakers", [
    FakeSpeakerObserver(reason="permission-missing"), FakeSpeakerObserver(error=RuntimeError("x")),
    FakeSpeakerObserver(stop_error=RuntimeError("x")),
])
def test_success_criteria_every_observer_failure_still_gives_a_recording_and_audio(repo, notifier, clock, speakers):
    proc, mic = FakeProcessCapture(), FakeMicCapture()
    active = StartRecording(repo, proc, mic, notifier, clock, "m", speakers=speakers).execute(pid=1)
    repo.touch(active.meeting.id, TAP_TRACK)
    repo.touch(active.meeting.id, MIC_TRACK)
    mixer = FakeMixer()
    clock.advance(minutes=10)

    meeting = StopRecording(repo, proc, mic, mixer, notifier, clock, speakers, FakeEnergyMeter(_timelines())).execute(active)

    assert mixer.calls[0][1].name == AUDIO and meeting.duration_seconds == 600
    assert repo.load_active() is None
