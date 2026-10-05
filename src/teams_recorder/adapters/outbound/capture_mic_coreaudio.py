"""MicCapture via the `teams-tap --mic` binary (AVAudioEngine).

Replaces ffmpeg/avfoundation as the default: in the first two real meetings ffmpeg
stopped receiving frames a few seconds after Teams opened the microphone (device
reconfiguration). AVAudioEngine receives the change notification and restarts the
capture; with `default` it follows the system's default input (a headset, for example).
"""
from __future__ import annotations

import signal
import subprocess
from pathlib import Path

from teams_recorder.adapters.outbound import process_control
from teams_recorder.application.ports import CaptureHandle
from teams_recorder.domain import CaptureError


class CoreAudioMicCapture:
    def __init__(self, binary: Path, log_path: Path | None = None, stop_timeout: float = 10.0, startup_grace: float = 1.5) -> None:
        self.binary = Path(binary)
        self.log_path = log_path
        self.stop_timeout = stop_timeout
        self.startup_grace = startup_grace
        self._procs: dict[int, subprocess.Popen] = {}

    def command(self, device: str, out: Path) -> list[str]:
        return [str(self.binary), "--mic", device or "default", "--out", str(out)]

    def start(self, device: str, out: Path) -> CaptureHandle:
        if not self.binary.exists():
            raise CaptureError(f"teams-tap binary not found at {self.binary}. Build it with: scripts/build-native.sh")
        proc = process_control.spawn(self.command(device, out), self.log_path, self.startup_grace)
        self._procs[proc.pid] = proc
        return CaptureHandle(pid=proc.pid, out=out)

    def is_running(self, handle: CaptureHandle) -> bool:
        proc = self._procs.get(handle.pid)
        if proc is not None:
            return proc.poll() is None
        return process_control.is_running(handle.pid)

    def stop(self, handle: CaptureHandle) -> Path:
        process_control.terminate(handle.pid, signal.SIGTERM, self.stop_timeout, self._procs)
        return handle.out
