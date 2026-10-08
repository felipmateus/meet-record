import subprocess
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.mixer_ffmpeg import FfmpegMixer
from teams_recorder.adapters.outbound.process_finder import find_pid
from teams_recorder.domain import CaptureError


def test_mixer_command_two_tracks(tmp_path: Path):
    cmd = FfmpegMixer(bitrate_kbps=96).command([tmp_path / "a.wav", tmp_path / "b.wav"], tmp_path / "out.m4a")
    assert cmd[0] == "ffmpeg"
    assert cmd.count("-i") == 2
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "amix=inputs=2" in filt and "loudnorm" in filt and "alimiter" in filt
    assert filt.count("afftdn") == 2 and filt.count("highpass") == 2  # one per track
    assert cmd[-1].endswith("out.m4a") and "96k" in cmd
    assert cmd[cmd.index("-ar") + 1] == "48000"


def test_mixer_command_single_track(tmp_path: Path):
    cmd = FfmpegMixer().command([tmp_path / "a.wav"], tmp_path / "out.m4a")
    assert "-filter_complex" not in cmd and "-af" in cmd
    assert "afftdn" in cmd[cmd.index("-af") + 1]


def test_mixer_without_denoise(tmp_path: Path):
    cmd = FfmpegMixer(denoise=False).command([tmp_path / "a.wav", tmp_path / "b.wav"], tmp_path / "out.m4a")
    filt = cmd[cmd.index("-filter_complex") + 1]
    assert "afftdn" not in filt and "alimiter" in filt


def test_usable_tracks_filters_missing_and_empty(tmp_path: Path):
    good = tmp_path / "good.wav"; good.write_bytes(b"\x00" * 4096)
    tiny = tmp_path / "tiny.wav"; tiny.write_bytes(b"\x00" * 44)
    assert FfmpegMixer.usable_tracks([good, tiny, tmp_path / "missing.wav"]) == [good]


def test_mix_without_usable_tracks_raises(tmp_path: Path):
    with pytest.raises(CaptureError, match="no usable audio track"):
        FfmpegMixer().mix([tmp_path / "missing.wav"], tmp_path / "out.m4a")


def test_find_pid_parses_pgrep_output():
    def fake_run(cmd, **kw):
        assert cmd == ["pgrep", "-x", "MSTeams"]
        return subprocess.CompletedProcess(cmd, 0, stdout="4312\n4001\n", stderr="")
    assert find_pid("MSTeams", runner=fake_run) == 4001


def test_find_pid_none_when_absent():
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")
    assert find_pid("MSTeams", runner=fake_run) is None
    def broken(cmd, **kw):
        raise OSError("no pgrep")
    assert find_pid("MSTeams", runner=broken) is None


def test_mix_timeout_grows_with_the_meeting():
    mixer = FfmpegMixer(timeout=600)
    assert mixer.timeout_for(60) == 600                 # short meetings keep the floor
    assert mixer.timeout_for(5165) == 10330             # the 86-minute meeting that failed at 600 s


def _fake_ffmpeg(tmp_path: Path, exit_code: int) -> str:
    """Writes some bytes to its .m4a output (not to the probe's `-`) and exits with `exit_code`."""
    script = tmp_path / "ffmpeg"
    script.write_text(f"#!/bin/sh\nfor a; do out=$a; done\ncase $out in *.m4a) printf partial > \"$out\";; esac\nexit {exit_code}\n")
    script.chmod(0o755)
    return str(script)


def _tracks(tmp_path: Path) -> list[Path]:
    tracks = [tmp_path / "tap.wav", tmp_path / "mic.wav"]
    for t in tracks:
        t.write_bytes(b"RIFF" + b"0" * 4096)
    return tracks


def test_failed_mix_leaves_no_audio_file(tmp_path: Path):
    out = tmp_path / "audio.m4a"
    with pytest.raises(CaptureError):
        FfmpegMixer(ffmpeg=_fake_ffmpeg(tmp_path, 1)).mix(_tracks(tmp_path), out)
    assert not out.exists() and not FfmpegMixer.partial_path(out).exists()


def test_successful_mix_is_renamed_into_place(tmp_path: Path):
    out = tmp_path / "audio.m4a"
    assert FfmpegMixer(ffmpeg=_fake_ffmpeg(tmp_path, 0)).mix(_tracks(tmp_path), out) == out
    assert out.read_text() == "partial" and not FfmpegMixer.partial_path(out).exists()
