import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import process_control
from teams_recorder.adapters.outbound.capture_coreaudio import CoreAudioTapCapture
from teams_recorder.adapters.outbound.capture_mic_coreaudio import CoreAudioMicCapture
from teams_recorder.adapters.outbound.capture_mic_ffmpeg import FfmpegMicCapture
from teams_recorder.application.ports import CaptureHandle
from teams_recorder.domain import CaptureError

FAKE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_recorder.py"

# The Python interpreter can take seconds to start in this environment; the tests
# wait for the fake recorder to signal readiness (file creation) before acting.
STARTUP = 5.0


def wait_for(path: Path, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"{path} did not appear within {timeout}s")


class ScriptedTap(CoreAudioTapCapture):
    """Same adapter, but the 'binary' is the fake Python script."""

    def command(self, pid: int, out: Path) -> list[str]:
        return [sys.executable, str(FAKE), "--out", str(out)]


class ScriptedMic(FfmpegMicCapture):
    def command(self, device: str, out: Path) -> list[str]:
        extra = ["--die"] if device == "broken" else []
        return [sys.executable, str(FAKE), "--out", str(out), *extra]


def test_tap_start_stop_roundtrip(tmp_path: Path):
    cap = ScriptedTap(binary=FAKE, log_path=tmp_path / "cap.log", startup_grace=0.3)
    out = tmp_path / "tap.wav"

    handle = cap.start(4242, out)
    assert process_control.is_running(handle.pid) and cap.is_running(handle)
    wait_for(out)

    assert cap.stop(handle) == out
    assert not process_control.is_running(handle.pid) and not cap.is_running(handle)
    assert out.read_bytes().endswith(b"END")  # received the signal and finalized the file


def test_spawn_creates_missing_log_directory(tmp_path: Path):
    cap = ScriptedTap(binary=FAKE, log_path=tmp_path / "log" / "sub" / "capture.log", startup_grace=0.3)
    handle = cap.start(1, tmp_path / "tap.wav")
    cap.stop(handle)
    assert (tmp_path / "log" / "sub" / "capture.log").exists()


def test_tap_fails_when_binary_missing(tmp_path: Path):
    cap = CoreAudioTapCapture(binary=tmp_path / "does-not-exist")
    with pytest.raises(CaptureError, match="teams-tap binary not found"):
        cap.start(1, tmp_path / "x.wav")


def test_mic_start_detects_immediate_death(tmp_path: Path):
    cap = ScriptedMic(log_path=tmp_path / "cap.log", startup_grace=STARTUP)
    with pytest.raises(CaptureError, match="exited right after starting"):
        cap.start("broken", tmp_path / "mic.wav")
    assert "simulated failure" in (tmp_path / "cap.log").read_text()


def test_stop_works_for_handle_from_another_process(tmp_path: Path):
    """`trec stop` runs in another process: it only has the PID read from disk."""
    out = tmp_path / "mic.wav"
    proc = subprocess.Popen([sys.executable, str(FAKE), "--out", str(out)])
    try:
        wait_for(out)  # signal handlers already installed
        cap = ScriptedMic(stop_timeout=5)
        cap.stop(CaptureHandle(pid=proc.pid, out=out))
        assert proc.wait(timeout=5) == 0
        assert out.read_bytes().endswith(b"END")
    finally:
        if proc.poll() is None:
            proc.kill()


def test_stop_is_idempotent_for_dead_pid(tmp_path: Path):
    cap = ScriptedTap(binary=FAKE)
    cap.stop(CaptureHandle(pid=99999999, out=tmp_path / "x.wav"))  # does not raise


def test_terminate_escalates_to_sigkill(tmp_path: Path):
    ready = tmp_path / "ready"
    proc = subprocess.Popen([
        sys.executable, "-c",
        f"import signal,time,pathlib; signal.signal(signal.SIGTERM, signal.SIG_IGN); pathlib.Path({str(ready)!r}).touch(); time.sleep(30)",
    ])
    try:
        wait_for(ready)
        process_control.terminate(proc.pid, signal.SIGTERM, timeout=0.5, known={})
        assert proc.wait(timeout=5) == -signal.SIGKILL
    finally:
        if proc.poll() is None:
            proc.kill()


class ScriptedCoreAudioMic(CoreAudioMicCapture):
    def command(self, device: str, out: Path) -> list[str]:
        return [sys.executable, str(FAKE), "--out", str(out)]


def test_coreaudio_mic_roundtrip(tmp_path: Path):
    cap = ScriptedCoreAudioMic(binary=FAKE, log_path=tmp_path / "cap.log", startup_grace=0.3)
    out = tmp_path / "mic.wav"
    handle = cap.start("default", out)
    wait_for(out)
    assert cap.is_running(handle)
    cap.stop(handle)
    assert out.read_bytes().endswith(b"END") and not cap.is_running(handle)


def test_coreaudio_mic_command_and_missing_binary(tmp_path: Path):
    cmd = CoreAudioMicCapture(binary=tmp_path / "teams-tap").command("", tmp_path / "m.wav")
    assert cmd[1:3] == ["--mic", "default"]
    with pytest.raises(CaptureError, match="teams-tap binary not found"):
        CoreAudioMicCapture(binary=tmp_path / "teams-tap").start("default", tmp_path / "m.wav")


def test_spawn_retries_transient_exec_errors(tmp_path: Path, monkeypatch):
    import errno
    import subprocess as sp
    real_popen = sp.Popen
    attempts = {"n": 0}

    def flaky(*args, **kwargs):
        attempts["n"] += 1
        if attempts["n"] <= 2:
            raise OSError(errno.EDEADLK, "Resource deadlock avoided")
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(process_control.subprocess, "Popen", flaky)
    monkeypatch.setattr(process_control, "SPAWN_RETRY_DELAY", 0)
    cap = ScriptedTap(binary=FAKE, startup_grace=0.3)
    handle = cap.start(1, tmp_path / "t.wav")
    cap.stop(handle)
    assert attempts["n"] == 3


def test_spawn_does_not_retry_permanent_errors(tmp_path: Path, monkeypatch):
    import errno

    def denied(*args, **kwargs):
        raise OSError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(process_control.subprocess, "Popen", denied)
    with pytest.raises(CaptureError, match="Permission denied"):
        ScriptedTap(binary=FAKE).start(1, tmp_path / "t.wav")


def test_warmup_runs_binary(tmp_path: Path):
    cap = ScriptedTap(binary=FAKE)
    assert cap.warmup() in (True, False)  # the fake does not accept --list, but warm-up never raises
