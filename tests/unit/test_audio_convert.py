"""The WAV conversion the transcriber and the speech detector share: docs/tasks/speech-check/task_02.md, subtask 2.1."""
from __future__ import annotations

import ast
from pathlib import Path

from teams_recorder.adapters.outbound import audio_convert
from teams_recorder.adapters.outbound.audio_convert import wav_convert_command
from teams_recorder.adapters.outbound.speech_whispercpp import WhisperCppSpeechDetector
from teams_recorder.adapters.outbound.transcriber_whispercpp import WhisperCppTranscriber

OUTBOUND = Path(audio_convert.__file__).parent


def _imports(module: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(module.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    return found


def test_the_command_is_the_one_the_transcriber_always_ran():
    assert wav_convert_command("ffmpeg", Path("a.m4a"), Path("a.wav")) == [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", "a.m4a",
        "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", "a.wav",
    ]


def test_the_ffmpeg_given_is_the_program_run():
    assert wav_convert_command("/opt/homebrew/bin/ffmpeg", Path("a.m4a"), Path("a.wav"))[0] == "/opt/homebrew/bin/ffmpeg"


def test_the_transcriber_and_the_speech_detector_delegate_to_it(tmp_path: Path):
    audio, wav = tmp_path / "a.m4a", tmp_path / "a.wav"

    assert WhisperCppTranscriber(tmp_path / "m.bin", ffmpeg="ff").convert_command(audio, wav) == wav_convert_command("ff", audio, wav)
    assert WhisperCppSpeechDetector(tmp_path / "v.bin", ffmpeg="ff").convert_command(audio, wav) == wav_convert_command("ff", audio, wav)


def test_the_conversion_module_imports_only_constants():
    assert _imports(OUTBOUND / "audio_convert.py") <= {"__future__", "pathlib", "teams_recorder.constants"}


def test_neither_adapter_imports_the_other():
    transcriber, speech = _imports(OUTBOUND / "transcriber_whispercpp.py"), _imports(OUTBOUND / "speech_whispercpp.py")

    assert "teams_recorder.adapters.outbound.speech_whispercpp" not in transcriber
    assert "teams_recorder.adapters.outbound.transcriber_whispercpp" not in speech
    assert {name for name in speech if name.startswith("teams_recorder.adapters")} == {
        "teams_recorder.adapters.outbound.audio_convert", "teams_recorder.adapters.outbound.process_control"}
