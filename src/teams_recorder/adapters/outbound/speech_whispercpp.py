"""Speech detector via whisper.cpp's `whisper-vad-speech-segments` (docs/tasks/speech-check, ADR-001).

Flow: converts the audio to a 16 kHz mono WAV with ffmpeg (a temporary directory, removed on exit), runs Silero VAD over it
with the project's VAD arguments and reads the speech segments the tool prints. The audio's length is read from the WAV, not
from the meeting's metadata. Everything is local; nothing is written to the meeting's folder.

A format change in the tool's output must read as a failed check, never as "no speech": `parse_speech_segments` raises
unless the count line and the segment lines agree.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import wave
from pathlib import Path

from teams_recorder.adapters.outbound.audio_convert import wav_convert_command
from teams_recorder.adapters.outbound.process_control import NO_WINDOW
from teams_recorder.constants import Audio, Bin, Files, Parse, Proc
from teams_recorder.domain import SpeechActivity, TranscriptionError
from teams_recorder.messages import Err

_TAIL_CHARS = 800


class WhisperCppSpeechDetector:
    def __init__(
        self,
        vad_model_path: Path,
        vad_tool: str = Bin.WHISPER_VAD,
        ffmpeg: str = Bin.FFMPEG,
        threads: int = 0,
        timeout: float = Proc.SPEECH_CHECK_TIMEOUT,
    ) -> None:
        self.vad_model_path = Path(vad_model_path)
        self.vad_tool = vad_tool
        self.ffmpeg = ffmpeg
        self.threads = threads or max(1, (os.cpu_count() or 4) // 2)
        self.timeout = timeout

    # --- commands (public for testing) ------------------------------------
    def convert_command(self, audio: Path, wav: Path) -> list[str]:
        return wav_convert_command(self.ffmpeg, audio, wav)   # the transcriber's conversion, shared

    def vad_command(self, wav: Path) -> list[str]:
        """`-np` keeps the tool's stdout to the results; the ggml start-up lines go to stderr, and the parser ignores them."""
        return [self.vad_tool, "-vm", str(self.vad_model_path), "-f", str(wav), "-np", "-t", str(self.threads), *Audio.VAD_ARGS]

    # --- SpeechDetector port ----------------------------------------------
    def activity(self, audio: Path) -> SpeechActivity:
        if not self.vad_model_path.exists():
            raise TranscriptionError(Err.MODEL_MISSING.format(path=self.vad_model_path, script=Files.DOWNLOAD_MODEL_SCRIPT))
        if not audio.exists():
            raise TranscriptionError(Err.AUDIO_MISSING.format(path=audio))
        with tempfile.TemporaryDirectory(prefix="trec-speech-") as tmp:
            wav = Path(tmp) / "audio16k.wav"
            self._run(self.convert_command(audio, wav), Err.STEP_CONVERT_WAV)
            segments = parse_speech_segments(self._run(self.vad_command(wav), Bin.WHISPER_VAD))
            audio_seconds = _seconds_of_audio(wav)
        return SpeechActivity(audio_seconds=audio_seconds, segments=segments)

    def _run(self, command: list[str], what: str) -> str:
        """Runs one command and returns its stderr and stdout (the tool prints its results to stdout)."""
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout, check=False, creationflags=NO_WINDOW)
        except FileNotFoundError as exc:
            raise TranscriptionError(Err.EXECUTABLE_MISSING.format(what=what, command=command[0])) from exc
        except subprocess.TimeoutExpired as exc:
            raise TranscriptionError(Err.TIMED_OUT.format(what=what, seconds=self.timeout)) from exc
        output = f"{result.stderr or ''}\n{result.stdout or ''}"
        if result.returncode != 0:
            raise TranscriptionError(Err.STEP_FAILED_CODE.format(what=what, code=result.returncode, tail=output.strip()[-_TAIL_CHARS:]))
        return output


def _seconds_of_audio(wav: Path) -> float:
    """Length of a PCM WAV (frames / rate). A file that is missing or unreadable is a failed check."""
    try:
        with wave.open(str(wav), "rb") as clip:
            return clip.getnframes() / float(clip.getframerate())
    except (OSError, EOFError, wave.Error, ZeroDivisionError) as exc:   # ZeroDivisionError: a header that claims a rate of 0
        raise TranscriptionError(Err.SPEECH_BAD_WAV.format(wav=wav, error=exc)) from exc


def parse_speech_segments(output: str) -> tuple[tuple[float, float], ...]:
    """The speech segments in seconds from the tool's output, which gives centiseconds:

        Detected 2 speech segments:
        Speech segment 0: start = 0.00, end = 419.00
        Speech segment 1: start = 458.00, end = 720.00

    (`2067.00` is 20.67 s). Other lines, such as ggml's start-up logs, are ignored. Raises TranscriptionError(Err.VAD_BAD_OUTPUT),
    with the output tail, when the count line is missing or its number differs from the segment lines read: a format change
    must not read as "no speech"."""
    expected: int | None = None
    segments: list[tuple[float, float]] = []
    for raw in output.splitlines():
        line = raw.strip()
        counted = re.match(Parse.VAD_COUNT, line)
        if counted and expected is None:
            expected = int(counted.group(1))
            continue
        found = re.match(Parse.VAD_SEGMENT, line)
        if found:
            segments.append((float(found.group(1)) / Audio.VAD_UNITS_PER_SECOND, float(found.group(2)) / Audio.VAD_UNITS_PER_SECOND))
    if expected is None or expected != len(segments):
        raise TranscriptionError(Err.VAD_BAD_OUTPUT.format(tail=output.strip()[-_TAIL_CHARS:]))
    return tuple(segments)
