"""ProcessAudioCapture via the Swift `teams-tap` binary (Core Audio Process Tap)."""
from __future__ import annotations

import signal
import subprocess
from pathlib import Path

from teams_recorder.adapters.outbound import process_control
from teams_recorder.application.ports import CaptureHandle
from teams_recorder.constants import Audio, Files, Proc
from teams_recorder.domain import CaptureError
from teams_recorder.messages import Err


class CoreAudioTapCapture:
    def __init__(
        self,
        binary: Path,
        log_path: Path | None = None,
        stop_timeout: float = Proc.STOP_TIMEOUT,
        startup_grace: float = Proc.TAP_STARTUP_GRACE,
        wait_audio: float = Audio.WAIT_AUDIO_SECONDS,
        bit_depth: int = Audio.DEFAULT_BIT_DEPTH,
    ) -> None:
        self.bit_depth = bit_depth
        self.binary = Path(binary)
        self.log_path = log_path
        self.stop_timeout = stop_timeout
        self.startup_grace = startup_grace
        self.wait_audio = wait_audio  # seconds teams-tap waits for the process to become an audio client
        self._procs: dict[int, subprocess.Popen[bytes]] = {}

    def command(self, pid: int, out: Path, epoch: float | None = None) -> list[str]:
        cmd = [str(self.binary), "--pid", str(pid), "--out", str(out), "--wait-audio", str(int(self.wait_audio)), "--bits", str(self.bit_depth)]
        return cmd + (["--epoch", f"{epoch:.3f}"] if epoch is not None else [])

    def warmup(self) -> bool:
        return self.binary.exists() and process_control.warmup(self.binary, ["--list"])

    def start(self, pid: int, out: Path, epoch: float | None = None) -> CaptureHandle:
        if not self.binary.exists():
            raise CaptureError(Err.BINARY_MISSING.format(path=self.binary, script=Files.BUILD_NATIVE_SCRIPT))
        proc = process_control.spawn(self.command(pid, out, epoch), self.log_path, self.startup_grace)
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
