"""Instala o daemon como LaunchAgent do usuário (sobe no login, reinicia se cair)."""
from __future__ import annotations

import os
import plistlib
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

LABEL = "local.teams-recorder.daemon"


@dataclass
class LaunchAgent:
    project_dir: Path
    data_dir: Path
    label: str = LABEL
    runner: object = subprocess.run
    extra_env: dict[str, str] | None = None
    sleep: object = time.sleep

    @property
    def plist_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"{self.label}.plist"

    def plist(self) -> dict:
        trec = self.project_dir / ".venv" / "bin" / "trec"
        home = str(Path.home())
        path = ":".join(["/opt/homebrew/bin", "/usr/local/bin", f"{home}/.local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin"])
        return {
            "Label": self.label,
            "ProgramArguments": [str(trec), "daemon"],
            "RunAtLoad": True,
            "KeepAlive": True,
            "ProcessType": "Background",
            "WorkingDirectory": str(self.project_dir),
            "EnvironmentVariables": {"PATH": path, "TEAMS_RECORDER_DIR": str(self.project_dir), "HOME": home, **(self.extra_env or {})},
            "StandardOutPath": str(self.data_dir / "log" / "daemon.out.log"),
            "StandardErrorPath": str(self.data_dir / "log" / "daemon.err.log"),
            "ThrottleInterval": 10,
        }

    def _domain(self) -> str:
        return f"gui/{os.getuid()}"

    def install(self) -> Path:
        (self.data_dir / "log").mkdir(parents=True, exist_ok=True)
        self.plist_path.parent.mkdir(parents=True, exist_ok=True)
        if self.is_loaded():
            self._bootout_and_wait()
        with self.plist_path.open("wb") as fh:
            plistlib.dump(self.plist(), fh)
        # Logo após um bootout o launchd pode responder "Input/output error" (5) por alguns segundos.
        last: subprocess.CompletedProcess | None = None
        for _ in range(10):
            last = self._launchctl("bootstrap", self._domain(), str(self.plist_path))
            if last.returncode == 0:
                return self.plist_path
            self.sleep(1)  # type: ignore[operator]
        raise RuntimeError(f"launchctl bootstrap falhou ({last.returncode}): {last.stderr.strip()}")  # type: ignore[union-attr]

    def _bootout_and_wait(self, timeout: float = 15.0) -> None:
        self._launchctl("bootout", f"{self._domain()}/{self.label}")
        deadline = time.monotonic() + timeout
        while self.is_loaded() and time.monotonic() < deadline:
            self.sleep(0.5)  # type: ignore[operator]

    def uninstall(self) -> bool:
        existed = self.plist_path.exists()
        if self.is_loaded():
            self._bootout_and_wait()
        self.plist_path.unlink(missing_ok=True)
        return existed

    def restart(self) -> None:
        self._launchctl("kickstart", "-k", f"{self._domain()}/{self.label}", check=True)

    def is_loaded(self) -> bool:
        result = self._launchctl("print", f"{self._domain()}/{self.label}")
        return result.returncode == 0

    def status(self) -> dict:
        result = self._launchctl("print", f"{self._domain()}/{self.label}")
        info = {"loaded": result.returncode == 0, "plist": str(self.plist_path), "plist_exists": self.plist_path.exists(), "pid": None, "state": None}
        for line in result.stdout.splitlines():
            s = line.strip()
            if s.startswith("pid = "):
                info["pid"] = int(s.split("=", 1)[1].strip())
            elif s.startswith("state = "):
                info["state"] = s.split("=", 1)[1].strip()
        return info

    def _launchctl(self, *args: str, check: bool = False) -> subprocess.CompletedProcess:
        result = self.runner(["launchctl", *args], capture_output=True, text=True, check=False)  # type: ignore[operator]
        if check and result.returncode != 0:
            raise RuntimeError(f"launchctl {' '.join(args)} falhou ({result.returncode}): {result.stderr.strip()}")
        return result
