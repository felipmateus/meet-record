import pytest

from teams_recorder.application.use_cases import AnalyzeMeeting, RenderMinutes, TranscribeMeeting
from teams_recorder.domain import MeetingStatus, RepositoryError, TranscriptionError, derive_status
from teams_recorder.domain.status import AUDIO, LOCK
from tests.fakes import FakeAnalyzer, FakeMinutesRenderer, FakeTranscriber


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
