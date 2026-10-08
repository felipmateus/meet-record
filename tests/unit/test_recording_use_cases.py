import pytest

from teams_recorder.application.use_cases import CancelRecording, StartRecording, StopRecording
from teams_recorder.domain import CaptureError, MeetingStatus, RepositoryError, derive_status
from teams_recorder.domain.status import AUDIO, MIC_TRACK, TAP_TRACK
from tests.fakes import FakeMicCapture, FakeMixer, FakeProcessCapture


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
