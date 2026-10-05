"""Mixagem real com ffmpeg: gera duas trilhas sintéticas e verifica o M4A resultante."""
import shutil
import subprocess
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.mixer_ffmpeg import FfmpegMixer

pytestmark = pytest.mark.slow
ffmpeg_missing = shutil.which("ffmpeg") is None


def _tone(path: Path, freq: int, seconds: float) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}", "-ar", "48000", str(path)],
        check=True,
    )


def _duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg não instalado")
def test_mix_two_tracks_produces_mono_aac(tmp_path: Path):
    tap, mic, out = tmp_path / "tap.wav", tmp_path / "mic.wav", tmp_path / "audio.m4a"
    _tone(tap, 440, 2.0)
    _tone(mic, 880, 3.0)

    result = FfmpegMixer(bitrate_kbps=64).mix([tap, mic], out)

    assert result == out and out.stat().st_size > 5000
    assert 2.9 <= _duration(out) <= 3.3  # duration=longest
    channels = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=channels,codec_name,sample_rate", "-of", "default=nw=1", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "channels=1" in channels and "codec_name=aac" in channels and "sample_rate=48000" in channels


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg não instalado")
def test_mix_single_track_when_other_is_empty(tmp_path: Path):
    tap, mic, out = tmp_path / "tap.wav", tmp_path / "mic.wav", tmp_path / "audio.m4a"
    _tone(mic, 660, 1.0)
    tap.write_bytes(b"RIFF" + b"\x00" * 40)  # trilha vazia (permissão negada, por exemplo)

    FfmpegMixer().mix([tap, mic], out)

    assert 0.9 <= _duration(out) <= 1.3
