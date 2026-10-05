"""CallDetector por heurística do sistema: asserções de energia do processo do Teams.

Durante uma chamada o Teams impede o Mac de dormir, criando asserções visíveis em
`pmset -g assertions`, no formato:
    pid 1234(MSTeams): [0x...] 00:05:12 PreventUserIdleDisplaySleep named: "..."
Fora de chamada essas asserções desaparecem. É uma heurística (risco R3): o detector
fica isolado atrás da porta e a CLI manual (`trec start/stop`) continua disponível.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field

from teams_recorder.adapters.outbound.process_finder import find_pid
from teams_recorder.application.ports import CallState

CALL_ASSERTIONS = (
    "PreventUserIdleDisplaySleep",
    "PreventUserIdleSystemSleep",
    "NoIdleSleepAssertion",
    "NoDisplaySleepAssertion",
)

_LINE = re.compile(r"^\s*pid\s+(\d+)\(([^)]+)\):.*?\b(" + "|".join(CALL_ASSERTIONS) + r")\b")


def parse_assertions(text: str, process_name: str) -> list[int]:
    """PIDs do processo `process_name` que seguram uma asserção típica de chamada."""
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
    runner: object = subprocess.run
    last_pids: list[int] = field(default_factory=list)

    def poll(self) -> CallState:
        try:
            result = self.runner(["pmset", "-g", "assertions"], capture_output=True, text=True, check=False, timeout=10)  # type: ignore[operator]
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
