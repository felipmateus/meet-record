"""FfmpegEnergyMeter: the command, the parser on ffmpeg's real output shape, and the failures (no real ffmpeg here)."""
import subprocess
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import energy_ffmpeg
from teams_recorder.adapters.outbound.energy_ffmpeg import FfmpegEnergyMeter, parse_levels
from teams_recorder.application.ports import EnergyMeter
from teams_recorder.domain import SILENCE_DB, CaptureError, EnergyTimeline

# ffmpeg 9 `ametadata=mode=print:...:file=-` output: integer seconds print without decimals, silence prints -inf.
OUTPUT = """frame:0    pts:0       pts_time:0
lavfi.astats.Overall.RMS_level=-21.073559
frame:1    pts:1600    pts_time:0.1
lavfi.astats.Overall.RMS_level=-inf
frame:10   pts:16000   pts_time:1
lavfi.astats.Overall.RMS_level=-85.545672
frame:15   pts:24000   pts_time:1.5
lavfi.astats.Overall.RMS_level=-101.5
"""


def test_it_is_an_energy_meter():
    assert isinstance(FfmpegEnergyMeter(), EnergyMeter)


def test_ut073_the_command_is_the_documented_filter_chain():
    cmd = FfmpegEnergyMeter("/opt/ffmpeg").command(Path("/m/tap.wav"))

    assert cmd[0] == "/opt/ffmpeg" and cmd[cmd.index("-i") + 1] == "/m/tap.wav" and "-nostdin" in cmd
    chain = cmd[cmd.index("-af") + 1]
    assert chain == ("aresample=16000,asetnsamples=n=1600,astats=metadata=1:reset=1,"
                     "ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=-")
    assert cmd[-3:] == ["-f", "null", "-"]


def test_ut074_parse_levels_maps_silence_to_the_floor_and_orders_by_time():
    assert parse_levels(OUTPUT) == EnergyTimeline(step=0.1, levels=(-21.073559, SILENCE_DB, -85.545672, -101.5))
    shuffled = "frame:1 pts:1600 pts_time:0.1\nlavfi.astats.Overall.RMS_level=-30.0\nframe:0 pts:0 pts_time:0\nlavfi.astats.Overall.RMS_level=-20.0\n"
    assert parse_levels(shuffled).levels == (-20.0, -30.0)


def test_ut074_parse_levels_ignores_what_is_not_a_window():
    assert parse_levels("").levels == () and parse_levels("size=N/A time=00:00:03.10 bitrate=N/A\n").levels == ()
    stray = "lavfi.astats.Overall.RMS_level=-12.0\nframe:0 pts:0 pts_time:0\nframe:1 pts:1600 pts_time:0.1\nlavfi.astats.Overall.RMS_level=-40.0\n"
    assert parse_levels(stray).levels == (-40.0,)   # a level needs its own frame line; a frame without a level is dropped


def test_ut074_measure_parses_stdout(monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return subprocess.CompletedProcess(cmd, 0, stdout=OUTPUT, stderr="")

    monkeypatch.setattr(energy_ffmpeg.subprocess, "run", run)

    timeline = FfmpegEnergyMeter(timeout=7).measure(Path("/m/mic.wav"))

    assert timeline.levels[0] == -21.073559 and seen["kw"]["timeout"] == 7 and seen["kw"]["capture_output"] is True


def test_ut075_a_non_zero_exit_is_a_capture_error_with_the_stderr_tail(monkeypatch):
    stderr = "x" * 600 + "Error opening input file /m/tap.wav"
    monkeypatch.setattr(energy_ffmpeg.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, stdout="", stderr=stderr))

    with pytest.raises(CaptureError) as raised:
        FfmpegEnergyMeter().measure(Path("/m/tap.wav"))

    message = str(raised.value)
    assert "tap.wav" in message and "(code 1)" in message and message.endswith("Error opening input file /m/tap.wav") and len(message) < 700


def test_ut075_a_timeout_or_a_missing_binary_is_a_capture_error(monkeypatch):
    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 5)

    monkeypatch.setattr(energy_ffmpeg.subprocess, "run", slow)
    with pytest.raises(CaptureError, match="timed out"):
        FfmpegEnergyMeter(timeout=5).measure(Path("/m/tap.wav"))

    def absent(cmd, **kw):
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    monkeypatch.setattr(energy_ffmpeg.subprocess, "run", absent)
    with pytest.raises(CaptureError, match="No such file"):
        FfmpegEnergyMeter("nope").measure(Path("/m/tap.wav"))


def test_ut075_output_without_a_level_is_a_capture_error(monkeypatch):
    monkeypatch.setattr(energy_ffmpeg.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""))
    with pytest.raises(CaptureError, match="no levels for tap.wav"):
        FfmpegEnergyMeter().measure(Path("/m/tap.wav"))
