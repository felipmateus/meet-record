"""Casos de uso de pós-processamento: transcrever e analisar uma reunião."""
from __future__ import annotations

from dataclasses import dataclass

from teams_recorder.application.ports import MeetingAnalyzer, MeetingRepository, Transcriber
from teams_recorder.domain import Analysis, Transcript, TranscriptionError
from teams_recorder.domain.status import AUDIO


@dataclass
class TranscribeMeeting:
    repo: MeetingRepository
    transcriber: Transcriber
    language: str = "pt"

    def execute(self, meeting_id: str) -> Transcript:
        if AUDIO not in self.repo.files(meeting_id):
            raise TranscriptionError(f"reunião {meeting_id} não tem {AUDIO}")
        with self.repo.lock(meeting_id):
            transcript = self.transcriber.transcribe(self.repo.path(meeting_id, AUDIO), self.language)
            self.repo.save_transcript(meeting_id, transcript)
        return transcript


@dataclass
class AnalyzeMeeting:
    repo: MeetingRepository
    analyzer: MeetingAnalyzer

    def execute(self, meeting_id: str) -> Analysis:
        meeting = self.repo.load_meta(meeting_id)
        transcript = self.repo.load_transcript(meeting_id)
        with self.repo.lock(meeting_id):
            analysis = self.analyzer.analyze(transcript, meeting)
            analysis.meeting_id = meeting_id
            self.repo.save_analysis(meeting_id, analysis)
        return analysis
