"""Post-processing use cases: transcribe and analyze a meeting."""
from __future__ import annotations

from dataclasses import dataclass

from teams_recorder.application.ports import MeetingAnalyzer, MeetingRepository, MinutesRenderer, Transcriber
from teams_recorder.constants import Audio
from teams_recorder.domain import Analysis, Transcript, TranscriptionError
from teams_recorder.domain.status import AUDIO
from teams_recorder.messages import Err


@dataclass
class TranscribeMeeting:
    repo: MeetingRepository
    transcriber: Transcriber
    language: str = Audio.DEFAULT_LANGUAGE

    def execute(self, meeting_id: str) -> Transcript:
        if AUDIO not in self.repo.files(meeting_id):
            raise TranscriptionError(Err.NO_AUDIO_FILE.format(meeting_id=meeting_id, filename=AUDIO))
        with self.repo.lock(meeting_id):
            transcript = self.transcriber.transcribe(self.repo.path(meeting_id, AUDIO), self.language)
            self.repo.save_transcript(meeting_id, transcript)
        return transcript


@dataclass
class AnalyzeMeeting:
    repo: MeetingRepository
    analyzer: MeetingAnalyzer
    minutes: MinutesRenderer | None = None

    def execute(self, meeting_id: str) -> Analysis:
        meeting = self.repo.load_meta(meeting_id)
        transcript = self.repo.load_transcript(meeting_id)
        with self.repo.lock(meeting_id):
            analysis = self.analyzer.analyze(transcript, meeting)
            analysis.meeting_id = meeting_id
            self.repo.save_analysis(meeting_id, analysis)
            if analysis.title and not meeting.title:
                meeting.title = analysis.title  # automatic recordings get a readable name
                self.repo.save_meta(meeting)
            if self.minutes is not None:
                self.repo.save_minutes(meeting_id, self.minutes.render(meeting, analysis))
        return analysis


@dataclass
class RenderMinutes:
    """(Re)renders minutes.md from an existing analysis.json, without calling the LLM."""

    repo: MeetingRepository
    minutes: MinutesRenderer

    def execute(self, meeting_id: str) -> str:
        meeting = self.repo.load_meta(meeting_id)
        analysis = self.repo.load_analysis(meeting_id)
        markdown = self.minutes.render(meeting, analysis)
        self.repo.save_minutes(meeting_id, markdown)
        return markdown
