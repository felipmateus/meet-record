"""Windows adapters with their OS calls faked: they run (and are tested) on macOS too."""
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest

from teams_recorder.adapters.outbound.confirm_windows import MessageBoxRecordingConfirmation, answer_for
from teams_recorder.adapters.outbound.detector_windows import MicUsage, MicUsageCallDetector, is_teams, teams_in_call
from teams_recorder.adapters.outbound.notifier_windows import ToastNotifier
from teams_recorder.adapters.outbound.scheduler_windows import ScheduledTask
from teams_recorder.adapters.outbound.winproc import root_pids
from teams_recorder.application.ports import CallState, ConfirmAnswer
from teams_recorder.constants import Windows
from teams_recorder.domain import Meeting
from teams_recorder.messages import Ask

TEAMS_PKG = "MSTeams_8wekyb3d8bbwe"
NS = {"t": Windows.TASK_NAMESPACE}


# --- call detector -------------------------------------------------------------------
@pytest.mark.parametrize("app, expected", [
    (TEAMS_PKG, True),
    ("C:#Users#ana#AppData#Local#Microsoft#Teams#current#ms-teams.exe", True),
    ("C:#Program Files#Zoom#bin#Zoom.exe", False),
    ("Microsoft.WindowsSoundRecorder_8wekyb3d8bbwe", False),
])
def test_is_teams(app, expected):
    assert is_teams(app, "ms-teams.exe") is expected


def test_in_call_only_while_teams_holds_the_microphone():
    idle = [MicUsage(TEAMS_PKG, start=100, stop=200), MicUsage("C:#Zoom.exe", start=300, stop=0)]
    assert not teams_in_call(idle, "ms-teams.exe")            # Zoom has the mic, Teams released it
    assert teams_in_call([MicUsage(TEAMS_PKG, start=100, stop=0)], "ms-teams.exe")
    assert not teams_in_call([MicUsage(TEAMS_PKG, start=0, stop=0)], "ms-teams.exe")   # never used


def test_detector_poll_and_pid():
    usage = [MicUsage(TEAMS_PKG, 1, 0)]
    d = MicUsageCallDetector(read_usage=lambda: usage, find_pid=lambda name: 4321)
    assert d.poll() is CallState.IN_CALL and d.teams_pid() == 4321
    usage[0] = MicUsage(TEAMS_PKG, 1, 2)
    assert d.poll() is CallState.IDLE


def test_detector_registry_failure_is_unknown():
    def broken():
        raise OSError("no key")

    def no_table(name):
        raise OSError("no snapshot")

    d = MicUsageCallDetector(read_usage=broken, find_pid=no_table)
    assert d.poll() is CallState.UNKNOWN and d.teams_pid() is None


def test_root_pids_pick_the_top_of_the_teams_tree():
    table = {
        10: (1, "explorer.exe"),
        20: (10, "ms-teams.exe"),     # main process
        21: (20, "ms-teams.exe"),     # helper of the same exe
        30: (20, "msedgewebview2.exe"),
        40: (1, "MS-TEAMS.EXE"),      # a second, unrelated instance (case-insensitive)
    }
    assert root_pids(table, "ms-teams.exe") == [20, 40]
    assert root_pids(table, "zoom.exe") == []


# --- keep-or-discard dialog --------------------------------------------------------------
def test_message_box_buttons_map_to_answers():
    assert answer_for(Windows.IDYES) is ConfirmAnswer.KEEP
    assert answer_for(Windows.IDNO) is ConfirmAnswer.DISCARD
    assert answer_for(Windows.MB_TIMEDOUT) is ConfirmAnswer.NO_ANSWER
    assert answer_for(0) is ConfirmAnswer.NO_ANSWER


def test_message_box_is_called_with_timeout_and_flags(clock):
    calls = []

    def box(text, title, flags, timeout_ms):
        calls.append((text, title, flags, timeout_ms))
        return Windows.IDNO

    confirm = MessageBoxRecordingConfirmation(timeout_seconds=20, message_box=box)
    assert confirm.ask(Meeting.start(clock.now(), pid=1)) is ConfirmAnswer.DISCARD
    assert calls == [(Ask.BODY_WINDOWS, Ask.TITLE, Windows.MB_FLAGS, 20000)]


def test_message_box_failure_keeps_the_recording(clock):
    def box(*a):
        raise OSError("user32 missing")

    assert MessageBoxRecordingConfirmation(message_box=box).ask(Meeting.start(clock.now(), pid=1)) is ConfirmAnswer.NO_ANSWER


# --- toast -----------------------------------------------------------------------------
def test_toast_runs_powershell_with_escaped_text():
    calls = []
    notifier = ToastNotifier(runner=lambda cmd, **kw: calls.append((cmd, kw)))
    notifier.notify("Recording started", "Meeting O'Brien\nsync")
    cmd, kw = calls[0]
    assert cmd[0] == "powershell" and cmd[1:6] == list(Windows.POWERSHELL_ARGS)
    script = cmd[-1]
    assert "'teams-recorder: Recording started'" in script
    assert "'Meeting O''Brien sync'" in script               # quote doubled, newline flattened
    assert Windows.TOAST_APP_ID in script and kw["creationflags"] == Windows.CREATE_NO_WINDOW


def test_toast_failure_is_swallowed():
    def runner(*a, **kw):
        raise subprocess.TimeoutExpired("powershell", 1)

    ToastNotifier(runner=runner).notify("t", "b")              # no exception


# --- Task Scheduler ----------------------------------------------------------------------
class FakeSchtasks:
    def __init__(self, existing=False, state="Running"):
        self.calls = []
        self.existing = existing
        self.state = state

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if cmd[0] == "powershell":
            return SimpleNamespace(returncode=0, stdout=self.state + "\n", stderr="")
        action = cmd[1]
        if action == "/Query":
            return SimpleNamespace(returncode=0 if self.existing else 1, stdout="", stderr="")
        if action == "/Create":
            self.existing = True
        if action == "/Delete":
            self.existing = False
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def _task(tmp_path, runner, **kw):
    return ScheduledTask(tmp_path / "proj", tmp_path / "data", runner=runner, user="RADIX\\ana", **kw)


def test_daemon_task_definition(tmp_path: Path):
    root = ET.fromstring(_task(tmp_path, FakeSchtasks()).definition())
    assert root.find("t:Triggers/t:LogonTrigger/t:UserId", NS).text == "RADIX\\ana"
    assert root.find("t:Principals/t:Principal/t:LogonType", NS).text == "InteractiveToken"
    assert root.find("t:Settings/t:ExecutionTimeLimit", NS).text == "PT0S"
    assert root.find("t:Settings/t:RestartOnFailure/t:Count", NS) is not None
    exec_ = root.find("t:Actions/t:Exec", NS)
    assert exec_.find("t:Command", NS).text.endswith("pythonw.exe")
    assert exec_.find("t:Arguments", NS).text == "-m teams_recorder.adapters.inbound.cli daemon"
    assert exec_.find("t:WorkingDirectory", NS).text == str(tmp_path / "proj")


def test_planner_task_runs_on_weekdays_at_the_hour(tmp_path: Path):
    task = ScheduledTask.planner(tmp_path / "proj", tmp_path / "data", hour=18, runner=FakeSchtasks())
    root = ET.fromstring(task.definition())
    trigger = root.find("t:Triggers/t:CalendarTrigger", NS)
    assert trigger.find("t:StartBoundary", NS).text.endswith("T18:00:00")
    days = [d.tag.split("}")[1] for d in trigger.find("t:ScheduleByWeek/t:DaysOfWeek", NS)]
    assert days == list(Windows.TASK_WEEKDAYS)
    assert root.find("t:Actions/t:Exec/t:Arguments", NS).text.endswith("plan --purge")
    assert root.find("t:Settings/t:RestartOnFailure", NS) is None


def test_install_creates_and_starts_the_daemon_task(tmp_path: Path):
    runner = FakeSchtasks()
    path = _task(tmp_path, runner).install()
    assert path.read_text(encoding="utf-16").startswith("<Task")
    actions = [c[1] for c in runner.calls if c[0] == "schtasks"]
    assert actions == ["/Query", "/Create", "/Run"]
    create = next(c for c in runner.calls if c[1] == "/Create")
    assert create[create.index("/TN") + 1] == "\\teams-recorder\\daemon" and "/F" in create


def test_install_replaces_an_existing_task_and_planner_is_not_started(tmp_path: Path):
    runner = FakeSchtasks(existing=True)
    ScheduledTask.planner(tmp_path / "proj", tmp_path / "data", hour=18, runner=runner).install()
    assert [c[1] for c in runner.calls] == ["/Query", "/End", "/Create"]


def test_uninstall_and_status(tmp_path: Path):
    runner = FakeSchtasks(existing=True, state="Running")
    task = _task(tmp_path, runner)
    status = task.status()
    assert status.loaded and status.state == "Running" and status.pid is None
    assert task.uninstall() is True and task.uninstall() is False
    assert not task.status().loaded


def test_failed_create_raises(tmp_path: Path):
    def runner(cmd, **kw):
        code = 1 if cmd[1] in ("/Query", "/Create") else 0
        return SimpleNamespace(returncode=code, stdout="", stderr="Access is denied.")

    with pytest.raises(RuntimeError, match="Access is denied"):
        _task(tmp_path, runner).install()
