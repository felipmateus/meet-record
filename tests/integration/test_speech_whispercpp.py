"""The speech adapter with a scripted VAD stand-in and real ffmpeg (IT-001, IT-002), and with the real tool (IT-005, slow):
docs/tasks/speech-check/_tests.md. The use case wired to this adapter (IT-003, IT-004) is in test_transcribe_speech.py."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.speech_whispercpp import WhisperCppSpeechDetector
from teams_recorder.config import ggml_model_file, load_settings
from teams_recorder.constants import Audio, Bin
from teams_recorder.domain import TranscriptionError, check_speech
from teams_recorder.messages import Err

FAKE_VAD = Path(__file__).resolve().parents[1] / "fixtures" / "fake_whisper_vad.py"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
SEGMENTS = ("--segments", "0:419,458:720")


class ScriptedSpeechDetector(WhisperCppSpeechDetector):
    """The real speech adapter with fake_whisper_vad.py in place of whisper-vad-speech-segments; `script` are the stand-in's
    scenario flags (`--segments 0:419,458:720`, `--none`, `--garbled`, `--mismatch`, `--log FILE`) and `fail` adds `--fail`."""

    def __init__(self, model_path: Path, fail: bool = False, script: tuple[str, ...] = (), **kwargs) -> None:
        super().__init__(model_path, vad_tool="fake", **kwargs)
        self.script = [*script, *(["--fail"] if fail else [])]

    def vad_command(self, wav: Path) -> list[str]:
        cmd = super().vad_command(wav)
        cmd[0:1] = [sys.executable, str(FAKE_VAD)]
        return cmd + self.script


def _tone(path: Path, seconds: float) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    "-c:a", "aac", str(path)], check=True)


def _calls(log: Path) -> list[list[str]]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def model(tmp_path: Path) -> Path:
    m = tmp_path / "ggml-fake.bin"
    m.write_bytes(b"\x00" * 16)
    return m


@pytest.fixture
def own_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The directory `tempfile` uses, so a test can see whether the adapter left anything in it."""
    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


@needs_ffmpeg
def test_it001_the_scripted_segments_and_the_length_of_the_converted_wav_come_back_and_the_temporary_folder_is_gone(
        model: Path, tmp_path: Path, own_tmp: Path):
    audio, log = tmp_path / "audio.m4a", tmp_path / "vad.log"
    _tone(audio, 27.3)
    detector = ScriptedSpeechDetector(model, script=(*SEGMENTS, "--log", str(log)))

    activity = detector.activity(audio)

    assert activity.audio_seconds == pytest.approx(27.3, abs=0.1)   # read from the converted WAV
    assert activity.segments == ((0.0, 4.19), (4.58, 7.2))
    (call,) = _calls(log)   # one run of the tool...
    assert call[call.index("-vm") + 1] == str(model) and "-np" in call
    assert call[call.index("-vt"):call.index("-vt") + len(Audio.VAD_ARGS)] == Audio.VAD_ARGS   # ...with the project's VAD arguments
    assert list(own_tmp.iterdir()) == []   # Safety Invariant 3: the WAV is gone


@needs_ffmpeg
def test_it001_the_check_writes_nothing_next_to_the_audio(model: Path, tmp_path: Path):
    audio = tmp_path / "meeting" / "audio.m4a"
    audio.parent.mkdir()
    _tone(audio, 5.0)

    ScriptedSpeechDetector(model, script=SEGMENTS).activity(audio)

    assert [p.name for p in audio.parent.iterdir()] == ["audio.m4a"]


@needs_ffmpeg
def test_it001_no_segment_is_a_valid_answer_with_the_length_kept(model: Path, tmp_path: Path, own_tmp: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio, 10.0)

    activity = ScriptedSpeechDetector(model, script=("--none",)).activity(audio)

    assert activity.segments == () and activity.audio_seconds == pytest.approx(10.0, abs=0.1)
    assert list(own_tmp.iterdir()) == []


@needs_ffmpeg
@pytest.mark.parametrize("flag", ["--garbled", "--mismatch"])
def test_it002_a_changed_output_format_raises_with_the_output_tail_never_no_speech(model: Path, tmp_path: Path, own_tmp: Path, flag: str):
    audio = tmp_path / "audio.m4a"
    _tone(audio, 27.3)

    with pytest.raises(TranscriptionError) as raised:
        ScriptedSpeechDetector(model, script=(*SEGMENTS, flag)).activity(audio)

    assert str(raised.value).startswith(Err.VAD_BAD_OUTPUT.format(tail=""))
    assert "Speech segment 0: start = 0.00, end = 419.00" in str(raised.value)   # the tail is the tool's own output
    assert list(own_tmp.iterdir()) == []


@needs_ffmpeg
def test_it002_a_failing_tool_names_itself_and_its_exit_code(model: Path, tmp_path: Path, own_tmp: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio, 27.3)

    with pytest.raises(TranscriptionError, match=r"whisper-vad-speech-segments failed \(code 1\).*simulated vad error"):
        ScriptedSpeechDetector(model, fail=True).activity(audio)

    assert list(own_tmp.iterdir()) == []   # nor does a failure leave the WAV behind


@needs_ffmpeg
def test_it002_audio_ffmpeg_cannot_read_fails_the_conversion_and_the_tool_never_runs(model: Path, tmp_path: Path, own_tmp: Path):
    audio, log = tmp_path / "audio.m4a", tmp_path / "vad.log"
    audio.write_bytes(b"this is not audio" * 100)

    with pytest.raises(TranscriptionError, match=r"conversion to 16 kHz WAV failed \(code"):
        ScriptedSpeechDetector(model, script=("--log", str(log))).activity(audio)

    assert not log.exists()
    assert list(own_tmp.iterdir()) == []


@needs_ffmpeg
def test_it002_a_missing_tool_executable_is_a_transcription_error(model: Path, tmp_path: Path, own_tmp: Path):
    audio = tmp_path / "audio.m4a"
    _tone(audio, 5.0)

    with pytest.raises(TranscriptionError, match="whisper-vad-speech-segments: executable not found"):
        WhisperCppSpeechDetector(model, vad_tool=str(tmp_path / "no-such-vad")).activity(audio)

    assert list(own_tmp.iterdir()) == []


# --- real tool -----------------------------------------------------------------------------------
# Opt-in: runs whisper.cpp's Silero VAD (no Claude credit); TREC_REAL_WHISPER=1 pytest -m slow tests/integration/test_speech_whispercpp.py
_settings = load_settings(Path(__file__).resolve().parents[2])
_vad_model = _settings.models_dir / ggml_model_file(_settings.vad_model)
real_ready = (
    os.environ.get("TREC_REAL_WHISPER") == "1"
    and shutil.which(Bin.WHISPER_VAD)
    and shutil.which("say")
    and shutil.which("ffmpeg")
    and _vad_model.exists()
)
PORTUGUESE = "Bom dia pessoal. Vamos começar pela revisão da sprint, depois falar do relatório de integração e dos próximos passos."


@pytest.mark.slow
@pytest.mark.skipif(not real_ready, reason=f"set TREC_REAL_WHISPER=1 (requires {Bin.WHISPER_VAD}, say, ffmpeg and the Silero model)")
def test_it005_the_real_tool_finds_no_segment_in_ten_seconds_of_silence(tmp_path: Path, own_tmp: Path):
    silence = tmp_path / "silence.wav"
    with wave.open(str(silence), "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(Audio.WHISPER_SAMPLE_RATE)
        clip.writeframes(b"\x00\x00" * 10 * Audio.WHISPER_SAMPLE_RATE)

    activity = WhisperCppSpeechDetector(_vad_model).activity(silence)

    assert activity.segments == ()
    assert activity.audio_seconds == pytest.approx(10.0, abs=0.05)
    assert check_speech(activity).found is False
    assert list(own_tmp.iterdir()) == []


@pytest.mark.slow
@pytest.mark.skipif(not real_ready, reason=f"set TREC_REAL_WHISPER=1 (requires {Bin.WHISPER_VAD}, say, ffmpeg and the Silero model)")
def test_it005_the_real_tool_finds_speech_in_a_say_clip_inside_the_clip(tmp_path: Path, own_tmp: Path):
    aiff, audio = tmp_path / "speech.aiff", tmp_path / "speech.m4a"
    subprocess.run(["say", "-v", "Luciana", "-o", str(aiff), PORTUGUESE], check=True)   # about 8 s of speech
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(aiff), "-c:a", "aac", "-b:a", "64k", str(audio)], check=True)

    activity = WhisperCppSpeechDetector(_vad_model).activity(audio)

    assert activity.speech_seconds >= 2.0, activity
    assert check_speech(activity).found is True
    assert activity.audio_seconds >= 5.0
    assert all(0.0 <= start < end <= activity.audio_seconds + 0.1 for start, end in activity.segments), activity   # centiseconds read as seconds
    assert list(own_tmp.iterdir()) == []
