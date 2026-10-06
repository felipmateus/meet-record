"""Windows recorders' stop-file protocol, exercised with the fake recorder (runs on any OS)."""
import os
import signal
import sys
from pathlib import Path

from teams_recorder.adapters.outbound import process_control
from teams_recorder.adapters.outbound.capture_wasapi import WasapiMicCapture, WasapiTapCapture
from tests.integration.test_capture_adapters import FAKE, wait_for


class ScriptedWasapiTap(WasapiTapCapture):
    """Same adapter; the 'binary' is the fake recorder, keeping only --out and --stop-file."""

    extra: list[str] = []

    def command(self, pid, out, epoch=None):
        return [sys.executable, str(FAKE), "--out", str(out), "--stop-file", str(self.stop_file(out)), *self.extra]


def _kill(pid):
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _meeting_dir(tmp_path):
    d = tmp_path / "recordings" / "2026-10-06_10-00-00"
    d.mkdir(parents=True)
    return d


def test_stop_file_stops_the_recorder_and_is_removed(tmp_path: Path):
    cap = ScriptedWasapiTap(FAKE, tmp_path / "run", log_path=tmp_path / "cap.log", startup_grace=0.3)
    out = _meeting_dir(tmp_path) / "teams.wav"
    handle = cap.start(4242, out)
    wait_for(out)
    assert cap.is_running(handle)

    assert cap.stop(handle) == out
    assert not process_control.is_running(handle.pid)
    assert out.read_bytes().endswith(b"END")                  # finalized the file on its own
    assert not cap.stop_file(out).exists()


def test_stop_from_another_process_uses_the_pid(tmp_path: Path):
    """`trec stop` runs in a new process: the adapter only has the handle saved on disk."""
    starter = ScriptedWasapiTap(FAKE, tmp_path / "run", startup_grace=0.3)
    out = _meeting_dir(tmp_path) / "teams.wav"
    handle = starter.start(1, out)
    wait_for(out)

    stopper = ScriptedWasapiTap(FAKE, tmp_path / "run", is_alive=process_control.is_running, kill=_kill)
    stopper.stop(handle)
    starter._procs[handle.pid].wait(timeout=10)                # reap the zombie the starter owns
    assert out.read_bytes().endswith(b"END")


def test_recorder_that_ignores_the_stop_file_is_terminated(tmp_path: Path):
    class Hanging(ScriptedWasapiTap):
        extra = ["--hang"]

    killed = []
    cap = Hanging(FAKE, tmp_path / "run", startup_grace=0.3, stop_timeout=0.5, kill=lambda pid: (killed.append(pid), _kill(pid)))
    out = _meeting_dir(tmp_path) / "teams.wav"
    handle = cap.start(1, out)
    wait_for(out)
    cap.stop(handle)
    assert killed == [handle.pid] and not process_control.is_running(handle.pid)


def test_stale_stop_file_is_cleared_before_start(tmp_path: Path):
    cap = ScriptedWasapiTap(FAKE, tmp_path / "run", startup_grace=0.3)
    out = _meeting_dir(tmp_path) / "teams.wav"
    cap.stop_file(out).parent.mkdir(parents=True)
    cap.stop_file(out).touch()
    handle = cap.start(1, out)                                 # would exit at once if the file stayed
    assert cap.is_running(handle)
    cap.stop(handle)


def test_commands_match_the_teams_tap_contract(tmp_path: Path):
    binary = tmp_path / "teams-tap.exe"
    out = tmp_path / "recordings" / "m1" / "mic.wav"
    tap = WasapiTapCapture(binary, tmp_path / "run").command(77, out.with_name("teams.wav"), epoch=1.5)
    assert tap[1:3] == ["--pid", "77"] and "--stop-file" in tap and tap[-2:] == ["--epoch", "1.500"]
    assert tap[tap.index("--stop-file") + 1].endswith("m1.teams.stop")
    mic = WasapiMicCapture(binary, tmp_path / "run").command("", out)
    assert mic[1:3] == ["--mic", "default"] and mic[mic.index("--stop-file") + 1].endswith("m1.mic.stop")


def test_missing_binary_points_to_the_windows_build_script(tmp_path: Path):
    import pytest

    from teams_recorder.domain import CaptureError

    with pytest.raises(CaptureError, match="build-native-windows.ps1"):
        WasapiTapCapture(tmp_path / "teams-tap.exe", tmp_path / "run").start(1, tmp_path / "m" / "t.wav")
