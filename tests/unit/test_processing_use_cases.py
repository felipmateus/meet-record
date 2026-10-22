import logging
from datetime import timedelta
from pathlib import Path

import pytest

from teams_recorder.application.use_cases import AnalyzeMeeting, RenderMinutes, TranscribeMeeting, gaps_text
from teams_recorder.domain import (
    CaptureStats, LanguageReason, MeetingStatus, RepositoryError, Segment, Transcript, TranscriptHealth, TranscriptionError, derive_status, sample_offsets,
)
from teams_recorder.domain.status import AUDIO, ERROR, LOCK, TRANSCRIPT_JSON
from teams_recorder.messages import Log, Notify
from tests.fakes import (
    FakeAnalyzer, FakeLanguageDetector, FakeMinutesRenderer, FakeNotifier, FakeTranscriber, looped_transcript, speech_transcript,
)


def test_ut045_transcribe_refuses_auto_as_the_language(repo):
    with pytest.raises(ValueError, match="auto"):
        TranscribeMeeting(repo, FakeTranscriber(), language="auto")


def test_transcribe_requires_audio(repo, meeting):
    repo.seed(meeting)
    with pytest.raises(TranscriptionError):
        TranscribeMeeting(repo, FakeTranscriber()).execute(meeting.id)


def test_transcribe_saves_and_releases_lock(repo, meeting):
    repo.seed(meeting, {AUDIO})
    transcriber = FakeTranscriber()

    result = TranscribeMeeting(repo, transcriber, language="pt").execute(meeting.id)

    assert transcriber.calls[0][0].name == AUDIO and transcriber.calls[0][1] == "pt"
    assert repo.load_transcript(meeting.id) is result
    assert derive_status(repo.files(meeting.id)) == MeetingStatus.TRANSCRIBED
    assert LOCK not in repo.files(meeting.id)


def test_transcribe_releases_lock_on_failure(repo, meeting):
    repo.seed(meeting, {AUDIO})
    with pytest.raises(RuntimeError):
        TranscribeMeeting(repo, FakeTranscriber(fail=True)).execute(meeting.id)
    assert LOCK not in repo.files(meeting.id)


def test_transcribe_refuses_when_locked(repo, meeting):
    repo.seed(meeting, {AUDIO, LOCK})
    with pytest.raises(RepositoryError):
        TranscribeMeeting(repo, FakeTranscriber()).execute(meeting.id)


def test_analyze_sets_meeting_id_and_saves(repo, meeting):
    repo.seed(meeting, {AUDIO}, transcript=FakeTranscriber().transcript)
    analyzer = FakeAnalyzer()

    analysis = AnalyzeMeeting(repo, analyzer).execute(meeting.id)

    assert analysis.meeting_id == meeting.id
    assert analyzer.calls[0][1] is meeting
    assert repo.load_analysis(meeting.id).summary == f"Summary of {meeting.id}"


def test_analyze_writes_minutes_and_names_untitled_meeting(repo, meeting):
    from teams_recorder.domain import Meeting
    from datetime import datetime
    m = Meeting.start(datetime(2026, 10, 6, 15, 0, 0))  # automatic recording: no title
    repo.seed(m, {AUDIO}, transcript=FakeTranscriber().transcript)

    class TitledAnalyzer(FakeAnalyzer):
        def analyze(self, transcript, meeting):
            a = super().analyze(transcript, meeting)
            a.title = "Revisão da sprint"
            return a

    renderer = FakeMinutesRenderer()
    AnalyzeMeeting(repo, TitledAnalyzer(), renderer).execute(m.id)

    assert repo.load_meta(m.id).title == "Revisão da sprint"
    assert renderer.calls[0][0].id == m.id and repo.minutes[m.id].startswith(f"# Minutes {m.id}")


def test_analyze_keeps_manual_title(repo, meeting):
    repo.seed(meeting, {AUDIO}, transcript=FakeTranscriber().transcript)  # title "Planejamento Sprint"

    class TitledAnalyzer(FakeAnalyzer):
        def analyze(self, transcript, m):
            a = super().analyze(transcript, m)
            a.title = "Outro título"
            return a

    AnalyzeMeeting(repo, TitledAnalyzer()).execute(meeting.id)
    assert repo.load_meta(meeting.id).title == "Planejamento Sprint" and meeting.id not in repo.minutes


def test_render_minutes_from_existing_analysis(repo, meeting):
    analysis = FakeAnalyzer().analyze(FakeTranscriber().transcript, meeting)
    repo.seed(meeting, {AUDIO}, transcript=FakeTranscriber().transcript, analysis=analysis)
    md = RenderMinutes(repo, FakeMinutesRenderer()).execute(meeting.id)
    assert repo.minutes[meeting.id] == md


# --- transcript health and the retry of a degraded transcript ----------------------------------

def _transcribe(repo, meeting, first, retry=None, notifier=None, **kwargs):
    repo.seed(meeting, {AUDIO})
    return TranscribeMeeting(repo, first, "pt", retry=retry, notifier=notifier, **kwargs).execute(meeting.id)


def test_healthy_transcript_is_saved_with_its_health_and_never_retried(repo, meeting):
    retry, notifier = FakeTranscriber(speech_transcript()), FakeNotifier()

    result = _transcribe(repo, meeting, FakeTranscriber(speech_transcript(minutes=10)), retry, notifier)

    assert result.health is not None and not result.health.degraded and not result.health.retried
    assert (result.health.covered_minutes, result.health.total_minutes) == (10, 10)
    assert repo.load_transcript(meeting.id).health == result.health
    assert retry.calls == [] and notifier.messages == []


def test_degraded_transcript_is_retried_and_the_healthier_result_kept(repo, meeting):
    first, retry, notifier = FakeTranscriber(looped_transcript()), FakeTranscriber(speech_transcript()), FakeNotifier()

    result = _transcribe(repo, meeting, first, retry, notifier)

    assert retry.calls == first.calls == [(repo.path(meeting.id, AUDIO), "pt")]
    # the saved transcript is the labelled copy of the kept pass, so the passes are told apart by their segments
    assert result.segments == retry.transcript.segments and repo.load_transcript(meeting.id) is result
    assert result.health is not None and not result.health.degraded and result.health.retried
    assert notifier.messages == []   # repaired: nothing to warn about


def test_still_degraded_after_the_retry_keeps_the_healthier_pass_and_notifies(repo, meeting):
    worse = looped_transcript(minutes=20, loop_minutes=18)
    first, retry, notifier = FakeTranscriber(looped_transcript(minutes=20, loop_minutes=15)), FakeTranscriber(worse), FakeNotifier()

    result = _transcribe(repo, meeting, first, retry, notifier)

    assert result.segments == first.transcript.segments and len(retry.calls) == 1
    assert result.health is not None and result.health.degraded and result.health.retried
    title, body = notifier.messages[-1]
    assert title == Notify.TRANSCRIPT_DEGRADED
    assert body == Notify.TRANSCRIPT_DEGRADED_BODY.format(
        meeting_id=meeting.id, loop=result.health.loop_share, gaps=Notify.NO_TEXT_IN.format(ranges="00:00:00–00:15:00"))


def test_without_a_retry_a_degraded_transcript_is_saved_marked_and_notified(repo, meeting):
    notifier = FakeNotifier()

    result = _transcribe(repo, meeting, FakeTranscriber(looped_transcript()), None, notifier)

    assert repo.load_transcript(meeting.id).health == result.health
    assert result.health is not None and result.health.degraded and not result.health.retried
    assert [t for t, _ in notifier.messages] == [Notify.TRANSCRIPT_DEGRADED]


def test_a_failed_retry_keeps_the_first_pass(repo, meeting):
    notifier = FakeNotifier()

    result = _transcribe(repo, meeting, FakeTranscriber(looped_transcript()), FakeTranscriber(fail_cleanly=True), notifier)

    assert result.health is not None and result.health.degraded and not result.health.retried
    assert LOCK not in repo.files(meeting.id) and [t for t, _ in notifier.messages] == [Notify.TRANSCRIPT_DEGRADED]


def test_loop_threshold_comes_from_the_use_case(repo, meeting):
    result = _transcribe(repo, meeting, FakeTranscriber(looped_transcript()), max_loop_share=0.95)
    assert result.health is not None and not result.health.degraded


def test_notification_lists_only_the_first_gaps():
    health = TranscriptHealth(0.5, 10, 30, True, ((0, 2), (4, 6), (8, 10), (12, 14), (20, 30)))
    assert gaps_text(health, limit=3) == Notify.RANGES_MORE.format(shown="00:00:00–00:02:00, 00:04:00–00:06:00, 00:08:00–00:10:00", more=2)
    assert gaps_text(health, limit=5).endswith("00:20:00–00:30:00")


def test_minutes_receive_the_transcript_health(repo, meeting):
    transcript = looped_transcript()
    _transcribe(repo, meeting, FakeTranscriber(transcript))
    renderer = FakeMinutesRenderer()

    AnalyzeMeeting(repo, FakeAnalyzer(), renderer).execute(meeting.id)
    RenderMinutes(repo, renderer).execute(meeting.id)

    assert renderer.healths == [transcript.health, transcript.health] and transcript.health is not None


def test_render_minutes_without_a_transcript_has_no_health(repo, meeting):
    repo.seed(meeting, {AUDIO}, analysis=FakeAnalyzer().analyze(FakeTranscriber().transcript, meeting))
    renderer = FakeMinutesRenderer()
    RenderMinutes(repo, renderer).execute(meeting.id)
    assert renderer.healths == [None]


def test_ut073_both_use_cases_pass_the_transcript_language_to_the_renderer(repo, meeting):
    english = Transcript([Segment(0.0, 2.0, "Hello, everyone.")], "en")
    repo.seed(meeting, {AUDIO, TRANSCRIPT_JSON}, transcript=english)
    renderer = FakeMinutesRenderer()

    AnalyzeMeeting(repo, FakeAnalyzer(), renderer).execute(meeting.id)
    RenderMinutes(repo, renderer).execute(meeting.id)

    assert renderer.languages == ["en", "en"]


def test_ut073_a_transcript_without_a_detection_record_renders_as_portuguese(repo, meeting):
    repo.seed(meeting, {AUDIO, TRANSCRIPT_JSON}, transcript=FakeTranscriber().transcript,
              analysis=FakeAnalyzer().analyze(FakeTranscriber().transcript, meeting))
    renderer = FakeMinutesRenderer()
    RenderMinutes(repo, renderer).execute(meeting.id)
    assert renderer.languages == ["pt"]


def test_ut073_a_meeting_without_a_transcript_renders_with_no_language(repo, meeting):
    repo.seed(meeting, {AUDIO}, analysis=FakeAnalyzer().analyze(FakeTranscriber().transcript, meeting))
    renderer = FakeMinutesRenderer()
    RenderMinutes(repo, renderer).execute(meeting.id)
    assert renderer.languages == [None]


def test_the_fake_transcriber_gives_the_transcript_of_the_audio_it_is_asked_for():
    other = looped_transcript()
    fake = FakeTranscriber(by_audio={Path("/b/audio.m4a"): other})
    assert fake.transcribe(Path("/b/audio.m4a"), "pt") is other
    assert fake.transcribe(Path("/a/audio.m4a"), "pt") is fake.transcript


def test_any_retry_failure_keeps_the_first_pass(repo, meeting):
    # e.g. a KeyError from whisper's JSON or an OSError reading it: not translated, still not worth losing the first pass
    notifier = FakeNotifier()

    result = _transcribe(repo, meeting, FakeTranscriber(looped_transcript()), FakeTranscriber(fail=True), notifier)

    assert repo.load_transcript(meeting.id) is result and result.health is not None and result.health.degraded
    assert LOCK not in repo.files(meeting.id) and [t for t, _ in notifier.messages] == [Notify.TRANSCRIPT_DEGRADED]


def test_an_empty_retry_does_not_replace_a_first_pass_with_text(repo, meeting):
    first = FakeTranscriber(looped_transcript(minutes=20, loop_minutes=15))   # 5 minutes of speech after the loop

    result = _transcribe(repo, meeting, first, FakeTranscriber(Transcript()))

    assert result.segments == first.transcript.segments and result.health is not None and result.health.retried and result.health.covered_minutes == 5


def test_health_is_measured_against_the_meeting_length(repo, clock):
    from datetime import timedelta
    from teams_recorder.domain import Meeting
    m = Meeting.start(clock.now())
    m.ended_at = m.started_at + timedelta(minutes=30, seconds=10)
    repo.seed(m, {AUDIO})

    result = TranscribeMeeting(repo, FakeTranscriber(speech_transcript(minutes=20)), "pt").execute(m.id)

    assert result.health is not None and (result.health.covered_minutes, result.health.total_minutes) == (20, 30)
    assert result.health.uncovered == ((20, 30),)   # the silent end of the meeting is reported, not hidden


# --- Teams track recorded at the wrong sample rate ---------------------------------------------

_BROKEN_TAP = CaptureStats(written_seconds=709.9, padded_seconds=474.9, short_padded_seconds=474.9, gaps=0, device_rates=(48000.0,))
_HEALTHY_TAP = CaptureStats(written_seconds=986.4, padded_seconds=7.4, short_padded_seconds=7.4, gaps=0, device_rates=(16000.0,))


def test_a_track_recorded_at_the_wrong_rate_flags_the_transcript_and_notifies(repo, meeting):
    notifier = FakeNotifier()
    repo.seed(meeting, {AUDIO}, capture_stats=_BROKEN_TAP)

    result = TranscribeMeeting(repo, FakeTranscriber(speech_transcript(minutes=12)), "pt", notifier=notifier).execute(meeting.id)

    assert result.health is not None and result.health.rate_mismatch
    assert result.health.short_padding_share == pytest.approx(0.669, abs=0.001)
    assert not result.health.degraded                      # the loop check is a separate verdict
    assert repo.load_transcript(meeting.id).health == result.health
    assert [title for title, _ in notifier.messages] == [Notify.RATE_MISMATCH]
    assert "67%" in notifier.messages[0][1] and meeting.id in notifier.messages[0][1]


def test_a_healthy_track_or_no_counters_leave_the_transcript_unflagged(repo, meeting):
    for stats in (_HEALTHY_TAP, None):
        notifier = FakeNotifier()
        repo.seed(meeting, {AUDIO}, capture_stats=stats)
        result = TranscribeMeeting(repo, FakeTranscriber(speech_transcript()), "pt", notifier=notifier).execute(meeting.id)
        assert result.health is not None and not result.health.rate_mismatch and result.health.short_padding_share == 0.0
        assert notifier.messages == []


@pytest.mark.parametrize("error", [RepositoryError("bad json"), PermissionError(1, "Operation not permitted")])
def test_unreadable_counters_skip_the_rate_check_and_keep_the_transcript(repo, meeting, error):
    class BrokenStatsRepo(type(repo)):
        def load_capture_stats(self, meeting_id):
            raise error

    broken = BrokenStatsRepo()
    broken.seed(meeting, {AUDIO})
    result = TranscribeMeeting(broken, FakeTranscriber(speech_transcript()), "pt").execute(meeting.id)
    assert result.health is not None and not result.health.rate_mismatch
    assert broken.load_transcript(meeting.id) is result      # the finished transcription is saved, not lost


def test_rate_check_thresholds_come_from_the_use_case(repo, meeting):
    repo.seed(meeting, {AUDIO}, capture_stats=_HEALTHY_TAP)   # 0.75% short padding
    result = TranscribeMeeting(repo, FakeTranscriber(speech_transcript()), "pt", max_short_pad_share=0.005).execute(meeting.id)
    assert result.health is not None and result.health.rate_mismatch


def test_a_track_at_the_wrong_rate_gets_no_retry(repo, meeting, caplog):
    # VAD cannot repair audio recorded at the wrong rate; on 2026-10-14 the useless retry took 4 minutes
    caplog.set_level(logging.INFO)
    repo.seed(meeting, {AUDIO}, capture_stats=_BROKEN_TAP)
    retry, notifier = FakeTranscriber(speech_transcript()), FakeNotifier()

    result = TranscribeMeeting(repo, FakeTranscriber(looped_transcript()), "pt", retry=retry, notifier=notifier).execute(meeting.id)

    assert retry.calls == [] and result.health is not None
    assert result.health.degraded and result.health.rate_mismatch and not result.health.retried
    assert {t for t, _ in notifier.messages} == {Notify.TRANSCRIPT_DEGRADED, Notify.RATE_MISMATCH}
    assert Log.TRANSCRIPT_RETRY_SKIPPED % meeting.id in caplog.text


def test_a_healthy_track_still_gets_the_retry(repo, meeting):
    repo.seed(meeting, {AUDIO}, capture_stats=_HEALTHY_TAP)
    retry = FakeTranscriber(speech_transcript())
    result = TranscribeMeeting(repo, FakeTranscriber(looped_transcript()), "pt", retry=retry).execute(meeting.id)
    assert len(retry.calls) == 1 and result.health is not None and result.health.retried and not result.health.rate_mismatch



def test_a_loop_free_retry_that_keeps_most_of_the_text_replaces_the_first_pass(repo, meeting):
    # the 85% rule through the use case: the retry has no loops but less text than the first pass "covers"
    first = looped_transcript(minutes=20, loop_minutes=2)   # 2 minutes looped, text in 18 of 20 minutes, degraded
    retry = speech_transcript(minutes=16)                   # no loops, text in 16 minutes: 16 >= 85% of 18
    result = _transcribe(repo, meeting, FakeTranscriber(first), FakeTranscriber(retry))
    assert result.segments == retry.segments and result.health is not None and not result.health.degraded and result.health.retried


def test_unreadable_capture_counters_still_allow_the_retry(repo, meeting):
    class BrokenStats(type(repo)):
        def load_capture_stats(self, meeting_id):
            raise RepositoryError("tap.stats.json unreadable")
    broken = BrokenStats()
    broken.seed(meeting, {AUDIO})
    retry = FakeTranscriber(speech_transcript())
    result = TranscribeMeeting(broken, FakeTranscriber(looped_transcript()), "pt", retry=retry).execute(meeting.id)
    assert len(retry.calls) == 1 and result.health is not None and not result.health.rate_mismatch


# --- the language of the meeting (docs/tasks/language-detection) ---------------------------------

def _detecting(repo, meeting, detector, transcriber=None, **kwargs):
    """`TranscribeMeeting` in detection mode, as the container builds it: `language` is the fallback, `languages` the allow-list."""
    repo.seed(meeting, {AUDIO})
    transcriber = transcriber or FakeTranscriber(speech_transcript(minutes=10))
    use = TranscribeMeeting(repo, transcriber, "pt", language_detector=detector, **kwargs)
    return use, transcriber


def test_ut030_the_detected_language_reaches_the_transcriber_and_the_saved_transcript(repo, meeting, caplog):
    caplog.set_level(logging.INFO)
    meeting.ended_at = meeting.started_at + timedelta(minutes=10)   # 3 samples
    detector = FakeLanguageDetector(["en"])
    use, transcriber = _detecting(repo, meeting, detector)

    result = use.execute(meeting.id)

    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), "en")]
    saved = repo.load_transcript(meeting.id)
    assert saved is result and saved.language == "en"
    assert saved.language_detection is not None and saved.language_detection.language == "en"
    assert saved.language_detection.reason is LanguageReason.MAJORITY and saved.language_detection.votes == saved.language_detection.counted == 3
    assert len(saved.language_detection.samples) == 3
    assert Log.LANGUAGE_DETECTED % (meeting.id, "en", 3, 3, 3) in caplog.text


def test_ut031_the_detector_gets_the_offsets_of_the_meeting_and_a_30_second_window(repo, meeting):
    meeting.ended_at = meeting.started_at + timedelta(minutes=37)
    detector = FakeLanguageDetector(["pt"])
    use, _ = _detecting(repo, meeting, detector)

    use.execute(meeting.id)

    assert detector.calls == [(repo.path(meeting.id, AUDIO), tuple(sample_offsets(37 * 60.0)), 30.0)]
    assert len(detector.calls[0][1]) == 8


def test_ut032_the_first_pass_and_the_retry_use_the_same_language(repo, meeting):
    first, retry = FakeTranscriber(looped_transcript()), FakeTranscriber(speech_transcript())
    use, _ = _detecting(repo, meeting, FakeLanguageDetector(["en"]), first, retry=retry)

    result = use.execute(meeting.id)

    assert first.calls == retry.calls == [(repo.path(meeting.id, AUDIO), "en")]
    assert result.language == "en" and result.health is not None and result.health.retried
    assert result.language_detection is not None and result.language_detection.language == "en"


@pytest.mark.parametrize("error", [TranscriptionError("whisper-cli timed out"), RuntimeError("a bug in the detector")], ids=["ut033", "ut034"])
def test_ut033_ut034_a_detector_that_raises_falls_back_without_an_error_or_a_notification(repo, meeting, caplog, error):
    caplog.set_level(logging.INFO)
    notifier = FakeNotifier()
    use, transcriber = _detecting(repo, meeting, FakeLanguageDetector(["en"], error=error), notifier=notifier)

    result = use.execute(meeting.id)

    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), "pt")]
    assert result.language == "pt" and result.language_detection is not None
    assert result.language_detection.reason is LanguageReason.DETECTION_FAILED and result.language_detection.samples == ()
    assert (result.language_detection.language, result.language_detection.counted, result.language_detection.votes) == ("pt", 0, 0)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and r.msg == Log.LANGUAGE_DETECTION_FAILED]
    assert len(warnings) == 1 and warnings[0].getMessage() == Log.LANGUAGE_DETECTION_FAILED % (meeting.id, "pt", error)
    assert notifier.messages == [] and ERROR not in repo.files(meeting.id) and LOCK not in repo.files(meeting.id)
    assert repo.load_transcript(meeting.id) is result


def test_ut035_a_meeting_of_unknown_length_is_sampled_once_at_its_start(repo, meeting):
    assert meeting.duration_seconds is None
    detector = FakeLanguageDetector(["pt"])
    use, _ = _detecting(repo, meeting, detector)

    result = use.execute(meeting.id)

    assert detector.calls[0][1] == (0.0,)
    assert result.language_detection is not None and result.language_detection.reason is LanguageReason.MAJORITY   # one sample: one vote is enough


def test_ut036_a_rate_mismatch_does_not_stop_the_detection(repo, meeting):
    repo.seed(meeting, {AUDIO}, capture_stats=_BROKEN_TAP)
    detector, transcriber = FakeLanguageDetector(["en"]), FakeTranscriber(speech_transcript(minutes=12))

    result = TranscribeMeeting(repo, transcriber, "pt", language_detector=detector).execute(meeting.id)

    assert len(detector.calls) == 1 and transcriber.calls == [(repo.path(meeting.id, AUDIO), "en")]
    assert result.health is not None and result.health.rate_mismatch
    assert result.language_detection is not None and result.language_detection.language == "en"


def test_ut037_a_transcription_failure_after_detection_saves_nothing(repo, meeting):
    use, _ = _detecting(repo, meeting, FakeLanguageDetector(["en"]), FakeTranscriber(fail_cleanly=True))

    with pytest.raises(TranscriptionError):
        use.execute(meeting.id)

    assert TRANSCRIPT_JSON not in repo.files(meeting.id) and LOCK not in repo.files(meeting.id)


def test_ut038_a_portuguese_meeting_is_transcribed_in_portuguese_and_the_record_is_saved(repo, meeting):
    use, transcriber = _detecting(repo, meeting, FakeLanguageDetector(["pt"]))

    result = use.execute(meeting.id)

    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), "pt")] and result.language == "pt"
    assert result.language_detection is not None and result.language_detection.reason is LanguageReason.MAJORITY
    assert repo.load_transcript(meeting.id).language_detection == result.language_detection


def test_ut039_a_fixed_language_detects_nothing_and_keeps_no_record(repo, meeting):
    repo.seed(meeting, {AUDIO})
    transcriber = FakeTranscriber(speech_transcript(minutes=10))

    result = TranscribeMeeting(repo, transcriber, "en").execute(meeting.id)

    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), "en")]
    assert result.language == "en" and result.language_detection is None


@pytest.mark.parametrize("answers, languages, fallback, reason", [
    (["is"], ("pt", "en"), "pt", LanguageReason.NO_USABLE_SAMPLE),           # not an allowed language
    (["en", "en", "pt", "pt"], ("pt", "en"), "pt", LanguageReason.NO_MAJORITY),
    (["en", None, None], ("pt", "en"), "pt", LanguageReason.TOO_FEW_VOTES),
    (["is"], ("en", "pt"), "en", LanguageReason.NO_USABLE_SAMPLE),           # the fallback is the use case's `language`
])
def test_an_undecided_meeting_is_transcribed_in_the_fallback_with_the_reason_logged(repo, meeting, caplog, answers, languages, fallback, reason):
    caplog.set_level(logging.INFO)
    meeting.ended_at = meeting.started_at + timedelta(minutes=20)   # 4 samples
    repo.seed(meeting, {AUDIO})
    transcriber = FakeTranscriber(speech_transcript(minutes=10))
    use = TranscribeMeeting(repo, transcriber, fallback, language_detector=FakeLanguageDetector(answers), languages=languages)

    result = use.execute(meeting.id)

    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), fallback)]
    detection = result.language_detection
    assert detection is not None and (detection.language, detection.reason, detection.votes) == (fallback, reason, 0)
    assert Log.LANGUAGE_FALLBACK % (meeting.id, fallback, reason.value, detection.counted, 4) in caplog.text


def test_a_detection_that_picks_the_second_allowed_language_is_the_winner_even_when_the_fallback_is_first(repo, meeting):
    meeting.ended_at = meeting.started_at + timedelta(minutes=10)
    repo.seed(meeting, {AUDIO})
    transcriber = FakeTranscriber(speech_transcript(minutes=10))
    use = TranscribeMeeting(repo, transcriber, "en", language_detector=FakeLanguageDetector(["pt"]), languages=("en", "pt"))

    result = use.execute(meeting.id)

    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), "pt")] and result.language == "pt"
