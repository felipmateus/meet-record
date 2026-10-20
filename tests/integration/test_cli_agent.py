"""The planner is gone (UT-090) and `trec agent install | restart | uninstall` remove the job an older version installed
(UT-091, UT-095, UT-096, IT-011). launchctl and schtasks are faked: nothing here touches the real launchd or Task Scheduler."""
import dataclasses
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from teams_recorder.adapters.inbound import cli
from teams_recorder.adapters.inbound.cli import app
from teams_recorder.adapters.outbound.launchd import LaunchAgent
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.adapters.outbound.scheduler_windows import ScheduledTask
from teams_recorder.config import ENV_PROJECT_DIR
from teams_recorder.constants import Launchd, Legacy, Platform
from teams_recorder.domain import Meeting
from teams_recorder.domain.status import AUDIO, TRANSCRIPT_JSON
from teams_recorder.messages import Cli, Err

runner = CliRunner()
PLANNER_MESSAGE = Cli.LEGACY_PLANNER_REMOVED


class FakeLaunchctl:
    """Stands in for `LaunchAgent._launchctl`: tracks which labels are loaded, nothing else runs."""

    def __init__(self, loaded: set[str]) -> None:
        self.loaded = set(loaded)
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, agent: LaunchAgent, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        verb = args[0]
        label = agent.label
        if verb == "bootout":
            self.loaded.discard(label)
        elif verb == "bootstrap":
            self.loaded.add(label)
        code = 0 if verb != "print" or label in self.loaded else 113
        return subprocess.CompletedProcess(args, code, stdout="\tpid = 42\n\tstate = running\n" if code == 0 else "", stderr="")

    def targets(self, verb: str) -> list[str]:
        return [call[-1].rsplit("/", 1)[-1] for call in self.calls if call[0] == verb]


@pytest.fixture
def mac(tmp_path: Path, monkeypatch):
    """A project and a home inside tmp_path, a fake launchctl, macOS settings."""
    monkeypatch.setenv(ENV_PROJECT_DIR, str(tmp_path / "proj"))
    (tmp_path / "proj").mkdir()
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    fake = FakeLaunchctl(set())
    monkeypatch.setattr(LaunchAgent, "_launchctl", lambda self, *a, check=False: fake(self, *a, check=check))
    monkeypatch.setattr(cli, "_settings", lambda: dataclasses.replace(cli.load_settings(tmp_path / "proj"), platform=Platform.MACOS))
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    return SimpleNamespace(fake=fake, agents=agents, planner_plist=agents / f"{Legacy.PLANNER_LABEL}.plist", daemon_plist=agents / f"{Launchd.DAEMON_LABEL}.plist")


def _legacy_installed(mac) -> None:
    mac.planner_plist.write_bytes(b"x")
    mac.fake.loaded.add(Legacy.PLANNER_LABEL)


def test_trec_plan_no_longer_exists():    # UT-090
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 2 and "No such command 'plan'" in result.output
    assert runner.invoke(app, ["plan", "--purge"]).exit_code == 2


def test_the_planner_is_addressed_only_through_the_legacy_constants():    # UT-096
    assert Legacy.PLANNER_LABEL == "local.teams-recorder.planner" and Legacy.PLANNER_TASK == "planner"
    assert not any(name.startswith("PLANNER") for name in vars(Launchd)) and not hasattr(LaunchAgent, "planner")
    assert not hasattr(ScheduledTask, "planner")
    src = Path(cli.__file__).resolve().parents[2]
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "Launchd.PLANNER" not in text and "TASK_PLANNER" not in text, path
        if path.name != "constants.py":
            assert "local.teams-recorder.planner" not in text, path
        if path.name != "cli.py":
            assert "Legacy.PLANNER" not in text, path


def test_status_help_and_the_analyzer_prompt_no_longer_describe_the_daily_plan():    # task_15 review 009
    assert "open actions" not in Cli.STATUS_CMD_HELP and "Activities" in Cli.STATUS_CMD_HELP
    assert "Activities" in runner.invoke(app, ["status", "--help"]).output
    prompt = (Path(cli.__file__).resolve().parents[4] / "prompts" / "analyze_system.md").read_text(encoding="utf-8").lower()
    assert "daily plan" not in prompt and "task cards" not in prompt


def test_agent_install_removes_the_old_planner_job(mac):    # UT-091
    _legacy_installed(mac)

    result = runner.invoke(app, ["agent", "install"])

    assert result.exit_code == 0, result.output
    assert PLANNER_MESSAGE.format(name=Legacy.PLANNER_LABEL) in result.output
    assert "Planner scheduled" not in result.output
    assert not mac.planner_plist.exists() and mac.daemon_plist.exists()
    assert mac.fake.targets("bootout") == [Legacy.PLANNER_LABEL]            # the daemon was not loaded: nothing to boot out
    assert Legacy.PLANNER_LABEL not in mac.fake.loaded and Launchd.DAEMON_LABEL in mac.fake.loaded


def test_agent_install_without_the_old_job_says_nothing_about_it(mac):
    result = runner.invoke(app, ["agent", "install"])
    assert result.exit_code == 0, result.output
    assert "planner" not in result.output.lower() and not mac.planner_plist.exists()
    assert Legacy.PLANNER_LABEL not in mac.fake.loaded


def test_agent_restart_removes_the_old_planner_job_and_restarts_the_daemon(mac):    # UT-095
    _legacy_installed(mac)
    mac.fake.loaded.add(Launchd.DAEMON_LABEL)

    result = runner.invoke(app, ["agent", "restart"])

    assert result.exit_code == 0, result.output
    assert PLANNER_MESSAGE.format(name=Legacy.PLANNER_LABEL) in result.output and Cli.DAEMON_RESTARTED in result.output
    assert not mac.planner_plist.exists()
    assert mac.fake.targets("bootout") == [Legacy.PLANNER_LABEL] and mac.fake.targets("kickstart") == [Launchd.DAEMON_LABEL]


def test_agent_restart_without_the_old_job_prints_no_message(mac):    # UT-095
    mac.fake.loaded.add(Launchd.DAEMON_LABEL)
    result = runner.invoke(app, ["agent", "restart"])
    assert result.exit_code == 0 and result.output.strip() == Cli.DAEMON_RESTARTED
    assert mac.fake.targets("bootout") == []


def test_agent_uninstall_removes_the_daemon_and_the_old_planner_job(mac):    # IT-011, UT-096
    _legacy_installed(mac)
    mac.daemon_plist.write_bytes(b"x")
    mac.fake.loaded.add(Launchd.DAEMON_LABEL)

    result = runner.invoke(app, ["agent", "uninstall"])

    assert result.exit_code == 0, result.output
    assert Cli.AGENT_REMOVED in result.output and PLANNER_MESSAGE.format(name=Legacy.PLANNER_LABEL) in result.output
    assert not mac.planner_plist.exists() and not mac.daemon_plist.exists() and not mac.fake.loaded
    assert sorted(mac.fake.targets("bootout")) == sorted([Launchd.DAEMON_LABEL, Legacy.PLANNER_LABEL])


def test_agent_uninstall_with_only_the_daemon_installed(mac):
    mac.daemon_plist.write_bytes(b"x")
    mac.fake.loaded.add(Launchd.DAEMON_LABEL)
    result = runner.invoke(app, ["agent", "uninstall"])
    assert result.exit_code == 0 and result.output.strip() == Cli.AGENT_REMOVED


def test_agent_status_has_no_planner_line(mac):
    mac.daemon_plist.write_bytes(b"x")
    mac.fake.loaded.add(Launchd.DAEMON_LABEL)
    result = runner.invoke(app, ["agent", "status"])
    assert result.exit_code == 0 and "loaded: yes" in result.output and "planner" not in result.output.lower()
    assert all(call[-1].endswith(Launchd.DAEMON_LABEL) for call in mac.fake.calls)   # the planner job is not even queried


# --- Windows: the same through Task Scheduler (untested on real Windows) -----------------------------------------------
class FakeScheduler:
    """Stands in for `ScheduledTask._schtasks`: tasks by name."""

    def __init__(self, tasks: set[str]) -> None:
        self.tasks = set(tasks)
        self.undeletable: set[str] = set()   # tasks whose `/Delete` fails (access denied), as the real `check=True` call raises
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, task: ScheduledTask, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        verb, name = args[0], task.task_name
        if verb == "/Delete" and name in self.undeletable and check:
            raise RuntimeError(Err.SCHTASKS_FAILED.format(args=" ".join(args), code=5, stderr="Access is denied."))
        if verb == "/Create":
            self.tasks.add(name)
        elif verb == "/Delete":
            self.tasks.discard(name)
        code = 0 if verb != "/Query" or name in self.tasks else 1
        return subprocess.CompletedProcess(args, code, stdout="", stderr="")

    def names(self, verb: str) -> list[str]:
        return [call[call.index("/TN") + 1] for call in self.calls if call[0] == verb]


@pytest.fixture
def windows(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(ENV_PROJECT_DIR, str(tmp_path / "proj"))
    (tmp_path / "proj").mkdir()
    fake = FakeScheduler(set())
    monkeypatch.setattr(ScheduledTask, "_schtasks", lambda self, *a, check=False: fake(self, *a, check=check))
    monkeypatch.setattr(cli, "_settings", lambda: dataclasses.replace(cli.load_settings(tmp_path / "proj"), platform=Platform.WINDOWS))
    return fake


DAEMON_TASK, PLANNER_TASK = "\\teams-recorder\\daemon", "\\teams-recorder\\planner"


def test_windows_install_deletes_the_old_planner_task(windows):    # UT-091
    windows.tasks.add(PLANNER_TASK)
    result = runner.invoke(app, ["agent", "install"])
    assert result.exit_code == 0, result.output
    assert PLANNER_MESSAGE.format(name=Legacy.PLANNER_TASK) in result.output
    assert windows.tasks == {DAEMON_TASK} and windows.names("/Delete") == [PLANNER_TASK]


def test_windows_restart_and_uninstall_remove_the_old_planner_task(windows):    # UT-095, UT-096
    windows.tasks |= {DAEMON_TASK, PLANNER_TASK}
    restarted = runner.invoke(app, ["agent", "restart"])
    assert restarted.exit_code == 0, restarted.output
    assert PLANNER_MESSAGE.format(name=Legacy.PLANNER_TASK) in restarted.output and windows.tasks == {DAEMON_TASK}
    windows.tasks.add(PLANNER_TASK)
    removed = runner.invoke(app, ["agent", "uninstall"])
    assert removed.exit_code == 0, removed.output
    assert Cli.AGENT_REMOVED in removed.output and PLANNER_MESSAGE.format(name=Legacy.PLANNER_TASK) in removed.output
    assert windows.tasks == set()
    assert windows.names("/Delete") == [PLANNER_TASK, DAEMON_TASK, PLANNER_TASK]


def test_windows_a_failing_delete_of_the_old_planner_task_does_not_stop_the_daemon(windows):    # UT-091, UT-095, UT-096
    windows.undeletable.add(PLANNER_TASK)
    warning = Cli.LEGACY_PLANNER_REMOVE_FAILED.format(name=Legacy.PLANNER_TASK, error="")
    windows.tasks.add(PLANNER_TASK)
    installed = runner.invoke(app, ["agent", "install"])
    assert installed.exit_code == 0, installed.output
    assert Cli.TASK_INSTALLED.split(":")[0] in installed.output and warning.split("(")[0] in installed.output
    assert DAEMON_TASK in windows.tasks and PLANNER_TASK in windows.tasks and Cli.LEGACY_PLANNER_REMOVED.split("(")[0] not in installed.output
    windows.calls.clear()
    restarted = runner.invoke(app, ["agent", "restart"])
    assert restarted.exit_code == 0, restarted.output
    assert warning.split("(")[0] in restarted.output and Cli.DAEMON_RESTARTED in restarted.output
    assert windows.names("/Run") == [DAEMON_TASK]                                  # the daemon was still restarted
    removed = runner.invoke(app, ["agent", "uninstall"])
    assert removed.exit_code == 0, removed.output
    assert Cli.AGENT_REMOVED in removed.output and warning.split("(")[0] in removed.output and DAEMON_TASK not in windows.tasks


# --- trec purge keeps working (UT-097) ---------------------------------------------------------------------------------
def test_trec_purge_removes_the_audio_of_old_transcribed_meetings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv(ENV_PROJECT_DIR, str(tmp_path))
    repo = FsMeetingRepository(tmp_path / "data")
    old = Meeting.start(datetime.now() - timedelta(days=45))
    young = Meeting.start(datetime.now() - timedelta(days=3))
    for m in (old, young):
        repo.create(m)
        repo.path(m.id, AUDIO).write_bytes(b"\x00")
        repo.path(m.id, TRANSCRIPT_JSON).write_text("{}")

    result = runner.invoke(app, ["purge"])

    assert result.exit_code == 0, result.output
    assert Cli.PURGED.format(count=1) in result.output and Cli.PURGED_LINE.format(meeting_id=old.id) in result.output
    assert not repo.path(old.id, AUDIO).exists() and repo.path(young.id, AUDIO).exists()
