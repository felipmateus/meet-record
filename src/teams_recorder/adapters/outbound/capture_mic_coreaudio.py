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
from teams_recorder.constants import Audio, Files, Proc
from teams_recorder.domain import CaptureError
from teams_recorder.messages import Err


class CoreAudioMicCapture:
    def __init__(self, binary: Path, log_path: Path | None = None, stop_timeout: float = Proc.STOP_TIMEOUT, startup_grace: float = Proc.MIC_STARTUP_GRACE) -> None:
        self.binary = Path(binary)
        self.log_path = log_path
        self.stop_timeout = stop_timeout
        self.startup_grace = startup_grace
        self._procs: dict[int, subprocess.Popen[bytes]] = {}

    def command(self, device: str, out: Path, epoch: float | None = None) -> list[str]:
        cmd = [str(self.binary), "--mic", device or Audio.DEFAULT_MIC_DEVICE, "--out", str(out)]
        return cmd + (["--epoch", f"{epoch:.3f}"] if epoch is not None else [])

    def start(self, device: str, out: Path, epoch: float | None = None) -> CaptureHandle:
        if not self.binary.exists():
            raise CaptureError(Err.BINARY_MISSING.format(path=self.binary, script=Files.BUILD_NATIVE_SCRIPT))
        proc = process_control.spawn(self.command(device, out, epoch), self.log_path, self.startup_grace)
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
