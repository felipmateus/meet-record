"""Máquina de estados do daemon com todas as portas simuladas."""
from dataclasses import dataclass

import pytest

from teams_recorder.adapters.inbound.daemon import Daemon
from teams_recorder.application.ports import CallState
from teams_recorder.application.use_cases import AnalyzeMeeting, CancelRecording, StartRecording, StopRecording, TranscribeMeeting
from teams_recorder.application.pipeline import Pipeline
from teams_recorder.domain import Meeting, MeetingStatus, derive_status
from teams_recorder.domain.status import AUDIO, MIC_TRACK, TAP_TRACK
from tests.fakes import FakeAnalyzer, FakeCallDetector, FakeMicCapture, FakeMixer, FakeProcessCapture, FakeTranscriber


@dataclass
class FakeContainer:
    """Só o que o Daemon usa do Container real."""
    repo: object
    detector: object
    notifier: object
    clock: object
    proc: FakeProcessCapture
    mic: FakeMicCapture

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


def _daemon(repo, notifier, clock, states, **kw):
    c = FakeContainer(repo, FakeCallDetector(states), notifier, clock, FakeProcessCapture(), FakeMicCapture())
    inline = lambda fn: fn()  # noqa: E731 - pós-processamento síncrono nos testes
    return Daemon(c, poll_seconds=0, start_after=2, stop_after=3, sleep=lambda s: None, run_in_background=inline, **kw), c


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
    assert titles[:2] == ["Gravação iniciada", "Gravação encerrada"]


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
    assert d.active is not None  # os dois UNKNOWN não zeraram a contagem


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

    d.recover()

    assert repo.load_active() is None
    assert derive_status(repo.files(orphan.meeting.id)) == MeetingStatus.RECORDED


def test_recover_clears_pointer_without_tracks(repo, notifier, clock):
    d, c = _daemon(repo, notifier, clock, [])
    c.start_recording().execute(pid=1)  # sem trilhas gravadas
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
    with pytest.raises(Exception, match="sem detector"):
        d.tick()


def test_dead_capturer_is_logged_once(repo, notifier, clock, caplog):
    import logging
    d, c = _daemon(repo, notifier, clock, [CallState.IN_CALL] * 5)
    d.tick(); d.tick()
    assert d.active is not None
    c.proc.died = {d.active.process_handle.pid}
    with caplog.at_level(logging.WARNING):
        d.tick(); d.tick()
    warnings = [r for r in caplog.records if "morreu durante a chamada" in r.getMessage()]
    assert len(warnings) == 1 and "teams-tap" in warnings[0].getMessage()
