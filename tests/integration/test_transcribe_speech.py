"""`TranscribeMeeting` wired to the speech adapter (the scripted VAD stand-in and real ffmpeg) and the file repository:
docs/tasks/speech-check/_tests.md IT-003 and IT-004. The adapter alone is in test_speech_whispercpp.py."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.application.use_cases import TranscribeMeeting
from teams_recorder.domain import Meeting
from teams_recorder.domain.status import AUDIO, TRANSCRIPT_JSON, TRANSCRIPT_TXT
from tests.fakes import FakeTranscriber, speech_transcript
from tests.integration.test_speech_whispercpp import ScriptedSpeechDetector, _tone, needs_ffmpeg


@pytest.fixture
def model(tmp_path: Path) -> Path:
    """A stand-in for the VAD model file: the adapter only checks that it exists, and the scripted tool never reads it."""
    path = tmp_path / "ggml-fake.bin"
    path.write_bytes(b"\x00" * 16)
    return path


@pytest.fixture
def recorded(tmp_path: Path) -> tuple[FsMeetingRepository, Meeting, Path]:
    """A meeting folder under a temporary data dir, with a 27.3 s `audio.m4a` that ffmpeg can read."""
    repo = FsMeetingRepository(tmp_path / "data")
    meeting = Meeting.start(datetime(2026, 10, 23, 14, 0, 5))
    repo.create(meeting)
    _tone(repo.path(meeting.id, AUDIO), 27.3)
    return repo, meeting, repo.path(meeting.id, AUDIO).parent


@needs_ffmpeg
def test_it003_no_speech_saves_the_empty_transcript_with_the_record_and_whisper_never_runs(recorded, model: Path):
    repo, meeting, folder = recorded
    transcriber, retry = FakeTranscriber(speech_transcript()), FakeTranscriber(speech_transcript())
    use = TranscribeMeeting(repo, transcriber, "pt", retry=retry, speech_detector=ScriptedSpeechDetector(model, script=("--none",)))

    result = use.execute(meeting.id)

    assert transcriber.calls == [] and retry.calls == []
    data = json.loads((folder / TRANSCRIPT_JSON).read_text(encoding="utf-8"))
    assert data["speech"]["found"] is False and data["speech"]["speech_seconds"] == 0.0 and data["speech"]["segments"] == 0
    assert data["speech"]["audio_seconds"] == pytest.approx(27.3, abs=0.1)
    assert data["segments"] == [] and data["language"] == "pt" and data["health"] is None
    assert "language_detection" not in data and "speakers" not in data
    assert (folder / TRANSCRIPT_TXT).read_text(encoding="utf-8").strip() == ""   # no lines; the repository writes one newline
    assert repo.load_transcript(meeting.id) == result and result.speech is not None and not result.speech.found


@needs_ffmpeg
def test_it004_speech_runs_the_same_whisper_call_as_without_a_detector_and_the_file_says_found(recorded, model: Path):
    repo, meeting, folder = recorded
    calls = {}
    for name, detector in (("off", None), ("on", ScriptedSpeechDetector(model, script=("--segments", "0:2000")))):
        transcriber = FakeTranscriber(speech_transcript(minutes=1))
        TranscribeMeeting(repo, transcriber, "pt", speech_detector=detector).execute(meeting.id)
        calls[name] = transcriber.calls
        saved = json.loads((folder / TRANSCRIPT_JSON).read_text(encoding="utf-8"))
        assert ("speech" in saved) == (name == "on")

    assert calls["on"] == calls["off"] == [(repo.path(meeting.id, AUDIO), "pt")]
    assert saved["speech"]["found"] is True and saved["speech"]["speech_seconds"] == 20.0 and saved["speech"]["segments"] == 1
    assert saved["speech"]["audio_seconds"] == pytest.approx(27.3, abs=0.1)
    assert saved["segments"]   # whisper's text is kept
