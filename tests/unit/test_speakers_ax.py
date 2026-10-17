"""AxSpeakerObserver: the helper as its own launchd job, driven through a fake launchctl (never the real one)."""
import plistlib
import signal
import subprocess
from pathlib import Path

import pytest

from teams_recorder.adapters.outbound.launchd import JobState, parse_print
from teams_recorder.adapters.outbound.speakers_ax import AxSpeakerObserver
from teams_recorder.application.ports import CaptureHandle, SpeakerObserver
from teams_recorder.constants import Launchd, Speakers
from teams_recorder.domain import SpeakerReason, SpeakersUnavailable
from teams_recorder.messages import Err

EPOCH = 1760655010.0
RUNNING = "\tstate = running\n\tpid = 4242\n\tlast exit code = (never exited)\n"
EXITED_3 = "\tstate = not running\n\tlast exit code = 3\n"
EXITED_1 = "\tstate = not running\n\tlast exit code = 1\n"
EXITED_0 = "\tstate = not running\n\tlast exit code = 0\n"
SPAWN_SCHEDULED = "\tstate = spawn scheduled\n"


class FakeLaunchctl:
    """Records every launchctl call. `prints` maps a job label to the successive `print` answers (the last one repeats);
    a label without answers is not loaded (exit 113). `fail` maps a subcommand to its exit code."""

    def __init__(self, prints=None, fail=None, hang=()):
        self.calls: list[list[str]] = []
        self.timeouts: list[float | None] = []   # the `timeout` each call carried
        self.prints = {label: list(answers) for label, answers in (prints or {}).items()}
        self.fail = fail or {}
        self.hang = set(hang)                    # subcommands that never answer: the call raises TimeoutExpired, like subprocess.run does

    def __call__(self, cmd, **kw):
        assert cmd[0] == "launchctl" and kw.get("check") is False
        self.calls.append(cmd)
        self.timeouts.append(kw.get("timeout"))
        sub = cmd[1]
        if sub in self.hang:
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        if sub in self.fail:
            return subprocess.CompletedProcess(cmd, self.fail[sub], stdout="", stderr="boom")
        if sub == "print":
            answers = self.prints.get(cmd[2].rsplit("/", 1)[-1])
            if not answers:
                return subprocess.CompletedProcess(cmd, 113, stdout="", stderr="not found")
            out = answers.pop(0) if len(answers) > 1 else answers[0]
            return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    def subcommands(self) -> list[str]:
        return [c[1] for c in self.calls]


class Terminator:
    def __init__(self):
        self.calls = []

    def __call__(self, pid, sig, timeout, known):
        self.calls.append((pid, sig, timeout))


@pytest.fixture
def helper(tmp_path: Path) -> Path:
    path = tmp_path / "teams-speakers"
    path.write_text("#!/bin/sh\n")
    return path


def observer(helper: Path, tmp_path: Path, launchctl: FakeLaunchctl, alive=lambda pid: False, terminate=None, **kw) -> AxSpeakerObserver:
    return AxSpeakerObserver(
        helper, tmp_path / "data" / "run", log_path=tmp_path / "data" / "log" / "speakers.log", runner=launchctl, sleep=lambda s: None,
        terminate=terminate or Terminator(), alive=alive, **kw,
    )


def test_it_is_a_speaker_observer(helper: Path, tmp_path: Path):
    assert isinstance(observer(helper, tmp_path, FakeLaunchctl()), SpeakerObserver)


def test_ut070_the_job_runs_the_helper_once_at_load_with_the_mandatory_epoch(helper: Path, tmp_path: Path):
    obs = observer(helper, tmp_path, FakeLaunchctl())
    out = tmp_path / "rec" / "speakers.jsonl"

    job = obs.job(out, EPOCH)

    assert job["Label"] == "local.teams-recorder.speakers"
    assert job["ProgramArguments"] == [str(helper), "--out", str(out), "--epoch", "1760655010.000", "--interval", "0.5"]
    assert job["RunAtLoad"] is True and "KeepAlive" not in job and job["ProcessType"] == "Background"
    assert job["StandardErrorPath"] == str(tmp_path / "data" / "log" / "speakers.log")


def test_ut070_start_boots_out_the_stale_job_then_bootstraps_and_returns_the_pid_from_print(helper: Path, tmp_path: Path):
    launchctl = FakeLaunchctl({Launchd.SPEAKERS_LABEL: [SPAWN_SCHEDULED, RUNNING]})
    obs = observer(helper, tmp_path, launchctl)
    out = tmp_path / "rec" / "speakers.jsonl"

    handle = obs.start(out, EPOCH)

    assert handle == CaptureHandle(pid=4242, out=out)
    plist = tmp_path / "data" / "run" / "local.teams-recorder.speakers.plist"
    assert plistlib.loads(plist.read_bytes()) == obs.job(out, EPOCH)
    assert launchctl.subcommands()[:2] == ["bootout", "bootstrap"] and set(launchctl.subcommands()[2:]) == {"print"}
    assert launchctl.calls[0][2].endswith("/local.teams-recorder.speakers") and launchctl.calls[0][2].startswith("gui/")
    assert launchctl.calls[1][2:] == [launchctl.calls[0][2].rsplit("/", 1)[0], str(plist)]


def test_ut070b_the_command_always_carries_the_epoch(helper: Path, tmp_path: Path):
    cmd = observer(helper, tmp_path, FakeLaunchctl()).command(tmp_path / "s.jsonl", 12.3456)
    assert cmd[cmd.index("--epoch") + 1] == "12.346" and cmd[cmd.index("--out") + 1] == str(tmp_path / "s.jsonl")
    with pytest.raises(TypeError):
        observer(helper, tmp_path, FakeLaunchctl()).start(tmp_path / "s.jsonl")   # type: ignore[call-arg]


def test_ut071_a_missing_binary_is_unavailable_and_spawns_nothing(tmp_path: Path):
    launchctl = FakeLaunchctl()
    obs = observer(tmp_path / "nope", tmp_path, launchctl)

    with pytest.raises(SpeakersUnavailable) as raised:
        obs.start(tmp_path / "s.jsonl", EPOCH)

    assert raised.value.reason == SpeakerReason.BINARY_MISSING
    assert str(tmp_path / "nope") in str(raised.value) and "scripts/build-native.sh" in str(raised.value)
    assert launchctl.calls == [] and not (tmp_path / "data" / "run").exists()
    assert obs.problems() == ["teams-speakers not built → scripts/build-native.sh"] and launchctl.calls == []


def test_ut072_exit_3_after_the_grace_is_the_missing_permission_and_the_job_is_booted_out(helper: Path, tmp_path: Path):
    launchctl = FakeLaunchctl({Launchd.SPEAKERS_LABEL: [EXITED_3]})
    obs = observer(helper, tmp_path, launchctl)

    with pytest.raises(SpeakersUnavailable) as raised:
        obs.start(tmp_path / "s.jsonl", EPOCH)

    assert raised.value.reason == SpeakerReason.PERMISSION_MISSING
    assert launchctl.subcommands()[-1] == "bootout" and launchctl.subcommands().count("bootout") == 2   # stale one, then this one
    assert not obs.plist_path().exists()


def test_ut072_any_other_early_exit_is_a_failed_start_quoting_the_log(helper: Path, tmp_path: Path):
    log = tmp_path / "data" / "log" / "speakers.log"
    log.parent.mkdir(parents=True)
    log.write_text("one\ntwo\nthree\nfour\n")
    launchctl = FakeLaunchctl({Launchd.SPEAKERS_LABEL: [EXITED_1]})
    obs = observer(helper, tmp_path, launchctl)

    with pytest.raises(SpeakersUnavailable) as raised:
        obs.start(tmp_path / "s.jsonl", EPOCH)

    assert raised.value.reason == SpeakerReason.START_FAILED
    assert "code 1" in str(raised.value) and str(raised.value).endswith("it exited with code 1. two | three | four")   # the last three lines
    assert launchctl.subcommands()[-1] == "bootout" and not obs.plist_path().exists()


def test_ut072_a_clean_exit_inside_the_grace_is_still_a_failed_start(helper: Path, tmp_path: Path):
    obs = observer(helper, tmp_path, FakeLaunchctl({Launchd.SPEAKERS_LABEL: [EXITED_0]}))
    with pytest.raises(SpeakersUnavailable) as raised:
        obs.start(tmp_path / "s.jsonl", EPOCH)
    assert raised.value.reason == SpeakerReason.START_FAILED


def test_a_job_that_never_ran_or_a_bootstrap_that_fails_is_a_failed_start(helper: Path, tmp_path: Path):
    never = FakeLaunchctl({Launchd.SPEAKERS_LABEL: [SPAWN_SCHEDULED]})
    with pytest.raises(SpeakersUnavailable) as raised:
        observer(helper, tmp_path, never).start(tmp_path / "s.jsonl", EPOCH)
    assert raised.value.reason == SpeakerReason.START_FAILED and "not running" in str(raised.value)

    refused = FakeLaunchctl(fail={"bootstrap": 5})
    with pytest.raises(SpeakersUnavailable) as raised:
        observer(helper, tmp_path, refused).start(tmp_path / "s.jsonl", EPOCH)
    assert raised.value.reason == SpeakerReason.START_FAILED and "bootstrap failed (5): boom" in str(raised.value)
    assert refused.subcommands().count("bootstrap") == 5          # retried: launchd answers 5 for a moment after a bootout
    assert not (tmp_path / "data" / "run" / "local.teams-recorder.speakers.plist").exists()


def test_ut072_stop_boots_the_job_out_and_removes_the_definition(helper: Path, tmp_path: Path):
    launchctl = FakeLaunchctl({Launchd.SPEAKERS_LABEL: [RUNNING]})
    terminator = Terminator()
    obs = observer(helper, tmp_path, launchctl, terminate=terminator)
    handle = obs.start(tmp_path / "s.jsonl", EPOCH)
    launchctl.calls.clear()

    assert obs.stop(handle) == handle.out

    assert launchctl.subcommands() == ["bootout"] and not obs.plist_path().exists() and terminator.calls == []


def test_stop_falls_back_to_sigterm_by_pid_when_launchctl_fails(helper: Path, tmp_path: Path):
    terminator = Terminator()
    obs = observer(helper, tmp_path, FakeLaunchctl(fail={"bootout": 36}), alive=lambda pid: True, terminate=terminator)
    obs.plist_path().parent.mkdir(parents=True)
    obs.plist_path().write_bytes(b"x")

    obs.stop(CaptureHandle(pid=4242, out=tmp_path / "s.jsonl"))

    assert terminator.calls == [(4242, signal.SIGTERM, obs.stop_timeout)] and not obs.plist_path().exists()


def test_stop_tolerates_a_job_and_a_process_that_are_already_gone(helper: Path, tmp_path: Path):
    terminator = Terminator()
    obs = observer(helper, tmp_path, FakeLaunchctl(fail={"bootout": 113}), alive=lambda pid: False, terminate=terminator)

    obs.stop(CaptureHandle(pid=4242, out=tmp_path / "s.jsonl"))

    assert terminator.calls == []


def test_stop_kills_a_helper_that_outlives_the_bootout(helper: Path, tmp_path: Path):
    terminator = Terminator()
    obs = observer(helper, tmp_path, FakeLaunchctl(), alive=lambda pid: True, terminate=terminator, stop_timeout=0.3)

    obs.stop(CaptureHandle(pid=4242, out=tmp_path / "s.jsonl"))

    assert terminator.calls == [(4242, signal.SIGKILL, 0.3)]


def test_is_running_asks_launchctl_then_the_pid(helper: Path, tmp_path: Path):
    handle = CaptureHandle(pid=4242, out=tmp_path / "s.jsonl")
    assert observer(helper, tmp_path, FakeLaunchctl({Launchd.SPEAKERS_LABEL: [RUNNING]})).is_running(handle) is True
    assert observer(helper, tmp_path, FakeLaunchctl({Launchd.SPEAKERS_LABEL: [EXITED_1]}), alive=lambda pid: True).is_running(handle) is False
    gone = FakeLaunchctl()   # not loaded: launchctl cannot say, so the pid does
    assert observer(helper, tmp_path, gone, alive=lambda pid: pid == 4242).is_running(handle) is True
    assert observer(helper, tmp_path, gone, alive=lambda pid: False).is_running(handle) is False


def test_ut072_problems_runs_the_check_as_its_own_job_and_reports_the_permission(helper: Path, tmp_path: Path):
    launchctl = FakeLaunchctl({Launchd.SPEAKERS_CHECK_LABEL: [EXITED_3]})
    obs = observer(helper, tmp_path, launchctl)

    [problem] = obs.problems()

    assert problem == Err.SPEAKERS_PROBLEM_PERMISSION.format(binary=helper)
    assert f"run `{helper} --check --prompt`" in problem and f"add it with the + button: {helper}" in problem
    assert "System Settings > Privacy & Security > Accessibility" in problem
    bootstrap = next(c for c in launchctl.calls if c[1] == "bootstrap")
    assert bootstrap[3].endswith("local.teams-recorder.speakers-check.plist")
    assert launchctl.subcommands()[-1] == "bootout" and not Path(bootstrap[3]).exists()      # short-lived: gone afterwards
    assert not any(c[-1].endswith("/" + Launchd.SPEAKERS_LABEL) for c in launchctl.calls)   # never the recording's job
    assert obs.check_job()["ProgramArguments"] == [str(helper), "--check"]


def test_problems_is_empty_when_the_check_passes(helper: Path, tmp_path: Path):
    assert observer(helper, tmp_path, FakeLaunchctl({Launchd.SPEAKERS_CHECK_LABEL: [RUNNING, EXITED_0]})).problems() == []


def test_problems_says_when_the_check_could_not_run(helper: Path, tmp_path: Path):
    [odd] = observer(helper, tmp_path, FakeLaunchctl({Launchd.SPEAKERS_CHECK_LABEL: [EXITED_1]})).problems()
    assert odd.startswith("the Accessibility permission could not be checked: it exited with code 1")
    [hung] = observer(helper, tmp_path, FakeLaunchctl({Launchd.SPEAKERS_CHECK_LABEL: [RUNNING]}), check_timeout=1.0).problems()
    assert hung == "the Accessibility permission could not be checked: it did not finish within 1 s"
    refused = FakeLaunchctl(fail={"bootstrap": 5})
    [bad] = observer(helper, tmp_path, refused).problems()
    assert "bootstrap failed (5)" in bad and refused.subcommands()[-1] == "bootout"


def test_parse_print_reads_pid_state_and_last_exit():
    assert parse_print(RUNNING) == JobState(pid=4242, state="running", last_exit=None) and parse_print(RUNNING).running
    assert parse_print(EXITED_3) == JobState(pid=None, state="not running", last_exit=3) and not parse_print(EXITED_3).running
    assert parse_print("") == JobState()


# --- review round 2: issue 003 (launchctl timeouts) and issue 041 (a job with no handle) -------------------------------

def test_every_launchctl_call_carries_a_timeout_and_a_print_a_short_one(helper: Path, tmp_path: Path):
    launchctl = FakeLaunchctl({Launchd.SPEAKERS_LABEL: [RUNNING], Launchd.SPEAKERS_CHECK_LABEL: [EXITED_0]})
    obs = observer(helper, tmp_path, launchctl)

    handle = obs.start(tmp_path / "s.jsonl", EPOCH)
    obs.is_running(handle)
    obs.problems()
    obs.stop(handle)
    obs.plist_path().parent.mkdir(parents=True, exist_ok=True)
    obs.plist_path().write_bytes(b"x")
    obs.stop_stale()

    assert launchctl.calls and all(t is not None and t > 0 for t in launchctl.timeouts)
    by_sub = {sub: {t for c, t in zip(launchctl.calls, launchctl.timeouts) if c[1] == sub} for sub in {c[1] for c in launchctl.calls}}
    assert by_sub["print"] == {Speakers.LAUNCHCTL_PRINT_TIMEOUT}
    assert by_sub["bootstrap"] == by_sub["bootout"] == {Speakers.LAUNCHCTL_TIMEOUT}
    assert Speakers.LAUNCHCTL_PRINT_TIMEOUT < Speakers.LAUNCHCTL_TIMEOUT


def test_a_print_that_times_out_is_a_job_that_is_not_running_and_never_raises(helper: Path, tmp_path: Path):
    launchctl = FakeLaunchctl(hang={"print"})
    handle = CaptureHandle(pid=4242, out=tmp_path / "s.jsonl")
    assert observer(helper, tmp_path, launchctl, alive=lambda pid: False).is_running(handle) is False   # the pid decides, as for any failed print
    assert observer(helper, tmp_path, launchctl, alive=lambda pid: True).is_running(handle) is True

    with pytest.raises(SpeakersUnavailable) as raised:       # the start sees no running job after the grace
        observer(helper, tmp_path, launchctl).start(tmp_path / "s.jsonl", EPOCH)
    assert raised.value.reason == SpeakerReason.START_FAILED
    [hung] = observer(helper, tmp_path, FakeLaunchctl(hang={"print"}), check_timeout=1.0).problems()
    assert hung == "the Accessibility permission could not be checked: it did not finish within 1 s"


def test_a_bootout_that_times_out_falls_back_to_the_pid(helper: Path, tmp_path: Path):
    terminator = Terminator()
    obs = observer(helper, tmp_path, FakeLaunchctl(hang={"bootout"}), alive=lambda pid: True, terminate=terminator)

    obs.stop(CaptureHandle(pid=4242, out=tmp_path / "s.jsonl"))

    assert terminator.calls == [(4242, signal.SIGTERM, obs.stop_timeout)]


def test_a_bootstrap_that_times_out_is_a_failed_start_not_a_hang(helper: Path, tmp_path: Path):
    launchctl = FakeLaunchctl(hang={"bootstrap"})
    with pytest.raises(SpeakersUnavailable) as raised:
        observer(helper, tmp_path, launchctl).start(tmp_path / "s.jsonl", EPOCH)
    assert raised.value.reason == SpeakerReason.START_FAILED and "did not answer within" in str(raised.value)


def test_stop_stale_boots_out_a_job_left_without_a_handle_and_removes_its_definition(helper: Path, tmp_path: Path):
    launchctl = FakeLaunchctl({Launchd.SPEAKERS_LABEL: [RUNNING]})
    terminator = Terminator()
    obs = observer(helper, tmp_path, launchctl, terminate=terminator)
    obs.plist_path().parent.mkdir(parents=True)
    obs.plist_path().write_bytes(b"x")   # the definition the interrupted start wrote before its bootstrap

    obs.stop_stale()

    assert launchctl.subcommands() == ["print", "bootout"] and launchctl.calls[1][2].endswith("/" + Launchd.SPEAKERS_LABEL)
    assert not obs.plist_path().exists() and terminator.calls == []


def test_stop_stale_stops_a_straggler_by_pid_and_survives_a_job_that_is_loaded_but_not_running(helper: Path, tmp_path: Path):
    terminator = Terminator()
    obs = observer(helper, tmp_path, FakeLaunchctl({Launchd.SPEAKERS_LABEL: [RUNNING]}), alive=lambda pid: True, terminate=terminator,
                   stop_timeout=0.3)
    obs.plist_path().parent.mkdir(parents=True)
    obs.plist_path().write_bytes(b"x")
    obs.stop_stale()
    assert terminator.calls == [(4242, signal.SIGKILL, 0.3)]

    scheduled = FakeLaunchctl({Launchd.SPEAKERS_LABEL: [SPAWN_SCHEDULED]})
    obs = observer(helper, tmp_path, scheduled)
    obs.plist_path().write_bytes(b"x")
    obs.stop_stale()
    assert scheduled.subcommands() == ["print", "bootout"] and not obs.plist_path().exists()


def test_stop_stale_asks_launchd_nothing_when_no_job_definition_exists(helper: Path, tmp_path: Path):
    launchctl = FakeLaunchctl({Launchd.SPEAKERS_LABEL: [RUNNING]})
    observer(helper, tmp_path, launchctl).stop_stale()
    assert launchctl.calls == []   # a job is bootstrapped from its definition, which only a stop removes: none, no job


def test_a_start_interrupted_after_the_bootstrap_is_cleaned_by_stop_stale(helper: Path, tmp_path: Path):
    """The whole sequence of issue 041 on the adapter: bootstrap done, handle never returned, the next process boots the job out."""
    launchctl = FakeLaunchctl({Launchd.SPEAKERS_LABEL: [RUNNING]})
    obs = observer(helper, tmp_path, launchctl)

    class Interrupted(Exception):
        pass

    def crash(label: str) -> None:
        raise Interrupted

    obs._watch = crash    # type: ignore[method-assign]   # the process dies inside the startup grace
    with pytest.raises(Interrupted):
        obs.start(tmp_path / "s.jsonl", EPOCH)
    assert obs.plist_path().exists() and "bootstrap" in launchctl.subcommands()

    after_restart = observer(helper, tmp_path, launchctl)   # a new process: no handle, same run dir
    launchctl.calls.clear()
    after_restart.stop_stale()

    assert launchctl.subcommands() == ["print", "bootout"] and not obs.plist_path().exists()
