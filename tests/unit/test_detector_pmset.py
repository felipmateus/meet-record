import subprocess
from pathlib import Path

from teams_recorder.adapters.outbound.detector_pmset import PmsetCallDetector, parse_assertions
from teams_recorder.application.ports import CallState

SAMPLE = (Path(__file__).resolve().parents[1] / "fixtures" / "pmset_assertions.txt").read_text()


def test_parse_finds_only_target_process_once():
    assert parse_assertions(SAMPLE, "MSTeams") == [51234]
    assert parse_assertions(SAMPLE, "caffeinate") == [4827]
    assert parse_assertions(SAMPLE, "WindowServer") == []  # UserIsActive não é asserção de chamada
    assert parse_assertions(SAMPLE, "Nada") == []
    assert parse_assertions("", "MSTeams") == []


def _runner(stdout: str, rc: int = 0):
    def run(cmd, **kw):
        assert cmd == ["pmset", "-g", "assertions"]
        return subprocess.CompletedProcess(cmd, rc, stdout=stdout, stderr="")
    return run


def test_poll_in_call_and_pid():
    d = PmsetCallDetector("MSTeams", runner=_runner(SAMPLE))
    assert d.poll() == CallState.IN_CALL
    assert d.teams_pid() == 51234


def test_poll_idle_falls_back_to_pgrep_for_pid(monkeypatch):
    d = PmsetCallDetector("MSTeams", runner=_runner("Listed by owning process:\n"))
    assert d.poll() == CallState.IDLE
    monkeypatch.setattr("teams_recorder.adapters.outbound.detector_pmset.find_pid", lambda name: 777)
    assert d.teams_pid() == 777


def test_poll_unknown_on_failure():
    assert PmsetCallDetector("MSTeams", runner=_runner("", rc=1)).poll() == CallState.UNKNOWN

    def boom(cmd, **kw):
        raise OSError("sem pmset")
    assert PmsetCallDetector("MSTeams", runner=boom).poll() == CallState.UNKNOWN
