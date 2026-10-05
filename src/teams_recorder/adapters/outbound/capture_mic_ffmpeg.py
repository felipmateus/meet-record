"""MicCapture via ffmpeg + AVFoundation. SIGINT makes ffmpeg finalize the file correctly."""
from __future__ import annotations

import signal
import subprocess
from pathlib import Path

from teams_recorder.adapters.outbound import process_control
from teams_recorder.application.ports import CaptureHandle
from teams_recorder.constants import Audio, Bin, Proc


class FfmpegMicCapture:
    def __init__(
        self,
        ffmpeg: str = Bin.FFMPEG,
        log_path: Path | None = None,
        sample_rate: int = Audio.SAMPLE_RATE,
        stop_timeout: float = Proc.STOP_TIMEOUT,
        startup_grace: float = Proc.MIC_STARTUP_GRACE,
    ) -> None:
        self.ffmpeg = ffmpeg
        self.log_path = log_path
        self.sample_rate = sample_rate
        self.stop_timeout = stop_timeout
        self.startup_grace = startup_grace
        self._procs: dict[int, subprocess.Popen[bytes]] = {}

    def command(self, device: str, out: Path) -> list[str]:
        # avfoundation accepts a device index or name; ":X" means "no video, audio X".
        return [
            self.ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-f", "avfoundation", "-i", f":{device}",
            "-ac", "1", "-ar", str(self.sample_rate),
            str(out),
        ]

    def start(self, device: str, out: Path, epoch: float | None = None) -> CaptureHandle:
        # ffmpeg cannot align to a shared epoch; the parameter is accepted for the port and ignored.
        proc = process_control.spawn(self.command(device, out), self.log_path, self.startup_grace)
        self._procs[proc.pid] = proc
        return CaptureHandle(pid=proc.pid, out=out)

    def is_running(self, handle: CaptureHandle) -> bool:
        proc = self._procs.get(handle.pid)
        if proc is not None:
            return proc.poll() is None
        return process_control.is_running(handle.pid)

    def stop(self, handle: CaptureHandle) -> Path:
        process_control.terminate(handle.pid, signal.SIGINT, self.stop_timeout, self._procs)
        return handle.out
