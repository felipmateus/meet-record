"""Encadeia as etapas após uma chamada e retoma reuniões pendentes.

Cada etapa falha isoladamente: o erro é registrado em error.txt na pasta da
reunião e as reuniões seguintes não são afetadas (RNF05).
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
        """Executa as etapas que faltam para a reunião, parando na primeira falha."""
        self.repo.clear_failed(meeting_id)
        steps = {
            MeetingStatus.RECORDED: ("transcrição", self.transcribe),
            MeetingStatus.TRANSCRIBED: ("análise", self.analyze),
        }
        while True:
            status = derive_status(self.repo.files(meeting_id))
            step = steps.get(status)
            if step is None:
                return status
            name, use_case = step
            try:
                use_case.execute(meeting_id)
            except Exception as exc:  # noqa: BLE001 - qualquer falha vira error.txt
                log.exception("falha na %s da reunião %s", name, meeting_id)
                self.repo.mark_failed(meeting_id, f"{name}: {exc}")
                self.notifier.notify(f"Falha na {name}", f"Reunião {meeting_id}: {exc}")
                return MeetingStatus.FAILED

    def resume_pending(self) -> dict[str, MeetingStatus]:
        """Retoma todas as reuniões gravadas que ainda não foram analisadas."""
        results: dict[str, MeetingStatus] = {}
        for meeting in self.repo.list_meetings():
            status = derive_status(self.repo.files(meeting.id))
            if status in (MeetingStatus.RECORDED, MeetingStatus.TRANSCRIBED):
                results[meeting.id] = self.process(meeting.id)
        return results
