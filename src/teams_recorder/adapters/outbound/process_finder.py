"""Locates the Microsoft Teams PID. Reused by the call detector."""
from __future__ import annotations

import subprocess
import sys
from typing import Callable

from teams_recorder.constants import Bin

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def find_pid(process_name: str, runner: Runner = subprocess.run) -> int | None:
    """Return the lowest PID whose executable name is exactly `process_name`, or None.

    On Windows: the root of the `process_name` process tree (e.g. the main ms-teams.exe).
    """
    if sys.platform == "win32":
        from teams_recorder.adapters.outbound.winproc import find_root_pid
        try:
            return find_root_pid(process_name)
        except OSError:
            return None
    try:
        result = runner([Bin.PGREP, "-x", process_name], capture_output=True, text=True, check=False)
    except OSError:
        return None
    pids = sorted(int(p) for p in result.stdout.split() if p.isdigit())
    return pids[0] if pids else None
