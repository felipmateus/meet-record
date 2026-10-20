"""Audio retention: deletes the audio of old meetings that already have a transcript."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from teams_recorder.application.ports import Clock, MeetingRepository
from teams_recorder.constants import Audio
from teams_recorder.domain.status import AUDIO, TRANSCRIPT_JSON


@dataclass
class PurgeOldAudio:
    repo: MeetingRepository
    clock: Clock
    retention_days: int = Audio.RETENTION_DAYS

    def execute(self) -> list[str]:
        cutoff = self.clock.now() - timedelta(days=self.retention_days)
        purged: list[str] = []
        for meeting in self.repo.list_meetings():
            files = self.repo.files(meeting.id)
            if AUDIO in files and TRANSCRIPT_JSON in files and meeting.started_at < cutoff:
                self.repo.delete_file(meeting.id, AUDIO)
                purged.append(meeting.id)
        return purged
