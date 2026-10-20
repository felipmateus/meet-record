"""Installs the daemon as a user LaunchAgent (starts at login, restarts if it dies)."""
from __future__ import annotations

import os
import plistlib
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from teams_recorder.constants import Bin, Env, Files, Launchd, Parse
from teams_recorder.messages import Err

LABEL = Launchd.DAEMON_LABEL

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass(frozen=True)
class AgentStatus:
    loaded: bool
    plist: Path
    plist_exists: bool
    pid: int | None
    state: str | None


@dataclass(frozen=True)
class JobState:
    """What `launchctl print` says about a job; a field is None when the output does not carry it."""

    pid: int | None = None
    state: str | None = None
    last_exit: int | None = None   # None while the job has never exited

    @property
    def running(self) -> bool:
        return self.pid is not None and self.state == Parse.LAUNCHCTL_RUNNING


def parse_print(output: str) -> JobState:
    """Reads pid, state and last exit code from `launchctl print` output (the last occurrence of each wins)."""
    pid: int | None = None
    state: str | None = None
    last_exit: int | None = None
    for line in output.splitlines():
        s = line.strip()
        if s.startswith(Parse.LAUNCHCTL_PID):
            pid = int(s.split("=", 1)[1].strip())
        elif s.startswith(Parse.LAUNCHCTL_STATE):
            state = s.split("=", 1)[1].strip()
        elif s.startswith(Parse.LAUNCHCTL_LAST_EXIT):
            value = s.split("=", 1)[1].strip()
            last_exit = int(value) if value.lstrip("-").isdigit() else None
    return JobState(pid, state, last_exit)


def job_domain() -> str:
    """The launchctl domain of the logged-in user's GUI session."""
    return Launchd.DOMAIN.format(uid=os.getuid())


def run_launchctl(runner: Runner, *args: str, timeout: float) -> "subprocess.CompletedProcess[str]":
    """One launchctl call that cannot hang its caller. A call that does not answer within `timeout` seconds is killed and
    reported as a failed one (exit `Launchd.TIMEOUT_EXIT`, the reason in stderr), so callers treat it like any refusal."""
    command = [Bin.LAUNCHCTL, *args]
    try:
        return runner(command, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            command, Launchd.TIMEOUT_EXIT, stdout="", stderr=Err.LAUNCHCTL_TIMED_OUT.format(args=" ".join(args), seconds=timeout))


@dataclass
class LaunchAgent:
    project_dir: Path
    data_dir: Path
    label: str = LABEL
    runner: Runner = subprocess.run
    extra_env: dict[str, str] | None = None
    sleep: Callable[[float], None] = time.sleep

    @property
    def plist_path(self) -> Path:
        return Path.home() / Files.PLIST_SUBDIR / f"{self.label}.plist"

    def plist(self) -> dict[str, Any]:
        trec = self.project_dir / Files.VENV_TREC
        home = str(Path.home())
        log_dir = self.data_dir / Files.LOG_DIR
        plist: dict[str, Any] = {
            "Label": self.label,
            "ProgramArguments": [str(trec), *Launchd.DAEMON_ARGS],
            "ProcessType": "Background",
            "WorkingDirectory": str(self.project_dir),
            "EnvironmentVariables": {"PATH": Launchd.PATH, Env.PROJECT_DIR: str(self.project_dir), "HOME": home, **(self.extra_env or {})},
            "StandardOutPath": str(log_dir / Files.AGENT_OUT_LOG.format(name=self._short)),
            "StandardErrorPath": str(log_dir / Files.AGENT_ERR_LOG.format(name=self._short)),
            "ThrottleInterval": Launchd.THROTTLE_SECONDS,
        }
        plist["RunAtLoad"] = True
        plist["KeepAlive"] = True
        return plist

    @property
    def _short(self) -> str:
        return self.label.rsplit(".", 1)[-1]

    def _domain(self) -> str:
        return job_domain()

    def _target(self) -> str:
        return f"{self._domain()}/{self.label}"

    def install(self) -> Path:
        (self.data_dir / Files.LOG_DIR).mkdir(parents=True, exist_ok=True)
        self.plist_path.parent.mkdir(parents=True, exist_ok=True)
        if self.is_loaded():
            self._bootout_and_wait()
        with self.plist_path.open("wb") as fh:
            plistlib.dump(self.plist(), fh)
        # Right after a bootout, launchd may answer "Input/output error" (5) for a few seconds.
        for _ in range(Launchd.BOOTSTRAP_RETRIES):
            last = self._launchctl("bootstrap", self._domain(), str(self.plist_path))
            if last.returncode == 0:
                return self.plist_path
            self.sleep(Launchd.BOOTSTRAP_RETRY_DELAY)
        raise RuntimeError(Err.LAUNCHCTL_FAILED.format(args="bootstrap", code=last.returncode, stderr=last.stderr.strip()))

    def _bootout_and_wait(self, timeout: float = Launchd.BOOTOUT_TIMEOUT) -> None:
        self._launchctl("bootout", self._target())
        deadline = time.monotonic() + timeout
        while self.is_loaded() and time.monotonic() < deadline:
            self.sleep(Launchd.BOOTOUT_POLL_SECONDS)

    def uninstall(self) -> bool:
        existed = self.plist_path.exists()
        if self.is_loaded():
            self._bootout_and_wait()
        self.plist_path.unlink(missing_ok=True)
        return existed

    def restart(self) -> None:
        self._launchctl("kickstart", "-k", self._target(), check=True)

    def is_loaded(self) -> bool:
        result = self._launchctl("print", self._target())
        return result.returncode == 0

    def status(self) -> AgentStatus:
        result = self._launchctl("print", self._target())
        job = parse_print(result.stdout)
        return AgentStatus(loaded=result.returncode == 0, plist=self.plist_path, plist_exists=self.plist_path.exists(), pid=job.pid, state=job.state)

    def _launchctl(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        result = self.runner([Bin.LAUNCHCTL, *args], capture_output=True, text=True, check=False)
        if check and result.returncode != 0:
            raise RuntimeError(Err.LAUNCHCTL_FAILED.format(args=" ".join(args), code=result.returncode, stderr=result.stderr.strip()))
        return result
