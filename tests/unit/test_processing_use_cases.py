import pytest

from teams_recorder.application.use_cases import AnalyzeMeeting, TranscribeMeeting
from teams_recorder.domain import MeetingStatus, RepositoryError, TranscriptionError, derive_status
from teams_recorder.domain.status import AUDIO, LOCK
from tests.fakes import FakeAnalyzer, FakeTranscriber


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
    assert repo.load_analysis(meeting.id).summary == f"Resumo de {meeting.id}"
