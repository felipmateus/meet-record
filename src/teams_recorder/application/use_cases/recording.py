"""Recording use cases: start, stop and cancel."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from teams_recorder.application.ports import (
    ActiveRecording,
    AudioMixer,
    Clock,
    DiskSpace,
    MeetingRepository,
    MicCapture,
    Notifier,
    ProcessAudioCapture,
)
from teams_recorder.constants import Audio, raw_bytes_per_hour
from teams_recorder.domain import CaptureError, Meeting, RepositoryError
from teams_recorder.domain.status import AUDIO, MIC_TRACK, TAP_TRACK
from teams_recorder.messages import Err, Notify

__all__ = ["ActiveRecording", "StartRecording", "StopRecording", "CancelRecording"]


@dataclass
class StartRecording:
    repo: MeetingRepository
    process_capture: ProcessAudioCapture
    mic_capture: MicCapture
    notifier: Notifier
    clock: Clock
    mic_device: str
    disk: DiskSpace | None = None
    raw_bytes_per_hour: int = raw_bytes_per_hour(Audio.DEFAULT_BIT_DEPTH)

    def execute(self, pid: int, title: str | None = None) -> ActiveRecording:
        if self.repo.load_active() is not None:
            raise RepositoryError(Err.RECORDING_IN_PROGRESS)
        meeting = Meeting.start(self.clock.now(), pid=pid, title=title)
        self.repo.create(meeting)
        epoch = meeting.started_at.timestamp()  # both tracks are aligned to the meeting start
        try:
            process_handle = self.process_capture.start(pid, self.repo.path(meeting.id, TAP_TRACK), epoch)
        except Exception as exc:
            self.repo.delete_meeting(meeting.id)
            if isinstance(exc, CaptureError):
                raise
            raise CaptureError(Err.TEAMS_CAPTURE_START.format(error=exc)) from exc
        try:
            mic_handle = self.mic_capture.start(self.mic_device, self.repo.path(meeting.id, MIC_TRACK), epoch)
        except Exception as exc:
            self.process_capture.stop(process_handle)
            self.repo.delete_meeting(meeting.id)
            raise CaptureError(Err.MIC_START.format(error=exc)) from exc
        active = ActiveRecording(meeting, process_handle, mic_handle)
        self.repo.save_active(active)
        self.notifier.notify(Notify.RECORDING_STARTED, Notify.RECORDING_STARTED_BODY.format(meeting_id=meeting.id))
        self._warn_if_low_disk()
        return active

    def _warn_if_low_disk(self) -> None:
        free = self.disk.free_bytes() if self.disk else None
        if free is not None and free < Audio.LOW_DISK_HOURS * self.raw_bytes_per_hour:
            self.notifier.notify(Notify.LOW_DISK, Notify.LOW_DISK_BODY.format(free=free / 1e9, hours=free / self.raw_bytes_per_hour))


@dataclass
class StopRecording:
    repo: MeetingRepository
    process_capture: ProcessAudioCapture
    mic_capture: MicCapture
    mixer: AudioMixer
    notifier: Notifier
    clock: Clock

    def execute(self, active: ActiveRecording) -> Meeting:
        return self.finalize(self.stop_capture(active))

    def stop_capture(self, active: ActiveRecording, ended_at: datetime | None = None) -> Meeting:
        """Fast part: stop both recorders and release the active-recording pointer.

        Done before mixing, which can take many minutes for a long meeting: while the pointer
        is held, a new call would be taken for this recording and not be recorded.
        """
        meeting = active.meeting
        self.process_capture.stop(active.process_handle)
        self.mic_capture.stop(active.mic_handle)
        meeting.ended_at = ended_at or self.clock.now()
        self.repo.save_meta(meeting)
        self.repo.clear_active()
        return meeting

    def finalize(self, meeting: Meeting) -> Meeting:
        """Slow part: mix the raw tracks into audio.m4a, then delete them."""
        self.mixer.mix([self.repo.path(meeting.id, TAP_TRACK), self.repo.path(meeting.id, MIC_TRACK)], self.repo.path(meeting.id, AUDIO))
        for track in (TAP_TRACK, MIC_TRACK):
            self.repo.delete_file(meeting.id, track)
        minutes = int((meeting.duration_seconds or 0) // 60)
        self.notifier.notify(Notify.RECORDING_STOPPED, Notify.RECORDING_STOPPED_BODY.format(minutes=minutes))
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
        self.repo.clear_active()
        self.discard(active.meeting.id)

    def discard(self, meeting_id: str) -> None:
        """Delete a meeting whose capture already stopped (e.g. discarded after the call ended)."""
        self.repo.delete_meeting(meeting_id)
        self.notifier.notify(Notify.RECORDING_CANCELLED, Notify.RECORDING_CANCELLED_BODY.format(meeting_id=meeting_id))
