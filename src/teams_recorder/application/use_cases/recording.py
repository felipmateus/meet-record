"""Recording use cases: start, stop and cancel."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from teams_recorder.application.ports import (
    ActiveRecording,
    AudioMixer,
    CaptureHandle,
    Clock,
    DiskSpace,
    EnergyMeter,
    MeetingRepository,
    MicCapture,
    Notifier,
    ProcessAudioCapture,
    SpeakerObserver,
)
from teams_recorder.constants import Audio, raw_bytes_per_hour
from teams_recorder.domain import CaptureError, EnergyTimeline, Meeting, RepositoryError, SpeakerReason, SpeakersUnavailable
from teams_recorder.domain.status import AUDIO, MIC_TRACK, SPEAKERS, TAP_TRACK
from teams_recorder.messages import Err, Log, Notify

__all__ = ["ActiveRecording", "StartRecording", "StopRecording", "CancelRecording"]

log = logging.getLogger(__name__)


def _stop_observer(speakers: SpeakerObserver | None, handle: CaptureHandle | None) -> None:
    """Best effort: the observer is an extra, so a failure to stop it never costs the recorders their stop.

    Without a handle the observer may still be running: its job exists from the bootstrap, a startup grace before its
    handle is persisted, and a crash or an interrupted `trec start` in that window leaves it behind. The job has a fixed
    label (safety invariant 11), so it is stopped without the handle."""
    if speakers is None:
        return
    try:
        if handle is None:
            speakers.stop_stale()
        else:
            speakers.stop(handle)
    except Exception as exc:  # noqa: BLE001 - see above
        log.warning(Log.SPEAKERS_STOP_FAILED, handle.pid if handle is not None else None, exc)


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
    speakers: SpeakerObserver | None = None   # reads who speaks from the Teams window; None: Windows or [speakers] enabled = false

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
        self.repo.save_active(active)   # before the observer's startup grace: a crash in it still leaves a recording to recover
        self._start_observer(active)
        self.notifier.notify(Notify.RECORDING_STARTED, Notify.RECORDING_STARTED_BODY.format(meeting_id=meeting.id))
        self._warn_if_low_disk()
        return active

    def _start_observer(self, active: ActiveRecording) -> None:
        """Starts the speaker observer after both recorders; its failure is recorded in speakers.jsonl and never raised."""
        if self.speakers is None:
            return
        meeting_id = active.meeting.id
        try:
            active.speakers_handle = self.speakers.start(self.repo.path(meeting_id, SPEAKERS), active.meeting.started_at.timestamp())
            self.repo.save_active(active)   # the handle is persisted before the recording is reported started: `trec stop` stops it
        except Exception as exc:  # noqa: BLE001 - the recording never depends on the observer
            # it started but its handle could not be persisted, or it failed half-way through its startup: do not leave a job running
            _stop_observer(self.speakers, active.speakers_handle)
            active.speakers_handle = None
            reason = exc.reason if isinstance(exc, SpeakersUnavailable) else SpeakerReason.START_FAILED.value
            log.warning(Log.SPEAKERS_UNAVAILABLE, meeting_id, reason, exc)
            try:
                self.repo.write_speakers_unavailable(meeting_id, reason)
            except Exception as write_exc:  # noqa: BLE001 - nor on the note saying why it did not run
                log.warning(Log.SPEAKERS_UNAVAILABLE_NOT_RECORDED, meeting_id, write_exc)
            return
        log.info(Log.SPEAKERS_STARTED, meeting_id, active.speakers_handle.pid)

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
    speakers: SpeakerObserver | None = None   # stopped with the recorders; None: no observer wired
    energy: EnergyMeter | None = None         # measures both raw tracks before they are deleted; None: not measured

    def execute(self, active: ActiveRecording) -> Meeting:
        return self.finalize(self.stop_capture(active))

    def stop_capture(self, active: ActiveRecording, ended_at: datetime | None = None) -> Meeting:
        """Fast part: stop the observer and both recorders, release the active-recording pointer, title the meeting.

        Done before mixing, which can take many minutes for a long meeting: while the pointer
        is held, a new call would be taken for this recording and not be recorded.
        """
        meeting = active.meeting
        _stop_observer(self.speakers, active.speakers_handle)   # first: its last events are on disk when this returns
        self.process_capture.stop(active.process_handle)
        self.mic_capture.stop(active.mic_handle)
        meeting.ended_at = ended_at or self.clock.now()
        self.repo.save_meta(meeting)
        self.repo.clear_active()
        self._title_from_window(meeting)
        return meeting

    def _title_from_window(self, meeting: Meeting) -> None:
        """An untitled meeting takes the subject the observer read from the Teams window; never fails the stop."""
        if meeting.title is not None:
            return
        try:
            speaker_log = self.repo.load_speaker_log(meeting.id, meeting.started_at.timestamp(), meeting.duration_seconds or 0.0)
            subject = speaker_log.subject if speaker_log is not None else None
            if not subject:
                return
            meeting.title = subject
            self.repo.save_meta(meeting)
        except Exception as exc:  # noqa: BLE001 - a title is a nicety
            meeting.title = None
            log.warning(Log.TITLE_FROM_WINDOW_FAILED, meeting.id, exc)
            return
        log.info(Log.TITLE_FROM_WINDOW, meeting.id, subject)

    def finalize(self, meeting: Meeting) -> Meeting:
        """Slow part: measure the raw tracks' energy, mix them into audio.m4a, then delete them."""
        self._measure_energy(meeting)   # the raw tracks are gone after this method; the labelling of the user's lines needs them
        self.mixer.mix([self.repo.path(meeting.id, TAP_TRACK), self.repo.path(meeting.id, MIC_TRACK)], self.repo.path(meeting.id, AUDIO))
        for track in (TAP_TRACK, MIC_TRACK):
            self.repo.delete_file(meeting.id, track)
        minutes = int((meeting.duration_seconds or 0) // 60)
        self.notifier.notify(Notify.RECORDING_STOPPED, Notify.RECORDING_STOPPED_BODY.format(minutes=minutes))
        return meeting


    def _measure_energy(self, meeting: Meeting) -> None:
        """Saves energy.json with both tracks, or nothing: a failure is logged and mixing goes on."""
        if self.energy is None:
            return
        timelines: dict[str, EnergyTimeline] = {}
        for track in (TAP_TRACK, MIC_TRACK):
            try:
                timeline = self.energy.measure(self.repo.path(meeting.id, track))
            except Exception as exc:  # noqa: BLE001 - the mix and the transcript do not depend on it
                log.warning(Log.ENERGY_FAILED, track, exc)
                return
            log.info(Log.ENERGY_MEASURED, track, len(timeline.levels) * timeline.step, len(timeline.levels))
            timelines[track] = timeline
        try:
            self.repo.save_energy(meeting.id, timelines)
        except Exception as exc:  # noqa: BLE001 - same
            log.warning(Log.ENERGY_NOT_SAVED, meeting.id, exc)


@dataclass
class CancelRecording:
    repo: MeetingRepository
    process_capture: ProcessAudioCapture
    mic_capture: MicCapture
    notifier: Notifier
    speakers: SpeakerObserver | None = None

    def execute(self, active: ActiveRecording) -> None:
        _stop_observer(self.speakers, active.speakers_handle)
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
