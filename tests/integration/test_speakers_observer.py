"""IT-003, IT-004: AxSpeakerObserver's lifecycle against the stand-in helper, through a fake launchctl that really runs the
job's ProgramArguments as a subprocess (the real launchctl is never called)."""
import json
import os
import plistlib
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.speakers_ax import AxSpeakerObserver
from teams_recorder.constants import Launchd
from teams_recorder.domain import SpeakerReason, SpeakersUnavailable

STAND_IN = Path(__file__).resolve().parents[1] / "fixtures" / "fake_speakers.py"
EPOCH = 1760655010.0


class ProcessLaunchctl:
    """`bootstrap` runs the plist's ProgramArguments; `print` reports pid and state (and the last exit code once it
    exited); `bootout` sends SIGTERM and waits, like launchd does. Anything else is refused."""

    def __init__(self) -> None:
        self.jobs: dict[str, subprocess.Popen[bytes]] = {}
        self.exit_codes: dict[str, int] = {}
        self.calls: list[list[str]] = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        sub, label = cmd[1], cmd[-1].rsplit("/", 1)[-1]
        if sub == "bootstrap":
            definition = plistlib.loads(Path(cmd[3]).read_bytes())
            assert definition["RunAtLoad"] is True and "KeepAlive" not in definition
            self.jobs[definition["Label"]] = subprocess.Popen(definition["ProgramArguments"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        job = self.jobs.get(label)
        if job is None:
            return subprocess.CompletedProcess(cmd, 113, "", "Could not find service")
        if sub == "print":
            code = job.poll()
            out = f"\tstate = running\n\tpid = {job.pid}\n" if code is None else f"\tstate = not running\n\tlast exit code = {code}\n"
            return subprocess.CompletedProcess(cmd, 0, out, "")
        if sub == "bootout":
            if job.poll() is None:
                job.send_signal(signal.SIGTERM)
                job.wait(timeout=10)
            self.exit_codes[label] = job.returncode
            del self.jobs[label]
            return subprocess.CompletedProcess(cmd, 0, "", "")
        raise AssertionError(f"unexpected launchctl call {cmd}")

    def stop_all(self) -> None:
        for job in self.jobs.values():
            job.kill()
            job.wait()


@pytest.fixture
def helper(tmp_path: Path) -> Path:
    path = tmp_path / "teams-speakers"
    path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{STAND_IN}" "$@"\n')
    path.chmod(0o755)
    return path


@pytest.fixture
def launchctl():
    fake = ProcessLaunchctl()
    yield fake
    fake.stop_all()


def _wait_for(path: Path, seconds: float = 20.0) -> None:
    deadline = time.monotonic() + seconds
    while not path.exists():
        assert time.monotonic() < deadline, f"{path} never appeared"
        time.sleep(0.05)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_it003_start_waits_for_the_helper_and_stop_ends_it_with_the_stop_event_last(helper, launchctl, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SPEAKERS_TRUSTED", "1")
    out = tmp_path / "rec" / "speakers.jsonl"
    out.parent.mkdir()
    observer = AxSpeakerObserver(helper, tmp_path / "data" / "run", log_path=tmp_path / "data" / "log" / "speakers.log",
                                 runner=launchctl, startup_grace=0.5)

    handle = observer.start(out, EPOCH)
    _wait_for(Path(f"{out}.ready"))

    assert handle.out == out and handle.pid == launchctl.jobs[Launchd.SPEAKERS_LABEL].pid
    assert observer.is_running(handle) is True
    assert observer.plist_path().exists()
    command = plistlib.loads(observer.plist_path().read_bytes())["ProgramArguments"]
    assert command[command.index("--epoch") + 1] == "1760655010.000"

    assert observer.stop(handle) == out

    assert launchctl.exit_codes[Launchd.SPEAKERS_LABEL] == 0                   # SIGTERM → the stand-in left normally
    events = [json.loads(line) for line in out.read_text().splitlines()]
    assert [e["event"] for e in events] == ["start", "stop"] and events[0]["epoch"] == EPOCH   # stop is the last line
    assert not _alive(handle.pid) and observer.is_running(handle) is False
    assert not observer.plist_path().exists() and launchctl.jobs == {}


def test_it004_a_missing_permission_raises_and_leaves_no_process_or_job(helper, launchctl, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_SPEAKERS_TRUSTED", "0")
    out = tmp_path / "rec" / "speakers.jsonl"
    out.parent.mkdir()
    observer = AxSpeakerObserver(helper, tmp_path / "data" / "run", log_path=tmp_path / "data" / "log" / "speakers.log",
                                 runner=launchctl, startup_grace=10.0)   # a ceiling: the loop ends when the job exits

    with pytest.raises(SpeakersUnavailable) as raised:
        observer.start(out, EPOCH)

    assert raised.value.reason == SpeakerReason.PERMISSION_MISSING
    assert launchctl.jobs == {} and launchctl.exit_codes[Launchd.SPEAKERS_LABEL] == 3
    assert not observer.plist_path().exists() and not out.exists()          # the helper made no file before exiting 3


@pytest.mark.parametrize("trusted, expected", [("1", []), ("0", "permission")])
def test_the_check_job_reports_the_stand_in_s_permission_and_leaves_nothing(helper, launchctl, tmp_path, monkeypatch, trusted, expected):
    monkeypatch.setenv("FAKE_SPEAKERS_TRUSTED", trusted)
    observer = AxSpeakerObserver(helper, tmp_path / "data" / "run", runner=launchctl, check_timeout=20.0)

    problems = observer.problems()

    assert (problems == []) if expected == [] else (len(problems) == 1 and "Accessibility permission missing" in problems[0])
    assert launchctl.jobs == {} and not observer.plist_path(Launchd.SPEAKERS_CHECK_LABEL).exists()
