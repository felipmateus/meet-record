"""Post-processing use cases: transcribe and analyze a meeting."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path

from teams_recorder.application.ports import (
    Clock, LanguageDetector, MeetingAnalyzer, MeetingRepository, MinutesRenderer, Notifier, Transcriber,
)
from teams_recorder.application.use_cases.verification import VerifyAnalysis
from teams_recorder.constants import Audio, Speakers, Transcription
from teams_recorder.domain import (
    Analysis, CaptureStats, LanguageDetection, LanguageReason, LanguageRules, RepositoryError, SpeakerReason, Transcript, TranscriptHealth,
    TranscriptionError, choose_language, label_segments, rate_mismatch, sample_offsets, transcript_health, user_label,
)
from teams_recorder.domain.status import AUDIO, MIC_TRACK, TAP_TRACK, TRANSCRIPT_JSON
from teams_recorder.messages import Err, Log, Minutes, Notify

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

    Before transcribing, the language is chosen when a `language_detector` is given ([transcription] language = "auto"): it
    samples the audio at regular offsets, `domain/language.choose_language` votes among `languages`, and the first pass and the
    retry both run in the winner. A meeting whose language cannot be decided, or whose detection fails for any reason, is
    transcribed in `language` (the fallback) and the record says why; detection never fails the transcription. The record is
    saved with the transcript. Without a detector, `language` is the fixed code and nothing is detected.

    Last, the segments are labelled with who said them (domain/speakers.py), from the observer's events and the
    tracks' energy the recording left in the folder. The labels are advisory: a failure to compute them saves the
    transcript as whisper made it. A meeting whose observer was wired but left no label, for a reason the user can
    fix, raises one notification per calendar day (the day of the transcription, `clock`).
    """

    repo: MeetingRepository
    transcriber: Transcriber
    language: str = Audio.DEFAULT_LANGUAGE   # whisper's language without a detector, the fallback with one: always a code, never "auto" (see __post_init__)
    max_loop_share: float = Transcription.MAX_LOOP_SHARE
    retry: Transcriber | None = None   # None: no second pass ([transcription] retry_on_loop off, or it would repeat the first)
    notifier: Notifier | None = None
    max_short_pad_share: float = Audio.MAX_SHORT_PAD_SHARE
    rate_check_min_seconds: float = Audio.RATE_CHECK_MIN_SECONDS
    clock: Clock | None = None   # the day of the daily notice (clock.now().date() at transcription); None: no notice
    user_name: str = ""          # [user] name: the label of the user's own lines when set
    language_detector: LanguageDetector | None = None   # None: [transcription] language is a code, nothing is detected
    languages: tuple[str, ...] = Transcription.LANGUAGES   # the languages detection may choose (the vote's allow-list); `language` is the fallback
    language_rules: LanguageRules = LanguageRules()

    def __post_init__(self) -> None:
        """Whisper must never get `-l auto`: until a detector decides, the language is a code (the container passes the fallback)."""
        if re.fullmatch(Transcription.LANGUAGE_CODE, self.language) is None:
            raise ValueError(Err.NOT_A_LANGUAGE_CODE.format(value=self.language))

    def execute(self, meeting_id: str) -> Transcript:
        if AUDIO not in self.repo.files(meeting_id):
            raise TranscriptionError(Err.NO_AUDIO_FILE.format(meeting_id=meeting_id, filename=AUDIO))
        duration = self.repo.load_meta(meeting_id).duration_seconds
        with self.repo.lock(meeting_id):
            mismatch = self._rate_mismatch(meeting_id)
            audio = self.repo.path(meeting_id, AUDIO)
            detection = self._language(meeting_id, audio, duration)
            language = self.language if detection is None else detection.language
            transcript = self._transcribe(meeting_id, audio, duration, language, allow_retry=mismatch is None)
            if transcript.health is not None and mismatch is not None:
                transcript.health = replace(transcript.health, rate_mismatch=True, short_padding_share=mismatch.short_padding_share)
            transcript.language_detection = detection
            transcript = self._label(meeting_id, transcript, duration)
            self.repo.save_transcript(meeting_id, transcript)
        self._notify_no_labels(meeting_id, transcript)
        health = transcript.health
        if health is not None and health.degraded and self.notifier is not None:
            gaps = Notify.NO_TEXT_IN.format(ranges=gaps_text(health)) if health.uncovered else ""
            self.notifier.notify(Notify.TRANSCRIPT_DEGRADED,
                                 Notify.TRANSCRIPT_DEGRADED_BODY.format(meeting_id=meeting_id, loop=health.loop_share, gaps=gaps))
        if health is not None and health.rate_mismatch and self.notifier is not None:
            self.notifier.notify(Notify.RATE_MISMATCH, Notify.RATE_MISMATCH_BODY.format(meeting_id=meeting_id, share=health.short_padding_share))
        return transcript

    def _language(self, meeting_id: str, audio: Path, duration: float | None) -> LanguageDetection | None:
        """How the meeting's language was chosen; None without a detector (the language is the fixed code). Advisory: any failure
        of the detector gives `self.language` with the reason DETECTION_FAILED, never an error, a notification or an `error.txt`."""
        if self.language_detector is None:
            return None
        try:
            samples = self.language_detector.detect(audio, sample_offsets(duration, self.language_rules), self.language_rules.window_seconds)
        except Exception as exc:  # noqa: BLE001 - detection is advisory: a missing tool, a timeout, a changed output format or a bug all mean the fallback
            log.warning(Log.LANGUAGE_DETECTION_FAILED, meeting_id, self.language, exc)
            return LanguageDetection(self.language, LanguageReason.DETECTION_FAILED)
        detection = choose_language(samples, self.languages, self.language, self.language_rules)
        if detection.detected:
            log.info(Log.LANGUAGE_DETECTED, meeting_id, detection.language, detection.votes, detection.counted, len(detection.samples))
        else:
            log.info(Log.LANGUAGE_FALLBACK, meeting_id, detection.language, detection.reason.value, detection.counted, len(detection.samples))
        return detection

    def _label(self, meeting_id: str, transcript: Transcript, duration: float | None) -> Transcript:
        """The transcript with its speaker labels; the transcript as it is when they cannot be computed."""
        try:
            started = self.repo.load_meta(meeting_id).started_at.timestamp()
            end = duration or max((s.end for s in transcript.segments), default=0.0)
            speaker_log = self.repo.load_speaker_log(meeting_id, started, end)
            energy = self.repo.load_energy(meeting_id)
            user = user_label(self.user_name, speaker_log, Minutes.SPEAKER_USER_FALLBACK)
            labelled = label_segments(transcript, speaker_log, energy.get(MIC_TRACK), energy.get(TAP_TRACK), user)
        except Exception as exc:  # noqa: BLE001 - advisory step that runs before the transcript is saved: whisper's work is never lost to it
            log.warning(Log.SPEAKERS_LABEL_FAILED, meeting_id, exc)
            return transcript
        summary = labelled.labels
        if summary is not None:
            log.info(Log.SPEAKERS_LABELLED, meeting_id, summary.labelled, summary.eligible, ", ".join(labelled.speakers))  # literal-ok: list separator
        return labelled

    def _notify_no_labels(self, meeting_id: str, transcript: Transcript) -> None:
        """The once-a-day notice for a wired observer that produced no label. `no-observer` (nothing was wired) is
        silent and `no-match` only logs. The marker is written after the notification went out."""
        summary = transcript.labels
        if summary is None or summary.reason is None:
            return
        reason = SpeakerReason(summary.reason)
        if reason is SpeakerReason.NO_OBSERVER:
            return
        body = Notify.NO_SPEAKER_LABELS_REASON.get(reason.value, reason.value)
        log.warning(Log.NO_SPEAKER_LABELS, meeting_id, reason.value)
        if not reason.notifies or self.clock is None or self.notifier is None:
            return
        today = self.clock.now().date()
        try:
            if self.repo.last_notice_day(Speakers.NOTICE_KEY) == today:
                return
            self.notifier.notify(Notify.NO_SPEAKER_LABELS, Notify.NO_SPEAKER_LABELS_BODY.format(meeting_id=meeting_id, reason=body))
            self.repo.save_notice_day(Speakers.NOTICE_KEY, today)
        except (RepositoryError, OSError) as exc:   # advisory: the transcript is saved already
            log.warning(Log.SPEAKERS_NOTICE_FAILED, meeting_id, exc)

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

    def _checked(self, transcriber: Transcriber, audio: Path, duration: float | None, language: str) -> tuple[Transcript, TranscriptHealth]:
        transcript = transcriber.transcribe(audio, language)
        transcript.language = language   # whisper's own `language` only echoes the code it was forced to
        health = transcript.health = transcript_health(transcript, self.max_loop_share, duration)
        return transcript, health

    def _transcribe(self, meeting_id: str, audio: Path, duration: float | None, language: str, allow_retry: bool) -> Transcript:
        """`allow_retry=False` when the audio itself is known to be broken: a second pass cannot repair it. Both passes use `language`."""
        first, health = self._checked(self.transcriber, audio, duration, language)
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
            second, retried = self._checked(self.retry, audio, duration, language)
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
    verify: VerifyAnalysis | None = None   # marks the claims before they are saved; None: not verified at all

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
                self.repo.save_minutes(meeting_id, self.minutes.render(meeting, analysis, transcript.health, language=transcript.language))
        return analysis


@dataclass
class RenderMinutes:
    """(Re)renders minutes.md from an existing analysis.json, without calling the LLM."""

    repo: MeetingRepository
    minutes: MinutesRenderer

    def execute(self, meeting_id: str) -> str:
        meeting = self.repo.load_meta(meeting_id)
        analysis = self.repo.load_analysis(meeting_id)
        transcript = self.repo.load_transcript(meeting_id) if TRANSCRIPT_JSON in self.repo.files(meeting_id) else None
        markdown = self.minutes.render(meeting, analysis, transcript.health if transcript else None, language=transcript.language if transcript else None)
        self.repo.save_minutes(meeting_id, markdown)
        return markdown
