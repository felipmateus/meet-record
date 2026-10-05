import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound import process_control
from teams_recorder.adapters.outbound.capture_coreaudio import CoreAudioTapCapture
from teams_recorder.adapters.outbound.capture_mic_ffmpeg import FfmpegMicCapture
from teams_recorder.application.ports import CaptureHandle
from teams_recorder.domain import CaptureError

FAKE = Path(__file__).resolve().parents[1] / "fixtures" / "fake_recorder.py"

# O interpretador Python pode levar segundos para subir neste ambiente; os testes
# esperam o gravador simulado sinalizar prontidão (criação do arquivo) antes de agir.
STARTUP = 5.0


def wait_for(path: Path, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"{path} não apareceu em {timeout}s")


class ScriptedTap(CoreAudioTapCapture):
    """Mesmo adaptador, mas o 'binário' é o script Python simulado."""

    def command(self, pid: int, out: Path) -> list[str]:
        return [sys.executable, str(FAKE), "--out", str(out)]


class ScriptedMic(FfmpegMicCapture):
    def command(self, device: str, out: Path) -> list[str]:
        extra = ["--die"] if device == "quebrado" else []
        return [sys.executable, str(FAKE), "--out", str(out), *extra]


def test_tap_start_stop_roundtrip(tmp_path: Path):
    cap = ScriptedTap(binary=FAKE, log_path=tmp_path / "cap.log", startup_grace=0.3)
    out = tmp_path / "tap.wav"

    handle = cap.start(4242, out)
    assert process_control.is_running(handle.pid)
    wait_for(out)

    assert cap.stop(handle) == out
    assert not process_control.is_running(handle.pid)
    assert out.read_bytes().endswith(b"END")  # recebeu o sinal e finalizou o arquivo


def test_spawn_creates_missing_log_directory(tmp_path: Path):
    cap = ScriptedTap(binary=FAKE, log_path=tmp_path / "log" / "sub" / "capture.log", startup_grace=0.3)
    handle = cap.start(1, tmp_path / "tap.wav")
    cap.stop(handle)
    assert (tmp_path / "log" / "sub" / "capture.log").exists()


def test_tap_fails_when_binary_missing(tmp_path: Path):
    cap = CoreAudioTapCapture(binary=tmp_path / "nao-existe")
    with pytest.raises(CaptureError, match="teams-tap não encontrado"):
        cap.start(1, tmp_path / "x.wav")


def test_mic_start_detects_immediate_death(tmp_path: Path):
    cap = ScriptedMic(log_path=tmp_path / "cap.log", startup_grace=STARTUP)
    with pytest.raises(CaptureError, match="encerrou logo ao iniciar"):
        cap.start("quebrado", tmp_path / "mic.wav")
    assert "falha simulada" in (tmp_path / "cap.log").read_text()


def test_stop_works_for_handle_from_another_process(tmp_path: Path):
    """`trec stop` roda em outro processo: só tem o PID lido do disco."""
    out = tmp_path / "mic.wav"
    proc = subprocess.Popen([sys.executable, str(FAKE), "--out", str(out)])
    try:
        wait_for(out)  # handlers de sinal já instalados
        cap = ScriptedMic(stop_timeout=5)
        cap.stop(CaptureHandle(pid=proc.pid, out=out))
        assert proc.wait(timeout=5) == 0
        assert out.read_bytes().endswith(b"END")
    finally:
        if proc.poll() is None:
            proc.kill()


def test_stop_is_idempotent_for_dead_pid(tmp_path: Path):
    cap = ScriptedTap(binary=FAKE)
    cap.stop(CaptureHandle(pid=99999999, out=tmp_path / "x.wav"))  # não levanta


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
