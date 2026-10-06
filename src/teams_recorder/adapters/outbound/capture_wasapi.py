"""ProcessAudioCapture and MicCapture on Windows, via `teams-tap.exe` (WASAPI).

Same command line as the macOS binary. The difference is how a recorder is stopped:
Windows has no SIGTERM, and `trec stop` runs in another process than the `trec start` that
launched the recorder, so neither stdin nor Ctrl+Break reach it. Each recorder gets a
`--stop-file` path derived from its output file; creating that file makes it pad the
tail, finalize the WAV and exit. If it does not exit in time it is terminated.
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Callable

from teams_recorder.adapters.outbound import process_control
from teams_recorder.application.ports import CaptureHandle
from teams_recorder.constants import Audio, Files, Proc, Windows
from teams_recorder.domain import CaptureError
from teams_recorder.messages import Err, Log

log = logging.getLogger(__name__)


def _default_kill(pid: int) -> None:
    from teams_recorder.adapters.outbound import winproc
    winproc.kill(pid)


class _StopFileRecorder:
    DEFAULT_STARTUP_GRACE = Proc.TAP_STARTUP_GRACE

    def __init__(
        self,
        binary: Path,
        stop_dir: Path,
        log_path: Path | None = None,
        stop_timeout: float = Proc.STOP_TIMEOUT,
        startup_grace: float | None = None,
        wait_audio: float = Audio.WAIT_AUDIO_SECONDS,
        is_alive: Callable[[int], bool] = process_control.is_running,
        kill: Callable[[int], None] = _default_kill,
    ) -> None:
        self.binary = Path(binary)
        self.stop_dir = Path(stop_dir)
        self.log_path = log_path
        self.stop_timeout = stop_timeout
        self.startup_grace = self.DEFAULT_STARTUP_GRACE if startup_grace is None else startup_grace
        self.wait_audio = wait_audio  # tap only: seconds teams-tap retries activation while Teams starts its audio
        self.is_alive = is_alive
        self.kill = kill
        self._procs: dict[int, subprocess.Popen[bytes]] = {}

    def stop_file(self, out: Path) -> Path:
        return self.stop_dir / Files.STOP_FILE.format(meeting_id=out.parent.name, track=out.stem)

    def _start(self, command: list[str], out: Path) -> CaptureHandle:
        if not self.binary.exists():
            raise CaptureError(Err.BINARY_MISSING.format(path=self.binary, script=Files.BUILD_NATIVE_SCRIPT_WINDOWS))
        self.stop_dir.mkdir(parents=True, exist_ok=True)
        self.stop_file(out).unlink(missing_ok=True)
        proc = process_control.spawn(command, self.log_path, self.startup_grace)
        self._procs[proc.pid] = proc
        return CaptureHandle(pid=proc.pid, out=out)

    def warmup(self) -> bool:
        return self.binary.exists() and process_control.warmup(self.binary, ["--list"])

    def is_running(self, handle: CaptureHandle) -> bool:
        proc = self._procs.get(handle.pid)
        if proc is not None:
            return proc.poll() is None
        return self.is_alive(handle.pid)

    def stop(self, handle: CaptureHandle) -> Path:
        stop_file = self.stop_file(handle.out)
        proc = self._procs.pop(handle.pid, None)
        alive: Callable[[], bool] = (lambda: proc.poll() is None) if proc is not None else (lambda: self.is_alive(handle.pid))
        if alive():
            stop_file.parent.mkdir(parents=True, exist_ok=True)
            stop_file.touch()
            deadline = time.monotonic() + self.stop_timeout
            while alive() and time.monotonic() < deadline:
                time.sleep(Windows.STOP_POLL_SECONDS)
            if alive():
                log.warning(Log.FORCED_STOP, handle.pid, self.stop_timeout)
                self.kill(handle.pid)
        if proc is not None:
            try:
                proc.wait(timeout=Proc.STOP_TIMEOUT)
            except subprocess.TimeoutExpired:
                pass
        stop_file.unlink(missing_ok=True)
        return handle.out


class WasapiTapCapture(_StopFileRecorder):
    """What Teams plays: WASAPI process loopback on the Teams process tree."""

    def command(self, pid: int, out: Path, epoch: float | None = None) -> list[str]:
        cmd = [str(self.binary), "--pid", str(pid), "--out", str(out), "--wait-audio", str(int(self.wait_audio)), "--stop-file", str(self.stop_file(out))]
        return cmd + (["--epoch", f"{epoch:.3f}"] if epoch is not None else [])

    def start(self, pid: int, out: Path, epoch: float | None = None) -> CaptureHandle:
        return self._start(self.command(pid, out, epoch), out)


class WasapiMicCapture(_StopFileRecorder):
    """The microphone, following the Windows default input device."""

    DEFAULT_STARTUP_GRACE = Proc.MIC_STARTUP_GRACE

    def command(self, device: str, out: Path, epoch: float | None = None) -> list[str]:
        cmd = [str(self.binary), "--mic", device or Audio.DEFAULT_MIC_DEVICE, "--out", str(out), "--stop-file", str(self.stop_file(out))]
        return cmd + (["--epoch", f"{epoch:.3f}"] if epoch is not None else [])

    def start(self, device: str, out: Path, epoch: float | None = None) -> CaptureHandle:
        return self._start(self.command(device, out, epoch), out)
