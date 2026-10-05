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


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg não instalado")
def test_anomalous_tracks_are_preserved(tmp_path: Path):
    meeting = tmp_path / "m"; meeting.mkdir()
    tap, mic, out = meeting / "tap.wav", meeting / "mic.wav", meeting / "audio.m4a"
    _tone(tap, 440, 6.0)
    _tone(mic, 880, 1.0)  # gravador do microfone "morreu" cedo

    FfmpegMixer().mix([tap, mic], out)

    assert (meeting / "debug" / "tap.wav").exists() and (meeting / "debug" / "mic.wav").exists()


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg não instalado")
def test_balanced_tracks_are_not_preserved(tmp_path: Path):
    meeting = tmp_path / "m"; meeting.mkdir()
    tap, mic, out = meeting / "tap.wav", meeting / "mic.wav", meeting / "audio.m4a"
    _tone(tap, 440, 2.0)
    _tone(mic, 880, 2.0)
    FfmpegMixer().mix([tap, mic], out)
    assert not (meeting / "debug").exists()


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg não instalado")
def test_probe_reports_duration_and_levels(tmp_path: Path):
    from teams_recorder.adapters.outbound.mixer_ffmpeg import probe
    t = tmp_path / "t.wav"; _tone(t, 440, 2.0)
    info = probe(t)
    assert 1.9 <= info["duration"] <= 2.1 and info["max_db"] is not None and info["mean_db"] is not None


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg não instalado")
def test_mix_output_never_clips(tmp_path: Path):
    """Duas trilhas quentes somadas não podem passar de 0 dBFS no arquivo final."""
    tap, mic, out = tmp_path / "tap.wav", tmp_path / "mic.wav", tmp_path / "audio.m4a"
    for path, freq in ((tap, 440), (mic, 660)):
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=3", "-af", "volume=0dB", "-ar", "48000", str(path)], check=True)
    FfmpegMixer().mix([tap, mic], out)
    stats = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(out), "-af", "astats=measure_overall=Peak_level:measure_perchannel=none", "-f", "null", "-"], capture_output=True, text=True).stderr
    peak = float(next(line.split(":")[1] for line in stats.splitlines() if "Peak level dB" in line))
    assert peak <= 0.0, peak
