"""Transcritor com whisper-cli simulado (sempre) e com whisper real (slow, se instalado)."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.transcriber_whispercpp import WhisperCppTranscriber
from teams_recorder.config import load_settings
from teams_recorder.domain import TranscriptionError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FAKE_CLI = FIXTURES / "fake_whisper_cli.py"
ffmpeg_missing = shutil.which("ffmpeg") is None


class ScriptedTranscriber(WhisperCppTranscriber):
    def __init__(self, model_path: Path, fail: bool = False) -> None:
        super().__init__(model_path, whisper_cli="fake")
        self.fail = fail

    def whisper_command(self, wav: Path, language: str, out_prefix: Path) -> list[str]:
        cmd = super().whisper_command(wav, language, out_prefix)
        cmd[0:1] = [sys.executable, str(FAKE_CLI)]
        return cmd + (["--fail"] if self.fail else [])


def _tone(path: Path, seconds: float = 1.0) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:a", "aac", str(path)], check=True)


@pytest.fixture
def model(tmp_path: Path) -> Path:
    m = tmp_path / "ggml-fake.bin"
    m.write_bytes(b"\x00" * 16)
    return m


def test_missing_model_is_a_clear_error(tmp_path: Path):
    with pytest.raises(TranscriptionError, match="modelo não encontrado"):
        WhisperCppTranscriber(tmp_path / "nao-existe.bin").transcribe(tmp_path / "a.m4a", "pt")


def test_missing_audio_is_a_clear_error(model: Path, tmp_path: Path):
    with pytest.raises(TranscriptionError, match="áudio não encontrado"):
        WhisperCppTranscriber(model).transcribe(tmp_path / "a.m4a", "pt")


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg não instalado")
def test_transcribe_with_fake_cli(model: Path, tmp_path: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio)

    t = ScriptedTranscriber(model).transcribe(audio, "pt")

    assert len(t.segments) == 2 and t.segments[0].text.startswith("Bom dia")


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg não instalado")
def test_cli_failure_is_wrapped(model: Path, tmp_path: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio)
    with pytest.raises(TranscriptionError, match="whisper-cli falhou.*erro simulado"):
        ScriptedTranscriber(model, fail=True).transcribe(audio, "pt")


# --- whisper real --------------------------------------------------------------
# Opt-in: carrega o modelo (574 MB) e usa a GPU; rode com TREC_REAL_WHISPER=1 pytest -m slow
_settings = load_settings(Path(__file__).resolve().parents[2])
real_ready = (
    os.environ.get("TREC_REAL_WHISPER") == "1"
    and shutil.which("whisper-cli")
    and shutil.which("say")
    and _settings.whisper_model_path.exists()
)


@pytest.mark.slow
@pytest.mark.skipif(not real_ready, reason="defina TREC_REAL_WHISPER=1 (requer whisper-cli, say e modelo)")
def test_real_whisper_transcribes_portuguese_speech(tmp_path: Path):
    phrase = "Bom dia pessoal, vamos começar pela revisão da sprint e depois falar do relatório de integração."
    aiff = tmp_path / "fala.aiff"
    audio = tmp_path / "fala.m4a"
    subprocess.run(["say", "-v", "Luciana", "-o", str(aiff), phrase], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(aiff), "-c:a", "aac", "-b:a", "64k", str(audio)], check=True)

    t = WhisperCppTranscriber(_settings.whisper_model_path).transcribe(audio, "pt")

    text = t.text.lower()
    assert t.segments and t.duration_seconds > 3
    for word in ("bom dia", "sprint", "relatório", "integração"):
        assert word in text, f"'{word}' não encontrado em: {t.text}"
