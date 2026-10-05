"""Utilidades para iniciar e encerrar subprocessos gravadores de forma previsível."""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path

from teams_recorder.domain import CaptureError

log = logging.getLogger(__name__)


def is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def spawn(command: list[str], log_path: Path | None, startup_grace: float) -> subprocess.Popen:
    """Inicia o comando e falha cedo se ele morrer dentro do período de carência."""
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
    stderr = open(log_path, "ab") if log_path else subprocess.DEVNULL  # noqa: SIM115
    try:
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=stderr)
    except OSError as exc:
        raise CaptureError(f"não consegui executar {command[0]}: {exc}") from exc
    finally:
        if log_path:
            stderr.close()  # o filho já herdou o descritor
    deadline = time.monotonic() + startup_grace
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            tail = _tail(log_path) if log_path else ""
            raise CaptureError(f"{Path(command[0]).name} encerrou logo ao iniciar (código {proc.returncode}). {tail}".strip())
        time.sleep(0.05)
    return proc


def terminate(pid: int, sig: signal.Signals, timeout: float, known: dict[int, subprocess.Popen]) -> None:
    """Envia `sig` e espera o processo sair; escala para SIGKILL se estourar o tempo."""
    proc = known.pop(pid, None)
    if proc is not None:
        if proc.poll() is None:
            proc.send_signal(sig)
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                log.warning("processo %s não saiu em %.0fs; SIGKILL", pid, timeout)
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
    log.warning("processo %s não saiu em %.0fs; SIGKILL", pid, timeout)
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
