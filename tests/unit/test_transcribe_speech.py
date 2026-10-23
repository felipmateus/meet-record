"""The speech check inside `TranscribeMeeting`, on fakes: docs/tasks/speech-check/_tests.md UT-040 to UT-052, UT-055 and UT-056.

The expected texts come from `messages`, so a wording change is one line there."""
from __future__ import annotations

import logging
from datetime import timedelta

import pytest

from teams_recorder.application.pipeline import Pipeline
from teams_recorder.application.use_cases import AnalyzeMeeting, StopRecording, TranscribeMeeting
from teams_recorder.domain import (
    CaptureStats, LanguageReason, MeetingStatus, SpeakerLog, SpeechActivity, SpeechCheck, TranscriptionError, derive_status, sample_offsets,
)
from teams_recorder.domain.status import AUDIO, ERROR, LOCK, TRANSCRIPT_JSON
from teams_recorder.messages import Log, Notify
from tests.fakes import (
    FakeAnalyzer, FakeLanguageDetector, FakeMicCapture, FakeMixer, FakeNotifier, FakeProcessCapture, FakeSpeechDetector, FakeTranscriber,
    InMemoryMeetingRepository, looped_transcript, speech_transcript,
)

SILENT = SpeechActivity(309.6, ())   # the 5-minute recording of 2026-10-17 in which nobody spoke
SPEECH = SpeechActivity(3138.0, ((0.0, 1000.0), (1100.0, 2000.0), (2100.0, 2876.4)))   # 2676.4 s of speech in 3 segments
SPEECH_CHECK = SpeechCheck(True, 2676.4, 3138.0, 3)
_BROKEN_TAP = CaptureStats(written_seconds=709.9, padded_seconds=474.9, short_padded_seconds=474.9, gaps=0, device_rates=(48000.0,))


class LockProbeNotifier(FakeNotifier):
    """Records whether the meeting was locked when each notification went out."""

    def __init__(self, repo: InMemoryMeetingRepository, meeting_id: str) -> None:
        super().__init__()
        self.repo, self.meeting_id = repo, meeting_id
        self.locked: list[bool] = []

    def notify(self, title: str, body: str) -> None:
        self.locked.append(LOCK in self.repo.files(self.meeting_id))
        super().notify(title, body)


class BrokenNotifier:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def notify(self, title: str, body: str) -> None:
        raise self.error


def _use(repo, meeting, detector, transcriber=None, **kwargs):
    """`TranscribeMeeting` in the fixed-language mode (no language detector), with the speech detector given."""
    repo.seed(meeting, {AUDIO})
    transcriber = transcriber or FakeTranscriber(speech_transcript(minutes=10))
    return TranscribeMeeting(repo, transcriber, "pt", speech_detector=detector, **kwargs), transcriber


def _records(caplog, template: str, level: int) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno == level and r.msg == template]


# --- UT-040: no speech ---------------------------------------------------------------------------------------------------

def test_ut040_a_recording_with_no_speech_is_saved_empty_and_whisper_never_runs(repo, meeting, clock, caplog):
    caplog.set_level(logging.INFO)
    first, retry, detector = FakeTranscriber(looped_transcript()), FakeTranscriber(speech_transcript()), FakeLanguageDetector(["en"])
    speech = FakeSpeechDetector(SILENT)
    repo.seed(meeting, {AUDIO})
    use = TranscribeMeeting(repo, first, "pt", retry=retry, language_detector=detector, speech_detector=speech, clock=clock)

    result = use.execute(meeting.id)

    assert first.calls == [] and retry.calls == [] and detector.calls == []
    assert speech.calls == [repo.path(meeting.id, AUDIO)]
    saved = repo.load_transcript(meeting.id)
    assert saved is result and saved.segments == [] and saved.language == "pt"
    assert saved.health is None and saved.language_detection is None and saved.labels is None
    assert saved.speech == SpeechCheck(found=False, speech_seconds=0.0, audio_seconds=309.6, segments=0)
    assert derive_status(repo.files(meeting.id)) is MeetingStatus.TRANSCRIBED
    (warning,) = _records(caplog, Log.NO_SPEECH, logging.WARNING)
    assert warning.getMessage() == Log.NO_SPEECH % (meeting.id, 0.0, 309.6 / 60, 2.0)
    assert not _records(caplog, Log.SPEECH_FOUND, logging.INFO) and not _records(caplog, Log.SPEECH_CHECK_FAILED, logging.WARNING)
    assert ERROR not in repo.files(meeting.id) and LOCK not in repo.files(meeting.id)


def test_ut040_the_empty_transcript_is_in_the_fallback_language_with_a_detector_wired(repo, meeting):
    """`language` is the fallback code, never a detected one (nothing was sampled) and never `auto`."""
    repo.seed(meeting, {AUDIO})
    use = TranscribeMeeting(repo, FakeTranscriber(), "en", language_detector=FakeLanguageDetector(["pt"]), languages=("en", "pt"),
                            speech_detector=FakeSpeechDetector(SILENT))

    result = use.execute(meeting.id)

    assert result.language == "en" and result.language_detection is None


# --- UT-041, UT-042: the notification -----------------------------------------------------------------------------------

@pytest.mark.parametrize(("seconds", "minutes"), [(60.0, "1 min"), (309.6, "5 min"), (3600.0, "60 min")])
def test_ut041_a_recording_of_a_minute_or_more_notifies_once_outside_the_lock(repo, meeting, seconds, minutes):
    notifier = LockProbeNotifier(repo, meeting.id)
    use, _ = _use(repo, meeting, FakeSpeechDetector(SpeechActivity(seconds)), notifier=notifier)

    use.execute(meeting.id)

    assert [title for title, _ in notifier.messages] == [Notify.NO_SPEECH]
    body = notifier.messages[0][1]
    assert body == Notify.NO_SPEECH_BODY.format(meeting_id=meeting.id, minutes=seconds / 60)
    assert meeting.id in body and f"{minutes} of audio" in body and "trec doctor" in body
    assert notifier.locked == [False]   # the transcript is saved and the lock released first


def test_ut041_a_shorter_recording_only_logs(repo, meeting, caplog):
    caplog.set_level(logging.INFO)
    notifier = FakeNotifier()
    use, transcriber = _use(repo, meeting, FakeSpeechDetector(SpeechActivity(59.9)), notifier=notifier)

    result = use.execute(meeting.id)

    assert notifier.messages == [] and transcriber.calls == []
    assert result.speech == SpeechCheck(False, 0.0, 59.9, 0) and repo.load_transcript(meeting.id) is result
    assert len(_records(caplog, Log.NO_SPEECH, logging.WARNING)) == 1


def test_ut041_each_transcription_of_a_no_speech_recording_notifies_with_no_daily_dedup(repo, meeting):
    notifier = FakeNotifier()
    use, _ = _use(repo, meeting, FakeSpeechDetector(SILENT), notifier=notifier)

    use.execute(meeting.id)
    use.execute(meeting.id)

    assert [title for title, _ in notifier.messages] == [Notify.NO_SPEECH, Notify.NO_SPEECH]
    assert repo.notice_days == {}   # no daily notice marker


def test_ut041_without_a_notifier_the_empty_transcript_is_still_saved(repo, meeting):
    use, _ = _use(repo, meeting, FakeSpeechDetector(SILENT))   # notifier=None
    assert use.execute(meeting.id).speech == SpeechCheck(False, 0.0, 309.6, 0)


@pytest.mark.parametrize("error", [RuntimeError("osascript crashed"), OSError("no display"), TranscriptionError("a domain error")])
def test_ut042_a_notifier_that_raises_never_fails_the_saved_transcript(repo, meeting, caplog, error):
    caplog.set_level(logging.INFO)
    notifier = BrokenNotifier(error)
    use, transcriber = _use(repo, meeting, FakeSpeechDetector(SILENT), notifier=notifier)

    result = use.execute(meeting.id)

    assert repo.load_transcript(meeting.id) is result and result.speech is not None and not result.speech.found and transcriber.calls == []
    (warning,) = _records(caplog, Log.NO_SPEECH_NOTIFY_FAILED, logging.WARNING)
    assert warning.getMessage() == Log.NO_SPEECH_NOTIFY_FAILED % (meeting.id, error) and meeting.id in warning.getMessage()
    assert ERROR not in repo.files(meeting.id) and LOCK not in repo.files(meeting.id)


def test_ut042_in_the_pipeline_the_meeting_stays_transcribed_and_goes_on_to_the_analysis(repo, meeting, clock):
    """Without the guard, `Pipeline.process` would write an `error.txt` for a meeting whose transcript was saved."""
    repo.seed(meeting, {AUDIO})
    transcribe = TranscribeMeeting(repo, FakeTranscriber(), "pt", notifier=BrokenNotifier(RuntimeError("no display")),
                                   speech_detector=FakeSpeechDetector(SILENT))
    stop = StopRecording(repo, FakeProcessCapture(), FakeMicCapture(), FakeMixer(), FakeNotifier(), clock)
    pipeline = Pipeline(repo, FakeNotifier(), stop, transcribe, AnalyzeMeeting(repo, FakeAnalyzer()))

    status = pipeline.process(meeting.id)

    assert status is MeetingStatus.ANALYZED and ERROR not in repo.files(meeting.id)


# --- UT-043: a recording with speech -------------------------------------------------------------------------------------

def test_ut043_a_recording_with_speech_gets_the_check_off_commands_and_the_record(repo, meeting, caplog):
    caplog.set_level(logging.INFO)
    meeting.ended_at = meeting.started_at + timedelta(seconds=SPEECH.audio_seconds)   # a recorded length: with none, the stand-in moves `health.total_minutes` (UT-045)
    runs = {}
    for name, detector in (("off", None), ("on", FakeSpeechDetector(SPEECH))):
        first, retry = FakeTranscriber(looped_transcript()), FakeTranscriber(speech_transcript())
        repo.seed(meeting, {AUDIO})
        use = TranscribeMeeting(repo, first, "pt", retry=retry, speech_detector=detector)
        runs[name] = (use.execute(meeting.id), first.calls, retry.calls)

    off, on = runs["off"], runs["on"]
    assert on[1] == off[1] == [(repo.path(meeting.id, AUDIO), "pt")] and on[2] == off[2] == [(repo.path(meeting.id, AUDIO), "pt")]
    assert on[0].health == off[0].health and on[0].health is not None and on[0].health.retried   # the retry ran in both
    assert off[0].speech is None
    assert on[0].speech == SPEECH_CHECK and repo.load_transcript(meeting.id).speech == SPEECH_CHECK
    (found,) = _records(caplog, Log.SPEECH_FOUND, logging.INFO)
    assert found.getMessage() == Log.SPEECH_FOUND % (meeting.id, 2676.4 / 60, 3138.0 / 60, 3)
    assert not _records(caplog, Log.NO_SPEECH, logging.WARNING)


def test_ut043_a_recording_with_speech_is_labelled_and_notifies_as_before(repo, meeting, clock):
    """The speech record does not stand in the way of the later steps: the labels, the degraded notice."""
    notifier = FakeNotifier()
    repo.seed(meeting, {AUDIO})
    repo.seed_speakers(meeting.id, SpeakerLog(unavailable="permission-missing"), {})
    use = TranscribeMeeting(repo, FakeTranscriber(looped_transcript()), "pt", notifier=notifier, clock=clock, speech_detector=FakeSpeechDetector(SPEECH))

    result = use.execute(meeting.id)

    assert result.speech == SPEECH_CHECK and result.labels is not None and result.labels.reason == "permission-missing"
    assert [title for title, _ in notifier.messages] == [Notify.NO_SPEAKER_LABELS, Notify.TRANSCRIPT_DEGRADED]


# --- UT-047, UT-048: what a no-speech recording skips ---------------------------------------------------------------------

def test_ut047_a_rate_mismatch_is_still_logged_but_the_empty_transcript_carries_no_flag_and_no_notice(repo, meeting, caplog):
    caplog.set_level(logging.INFO)
    notifier = FakeNotifier()
    repo.seed(meeting, {AUDIO}, capture_stats=_BROKEN_TAP)
    use = TranscribeMeeting(repo, FakeTranscriber(), "pt", notifier=notifier, speech_detector=FakeSpeechDetector(SILENT))

    result = use.execute(meeting.id)

    assert len(_records(caplog, Log.RATE_MISMATCH, logging.WARNING)) == 1
    assert result.health is None and result.segments == []
    assert [title for title, _ in notifier.messages] == [Notify.NO_SPEECH]   # not Notify.RATE_MISMATCH


def test_ut048_the_labelling_does_not_run_for_a_recording_with_no_speech(repo, meeting, clock, caplog):
    caplog.set_level(logging.INFO)
    notifier = FakeNotifier()
    repo.seed(meeting, {AUDIO})
    repo.seed_speakers(meeting.id, SpeakerLog(unavailable="permission-missing"), {})   # a log that would label nothing, and notify
    use = TranscribeMeeting(repo, FakeTranscriber(), "pt", notifier=notifier, clock=clock, speech_detector=FakeSpeechDetector(SpeechActivity(30.0)))

    result = use.execute(meeting.id)

    assert repo.speaker_log_calls == []   # `_label` never read the log
    assert result.labels is None and result.speakers == [] and result.user_label is None
    assert notifier.messages == [] and repo.notice_days == {}
    assert not any(Log.SPEAKERS_LABELLED in r.msg or Log.NO_SPEAKER_LABELS in r.msg for r in caplog.records)


# --- UT-049: a meeting transcribed again ----------------------------------------------------------------------------------

def test_ut049_transcribing_again_replaces_the_transcript_in_either_direction(repo, meeting):
    detector = FakeSpeechDetector(SPEECH)
    use, transcriber = _use(repo, meeting, detector)

    with_speech = use.execute(meeting.id)
    assert with_speech.segments and with_speech.speech == SPEECH_CHECK and len(transcriber.calls) == 1

    detector.script = SILENT
    silent = use.execute(meeting.id)
    stored = repo.load_transcript(meeting.id)
    assert stored is silent and stored.segments == [] and stored.speech == SpeechCheck(False, 0.0, 309.6, 0) and stored.health is None
    assert len(transcriber.calls) == 1   # whisper did not run the second time

    detector.script = SPEECH
    again = use.execute(meeting.id)
    stored = repo.load_transcript(meeting.id)
    assert stored is again and stored.segments and stored.speech == SPEECH_CHECK and len(transcriber.calls) == 2
    assert ERROR not in repo.files(meeting.id) and LOCK not in repo.files(meeting.id)


# --- UT-050, UT-051: no check, and a check that fails ---------------------------------------------------------------------

def test_ut050_without_a_detector_nothing_is_checked_and_the_transcription_is_as_before(repo, meeting, caplog):
    caplog.set_level(logging.INFO)
    use, transcriber = _use(repo, meeting, None)

    result = use.execute(meeting.id)

    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), "pt")]
    assert result.speech is None and repo.load_transcript(meeting.id).speech is None and result.segments
    assert not any(r.msg in (Log.SPEECH_FOUND, Log.NO_SPEECH, Log.SPEECH_CHECK_FAILED) for r in caplog.records)


@pytest.mark.parametrize("error", [TranscriptionError("whisper-vad-speech-segments: timed out after 300s"), RuntimeError("a bug in the detector")],
                         ids=["transcription-error", "bug"])
def test_ut051_a_check_that_fails_is_one_warning_and_the_meeting_is_transcribed_as_without_it(repo, meeting, caplog, error):
    caplog.set_level(logging.INFO)
    notifier = FakeNotifier()
    detector = FakeSpeechDetector(error=error)
    use, transcriber = _use(repo, meeting, detector, notifier=notifier)

    result = use.execute(meeting.id)

    assert detector.calls == [repo.path(meeting.id, AUDIO)]
    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), "pt")] and result.segments
    assert result.speech is None and repo.load_transcript(meeting.id) is result
    (warning,) = _records(caplog, Log.SPEECH_CHECK_FAILED, logging.WARNING)
    assert warning.getMessage() == Log.SPEECH_CHECK_FAILED % (meeting.id, error) and str(error) in warning.getMessage()
    assert not _records(caplog, Log.NO_SPEECH, logging.WARNING)
    assert notifier.messages == [] and ERROR not in repo.files(meeting.id) and LOCK not in repo.files(meeting.id)


def test_ut051_a_failed_check_leaves_the_commands_of_the_language_detection_and_the_retry_alone(repo, meeting):
    """Safety Invariant 2: a failed check never changes the whisper commands."""
    runs = []
    for detector in (None, FakeSpeechDetector(error=RuntimeError("boom"))):
        first, retry, language = FakeTranscriber(looped_transcript()), FakeTranscriber(speech_transcript()), FakeLanguageDetector(["en"])
        repo.seed(meeting, {AUDIO})
        TranscribeMeeting(repo, first, "pt", retry=retry, language_detector=language, speech_detector=detector).execute(meeting.id)
        runs.append((first.calls, retry.calls, language.calls))
    assert runs[0] == runs[1] and runs[0][0][0][1] == "en"


# --- UT-052: the off switch ------------------------------------------------------------------------------------------------

def test_ut052_a_meeting_saved_as_no_speech_is_transcribed_when_the_check_is_off(repo, meeting):
    use, _ = _use(repo, meeting, FakeSpeechDetector(SILENT))
    assert use.execute(meeting.id).segments == []

    transcriber = FakeTranscriber(speech_transcript(minutes=10))
    off = TranscribeMeeting(repo, transcriber, "pt", speech_detector=None)
    result = off.execute(meeting.id)

    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), "pt")]
    stored = repo.load_transcript(meeting.id)
    assert stored is result and stored.segments and stored.speech is None and stored.health is not None


def test_a_meeting_without_audio_still_fails_before_the_check(repo, meeting):
    detector = FakeSpeechDetector(SILENT)
    repo.seed(meeting, set())
    with pytest.raises(TranscriptionError):
        TranscribeMeeting(repo, FakeTranscriber(), "pt", speech_detector=detector).execute(meeting.id)
    assert detector.calls == [] and TRANSCRIPT_JSON not in repo.files(meeting.id)


def test_a_transcriber_that_raises_after_the_check_saves_nothing(repo, meeting):
    repo.seed(meeting, {AUDIO})
    use = TranscribeMeeting(repo, FakeTranscriber(fail=True), "pt", speech_detector=FakeSpeechDetector(SPEECH))
    with pytest.raises(RuntimeError):
        use.execute(meeting.id)
    assert TRANSCRIPT_JSON not in repo.files(meeting.id) and LOCK not in repo.files(meeting.id)


# --- UT-044 to UT-046, UT-055, UT-056: the language samples and the duration stand-in ----------------------------------------

VANS_SECONDS = 2185.0   # the meeting of the vans: 8 planned samples, speech in the 4th, 5th and 6th windows only
VANS_SPEECH = [0.0, 0.0, 0.0, 9.0, 14.0, 5.0, 0.0, 0.0]   # seconds of speech in each planned 30 s window


def _sampled(repo, meeting, seconds: float = VANS_SECONDS):
    """A meeting of `seconds` seconds with its audio, and the offsets the language detection plans for it."""
    meeting.ended_at = meeting.started_at + timedelta(seconds=seconds)
    repo.seed(meeting, {AUDIO})
    return sample_offsets(seconds)


def _activity(offsets: list[float], speech: list[float], audio_seconds: float = VANS_SECONDS) -> SpeechActivity:
    """Speech inside each window, 2 s after its start: `speech[i]` seconds in the window of `offsets[i]`."""
    return SpeechActivity(audio_seconds, tuple((at + 2.0, at + 2.0 + seconds) for at, seconds in zip(offsets, speech, strict=True) if seconds))


def _auto(repo, speech_detector, language_detector, transcriber=None, **kwargs):
    """`TranscribeMeeting` in auto mode as the container builds it (the fallback is `pt`), with a first pass and a retry on fakes."""
    transcriber = transcriber or FakeTranscriber(looped_transcript())
    retry = FakeTranscriber(speech_transcript())
    use = TranscribeMeeting(repo, transcriber, "pt", retry=retry, language_detector=language_detector, speech_detector=speech_detector, **kwargs)
    return use, transcriber, retry


def test_ut044_only_the_windows_with_speech_are_sent_and_the_dropped_count_is_logged(repo, meeting, caplog):
    caplog.set_level(logging.INFO)
    offsets = _sampled(repo, meeting)
    speech, language = FakeSpeechDetector(_activity(offsets, VANS_SPEECH)), FakeLanguageDetector(["pt"])
    use, _, _ = _auto(repo, speech, language)

    result = use.execute(meeting.id)

    assert len(offsets) == 8
    assert language.calls == [(repo.path(meeting.id, AUDIO), (offsets[3], offsets[4], offsets[5]), 30.0)]
    detection = result.language_detection
    assert detection is not None and [sample.at for sample in detection.samples] == [offsets[3], offsets[4], offsets[5]]
    assert detection.reason is LanguageReason.MAJORITY and (detection.counted, detection.votes) == (3, 3)
    (dropped,) = _records(caplog, Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH, logging.INFO)
    assert dropped.getMessage() == Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH % (meeting.id, 5, 8) and "5 of 8" in dropped.getMessage()
    assert speech.calls == [repo.path(meeting.id, AUDIO)]   # the activity of the check is the one the language detection uses: VAD ran once
    assert repo.load_transcript(meeting.id) is result


def test_ut044_a_window_with_less_than_three_seconds_of_speech_is_not_sent(repo, meeting):
    offsets = _sampled(repo, meeting)
    language = FakeLanguageDetector(["pt"])
    use, _, _ = _auto(repo, FakeSpeechDetector(_activity(offsets, [0.0, 2.9, 0.0, 3.0, 14.0, 5.0, 0.0, 2.5])), language)

    use.execute(meeting.id)

    assert language.calls[0][1] == (offsets[3], offsets[4], offsets[5])


def test_ut044_speech_in_every_window_drops_nothing_and_logs_nothing(repo, meeting, caplog):
    caplog.set_level(logging.INFO)
    offsets = _sampled(repo, meeting)
    language = FakeLanguageDetector(["pt"])
    use, _, _ = _auto(repo, FakeSpeechDetector(_activity(offsets, [5.0] * 8)), language)

    result = use.execute(meeting.id)

    assert language.calls[0][1] == tuple(offsets) and result.language_detection is not None and len(result.language_detection.samples) == 8
    assert not _records(caplog, Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH, logging.INFO)


def test_ut044_with_no_activity_every_planned_sample_is_sent_as_before(repo, meeting, caplog):
    """The check is off (no detector) or failed: the samples are planned and sent exactly as they were before the check existed."""
    caplog.set_level(logging.INFO)
    offsets = _sampled(repo, meeting)
    for speech in (None, FakeSpeechDetector(error=RuntimeError("boom"))):
        language = FakeLanguageDetector(["en"])
        use, _, _ = _auto(repo, speech, language)

        result = use.execute(meeting.id)

        assert language.calls == [(repo.path(meeting.id, AUDIO), tuple(offsets), 30.0)]
        assert result.language_detection is not None and len(result.language_detection.samples) == 8 and result.speech is None
    assert not _records(caplog, Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH, logging.INFO)


def test_ut045_a_meeting_without_a_length_is_planned_and_measured_over_the_audio_the_check_measured(repo, meeting):
    assert meeting.duration_seconds is None
    repo.seed(meeting, {AUDIO})
    language = FakeLanguageDetector(["pt"])
    use, transcriber, _ = _auto(repo, FakeSpeechDetector(SpeechActivity(1800.0, ((0.0, 1800.0),))), language, FakeTranscriber(speech_transcript(minutes=20)))

    result = use.execute(meeting.id)

    assert language.calls[0][1] == tuple(sample_offsets(1800.0)) and len(language.calls[0][1]) == 6
    assert result.health is not None and (result.health.total_minutes, result.health.covered_minutes) == (30, 20)
    assert result.health.uncovered == ((20, 30),) and transcriber.calls == [(repo.path(meeting.id, AUDIO), "pt")]


def test_ut045_without_the_check_a_meeting_without_a_length_keeps_its_single_sample_and_its_health(repo, meeting):
    """The baseline the stand-in changes: one sample at 0 and the length of the text."""
    repo.seed(meeting, {AUDIO})
    language = FakeLanguageDetector(["pt"])
    use, _, _ = _auto(repo, None, language, FakeTranscriber(speech_transcript(minutes=20)))

    result = use.execute(meeting.id)

    assert language.calls[0][1] == (0.0,)
    assert result.health is not None and result.health.total_minutes == 20


def test_ut045_the_recorded_length_wins_over_the_one_the_check_measured(repo, meeting):
    offsets = _sampled(repo, meeting, seconds=600.0)
    language = FakeLanguageDetector(["pt"])
    use, _, _ = _auto(repo, FakeSpeechDetector(SpeechActivity(1800.0, ((0.0, 1800.0),))), language, FakeTranscriber(speech_transcript(minutes=10)))

    result = use.execute(meeting.id)

    assert language.calls[0][1] == tuple(offsets) == tuple(sample_offsets(600.0))
    assert result.health is not None and result.health.total_minutes == 10


def test_ut045_the_stand_in_reaches_the_fixed_language_health_too(repo, meeting):
    repo.seed(meeting, {AUDIO})
    use = TranscribeMeeting(repo, FakeTranscriber(speech_transcript(minutes=20)), "pt", speech_detector=FakeSpeechDetector(SpeechActivity(1800.0, ((0.0, 1800.0),))))

    result = use.execute(meeting.id)

    assert result.health is not None and result.health.total_minutes == 30 and result.language_detection is None


def test_ut046_speech_that_fills_no_window_leaves_no_usable_sample_and_the_detector_is_not_called(repo, meeting, caplog):
    caplog.set_level(logging.INFO)
    offsets = _sampled(repo, meeting)
    segments = ((offsets[1] + 5.0, offsets[1] + 6.25), (offsets[6] + 5.0, offsets[6] + 6.25))   # 2.5 s: speech, but 1.25 s in two windows
    speech, language = FakeSpeechDetector(SpeechActivity(VANS_SECONDS, segments)), FakeLanguageDetector(["en"])
    use, transcriber, retry = _auto(repo, speech, language)

    result = use.execute(meeting.id)

    assert result.speech == SpeechCheck(True, 2.5, VANS_SECONDS, 2) and result.segments
    assert language.calls == []
    detection = result.language_detection
    assert detection is not None and detection.reason is LanguageReason.NO_USABLE_SAMPLE and detection.language == "pt"
    assert (detection.counted, detection.votes, detection.samples) == (0, 0, ())
    assert result.language == "pt" and transcriber.calls == retry.calls == [(repo.path(meeting.id, AUDIO), "pt")]
    (dropped,) = _records(caplog, Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH, logging.INFO)
    assert dropped.getMessage() == Log.LANGUAGE_SAMPLES_WITHOUT_SPEECH % (meeting.id, 8, 8)
    assert not _records(caplog, Log.LANGUAGE_DETECTION_FAILED, logging.WARNING)


def test_ut055_one_window_with_speech_of_eight_planned_cannot_decide_the_language(repo, meeting, caplog):
    caplog.set_level(logging.INFO)
    offsets = _sampled(repo, meeting)
    language = FakeLanguageDetector(["en"])   # 0.99
    use, transcriber, retry = _auto(repo, FakeSpeechDetector(_activity(offsets, [0.0, 0.0, 0.0, 12.0, 0.0, 0.0, 0.0, 0.0])), language)

    result = use.execute(meeting.id)

    assert language.calls[0][1] == (offsets[3],)
    detection = result.language_detection
    assert detection is not None and detection.reason is LanguageReason.TOO_FEW_VOTES and detection.language == "pt" and not detection.detected
    assert (detection.counted, detection.votes) == (1, 0)
    assert [(sample.at, sample.language) for sample in detection.samples] == [(offsets[3], "en")]
    assert result.language == "pt" and transcriber.calls == retry.calls == [(repo.path(meeting.id, AUDIO), "pt")]
    (fallback,) = _records(caplog, Log.LANGUAGE_FALLBACK, logging.INFO)
    assert fallback.getMessage() == Log.LANGUAGE_FALLBACK % (meeting.id, "pt", "too-few-votes", 1, 1)


def test_ut055_a_meeting_planned_with_one_sample_is_still_decided_by_it(repo, meeting):
    offsets = _sampled(repo, meeting, seconds=20.0)
    language = FakeLanguageDetector(["en"])
    use, transcriber, _ = _auto(repo, FakeSpeechDetector(_activity(offsets, [12.0], audio_seconds=20.0)), language, FakeTranscriber(speech_transcript(minutes=1)))

    result = use.execute(meeting.id)

    assert offsets == [0.0] and language.calls[0][1] == (0.0,)
    assert result.language_detection is not None and result.language_detection.reason is LanguageReason.MAJORITY
    assert result.language == "en" and transcriber.calls == [(repo.path(meeting.id, AUDIO), "en")]


def test_ut056_in_auto_mode_the_filter_changes_the_language_and_nothing_else_in_the_whisper_commands(repo, meeting, caplog):
    caplog.set_level(logging.INFO)
    offsets = _sampled(repo, meeting)
    activity = _activity(offsets, VANS_SPEECH)
    runs = {}
    for name, speech, script in (("off", None, ["en", "en", "en", "pt", "pt", "pt", "en", "en"]), ("on", FakeSpeechDetector(activity), ["pt", "pt", "pt"])):
        use, first, retry = _auto(repo, speech, FakeLanguageDetector(script))
        result = use.execute(meeting.id)
        runs[name] = (result, first.calls, retry.calls)

    (off, off_first, off_retry), (on, on_first, on_retry) = runs["off"], runs["on"]
    assert off.language == "en" and off.language_detection is not None and (off.language_detection.votes, off.language_detection.counted) == (5, 8)
    assert on.language == "pt" and on.language_detection is not None and (on.language_detection.votes, on.language_detection.counted) == (3, 3)
    audio = repo.path(meeting.id, AUDIO)
    assert off_first == off_retry == [(audio, "en")] and on_first == on_retry == [(audio, "pt")]
    assert on.health == off.health and on.health is not None and on.health.retried   # the retry ran in both, and measured the same
    assert off_first != on_first and [(audio, "") for audio, _ in off_first] == [(audio, "") for audio, _ in on_first]   # only the language differs
    assert on.speech == SpeechCheck(True, 28.0, VANS_SECONDS, 3) and off.speech is None


def test_ut056_when_the_filter_drops_nothing_the_commands_and_the_record_are_the_check_off_ones(repo, meeting):
    offsets = _sampled(repo, meeting)
    runs = []
    for speech in (None, FakeSpeechDetector(_activity(offsets, [5.0] * 8))):
        language = FakeLanguageDetector(["en", "en", "pt", "en", "en", "pt", "en", "en"])
        use, first, retry = _auto(repo, speech, language)
        result = use.execute(meeting.id)
        runs.append((result, first.calls, retry.calls, language.calls))

    (off, *off_calls), (on, *on_calls) = runs
    assert off_calls == on_calls
    assert on.language_detection == off.language_detection and on.health == off.health and on.language == off.language == "en"
    assert on.speech is not None and off.speech is None
