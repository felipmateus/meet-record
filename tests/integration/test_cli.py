from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from teams_recorder.adapters.inbound.cli import app
from teams_recorder.adapters.outbound.launchd import AgentStatus
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.config import ENV_PROJECT_DIR
from teams_recorder.domain import Meeting
from teams_recorder.domain.status import AUDIO

runner = CliRunner()


def _project(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv(ENV_PROJECT_DIR, str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("status", "doctor", "purge", "start", "stop", "transcribe", "analyze", "plan"):
        assert cmd in result.output


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0 and "teams-recorder 0.1.0" in result.output


def test_status_shows_meetings_and_next_step(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0), title="Daily")
    repo.create(m)
    repo.path(m.id, AUDIO).write_bytes(b"\x00")

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert "Meetings: 1" in result.output
    assert "2026-10-06_14-00-00 Daily  [recorded] → next: transcribe" in result.output
    assert "API key: MISSING" in result.output
    assert "Open actions: 0" in result.output


def test_plan_requires_provider_prerequisites(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["plan"])
    assert result.exit_code == 1 and "ANTHROPIC_API_KEY" in result.output


def test_plan_invalid_date(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    result = runner.invoke(app, ["plan", "--date", "yesterday"])
    assert result.exit_code == 1 and "invalid date" in result.output


def test_plan_empty_day_writes_plan_without_calling_model(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    result = runner.invoke(app, ["plan", "--date", "2026-10-06", "--purge"])
    assert result.exit_code == 0, result.output
    assert "0 new actions" in result.output and "Audio files removed by retention: 0" in result.output
    assert (project / "data" / "plans" / "2026-10-06.md").read_text().startswith("# Plan 2026-10-06")


def test_daemon_once_reports_detector_state(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setenv("TREC_TEAMS_PROCESS", "ProcessThatDoesNotExist")
    result = runner.invoke(app, ["daemon", "--once"])
    assert result.exit_code == 0, result.output
    assert "detector (ProcessThatDoesNotExist): idle" in result.output


def test_agent_status_when_not_installed(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    # does not depend on the machine's real launchd (the agent may actually be installed)
    monkeypatch.setattr(
        "teams_recorder.adapters.inbound.cli.LaunchAgent.status",
        lambda self: AgentStatus(loaded=False, plist=self.plist_path, plist_exists=False, pid=None, state=None),
    )
    result = runner.invoke(app, ["agent", "status"])
    assert result.exit_code == 1 and "loaded: no" in result.output and "not scheduled" in result.output


def test_analyze_requires_api_key(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["analyze"])
    assert result.exit_code == 1 and "ANTHROPIC_API_KEY" in result.output


def test_analyze_nothing_pending(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    result = runner.invoke(app, ["analyze"])
    assert result.exit_code == 0 and "No meeting pending analysis" in result.output


def test_transcribe_nothing_pending(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["transcribe"])
    assert result.exit_code == 0 and "No meeting pending" in result.output


def test_transcribe_unknown_meeting(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["transcribe", "2026-01-01_00-00-00"])
    assert result.exit_code == 1 and "does not exist" in result.output


def test_transcribe_marks_failure_when_model_missing(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0))
    repo.create(m)
    repo.path(m.id, AUDIO).write_bytes(b"\x00" * 2048)

    result = runner.invoke(app, ["transcribe"])

    assert result.exit_code == 1
    assert "FAILED" in result.output and "model not found" in result.output
    assert (project / "data" / "recordings" / m.id / "error.txt").exists()


def test_stop_and_cancel_without_active_recording(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    for cmd in ("stop", "cancel"):
        result = runner.invoke(app, [cmd])
        assert result.exit_code == 1
        assert "no recording in progress" in result.output


def test_start_without_teams_running(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setattr("teams_recorder.adapters.inbound.cli.find_pid", lambda name: None)
    result = runner.invoke(app, ["start"])
    assert result.exit_code == 1
    assert "is not running" in result.output


def test_start_with_pid_but_missing_binary(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["start", "--pid", "1"])
    assert result.exit_code == 1
    assert "teams-tap binary not found" in result.output
    # nothing was left behind
    assert not (tmp_path / "data" / "current_recording.json").exists()
    assert list((tmp_path / "data" / "recordings").iterdir()) == []


def test_doctor_reports_missing_key(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output
    assert "ffmpeg" in result.output


def test_purge_runs(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["purge"])
    assert result.exit_code == 0 and "Audio files removed: 0" in result.output


def test_analyze_with_claude_code_provider_requires_binary(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setenv("TREC_LLM_PROVIDER", "claude-code")
    monkeypatch.setattr("teams_recorder.adapters.inbound.cli.shutil.which", lambda name: None)
    result = runner.invoke(app, ["analyze"])
    assert result.exit_code == 1 and "Claude Code" in result.output


def test_transcribe_retries_failed_meetings(tmp_path: Path, monkeypatch):
    """A meeting that failed transcription counts as pending (error.txt does not hide it)."""
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0))
    repo.create(m)
    repo.path(m.id, AUDIO).write_bytes(b"\x00" * 2048)
    repo.mark_failed(m.id, "transcription: previous failure")

    result = runner.invoke(app, ["transcribe"])

    assert "No meeting pending" not in result.output
    assert "Transcribing" in result.output
