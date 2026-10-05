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
    assert "amix=inputs=2" in filt and "loudnorm" in filt
    assert cmd[-1].endswith("out.m4a") and "96k" in cmd
    assert cmd[cmd.index("-ar") + 1] == "48000"


def test_mixer_command_single_track(tmp_path: Path):
    cmd = FfmpegMixer().command([tmp_path / "a.wav"], tmp_path / "out.m4a")
    assert "-filter_complex" not in cmd and "-af" in cmd


def test_usable_tracks_filters_missing_and_empty(tmp_path: Path):
    good = tmp_path / "good.wav"; good.write_bytes(b"\x00" * 4096)
    tiny = tmp_path / "tiny.wav"; tiny.write_bytes(b"\x00" * 44)
    assert FfmpegMixer.usable_tracks([good, tiny, tmp_path / "missing.wav"]) == [good]


def test_mix_without_usable_tracks_raises(tmp_path: Path):
    with pytest.raises(CaptureError, match="nenhuma trilha"):
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
        raise OSError("sem pgrep")
    assert find_pid("MSTeams", runner=broken) is None
