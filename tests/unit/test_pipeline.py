from teams_recorder.application.pipeline import Pipeline
from teams_recorder.application.use_cases import AnalyzeMeeting, StartRecording, StopRecording, TranscribeMeeting
from teams_recorder.domain import Meeting, MeetingStatus, derive_status
from teams_recorder.domain.status import AUDIO, ERROR, TRANSCRIPT_JSON
from tests.fakes import FakeAnalyzer, FakeMicCapture, FakeMixer, FakeProcessCapture, FakeTranscriber


def _pipeline(repo, notifier, clock, *, transcriber=None, analyzer=None):
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
