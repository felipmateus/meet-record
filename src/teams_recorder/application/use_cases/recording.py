"""Recording use cases: start, stop and cancel."""
from __future__ import annotations

from dataclasses import dataclass

from teams_recorder.application.ports import (
    ActiveRecording,
    AudioMixer,
    Clock,
    MeetingRepository,
    MicCapture,
    Notifier,
    ProcessAudioCapture,
)
from teams_recorder.domain import CaptureError, Meeting, RepositoryError
from teams_recorder.domain.status import AUDIO, MIC_TRACK, TAP_TRACK

__all__ = ["ActiveRecording", "StartRecording", "StopRecording", "CancelRecording"]


@dataclass
class StartRecording:
    repo: MeetingRepository
    process_capture: ProcessAudioCapture
    mic_capture: MicCapture
    notifier: Notifier
    clock: Clock
    mic_device: str

    def execute(self, pid: int, title: str | None = None) -> ActiveRecording:
        if self.repo.load_active() is not None:
            raise RepositoryError("a recording is already in progress; use `trec stop` or `trec cancel`")
        meeting = Meeting.start(self.clock.now(), pid=pid, title=title)
        self.repo.create(meeting)
        try:
            process_handle = self.process_capture.start(pid, self.repo.path(meeting.id, TAP_TRACK))
        except Exception as exc:
            self.repo.delete_meeting(meeting.id)
            if isinstance(exc, CaptureError):
                raise
            raise CaptureError(f"failed to start the Teams capture: {exc}") from exc
        try:
            mic_handle = self.mic_capture.start(self.mic_device, self.repo.path(meeting.id, MIC_TRACK))
        except Exception as exc:
            self.process_capture.stop(process_handle)
            self.repo.delete_meeting(meeting.id)
            raise CaptureError(f"failed to start the microphone: {exc}") from exc
        active = ActiveRecording(meeting, process_handle, mic_handle)
        self.repo.save_active(active)
        self.notifier.notify("Recording started", f"Meeting {meeting.id}")
        return active


@dataclass
class StopRecording:
    repo: MeetingRepository
    process_capture: ProcessAudioCapture
    mic_capture: MicCapture
    mixer: AudioMixer
    notifier: Notifier
    clock: Clock

    def execute(self, active: ActiveRecording) -> Meeting:
        meeting = active.meeting
        tap = self.process_capture.stop(active.process_handle)
        mic = self.mic_capture.stop(active.mic_handle)
        meeting.ended_at = self.clock.now()
        self.mixer.mix([tap, mic], self.repo.path(meeting.id, AUDIO))
        for track in (TAP_TRACK, MIC_TRACK):
            self.repo.delete_file(meeting.id, track)
        self.repo.save_meta(meeting)
        self.repo.clear_active()
        minutes = int((meeting.duration_seconds or 0) // 60)
        self.notifier.notify("Recording stopped", f"{minutes} min. Transcribing…")
        return meeting


@dataclass
class CancelRecording:
    repo: MeetingRepository
    process_capture: ProcessAudioCapture
    mic_capture: MicCapture
    notifier: Notifier

    def execute(self, active: ActiveRecording) -> None:
        for capture, handle in ((self.process_capture, active.process_handle), (self.mic_capture, active.mic_handle)):
            try:
                capture.stop(handle)
            except Exception:  # noqa: BLE001 - cancellation is best effort
                pass
        self.repo.delete_meeting(active.meeting.id)
        self.repo.clear_active()
        self.notifier.notify("Recording cancelled", f"Meeting {active.meeting.id} discarded")
