"""MicCapture via ffmpeg + AVFoundation. SIGINT faz o ffmpeg finalizar o arquivo corretamente."""
from __future__ import annotations

import signal
import subprocess
from pathlib import Path

from teams_recorder.adapters.outbound import process_control
from teams_recorder.application.ports import CaptureHandle


class FfmpegMicCapture:
    def __init__(self, ffmpeg: str = "ffmpeg", log_path: Path | None = None, sample_rate: int = 48000, stop_timeout: float = 10.0, startup_grace: float = 1.5) -> None:
        self.ffmpeg = ffmpeg
        self.log_path = log_path
        self.sample_rate = sample_rate
        self.stop_timeout = stop_timeout
        self.startup_grace = startup_grace
        self._procs: dict[int, subprocess.Popen] = {}

    def command(self, device: str, out: Path) -> list[str]:
        # avfoundation aceita índice ou nome do dispositivo; ":X" significa "sem vídeo, áudio X".
        return [
            self.ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-f", "avfoundation", "-i", f":{device}",
            "-ac", "1", "-ar", str(self.sample_rate),
            str(out),
        ]

    def start(self, device: str, out: Path) -> CaptureHandle:
        proc = process_control.spawn(self.command(device, out), self.log_path, self.startup_grace)
        self._procs[proc.pid] = proc
        return CaptureHandle(pid=proc.pid, out=out)

    def stop(self, handle: CaptureHandle) -> Path:
        process_control.terminate(handle.pid, signal.SIGINT, self.stop_timeout, self._procs)
        return handle.out
