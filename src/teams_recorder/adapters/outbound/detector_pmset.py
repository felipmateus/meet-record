"""CallDetector based on a system heuristic: power assertions held by the Teams process.

During a call Teams prevents the Mac from sleeping, creating assertions visible in
`pmset -g assertions`, in the format:
    pid 1234(MSTeams): [0x...] 00:05:12 PreventUserIdleDisplaySleep named: "..."
Outside a call these assertions disappear. It is a heuristic (risk R3): the detector
stays isolated behind the port and the manual CLI (`trec start/stop`) remains available.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from typing import Callable

from teams_recorder.adapters.outbound.process_finder import find_pid
from teams_recorder.application.ports import CallState
from teams_recorder.constants import Bin, Detector

CALL_ASSERTIONS = Detector.CALL_ASSERTIONS

_LINE = re.compile(r"^\s*pid\s+(\d+)\(([^)]+)\):.*?\b(" + "|".join(CALL_ASSERTIONS) + r")\b")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def parse_assertions(text: str, process_name: str) -> list[int]:
    """PIDs of process `process_name` that hold an assertion typical of a call."""
    pids: list[int] = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if m and m.group(2) == process_name:
            pid = int(m.group(1))
            if pid not in pids:
                pids.append(pid)
    return pids


@dataclass
class PmsetCallDetector:
    process_name: str
    runner: Runner = subprocess.run
    last_pids: list[int] = field(default_factory=list)

    def poll(self) -> CallState:
        try:
            result = self.runner([Bin.PMSET, "-g", "assertions"], capture_output=True, text=True, check=False, timeout=Detector.PMSET_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired):
            return CallState.UNKNOWN
        if result.returncode != 0:
            return CallState.UNKNOWN
        self.last_pids = parse_assertions(result.stdout, self.process_name)
        return CallState.IN_CALL if self.last_pids else CallState.IDLE

    def teams_pid(self) -> int | None:
        if self.last_pids:
            return self.last_pids[0]
        return find_pid(self.process_name)
