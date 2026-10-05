"""Locates the Microsoft Teams PID. Will be reused by the call detector (phase 5)."""
from __future__ import annotations

import subprocess


def find_pid(process_name: str, runner=subprocess.run) -> int | None:
    """Return the lowest PID whose executable name is exactly `process_name`, or None."""
    try:
        result = runner(["pgrep", "-x", process_name], capture_output=True, text=True, check=False)
    except OSError:
        return None
    pids = sorted(int(p) for p in result.stdout.split() if p.isdigit())
    return pids[0] if pids else None
