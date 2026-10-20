"""Chains the steps after a call and resumes pending meetings.

Each step fails in isolation: the error is written to error.txt in the meeting
folder and other meetings are not affected (NFR05).
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from teams_recorder.application.ports import MeetingRepository, Notifier
from teams_recorder.application.use_cases.processing import AnalyzeMeeting, TranscribeMeeting
from teams_recorder.application.use_cases.recording import ActiveRecording, StopRecording
from teams_recorder.domain import Meeting, MeetingStatus, derive_status
from teams_recorder.domain.status import AUDIO, MIC_TRACK, TAP_TRACK
from teams_recorder.messages import Err, Log, Notify, Step

log = logging.getLogger(__name__)


@dataclass
class Pipeline:
    repo: MeetingRepository
    notifier: Notifier
    stop: StopRecording
    transcribe: TranscribeMeeting
    analyze: AnalyzeMeeting
    after_analysis: Callable[[str], None] | None = None   # called once a meeting reaches ANALYZED; failures are logged, never error.txt

    def run_after_call(self, active: ActiveRecording) -> Meeting:
        return self.after_stop(self.stop.stop_capture(active))

    def after_stop(self, meeting: Meeting) -> Meeting:
        """Mix a stopped recording, then transcribe and analyze it. A mixing failure becomes error.txt."""
        try:
            self.stop.finalize(meeting)
        except Exception as exc:  # noqa: BLE001 - the raw tracks stay; the next daemon start retries
            log.exception(Log.STEP_FAILED, Step.MIXING, meeting.id)
            self.repo.mark_failed(meeting.id, Err.STEP_ERROR.format(step=Step.MIXING, error=exc))
            self.notifier.notify(Notify.STEP_FAILED.format(step=Step.MIXING.capitalize()), Notify.STEP_FAILED_BODY.format(meeting_id=meeting.id, error=exc))
            return meeting
        self.process(meeting.id)
        return meeting

    def process(self, meeting_id: str) -> MeetingStatus:
        """Run the remaining steps for the meeting, stopping at the first failure."""
        self.repo.clear_failed(meeting_id)
        steps: dict[MeetingStatus, tuple[str, TranscribeMeeting | AnalyzeMeeting]] = {
            MeetingStatus.RECORDED: (Step.TRANSCRIPTION, self.transcribe),
            MeetingStatus.TRANSCRIBED: (Step.ANALYSIS, self.analyze),
        }
        analyzed_now = False
        while True:
            status = derive_status(self.repo.files(meeting_id))
            step = steps.get(status)
            if step is None:
                if analyzed_now and status == MeetingStatus.ANALYZED:
                    self._after_analysis(meeting_id)
                return status
            name, use_case = step
            try:
                use_case.execute(meeting_id)
                analyzed_now = use_case is self.analyze
            except Exception as exc:  # noqa: BLE001 - any failure becomes error.txt
                log.exception(Log.STEP_FAILED, name, meeting_id)
                self.repo.mark_failed(meeting_id, Err.STEP_ERROR.format(step=name, error=exc))
                self.notifier.notify(
                    Notify.STEP_FAILED.format(step=name.capitalize()),
                    Notify.STEP_FAILED_BODY.format(meeting_id=meeting_id, error=exc),
                )
                return MeetingStatus.FAILED

    def _after_analysis(self, meeting_id: str) -> None:
        """Tells the hook that the meeting was analyzed. What the hook does is not this meeting's pipeline: its failure is
        logged, and the meeting stays analyzed without an error file."""
        if self.after_analysis is None:
            return
        try:
            self.after_analysis(meeting_id)
        except Exception:  # noqa: BLE001 - never error.txt: the analysis itself succeeded
            log.exception(Log.AFTER_ANALYSIS_FAILED, meeting_id)

    def resume_pending(self) -> dict[str, MeetingStatus]:
        """Resume every meeting that has not been analyzed yet, including stopped recordings that
        were never mixed (the daemon died, or mixing failed: the raw tracks are retried)."""
        results: dict[str, MeetingStatus] = {}
        active = self.repo.load_active()
        for meeting in self.repo.list_meetings():
            files = self.repo.files(meeting.id)
            if active is not None and active.meeting.id == meeting.id:
                continue
            if AUDIO not in files and (TAP_TRACK in files or MIC_TRACK in files):
                log.info(Log.STOPPED_NOT_MIXED, meeting.id)
                self.repo.clear_failed(meeting.id)
                self.after_stop(meeting)
                results[meeting.id] = derive_status(self.repo.files(meeting.id))
                continue
            status = derive_status(files)
            if status in (MeetingStatus.RECORDED, MeetingStatus.TRANSCRIBED):
                results[meeting.id] = self.process(meeting.id)
        return results
