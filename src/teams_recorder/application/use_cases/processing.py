"""Post-processing use cases: transcribe and analyze a meeting."""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

from teams_recorder.application.ports import MeetingAnalyzer, MeetingRepository, MinutesRenderer, Notifier, Transcriber
from teams_recorder.application.use_cases.verification import VerifyAnalysis
from teams_recorder.constants import Audio, Transcription
from teams_recorder.domain import (
    Analysis, CaptureStats, RepositoryError, Transcript, TranscriptHealth, TranscriptionError, rate_mismatch, transcript_health,
)
from teams_recorder.domain.status import AUDIO, TRANSCRIPT_JSON
from teams_recorder.messages import Err, Log, Notify

log = logging.getLogger(__name__)


def gaps_text(health: TranscriptHealth, limit: int = Transcription.RANGES_IN_NOTIFICATION) -> str:
    """The time ranges without text, the first `limit` of them, for a notification or a CLI line."""
    ranges = health.uncovered_ranges()
    shown = ", ".join(ranges[:limit])
    return Notify.RANGES_MORE.format(shown=shown, more=len(ranges) - limit) if len(ranges) > limit else shown


@dataclass
class TranscribeMeeting:
    """Transcribes a meeting and checks the result for whisper hallucination loops.

    A degraded transcript (more than `max_loop_share` of its segments in loops) is transcribed once
    more with `retry`, the anti-loop settings, and the healthier of the two is kept; both are measured
    against the meeting's length, so a retry that comes back empty or cut short never wins. A retry that
    fails, for any reason, keeps the first pass. One still degraded is saved anyway, marked in its health,
    so the analysis runs on what there is, and the user is notified.

    The Teams track's capture counters are checked too: one recorded at the wrong sample rate (see
    domain/health.rate_mismatch) is garbled before whisper sees it, so its transcript is flagged in the
    health and the user is notified, instead of the minutes silently resting on hallucinations. The
    counters are read before transcribing, and such a track gets no retry: VAD cannot repair it.
    """

    repo: MeetingRepository
    transcriber: Transcriber
    language: str = Audio.DEFAULT_LANGUAGE
    max_loop_share: float = Transcription.MAX_LOOP_SHARE
    retry: Transcriber | None = None   # None: no second pass ([transcription] retry_on_loop off, or it would repeat the first)
    notifier: Notifier | None = None
    max_short_pad_share: float = Audio.MAX_SHORT_PAD_SHARE
    rate_check_min_seconds: float = Audio.RATE_CHECK_MIN_SECONDS

    def execute(self, meeting_id: str) -> Transcript:
        if AUDIO not in self.repo.files(meeting_id):
            raise TranscriptionError(Err.NO_AUDIO_FILE.format(meeting_id=meeting_id, filename=AUDIO))
        duration = self.repo.load_meta(meeting_id).duration_seconds
        with self.repo.lock(meeting_id):
            mismatch = self._rate_mismatch(meeting_id)
            transcript = self._transcribe(meeting_id, self.repo.path(meeting_id, AUDIO), duration, allow_retry=mismatch is None)
            if transcript.health is not None and mismatch is not None:
                transcript.health = replace(transcript.health, rate_mismatch=True, short_padding_share=mismatch.short_padding_share)
            self.repo.save_transcript(meeting_id, transcript)
        health = transcript.health
        if health is not None and health.degraded and self.notifier is not None:
            gaps = Notify.NO_TEXT_IN.format(ranges=gaps_text(health)) if health.uncovered else ""
            self.notifier.notify(Notify.TRANSCRIPT_DEGRADED,
                                 Notify.TRANSCRIPT_DEGRADED_BODY.format(meeting_id=meeting_id, loop=health.loop_share, gaps=gaps))
        if health is not None and health.rate_mismatch and self.notifier is not None:
            self.notifier.notify(Notify.RATE_MISMATCH, Notify.RATE_MISMATCH_BODY.format(meeting_id=meeting_id, share=health.short_padding_share))
        return transcript

    def _rate_mismatch(self, meeting_id: str) -> CaptureStats | None:
        """The Teams track's counters when they show a sample-rate mismatch, else None. Read before transcribing,
        since teams-tap writes them when the recording stops. Advisory: unreadable counters skip the check
        rather than fail the transcription."""
        try:
            stats = self.repo.load_capture_stats(meeting_id)
        except (RepositoryError, OSError) as exc:   # OSError: a repository that does not translate its I/O errors
            log.warning(Log.CAPTURE_STATS_UNREADABLE, meeting_id, exc)
            return None
        if stats is None or not rate_mismatch(stats, self.max_short_pad_share, self.rate_check_min_seconds):
            return None
        rates = ", ".join(f"{r:.0f}" for r in stats.device_rates) or "?"   # literal-ok: list separator and unknown marker in a log argument
        log.warning(Log.RATE_MISMATCH, meeting_id, 100 * stats.short_padding_share, stats.short_padded_seconds, stats.written_seconds, rates)
        return stats

    def _checked(self, transcriber: Transcriber, audio: Path, duration: float | None) -> tuple[Transcript, TranscriptHealth]:
        transcript = transcriber.transcribe(audio, self.language)
        health = transcript.health = transcript_health(transcript, self.max_loop_share, duration)
        return transcript, health

    def _transcribe(self, meeting_id: str, audio: Path, duration: float | None, allow_retry: bool) -> Transcript:
        """`allow_retry=False` when the audio itself is known to be broken: a second pass cannot repair it."""
        first, health = self._checked(self.transcriber, audio, duration)
        if not health.degraded:
            return first
        log.warning(Log.TRANSCRIPT_DEGRADED, meeting_id, 100 * health.loop_share, health.covered_minutes, health.total_minutes)
        if self.retry is None:
            return first
        if not allow_retry:
            log.info(Log.TRANSCRIPT_RETRY_SKIPPED, meeting_id)
            return first
        log.info(Log.TRANSCRIPT_RETRY, meeting_id)
        try:
            second, retried = self._checked(self.retry, audio, duration)
        except Exception as exc:  # noqa: BLE001 - any failure: the first pass is degraded but still the best there is
            log.exception(Log.TRANSCRIPT_RETRY_FAILED, meeting_id, exc)
            return first
        keep_retry = retried.is_healthier_than(health)
        log.info(Log.TRANSCRIPT_RETRY_RESULT, meeting_id, 100 * retried.loop_share, retried.covered_minutes, retried.total_minutes,
                 Log.PASS_RETRY if keep_retry else Log.PASS_FIRST)
        kept, kept_health = (second, retried) if keep_retry else (first, health)
        kept.health = replace(kept_health, retried=True)
        return kept


@dataclass
class AnalyzeMeeting:
    repo: MeetingRepository
    analyzer: MeetingAnalyzer
    minutes: MinutesRenderer | None = None
    verify: VerifyAnalysis | None = None   # marks the claims before they are saved; None: not verified (until task 7.0 wires it)

    def execute(self, meeting_id: str) -> Analysis:
        meeting = self.repo.load_meta(meeting_id)
        transcript = self.repo.load_transcript(meeting_id)
        with self.repo.lock(meeting_id):
            analysis = self.analyzer.analyze(transcript, meeting)
            analysis.meeting_id = meeting_id
            if self.verify is not None:
                analysis = self.verify.execute(meeting, analysis, transcript)
            self.repo.save_analysis(meeting_id, analysis)
            if analysis.title and not meeting.title:
                meeting.title = analysis.title  # automatic recordings get a readable name
                self.repo.save_meta(meeting)
            if self.minutes is not None:
                self.repo.save_minutes(meeting_id, self.minutes.render(meeting, analysis, transcript.health))
        return analysis


@dataclass
class RenderMinutes:
    """(Re)renders minutes.md from an existing analysis.json, without calling the LLM."""

    repo: MeetingRepository
    minutes: MinutesRenderer

    def execute(self, meeting_id: str) -> str:
        meeting = self.repo.load_meta(meeting_id)
        analysis = self.repo.load_analysis(meeting_id)
        health = self.repo.load_transcript(meeting_id).health if TRANSCRIPT_JSON in self.repo.files(meeting_id) else None
        markdown = self.minutes.render(meeting, analysis, health)
        self.repo.save_minutes(meeting_id, markdown)
        return markdown
