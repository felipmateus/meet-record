"""ProcessAudioCapture via o binário Swift `teams-tap` (Core Audio Process Tap)."""
from __future__ import annotations

import signal
import subprocess
from pathlib import Path

from teams_recorder.adapters.outbound import process_control
from teams_recorder.application.ports import CaptureHandle
from teams_recorder.domain import CaptureError


class CoreAudioTapCapture:
    def __init__(self, binary: Path, log_path: Path | None = None, stop_timeout: float = 10.0, startup_grace: float = 1.0, wait_audio: float = 20.0) -> None:
        self.binary = Path(binary)
        self.log_path = log_path
        self.stop_timeout = stop_timeout
        self.startup_grace = startup_grace
        self.wait_audio = wait_audio  # segundos que o teams-tap espera o processo virar cliente de áudio
        self._procs: dict[int, subprocess.Popen] = {}

    def command(self, pid: int, out: Path) -> list[str]:
        return [str(self.binary), "--pid", str(pid), "--out", str(out), "--wait-audio", str(int(self.wait_audio))]

    def start(self, pid: int, out: Path) -> CaptureHandle:
        if not self.binary.exists():
            raise CaptureError(
                f"binário teams-tap não encontrado em {self.binary}. "
                "Compile com: cd native/teams-tap && swift build -c release"
            )
        proc = process_control.spawn(self.command(pid, out), self.log_path, self.startup_grace)
        self._procs[proc.pid] = proc
        return CaptureHandle(pid=proc.pid, out=out)

    def stop(self, handle: CaptureHandle) -> Path:
        process_control.terminate(handle.pid, signal.SIGTERM, self.stop_timeout, self._procs)
        return handle.out
