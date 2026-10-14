import pytest

from teams_recorder.application.use_cases import AnalyzeMeeting, RenderMinutes, TranscribeMeeting, gaps_text
from teams_recorder.domain import CaptureStats, MeetingStatus, RepositoryError, Transcript, TranscriptHealth, TranscriptionError, derive_status
from teams_recorder.domain.status import AUDIO, LOCK
from teams_recorder.messages import Notify
from tests.fakes import FakeAnalyzer, FakeMinutesRenderer, FakeNotifier, FakeTranscriber, looped_transcript, speech_transcript


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
    assert result is retry.transcript and repo.load_transcript(meeting.id) is result
    assert result.health is not None and not result.health.degraded and result.health.retried
    assert notifier.messages == []   # repaired: nothing to warn about


def test_still_degraded_after_the_retry_keeps_the_healthier_pass_and_notifies(repo, meeting):
    worse = looped_transcript(minutes=20, loop_minutes=18)
    first, retry, notifier = FakeTranscriber(looped_transcript(minutes=20, loop_minutes=15)), FakeTranscriber(worse), FakeNotifier()

    result = _transcribe(repo, meeting, first, retry, notifier)

    assert result is first.transcript and len(retry.calls) == 1
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


def test_any_retry_failure_keeps_the_first_pass(repo, meeting):
    # e.g. a KeyError from whisper's JSON or an OSError reading it: not translated, still not worth losing the first pass
    notifier = FakeNotifier()

    result = _transcribe(repo, meeting, FakeTranscriber(looped_transcript()), FakeTranscriber(fail=True), notifier)

    assert repo.load_transcript(meeting.id) is result and result.health is not None and result.health.degraded
    assert LOCK not in repo.files(meeting.id) and [t for t, _ in notifier.messages] == [Notify.TRANSCRIPT_DEGRADED]


def test_an_empty_retry_does_not_replace_a_first_pass_with_text(repo, meeting):
    first = FakeTranscriber(looped_transcript(minutes=20, loop_minutes=15))   # 5 minutes of speech after the loop

    result = _transcribe(repo, meeting, first, FakeTranscriber(Transcript()))

    assert result is first.transcript and result.health is not None and result.health.retried and result.health.covered_minutes == 5


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
