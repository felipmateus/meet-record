"""Runs the daemon as a Windows Task Scheduler task (the launchd counterpart).

One task in the \\teams-recorder\\ folder, for the current user only, runs only while the
user is logged on (it shows dialogs and toasts) and with standard rights: it starts at logon, has
no time limit, is restarted if it fails and is started at once on install. It runs
`.venv\\Scripts\\pythonw.exe -m teams_recorder.adapters.inbound.cli daemon`, so no console window opens.
The XML definition is kept in <data>/tasks for reference. A task an older version installed
is removed through `uninstall()` of a task built with its name.
"""
from __future__ import annotations

import os
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from teams_recorder.adapters.outbound.launchd import AgentStatus
from teams_recorder.constants import Bin, Env, Files, Launchd, Windows
from teams_recorder.messages import Err

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


@dataclass
class ScheduledTask:
    project_dir: Path
    data_dir: Path
    name: str = Windows.TASK_DAEMON
    args: tuple[str, ...] = Launchd.DAEMON_ARGS
    runner: Runner = subprocess.run
    user: str = field(default_factory=lambda: _current_user())

    @property
    def task_name(self) -> str:
        return f"\\{Windows.TASK_FOLDER}\\{self.name}"

    @property
    def xml_path(self) -> Path:
        return self.data_dir / Files.TASKS_DIR / Files.TASK_XML.format(name=self.name)

    # --- definition ---------------------------------------------------------------
    def definition(self) -> str:
        ns = Windows.TASK_NAMESPACE
        task = ET.Element("Task", version="1.2", xmlns=ns)
        triggers = ET.SubElement(task, "Triggers")
        trigger = ET.SubElement(triggers, "LogonTrigger")
        ET.SubElement(trigger, "UserId").text = self.user
        ET.SubElement(trigger, "Enabled").text = "true"

        principal = ET.SubElement(ET.SubElement(task, "Principals"), "Principal", id="Author")
        ET.SubElement(principal, "UserId").text = self.user
        ET.SubElement(principal, "LogonType").text = "InteractiveToken"
        ET.SubElement(principal, "RunLevel").text = "LeastPrivilege"

        settings = ET.SubElement(task, "Settings")
        for tag, value in (
            ("MultipleInstancesPolicy", "IgnoreNew"),
            ("DisallowStartIfOnBatteries", "false"),
            ("StopIfGoingOnBatteries", "false"),
            ("StartWhenAvailable", "true"),
            ("ExecutionTimeLimit", "PT0S"),
        ):
            ET.SubElement(settings, tag).text = value
        restart = ET.SubElement(settings, "RestartOnFailure")
        ET.SubElement(restart, "Interval").text = Windows.TASK_RESTART_INTERVAL
        ET.SubElement(restart, "Count").text = str(Windows.TASK_RESTART_COUNT)

        action = ET.SubElement(ET.SubElement(task, "Actions", Context="Author"), "Exec")
        ET.SubElement(action, "Command").text = str(self.project_dir / Files.VENV_PYTHONW)
        ET.SubElement(action, "Arguments").text = subprocess.list2cmdline(["-m", Files.CLI_MODULE, *self.args])
        ET.SubElement(action, "WorkingDirectory").text = str(self.project_dir)
        ET.indent(task)
        return ET.tostring(task, encoding="unicode")

    # --- lifecycle ------------------------------------------------------------------
    def install(self) -> Path:
        (self.data_dir / Files.LOG_DIR).mkdir(parents=True, exist_ok=True)
        self.xml_path.parent.mkdir(parents=True, exist_ok=True)
        self.xml_path.write_text(self.definition(), encoding="utf-16")   # schtasks /XML expects UTF-16
        if self.is_loaded():
            self._schtasks("/End", "/TN", self.task_name)
        self._schtasks("/Create", "/TN", self.task_name, "/XML", str(self.xml_path), "/F", check=True)
        self._schtasks("/Run", "/TN", self.task_name, check=True)
        return self.xml_path

    def uninstall(self) -> bool:
        if not self.is_loaded():
            return False
        self._schtasks("/End", "/TN", self.task_name)
        self._schtasks("/Delete", "/TN", self.task_name, "/F", check=True)
        return True

    def restart(self) -> None:
        self._schtasks("/End", "/TN", self.task_name)
        self._schtasks("/Run", "/TN", self.task_name, check=True)

    def is_loaded(self) -> bool:
        return self._schtasks("/Query", "/TN", self.task_name).returncode == 0

    def status(self) -> AgentStatus:
        loaded = self.is_loaded()
        state: str | None = None
        if loaded:
            script = Windows.TASK_STATE_SCRIPT.format(folder=Windows.TASK_FOLDER, name=self.name)
            result = self.runner([Bin.POWERSHELL, *Windows.POWERSHELL_ARGS, script], capture_output=True, text=True, check=False,
                                 creationflags=Windows.CREATE_NO_WINDOW)
            state = result.stdout.strip() or None
        return AgentStatus(loaded=loaded and state != Windows.TASK_DISABLED, plist=self.xml_path, plist_exists=self.xml_path.exists(), pid=None, state=state)

    def _schtasks(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        result = self.runner([Bin.SCHTASKS, *args], capture_output=True, text=True, check=False, creationflags=Windows.CREATE_NO_WINDOW)
        if check and result.returncode != 0:
            raise RuntimeError(Err.SCHTASKS_FAILED.format(args=" ".join(args), code=result.returncode, stderr=(result.stderr or result.stdout).strip()))
        return result


def _current_user() -> str:
    user = os.environ.get(Env.WINDOWS_USER, "")
    domain = os.environ.get(Env.WINDOWS_DOMAIN, "")
    return f"{domain}\\{user}" if domain else user
