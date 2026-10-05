import plistlib
import subprocess
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.launchd import LABEL, AgentStatus, LaunchAgent


class Recorder:
    """Simulates launchctl. After a bootout, `print` starts answering 'not loaded'."""

    def __init__(self, outputs=None):
        self.calls = []
        self.outputs = outputs or {}
        self.booted_out = False

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        key = cmd[1]
        if key == "bootout":
            self.booted_out = True
        if key == "print" and self.booted_out:
            return subprocess.CompletedProcess(cmd, 113, stdout="", stderr="error")
        rc, out = self.outputs.get(key, (0, ""))
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr="error" if rc else "")


@pytest.fixture
def agent(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return LaunchAgent(tmp_path / "proj", tmp_path / "proj" / "data", runner=Recorder({"print": (113, "")}), sleep=lambda s: None)


def test_plist_contents(agent: LaunchAgent, tmp_path: Path):
    pl = agent.plist()
    assert pl["Label"] == LABEL
    assert pl["ProgramArguments"] == [str(tmp_path / "proj" / ".venv" / "bin" / "trec"), "daemon"]
    assert pl["RunAtLoad"] and pl["KeepAlive"]
    assert "/opt/homebrew/bin" in pl["EnvironmentVariables"]["PATH"]
    assert pl["EnvironmentVariables"]["TEAMS_RECORDER_DIR"] == str(tmp_path / "proj")
    assert pl["StandardErrorPath"].endswith("daemon.err.log")


def test_install_writes_plist_and_bootstraps(agent: LaunchAgent):
    path = agent.install()
    assert path.exists() and path.name == f"{LABEL}.plist"
    with path.open("rb") as fh:
        assert plistlib.load(fh)["Label"] == LABEL
    subcommands = [c[1] for c in agent.runner.calls]
    assert subcommands == ["print", "bootstrap"]  # was not loaded → no bootout
    assert agent.runner.calls[-1][2].startswith("gui/")


def test_install_boots_out_when_already_loaded(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    ag = LaunchAgent(tmp_path / "p", tmp_path / "p" / "data", runner=Recorder({"print": (0, "\tpid = 42\n\tstate = running\n")}), sleep=lambda s: None)
    ag.install()
    assert [c[1] for c in ag.runner.calls] == ["print", "bootout", "print", "bootstrap"]


def test_status_and_uninstall(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    ag = LaunchAgent(tmp_path / "p", tmp_path / "p" / "data", runner=Recorder({"print": (0, "\tpid = 42\n\tstate = running\n")}), sleep=lambda s: None)
    ag.plist_path.parent.mkdir(parents=True)
    ag.plist_path.write_bytes(b"x")
    info = ag.status()
    assert info == AgentStatus(loaded=True, plist=ag.plist_path, plist_exists=True, pid=42, state="running")
    assert ag.uninstall() is True
    assert not ag.plist_path.exists()
    assert "bootout" in [c[1] for c in ag.runner.calls]


def test_bootstrap_failure_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    ag = LaunchAgent(tmp_path / "p", tmp_path / "p" / "data", runner=Recorder({"print": (113, ""), "bootstrap": (5, "")}), sleep=lambda s: None)
    with pytest.raises(RuntimeError, match="bootstrap"):
        ag.install()
    assert sum(1 for c in ag.runner.calls if c[1] == "bootstrap") == 10  # retried several times


def test_extra_env_is_merged(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    ag = LaunchAgent(tmp_path / "p", tmp_path / "p" / "data", extra_env={"TREC_LLM_PROVIDER": "claude-code"})
    env = ag.plist()["EnvironmentVariables"]
    assert env["TREC_LLM_PROVIDER"] == "claude-code" and "PATH" in env


def test_planner_agent_is_scheduled_not_resident(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    ag = LaunchAgent.planner(tmp_path / "p", tmp_path / "p" / "data", hour=18, extra_env={"TREC_LLM_PROVIDER": "claude-code"})
    pl = ag.plist()
    assert pl["Label"] == "local.teams-recorder.planner"
    assert pl["ProgramArguments"][1:] == ["plan", "--purge"]
    assert "KeepAlive" not in pl and "RunAtLoad" not in pl
    assert pl["StartCalendarInterval"] == [{"Hour": 18, "Minute": 0, "Weekday": wd} for wd in range(1, 6)]
    assert pl["StandardOutPath"].endswith("planner.out.log")
    assert ag.plist_path.name == "local.teams-recorder.planner.plist"
