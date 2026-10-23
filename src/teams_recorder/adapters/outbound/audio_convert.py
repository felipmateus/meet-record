"""The conversion every whisper.cpp tool reads: any audio to 16 kHz mono 16-bit PCM WAV, with ffmpeg.

A neutral module (it imports only `constants`) so the transcriber and the speech detector share one command without either
importing the other (AGENTS.md › Architecture). A change of conversion tool is made here once."""
from __future__ import annotations

from pathlib import Path

from teams_recorder.constants import Audio


def wav_convert_command(ffmpeg: str, audio: Path, wav: Path) -> list[str]:
    """The ffmpeg command that writes `audio` as a 16 kHz mono WAV at `wav`, a format whisper.cpp reads without decoders."""
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(audio),
        "-ac", "1", "-ar", str(Audio.WHISPER_SAMPLE_RATE), "-c:a", "pcm_s16le", str(wav),
    ]
