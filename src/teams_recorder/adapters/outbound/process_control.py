"""Utilities to start and stop recorder subprocesses predictably."""
from __future__ import annotations

import errno
import logging
import os
import signal
import subprocess
import time
from pathlib import Path

from teams_recorder.domain import CaptureError

log = logging.getLogger(__name__)

# Transient exec errors on macOS: EDEADLK ("Resource deadlock avoided") was observed on
# the first run of teams-tap by a freshly started daemon, 4 times in 10 s, and then went
# away. EAGAIN/ETXTBSY belong to the same family. Worth retrying before giving up.
TRANSIENT_ERRNOS = {errno.EDEADLK, errno.EAGAIN, errno.ETXTBSY}
SPAWN_RETRIES = 12
SPAWN_RETRY_DELAY = 0.5


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def spawn(command: list[str], log_path: Path | None, startup_grace: float) -> subprocess.Popen:
    """Starts the command and fails early if it dies within the grace period."""
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    stderr = open(log_path, "ab") if log_path else subprocess.DEVNULL  # noqa: SIM115
    try:
        proc = _popen_with_retry(command, stderr)
    except OSError as exc:
        raise CaptureError(f"could not execute {command[0]}: {exc}") from exc
    finally:
        if log_path:
            stderr.close()  # the child has already inherited the descriptor
    deadline = time.monotonic() + startup_grace
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            tail = _tail(log_path) if log_path else ""
            raise CaptureError(f"{Path(command[0]).name} exited right after starting (code {proc.returncode}). {tail}".strip())
        time.sleep(0.05)
    return proc


def _popen_with_retry(command: list[str], stderr) -> subprocess.Popen:
    last: OSError | None = None
    for attempt in range(1, SPAWN_RETRIES + 1):
        try:
            return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr)
        except OSError as exc:
            if exc.errno not in TRANSIENT_ERRNOS:
                raise
            last = exc
            log.warning("exec of %s failed (%s); attempt %d/%d", Path(command[0]).name, exc.strerror, attempt, SPAWN_RETRIES)
            time.sleep(SPAWN_RETRY_DELAY)
    assert last is not None
    raise last


def warmup(binary: Path, args: list[str], timeout: float = 15.0) -> bool:
    """Runs the binary once (in a harmless mode) to trigger any system evaluation early."""
    try:
        subprocess.run([str(binary), *args], capture_output=True, timeout=timeout, check=False)
        return True
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("warm-up of %s failed: %s", binary.name, exc)
        return False


def terminate(pid: int, sig: signal.Signals, timeout: float, known: dict[int, subprocess.Popen]) -> None:
    """Sends `sig` and waits for the process to exit; escalates to SIGKILL on timeout."""
    proc = known.pop(pid, None)
    if proc is not None:
        if proc.poll() is None:
            proc.send_signal(sig)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                log.warning("process %s did not exit within %.0fs; SIGKILL", pid, timeout)
                proc.kill()
                proc.wait(timeout=5)
        return
    if not is_running(pid):
        return
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_running(pid):
            return
        time.sleep(0.1)
    log.warning("process %s did not exit within %.0fs; SIGKILL", pid, timeout)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _tail(path: Path | None, lines: int = 3) -> str:
    if not path or not path.exists():
        return ""
    try:
        return " | ".join(path.read_text(errors="replace").splitlines()[-lines:])
    except OSError:
        return ""
