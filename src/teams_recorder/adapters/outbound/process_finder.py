"""Localiza o PID do Microsoft Teams. Será reaproveitado pelo detector de chamadas (fase 5)."""
from __future__ import annotations

import subprocess


def find_pid(process_name: str, runner=subprocess.run) -> int | None:
    """Retorna o menor PID cujo nome de executável é exatamente `process_name`, ou None."""
    try:
        result = runner(["pgrep", "-x", process_name], capture_output=True, text=True, check=False)
    except OSError:
        return None
    pids = sorted(int(p) for p in result.stdout.split() if p.isdigit())
    return pids[0] if pids else None
