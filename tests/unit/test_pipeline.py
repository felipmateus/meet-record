from teams_recorder.application.pipeline import Pipeline
from teams_recorder.application.use_cases import AnalyzeMeeting, StartRecording, StopRecording, TranscribeMeeting
from teams_recorder.domain import Meeting, MeetingStatus, derive_status
from teams_recorder.domain.status import ANALYSIS, AUDIO, ERROR, TRANSCRIPT_JSON
from teams_recorder.messages import Log
from tests.fakes import FakeAnalyzer, FakeMicCapture, FakeMixer, FakeProcessCapture, FakeTranscriber


def _pipeline(repo, notifier, clock, *, transcriber=None, analyzer=None, after_analysis=None):
    proc, mic = FakeProcessCapture(), FakeMicCapture()

    class MixerThatWrites(FakeMixer):
        def mix(self, tracks, out):
            repo.touch(out.parent.name, AUDIO)
            return super().mix(tracks, out)

    stop = StopRecording(repo, proc, mic, MixerThatWrites(), notifier, clock)
    start = StartRecording(repo, proc, mic, notifier, clock, "mic")
    pipeline = Pipeline(
        repo, notifier, stop,
        TranscribeMeeting(repo, transcriber or FakeTranscriber()),
        AnalyzeMeeting(repo, analyzer or FakeAnalyzer()),
        after_analysis,
    )
    return start, pipeline


def test_run_after_call_goes_to_analyzed(repo, notifier, clock):
    start, pipeline = _pipeline(repo, notifier, clock)
    active = start.execute(pid=1)

    meeting = pipeline.run_after_call(active)

    assert derive_status(repo.files(meeting.id)) == MeetingStatus.ANALYZED
    titles = [t for t, _ in notifier.messages]
    assert titles == ["Recording started", "Recording stopped"]


def test_failure_in_transcription_marks_error_and_stops(repo, notifier, clock):
    start, pipeline = _pipeline(repo, notifier, clock, transcriber=FakeTranscriber(fail=True))
    active = start.execute(pid=1)

    pipeline.run_after_call(active)

    files = repo.files(active.meeting.id)
    assert ERROR in files and TRANSCRIPT_JSON not in files
    assert "transcription" in repo.last_error
    assert notifier.messages[-1][0] == "Transcription failed"


def test_failure_in_analysis_keeps_transcript(repo, notifier, clock):
    start, pipeline = _pipeline(repo, notifier, clock, analyzer=FakeAnalyzer(fail=True))
    active = start.execute(pid=1)

    status = pipeline.run_after_call(active) and derive_status(repo.files(active.meeting.id))

    assert status == MeetingStatus.FAILED
    assert TRANSCRIPT_JSON in repo.files(active.meeting.id)
    assert "analysis" in repo.last_error


def test_process_clears_previous_error_and_resumes(repo, notifier, clock):
    _, pipeline = _pipeline(repo, notifier, clock)
    m = Meeting.start(clock.now())
    repo.seed(m, {AUDIO, ERROR})

    status = pipeline.process(m.id)

    assert status == MeetingStatus.ANALYZED
    assert ERROR not in repo.files(m.id)


def test_resume_pending_only_touches_unfinished(repo, notifier, clock):
    _, pipeline = _pipeline(repo, notifier, clock)
    recorded = Meeting.start(clock.now()); repo.seed(recorded, {AUDIO})
    clock.advance(hours=1)
    transcribed = Meeting.start(clock.now()); repo.seed(transcribed, {AUDIO, TRANSCRIPT_JSON}, transcript=FakeTranscriber().transcript)
    clock.advance(hours=1)
    recording = Meeting.start(clock.now()); repo.seed(recording)

    results = pipeline.resume_pending()

    assert results == {recorded.id: MeetingStatus.ANALYZED, transcribed.id: MeetingStatus.ANALYZED}
    assert derive_status(repo.files(recording.id)) == MeetingStatus.RECORDING


# --- recordings stopped but never mixed ---------------------------------------------------
def _stopped_not_mixed(repo, start, clock):
    from teams_recorder.domain.status import MIC_TRACK, TAP_TRACK

    active = start.execute(pid=1)
    for track in (TAP_TRACK, MIC_TRACK):
        repo.touch(active.meeting.id, track)
    repo.clear_active()                     # what stop_capture leaves behind if mixing never ran
    return active.meeting.id


def test_resume_pending_mixes_stopped_recordings(repo, notifier, clock):
    start, pipeline = _pipeline(repo, notifier, clock)
    meeting_id = _stopped_not_mixed(repo, start, clock)
    assert pipeline.resume_pending() == {meeting_id: MeetingStatus.ANALYZED}


def test_resume_pending_skips_the_recording_in_progress(repo, notifier, clock):
    from teams_recorder.domain.status import TAP_TRACK

    start, pipeline = _pipeline(repo, notifier, clock)
    active = start.execute(pid=1)
    repo.touch(active.meeting.id, TAP_TRACK)
    assert pipeline.resume_pending() == {}


def test_mixing_failure_keeps_tracks_marks_error_and_is_retried(repo, notifier, clock):
    from teams_recorder.domain import CaptureError
    from teams_recorder.domain.status import MIC_TRACK, TAP_TRACK

    start, pipeline = _pipeline(repo, notifier, clock)
    meeting_id = _stopped_not_mixed(repo, start, clock)
    real_mix = pipeline.stop.mixer.mix

    def failing(tracks, out):
        raise CaptureError("ffmpeg failed to mix: timed out")

    pipeline.stop.mixer.mix = failing
    pipeline.resume_pending()
    files = repo.files(meeting_id)
    assert ERROR in files and TAP_TRACK in files and MIC_TRACK in files and AUDIO not in files
    assert ("Mixing failed", f"Meeting {meeting_id}: ffmpeg failed to mix: timed out") in notifier.messages

    pipeline.stop.mixer.mix = real_mix          # next daemon start: retried from the raw tracks
    assert pipeline.resume_pending() == {meeting_id: MeetingStatus.ANALYZED}


# --- the after-analysis hook (the daemon's curator worker) ----------------------------------
def test_after_analysis_is_called_once_with_each_meeting_that_reaches_analyzed(repo, notifier, clock):
    seen: list[str] = []
    start, pipeline = _pipeline(repo, notifier, clock, after_analysis=seen.append)
    active = start.execute(pid=1)

    pipeline.run_after_call(active)

    assert seen == [active.meeting.id] and derive_status(repo.files(active.meeting.id)) == MeetingStatus.ANALYZED


def test_resume_pending_calls_the_hook_for_the_meetings_it_analyzes_and_not_for_the_analyzed_ones(repo, notifier, clock):
    seen: list[str] = []
    _, pipeline = _pipeline(repo, notifier, clock, after_analysis=seen.append)
    done = Meeting.start(clock.now()); repo.seed(done, {AUDIO, TRANSCRIPT_JSON, ANALYSIS}, transcript=FakeTranscriber().transcript)
    clock.advance(hours=1)
    transcribed = Meeting.start(clock.now()); repo.seed(transcribed, {AUDIO, TRANSCRIPT_JSON}, transcript=FakeTranscriber().transcript)

    pipeline.resume_pending()
    pipeline.process(done.id)   # already analyzed: nothing ran, so nothing to announce

    assert seen == [transcribed.id]


def test_a_failed_step_does_not_call_the_hook(repo, notifier, clock):
    seen: list[str] = []
    start, pipeline = _pipeline(repo, notifier, clock, analyzer=FakeAnalyzer(fail=True), after_analysis=seen.append)
    pipeline.run_after_call(start.execute(pid=1))
    start, pipeline = _pipeline(repo, notifier, clock, transcriber=FakeTranscriber(fail=True), after_analysis=seen.append)
    clock.advance(hours=1)
    pipeline.run_after_call(start.execute(pid=1))

    assert seen == []


def test_a_failing_hook_is_logged_and_never_written_to_error_txt(repo, notifier, clock, caplog):
    def broken(meeting_id: str) -> None:
        raise RuntimeError("queue is gone")

    start, pipeline = _pipeline(repo, notifier, clock, after_analysis=broken)
    active = start.execute(pid=1)

    with caplog.at_level("ERROR"):
        pipeline.run_after_call(active)

    files = repo.files(active.meeting.id)
    assert derive_status(files) == MeetingStatus.ANALYZED and ERROR not in files and not hasattr(repo, "last_error")   # mark_failed never ran
    assert Log.AFTER_ANALYSIS_FAILED % active.meeting.id in caplog.text and "queue is gone" in caplog.text
    assert [t for t, _ in notifier.messages] == ["Recording started", "Recording stopped"]
