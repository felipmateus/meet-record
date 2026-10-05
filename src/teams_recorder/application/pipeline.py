"""Chains the steps after a call and resumes pending meetings.

Each step fails in isolation: the error is written to error.txt in the meeting
folder and other meetings are not affected (NFR05).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from teams_recorder.application.ports import MeetingRepository, Notifier
from teams_recorder.application.use_cases.processing import AnalyzeMeeting, TranscribeMeeting
from teams_recorder.application.use_cases.recording import ActiveRecording, StopRecording
from teams_recorder.domain import Meeting, MeetingStatus, derive_status

log = logging.getLogger(__name__)


@dataclass
class Pipeline:
    repo: MeetingRepository
    notifier: Notifier
    stop: StopRecording
    transcribe: TranscribeMeeting
    analyze: AnalyzeMeeting

    def run_after_call(self, active: ActiveRecording) -> Meeting:
        meeting = self.stop.execute(active)
        self.process(meeting.id)
        return meeting

    def process(self, meeting_id: str) -> MeetingStatus:
        """Run the remaining steps for the meeting, stopping at the first failure."""
        self.repo.clear_failed(meeting_id)
        steps = {
            MeetingStatus.RECORDED: ("transcription", self.transcribe),
            MeetingStatus.TRANSCRIBED: ("analysis", self.analyze),
        }
        while True:
            status = derive_status(self.repo.files(meeting_id))
            step = steps.get(status)
            if step is None:
                return status
            name, use_case = step
            try:
                use_case.execute(meeting_id)
            except Exception as exc:  # noqa: BLE001 - any failure becomes error.txt
                log.exception("%s failed for meeting %s", name, meeting_id)
                self.repo.mark_failed(meeting_id, f"{name}: {exc}")
                self.notifier.notify(f"{name.capitalize()} failed", f"Meeting {meeting_id}: {exc}")
                return MeetingStatus.FAILED

    def resume_pending(self) -> dict[str, MeetingStatus]:
        """Resume every recorded meeting that has not been analyzed yet."""
        results: dict[str, MeetingStatus] = {}
        for meeting in self.repo.list_meetings():
            status = derive_status(self.repo.files(meeting.id))
            if status in (MeetingStatus.RECORDED, MeetingStatus.TRANSCRIBED):
                results[meeting.id] = self.process(meeting.id)
        return results
