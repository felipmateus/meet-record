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
