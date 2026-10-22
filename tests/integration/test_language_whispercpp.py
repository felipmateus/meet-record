"""The language adapter with a scripted whisper stand-in and real ffmpeg (IT-001 to IT-003), and with the real whisper
(IT-004, slow): docs/tasks/language-detection/_tests.md."""
import json
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.language_whispercpp import WhisperCppLanguageDetector
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.application.use_cases import TranscribeMeeting
from teams_recorder.config import load_settings
from teams_recorder.domain import LanguageReason, LanguageSample, Meeting, TranscriptionError, choose_language
from teams_recorder.domain.status import AUDIO, ERROR, TRANSCRIPT_JSON
from teams_recorder.messages import Err, Log
from tests.fakes import FakeNotifier, FakeTranscriber, speech_transcript
from tests.integration.test_transcriber_whispercpp import ScriptedLanguageDetector

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
ALLOWED = ("pt", "en")


@pytest.fixture
def model(tmp_path: Path) -> Path:
    m = tmp_path / "ggml-fake.bin"
    m.write_bytes(b"\x00" * 16)
    return m


def _tone(path: Path, seconds: float) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:a", "aac", str(path)], check=True)


def _calls(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _files(call: list[str]) -> list[str]:
    return [call[i + 1] for i, arg in enumerate(call) if arg == "-f"]


@pytest.fixture
def own_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The directory `tempfile` uses, so a test can see whether the adapter left anything in it."""
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


@needs_ffmpeg
def test_it001_three_scripted_answers_are_bound_to_their_offsets_in_one_whisper_call(model: Path, tmp_path: Path, own_tmp: Path):
    audio, log = tmp_path / "audio.m4a", tmp_path / "whisper.log"
    _tone(audio, 600.0)
    detector = ScriptedLanguageDetector(model, script=("--langs", "en:0.993,is:0.965,en:0.997", "--log", str(log)))

    samples = detector.detect(audio, [15.0, 285.0, 555.0], 30.0)

    assert samples == [LanguageSample(15.0, "en", 0.993), LanguageSample(285.0, "is", 0.965), LanguageSample(555.0, "en", 0.997)]
    (call,) = _calls(log)   # a single whisper call...
    assert len(_files(call)) == 3 and "-np" not in call and call[call.index("-l") + 1] == "auto"   # ...over the three clips
    assert list(own_tmp.iterdir()) == []   # Safety Invariant 4: the clips are gone


@needs_ffmpeg
def test_it002_a_failing_whisper_names_the_tool_and_its_exit_code(model: Path, tmp_path: Path, own_tmp: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio, 60.0)

    with pytest.raises(TranscriptionError, match=r"whisper-cli failed \(code 2\).*simulated whisper error"):
        ScriptedLanguageDetector(model, fail=True).detect(audio, [0.0], 30.0)

    assert list(own_tmp.iterdir()) == []   # nor does a failure leave them behind


@needs_ffmpeg
def test_it002_whisper_that_prints_no_answer_for_any_clip_raises_with_the_output_tail(model: Path, tmp_path: Path, own_tmp: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio, 600.0)

    with pytest.raises(TranscriptionError) as raised:
        ScriptedLanguageDetector(model, script=("--langs", "-,-,-")).detect(audio, [15.0, 285.0, 555.0], 30.0)

    assert str(raised.value).startswith(Err.WHISPER_NO_LANGUAGE.format(count=3, tail=""))
    assert "main: processing" in str(raised.value)   # the tail is whisper's own output
    assert list(own_tmp.iterdir()) == []


def _recorded(tmp_path: Path, minutes: int = 10) -> tuple[FsMeetingRepository, Meeting]:
    """A meeting on disk whose audio is a tone as long as the meeting (so the offsets fall inside it)."""
    repo = FsMeetingRepository(tmp_path / "data")
    meeting = Meeting.start(datetime(2026, 10, 8, 10, 30, 52))
    meeting.ended_at = meeting.started_at + timedelta(minutes=minutes)
    repo.create(meeting)
    _tone(repo.path(meeting.id, AUDIO), minutes * 60.0)
    return repo, meeting


@needs_ffmpeg
@pytest.mark.parametrize("failure", [dict(fail=True), dict(script=("--langs", "-,-,-"))], ids=["whisper-fails", "no-answer-line"])
def test_it002_a_detector_that_cannot_answer_falls_back_to_portuguese_through_the_use_case(
        model: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture, failure: dict):
    caplog.set_level(logging.INFO)
    repo, meeting = _recorded(tmp_path)
    transcriber, notifier = FakeTranscriber(speech_transcript(minutes=10)), FakeNotifier()
    use = TranscribeMeeting(repo, transcriber, "pt", notifier=notifier, language_detector=ScriptedLanguageDetector(model, **failure))

    transcript = use.execute(meeting.id)

    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), "pt")] and transcript.language == "pt"
    warning = next(r for r in caplog.records if r.msg == Log.LANGUAGE_DETECTION_FAILED)
    assert warning.levelno == logging.WARNING and warning.args is not None
    assert warning.args[:2] == (meeting.id, "pt") and isinstance(warning.args[2], TranscriptionError)
    assert str(warning.args[2]) in warning.getMessage()
    if "script" in failure:
        assert str(warning.args[2]).startswith(Err.WHISPER_NO_LANGUAGE.format(count=3, tail="")) and "main: processing" in str(warning.args[2])
    else:
        assert "whisper-cli failed (code 2)" in str(warning.args[2])
    stored = json.loads(repo.path(meeting.id, TRANSCRIPT_JSON).read_text(encoding="utf-8"))
    assert stored["language"] == "pt" and stored["language_detection"]["reason"] == "detection-failed" and stored["language_detection"]["samples"] == []
    assert ERROR not in repo.files(meeting.id) and notifier.messages == []


@needs_ffmpeg
def test_it002_the_answers_of_the_scripted_whisper_choose_the_language_through_the_use_case(model: Path, tmp_path: Path):
    repo, meeting = _recorded(tmp_path)
    transcriber = FakeTranscriber(speech_transcript(minutes=10))
    detector = ScriptedLanguageDetector(model, script=("--langs", "en:0.99,is:0.96,en:0.97"))

    transcript = TranscribeMeeting(repo, transcriber, "pt", language_detector=detector).execute(meeting.id)

    assert transcriber.calls == [(repo.path(meeting.id, AUDIO), "en")] and transcript.language == "en"
    stored = json.loads(repo.path(meeting.id, TRANSCRIPT_JSON).read_text(encoding="utf-8"))["language_detection"]
    assert (stored["language"], stored["reason"], stored["counted"], stored["votes"]) == ("en", "majority", 2, 2)
    assert [(x["language"], x["p"]) for x in stored["samples"]] == [("en", 0.99), ("is", 0.96), ("en", 0.97)]


@needs_ffmpeg
def test_it002_some_clips_without_an_answer_are_not_an_error(model: Path, tmp_path: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio, 600.0)

    samples = ScriptedLanguageDetector(model, script=("--langs", "en:0.99,-,pt:0.98")).detect(audio, [15.0, 285.0, 555.0], 30.0)

    assert [(s.at, s.language, s.probability) for s in samples] == [(15.0, "en", 0.99), (285.0, None, 0.0), (555.0, "pt", 0.98)]


@needs_ffmpeg
def test_it003_a_clip_past_the_end_of_the_audio_is_left_out_and_has_no_answer(model: Path, tmp_path: Path):
    audio, log = tmp_path / "audio.m4a", tmp_path / "whisper.log"
    _tone(audio, 60.0)
    detector = ScriptedLanguageDetector(model, script=("--langs", "en:0.99", "--log", str(log)))

    samples = detector.detect(audio, [15.0, 900.0], 30.0)

    assert samples == [LanguageSample(15.0, "en", 0.99), LanguageSample(900.0, None, 0.0)]
    (call,) = _calls(log)
    assert len(_files(call)) == 1   # only the first clip reached whisper


@needs_ffmpeg
def test_it003_a_binding_survives_a_skipped_clip_in_the_middle(model: Path, tmp_path: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio, 60.0)

    samples = ScriptedLanguageDetector(model, script=("--langs", "en:0.99,pt:0.98")).detect(audio, [0.0, 900.0, 20.0], 30.0)

    assert [(s.at, s.language) for s in samples] == [(0.0, "en"), (900.0, None), (20.0, "pt")]


@needs_ffmpeg
def test_no_usable_clip_means_no_whisper_call(model: Path, tmp_path: Path):
    audio, log = tmp_path / "audio.m4a", tmp_path / "whisper.log"
    _tone(audio, 10.0)

    samples = ScriptedLanguageDetector(model, script=("--log", str(log))).detect(audio, [900.0, 1200.0], 30.0)

    assert [s.language for s in samples] == [None, None]
    assert not log.exists()


@needs_ffmpeg
def test_a_missing_whisper_executable_is_a_transcription_error(model: Path, tmp_path: Path, own_tmp: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio, 60.0)

    with pytest.raises(TranscriptionError, match="whisper-cli: executable not found"):
        WhisperCppLanguageDetector(model, whisper_cli=str(tmp_path / "no-such-whisper")).detect(audio, [0.0], 30.0)

    assert list(own_tmp.iterdir()) == []


# --- real whisper --------------------------------------------------------------
# Opt-in: loads the model (574 MB); run with TREC_REAL_WHISPER=1 pytest -m slow tests/integration/test_language_whispercpp.py
_settings = load_settings(Path(__file__).resolve().parents[2])
real_ready = (
    os.environ.get("TREC_REAL_WHISPER") == "1"
    and shutil.which("whisper-cli")
    and shutil.which("say")
    and shutil.which("ffmpeg")
    and _settings.whisper_model_path.exists()
)
ENGLISH = "Good morning everyone. Let us start with the review of the sprint, then talk about the integration report and the next steps. "
PORTUGUESE = "Bom dia pessoal. Vamos começar pela revisão da sprint, depois falar do relatório de integração e dos próximos passos. "


def _spoken(tmp_path: Path, voice: str, phrase: str) -> Path:
    aiff, audio = tmp_path / f"{voice}.aiff", tmp_path / f"{voice}.m4a"
    subprocess.run(["say", "-v", voice, "-o", str(aiff), phrase * 4], check=True)   # about 40 s of speech
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(aiff), "-c:a", "aac", "-b:a", "64k", str(audio)], check=True)
    return audio


@pytest.mark.slow
@pytest.mark.skipif(not real_ready, reason="set TREC_REAL_WHISPER=1 (requires whisper-cli, say, ffmpeg and the model)")
@pytest.mark.parametrize("voice, phrase, language", [("Samantha", ENGLISH, "en"), ("Luciana", PORTUGUESE, "pt")])
def test_it004_real_whisper_hears_the_language_of_every_sample(tmp_path: Path, voice: str, phrase: str, language: str):
    audio = _spoken(tmp_path, voice, phrase)

    samples = WhisperCppLanguageDetector(_settings.whisper_model_path).detect(audio, [0.0, 5.0, 10.0], 30.0)

    assert [s.language for s in samples] == [language] * 3, samples
    assert all(s.probability >= 0.5 for s in samples), samples
    chosen = choose_language(samples, ALLOWED, "pt")
    assert (chosen.language, chosen.reason) == (language, LanguageReason.MAJORITY)
