"""Transcriber with a fake whisper-cli (always) and with the real whisper (slow, if installed)."""
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from datetime import datetime

import pytest

from teams_recorder.adapters.outbound.language_whispercpp import WhisperCppLanguageDetector
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.adapters.outbound.transcriber_whispercpp import WhisperCppTranscriber
from teams_recorder.application.use_cases import TranscribeMeeting
from teams_recorder.config import load_settings
from teams_recorder.domain import Meeting, TranscriptionError
from teams_recorder.domain.status import AUDIO, TRANSCRIPT_JSON
from teams_recorder.messages import Notify
from tests.fakes import FakeNotifier

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FAKE_CLI = FIXTURES / "fake_whisper_cli.py"
ffmpeg_missing = shutil.which("ffmpeg") is None


class ScriptedTranscriber(WhisperCppTranscriber):
    """The real adapter with fake_whisper_cli.py in place of whisper-cli; `script` are the stand-in's scenario flags."""

    def __init__(self, model_path: Path, fail: bool = False, script: tuple[str, ...] = (), **kwargs) -> None:
        super().__init__(model_path, whisper_cli="fake", **kwargs)
        self.script = [*script, *(["--fail"] if fail else [])]

    def whisper_command(self, wav: Path, language: str, out_prefix: Path) -> list[str]:
        cmd = super().whisper_command(wav, language, out_prefix)
        cmd[0:1] = [sys.executable, str(FAKE_CLI)]
        return cmd + self.script


class ScriptedLanguageDetector(WhisperCppLanguageDetector):
    """The real language adapter with fake_whisper_cli.py in place of whisper-cli; `script` are the stand-in's scenario flags
    (`--langs en:0.99,-`, `--log FILE`) and `fail` adds `--fail`."""

    def __init__(self, model_path: Path, fail: bool = False, script: tuple[str, ...] = (), **kwargs) -> None:
        super().__init__(model_path, whisper_cli="fake", **kwargs)
        self.script = [*script, *(["--fail"] if fail else [])]

    def detect_command(self, wavs: Sequence[Path]) -> list[str]:
        cmd = super().detect_command(wavs)
        cmd[0:1] = [sys.executable, str(FAKE_CLI)]
        return cmd + self.script


def _tone(path: Path, seconds: float = 1.0) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac", str(path)], check=True)


@pytest.fixture
def model(tmp_path: Path) -> Path:
    m = tmp_path / "ggml-fake.bin"
    m.write_bytes(b"\x00" * 16)
    return m


def test_missing_model_is_a_clear_error(tmp_path: Path):
    with pytest.raises(TranscriptionError, match="model not found"):
        WhisperCppTranscriber(tmp_path / "does-not-exist.bin").transcribe(tmp_path / "a.m4a", "pt")


def test_missing_audio_is_a_clear_error(model: Path, tmp_path: Path):
    with pytest.raises(TranscriptionError, match="audio not found"):
        WhisperCppTranscriber(model).transcribe(tmp_path / "a.m4a", "pt")


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_transcribe_with_fake_cli(model: Path, tmp_path: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio)

    t = ScriptedTranscriber(model).transcribe(audio, "pt")

    assert len(t.segments) == 2 and t.segments[0].text.startswith("Bom dia")


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_cli_failure_is_wrapped(model: Path, tmp_path: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio)
    with pytest.raises(TranscriptionError, match="whisper-cli failed.*simulated whisper error"):
        ScriptedTranscriber(model, fail=True).transcribe(audio, "pt")


# --- transcript health with the scripted whisper: the anti-loop retry ------------------------
def _recorded(tmp_path: Path) -> tuple[FsMeetingRepository, Meeting]:
    repo = FsMeetingRepository(tmp_path / "data")
    meeting = Meeting.start(datetime(2026, 10, 8, 10, 30, 52))
    repo.create(meeting)
    _tone(repo.path(meeting.id, AUDIO))
    return repo, meeting


def _passes(model: Path, tmp_path: Path, scenario: str) -> tuple[ScriptedTranscriber, ScriptedTranscriber, Path]:
    """The two transcribers the container builds by default: -mc 0, then -mc 0 with VAD."""
    log, vad = tmp_path / "whisper-calls.jsonl", tmp_path / "ggml-silero-v5.1.2.bin"
    vad.write_bytes(b"\x00")
    script = (scenario, "--log", str(log))
    return ScriptedTranscriber(model, script=script), ScriptedTranscriber(model, script=script, vad_model_path=vad, max_context=0), log


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_a_hallucination_loop_is_repaired_by_the_vad_retry(model: Path, tmp_path: Path):
    repo, meeting = _recorded(tmp_path)
    first, retry, log = _passes(model, tmp_path, "--loop")
    notifier = FakeNotifier()

    TranscribeMeeting(repo, first, "pt", retry=retry, notifier=notifier).execute(meeting.id)

    calls = [json.loads(line) for line in log.read_text().splitlines()]
    assert [c[c.index("-mc") + 1] for c in calls] == ["0", "0"]
    assert "--vad" not in calls[0] and "--vad" in calls[1]
    saved = repo.load_transcript(meeting.id)
    assert saved.health is not None and saved.health.retried and not saved.health.degraded
    assert (saved.health.covered_minutes, saved.health.total_minutes) == (10, 10)
    assert "A CIDADE NO BRASIL" not in saved.text and notifier.messages == []


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg not installed")
def test_a_loop_the_retry_cannot_fix_is_saved_degraded_and_notified(model: Path, tmp_path: Path):
    repo, meeting = _recorded(tmp_path)
    first, retry, log = _passes(model, tmp_path, "--loop-always")
    notifier = FakeNotifier()

    transcript = TranscribeMeeting(repo, first, "pt", retry=retry, notifier=notifier).execute(meeting.id)

    assert len(log.read_text().splitlines()) == 2
    health = json.loads(repo.path(meeting.id, TRANSCRIPT_JSON).read_text())["health"]
    assert health["degraded"] and health["retried"] and health["uncovered"] == [[0, 8]] and health["covered_minutes"] == 2
    assert transcript.health is not None and transcript.health.loop_share == 96 / 108   # 8 min of loop every 5 s, 2 min of speech every 10 s
    assert notifier.messages == [(Notify.TRANSCRIPT_DEGRADED, Notify.TRANSCRIPT_DEGRADED_BODY.format(
        meeting_id=meeting.id, loop=transcript.health.loop_share, gaps=Notify.NO_TEXT_IN.format(ranges="00:00:00–00:08:00")))]


# --- real whisper --------------------------------------------------------------
# Opt-in: loads the model (574 MB) and uses the GPU; run with TREC_REAL_WHISPER=1 pytest -m slow
_settings = load_settings(Path(__file__).resolve().parents[2])
real_ready = (
    os.environ.get("TREC_REAL_WHISPER") == "1"
    and shutil.which("whisper-cli")
    and shutil.which("say")
    and _settings.whisper_model_path.exists()
)


@pytest.mark.slow
@pytest.mark.skipif(not real_ready, reason="set TREC_REAL_WHISPER=1 (requires whisper-cli, say and the model)")
def test_real_whisper_transcribes_portuguese_speech(tmp_path: Path):
    # Portuguese phrase on purpose: the test exercises transcription of pt-BR speech.
    phrase = "Bom dia pessoal, vamos começar pela revisão da sprint e depois falar do relatório de integração."
    aiff = tmp_path / "speech.aiff"
    audio = tmp_path / "speech.m4a"
    subprocess.run(["say", "-v", "Luciana", "-o", str(aiff), phrase], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(aiff), "-c:a", "aac", "-b:a", "64k", str(audio)], check=True)

    t = WhisperCppTranscriber(_settings.whisper_model_path).transcribe(audio, "pt")

    text = t.text.lower()
    assert t.segments and t.duration_seconds > 3
    for word in ("bom dia", "sprint", "relatório", "integração"):
        assert word in text, f"'{word}' not found in: {t.text}"


_vad_model = _settings.retry_vad_model_path


@pytest.mark.slow
@pytest.mark.skipif(not (real_ready and _vad_model and _vad_model.exists()), reason="set TREC_REAL_WHISPER=1 (requires whisper-cli, say, the model and the VAD model)")
def test_real_whisper_runs_the_anti_loop_retry_settings(tmp_path: Path):
    # The retry's command (-mc 0 plus Silero VAD) on the real whisper-cli, with silence around the speech
    # (where whisper hallucinates): the speech is kept and the transcript is healthy.
    from teams_recorder.domain import transcript_health
    phrase = "Bom dia pessoal, vamos começar pela revisão da sprint e depois falar do relatório de integração."
    aiff, audio = tmp_path / "speech.aiff", tmp_path / "speech.m4a"
    subprocess.run(["say", "-v", "Luciana", "-o", str(aiff), phrase], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-t", "20", "-i", "anullsrc=r=22050:cl=mono", "-i", str(aiff),
                    "-filter_complex", "[0][1][0]concat=n=3:v=0:a=1", "-c:a", "aac", "-b:a", "64k", str(audio)], check=True)

    t = WhisperCppTranscriber(_settings.whisper_model_path, vad_model_path=_vad_model, max_context=0).transcribe(audio, "pt")

    assert "sprint" in t.text.lower() and "relatório" in t.text.lower(), t.text
    assert not transcript_health(t, max_loop_share=0.10).degraded
