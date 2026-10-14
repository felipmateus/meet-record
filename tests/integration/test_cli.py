import os
import sys
from datetime import date, datetime
from pathlib import Path

from typer.testing import CliRunner

from teams_recorder.adapters.inbound.cli import app
from teams_recorder.adapters.outbound.launchd import AgentStatus
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.config import ENV_PROJECT_DIR
from teams_recorder.constants import Files
from teams_recorder.adapters.outbound.planner_claude import ClaudePlanner
from teams_recorder.adapters.outbound.stories_claude import ClaudeStoryWriter
from teams_recorder.domain import Action, DailyPlan, Meeting, Publication, StoryDrafts, UserStory
from teams_recorder.domain.status import AUDIO
from teams_recorder.messages import Cli, Err, Notify

runner = CliRunner()


def _project(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv(ENV_PROJECT_DIR, str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("status", "doctor", "purge", "start", "stop", "transcribe", "analyze", "plan", "stories"):
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


def test_minutes_command(tmp_path: Path, monkeypatch):
    import json as _json
    from teams_recorder.adapters.outbound import codec
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    assert runner.invoke(app, ["minutes"]).output.strip() == "No analyzed meeting without minutes."
    m = Meeting.start(datetime(2026, 10, 6, 14, 0, 0))
    repo.create(m)
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "sample_analysis_v2.json"
    repo.save_analysis(m.id, codec.analysis_from_dict(_json.loads(fixture.read_text())))

    result = runner.invoke(app, ["minutes"])

    assert result.exit_code == 0, result.output
    minutes = project / "data" / "recordings" / m.id / "minutes.md"
    assert minutes.read_text().startswith("# Ata: Revisão da sprint de integração")
    assert runner.invoke(app, ["minutes"]).output.strip() == "No analyzed meeting without minutes."
    assert "minutes.md" in runner.invoke(app, ["minutes", "--all"]).output


def test_plan_with_stories_enabled_writes_empty_drafts_without_calling_model(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    (project / "config.toml").write_text('[stories]\nenabled = true\nguide = "guide.md"\n')
    (project / "guide.md").write_text("# Guia\n")
    result = runner.invoke(app, ["plan", "--date", "2026-10-06"])
    assert result.exit_code == 0, result.output
    assert "Drafting user stories for 2026-10-06…" + Cli.STORIES_OK.format(stories=0, tasks=0, skipped=0) in result.output
    drafts = (project / "data" / "plans" / "2026-10-06.stories.md").read_text()
    assert "Nenhuma ação nova no plano deste dia." in drafts


def test_stories_without_a_plan_fails(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    result = runner.invoke(app, ["stories", "--date", "2026-10-06"])
    assert result.exit_code == 1 and "no plan for 2026-10-06" in result.output


def test_plan_refuses_to_redraft_a_published_day_but_keeps_the_plan(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    notified: list[tuple[str, str]] = []
    monkeypatch.setattr("teams_recorder.adapters.outbound.notifier_macos.MacOSNotifier.notify", lambda self, t, b: notified.append((t, b)))
    (project / "config.toml").write_text('[stories]\nenabled = true\nguide = "guide.md"\n')
    (project / "guide.md").write_text("# Guia\n")
    published = UserStory("Exportar horas", "n", publications=[Publication("backlog-md", "TASK-1", datetime(2026, 10, 6, 18, 0))])
    FsMeetingRepository(project / "data").save_story_drafts(StoryDrafts(date(2026, 10, 6), [published]), "# published\n")

    result = runner.invoke(app, ["plan", "--date", "2026-10-06"])

    assert result.exit_code == 1
    assert Err.STORIES_ALREADY_PUBLISHED.format(day="2026-10-06") in result.output
    assert (project / "data" / "plans" / "2026-10-06.md").exists()
    assert (project / "data" / "plans" / "2026-10-06.stories.md").read_text() == "# published\n"
    assert notified[-1][0] == Notify.STORIES_FAILED


def test_unknown_story_destination_stops_the_command(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    (project / "config.toml").write_text('[stories]\ndestinations = ["trello"]\n')
    result = runner.invoke(app, ["plan", "--date", "2026-10-06"])
    message = Err.INVALID_DESTINATION.format(value="trello", options=("backlog-md",))
    assert result.exit_code != 0 and str(result.exception) == message
    assert not (project / "data" / "plans" / "2026-10-06.md").exists()



FAKE_BACKLOG = Path(__file__).resolve().parents[1] / "fixtures" / "fake_backlog_cli.py"
BOARD_CONFIG = 'statuses: ["Triagem", "To Do", "In Progress", "Done"]\nauto_commit: false\nremote_operations: false\n'
DAY = date(2026, 10, 9)


def _board_project(tmp_path: Path, monkeypatch, *, publish: bool = False, board: str = BOARD_CONFIG, dedup_days: int = 30) -> Path:
    """A project publishing to a Backlog.md board in its own folder, through the scripted `backlog` on PATH."""
    project = _project(tmp_path, monkeypatch)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "backlog").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE_BACKLOG}" "$@"\n')
    (bin_dir / "backlog").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_BACKLOG_LOG", str(tmp_path / "backlog-calls.jsonl"))
    monkeypatch.setattr("teams_recorder.adapters.outbound.notifier_macos.MacOSNotifier.notify", lambda self, t, b: None)
    (project / "backlog").mkdir()
    (project / "backlog" / "config.yml").write_text(board)
    (project / "guide.md").write_text("# Guia\n")
    (project / "config.toml").write_text(
        f'[stories]\nenabled = true\nguide = "guide.md"\ndestinations = ["backlog-md"]\npublish = {str(publish).lower()}\n'
        f'dedup_days = {dedup_days}\n[stories.backlog_md]\nproject_dir = "."\n'
    )
    return project


def _drafts(project: Path, *titles: str, day: date = DAY, plan: bool = True) -> FsMeetingRepository:
    fs = FsMeetingRepository(project / "data")
    if plan:
        fs.save_plan(DailyPlan(day, "# plano\n", new_actions=[Action("Exportar horas", "usuário", "m1", id="a1")]))
    fs.save_story_drafts(StoryDrafts(day, [UserStory(t, "Como gestor, quero isso", source_action_ids=["a1"]) for t in titles]), "#\n")
    return fs


def _backlog_calls(tmp_path: Path) -> int:
    log = tmp_path / "backlog-calls.jsonl"
    return len(log.read_text().splitlines()) if log.exists() else 0


def _published(title: str, ref: str) -> str:
    return Cli.PUBLISHED_LINE.format(title=title, destination="backlog-md", ref=ref)


def test_publish_needs_destinations(tmp_path: Path, monkeypatch):
    _project(tmp_path, monkeypatch)
    result = runner.invoke(app, ["publish", "--date", "2026-10-09"])
    assert result.exit_code == 1 and Cli.NO_DESTINATIONS in result.output


def test_publish_needs_drafts_and_notifies_the_error(tmp_path: Path, monkeypatch):
    _board_project(tmp_path, monkeypatch)
    notified: list[tuple[str, str]] = []
    monkeypatch.setattr("teams_recorder.adapters.outbound.notifier_macos.LogNotifier.notify", lambda self, t, b: notified.append((t, b)))
    result = runner.invoke(app, ["publish", "--date", "2026-10-09"])
    assert result.exit_code == 1 and Err.STORIES_MISSING.format(day="2026-10-09") in result.output
    assert notified == [(Notify.PUBLISH_FAILED, Notify.PUBLISH_ERROR_BODY.format(day="2026-10-09", error=Err.STORIES_MISSING.format(day="2026-10-09")))]


def test_publish_sends_each_story_once(tmp_path: Path, monkeypatch):
    project = _board_project(tmp_path, monkeypatch)
    fs = _drafts(project, "Exportar horas", "Validar filtros")

    first = runner.invoke(app, ["publish", "--date", "2026-10-09"])

    assert first.exit_code == 0, first.output
    assert _published("Exportar horas", "TASK-1") in first.output and _published("Validar filtros", "TASK-2") in first.output
    assert [s.publication("backlog-md").ref for s in fs.load_story_drafts(DAY).stories] == ["TASK-1", "TASK-2"]

    again = runner.invoke(app, ["publish", "--date", "2026-10-09"])

    assert again.exit_code == 0 and Cli.ALREADY_PUBLISHED.format(count=2) in again.output
    assert _backlog_calls(tmp_path) == 2


def test_publish_only_selected_stories(tmp_path: Path, monkeypatch):
    project = _board_project(tmp_path, monkeypatch)
    _drafts(project, "Um", "Dois")
    result = runner.invoke(app, ["publish", "--date", "2026-10-09", "--only", "2"])
    assert result.exit_code == 0 and _published("Dois", "TASK-1") in result.output and _backlog_calls(tmp_path) == 1
    bad = runner.invoke(app, ["publish", "--date", "2026-10-09", "--only", "x"])
    assert bad.exit_code == 1 and Cli.INVALID_ONLY.format(value="x") in bad.output


def test_publish_failure_exits_1(tmp_path: Path, monkeypatch):
    project = _board_project(tmp_path, monkeypatch)
    _drafts(project, "Um")
    monkeypatch.setenv("FAKE_BACKLOG_MODE", "fail")
    result = runner.invoke(app, ["publish", "--date", "2026-10-09"])
    assert result.exit_code == 1
    assert Cli.PUBLISH_FAILURE_LINE.format(title="Um", destination="backlog-md", error="").rstrip() in result.output


def _plan_with_one_story(monkeypatch):
    monkeypatch.setattr(ClaudePlanner, "plan", lambda self, day, analyses, previous, open_actions: DailyPlan(
        day, "# plano\n", new_actions=[Action("Exportar horas", "usuário", "m1", id="a1")]))
    monkeypatch.setattr(ClaudeStoryWriter, "draft", lambda self, day, actions, analyses, existing: StoryDrafts(
        day, [UserStory("Exportar horas", "Como gestor, quero isso", source_action_ids=[a.id for a in actions])]))


def test_plan_drafts_and_publishes(tmp_path: Path, monkeypatch):
    _board_project(tmp_path, monkeypatch, publish=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _plan_with_one_story(monkeypatch)

    result = runner.invoke(app, ["plan", "--date", "2026-10-09", "--purge"])

    assert result.exit_code == 0, result.output
    assert _published("Exportar horas", "TASK-1") in result.output
    assert Cli.PURGED_RETENTION.format(count=0) in result.output


def test_plan_keeps_the_plan_and_purges_when_publishing_fails(tmp_path: Path, monkeypatch):
    project = _board_project(tmp_path, monkeypatch, publish=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("FAKE_BACKLOG_MODE", "fail")
    _plan_with_one_story(monkeypatch)

    result = runner.invoke(app, ["plan", "--date", "2026-10-09", "--purge"])

    assert result.exit_code == 1
    assert Cli.PURGED_RETENTION.format(count=0) in result.output                  # the purge still ran
    assert (project / "data" / "plans" / "2026-10-09.md").exists()
    assert FsMeetingRepository(project / "data").load_story_drafts(DAY).stories[0].publications == []


def test_stories_publish_right_after_drafting(tmp_path: Path, monkeypatch):
    project = _board_project(tmp_path, monkeypatch, publish=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _plan_with_one_story(monkeypatch)
    _drafts(project)   # the plan with one new action; no stories yet

    result = runner.invoke(app, ["stories", "--date", "2026-10-09"])

    assert result.exit_code == 0, result.output
    assert _published("Exportar horas", "TASK-1") in result.output


def test_plan_on_an_empty_day_publishes_nothing(tmp_path: Path, monkeypatch):
    _board_project(tmp_path, monkeypatch, publish=True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    result = runner.invoke(app, ["plan", "--date", "2026-10-06"])
    assert result.exit_code == 0, result.output
    assert Cli.NOTHING_TO_PUBLISH in result.output and _backlog_calls(tmp_path) == 0


def test_doctor_lists_the_destination_and_its_problems(tmp_path: Path, monkeypatch):
    project = _board_project(tmp_path, monkeypatch, publish=True, board=BOARD_CONFIG.replace('"Triagem", ', ""))
    result = runner.invoke(app, ["doctor"])
    line = Cli.DESTINATION_LINE.format(mark=Cli.MISSING_MARK, destination="backlog-md", state=Cli.DESTINATION_NOT_READY)
    problem = Err.BACKLOG_STATUS_MISSING.format(status="Triagem", config=project.resolve() / "backlog" / "config.yml")
    assert line in result.output and Cli.DESTINATION_PROBLEM.format(problem=problem) in result.output


def test_status_counts_the_stories_waiting_in_the_window(tmp_path: Path, monkeypatch):
    project = _board_project(tmp_path, monkeypatch, dedup_days=2)
    monkeypatch.setattr("teams_recorder.adapters.outbound.clock.SystemClock.now", lambda self: datetime(2026, 10, 10, 9, 0))
    fs = _drafts(project, "Hoje", day=date(2026, 10, 10))
    _drafts(project, "Ontem", day=date(2026, 10, 9))
    _drafts(project, "Fora da janela", day=date(2026, 10, 8))
    published = UserStory("Publicada", "n", publications=[Publication("backlog-md", "TASK-9", datetime(2026, 10, 10, 8, 0))])
    fs.save_story_drafts(StoryDrafts(date(2026, 10, 10), [*fs.load_story_drafts(date(2026, 10, 10)).stories, published]), "#\n")

    result = runner.invoke(app, ["status"])

    assert Cli.STORIES_WAITING.format(count=2) in result.output        # today and yesterday, not the published one


# --- transcript health -------------------------------------------------------------------------
def _with_transcribers(monkeypatch, first, retry=None):
    """`trec` with fake transcribers in the container it builds (everything else as configured)."""
    from dataclasses import replace
    from teams_recorder.adapters.inbound import cli
    build = cli.build_container
    monkeypatch.setattr(cli, "build_container", lambda settings, **kw: replace(build(settings, **kw), transcriber=first, retry_transcriber=retry))


def test_transcribe_reports_health_and_a_degraded_transcript(tmp_path: Path, monkeypatch):
    from tests.fakes import FakeTranscriber, looped_transcript
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    m = Meeting.start(datetime(2026, 10, 8, 10, 30, 52)); repo.create(m)
    repo.path(m.id, AUDIO).write_bytes(b"\x00")
    _with_transcribers(monkeypatch, FakeTranscriber(looped_transcript(minutes=20, loop_minutes=15)), FakeTranscriber(looped_transcript(minutes=20, loop_minutes=16)))

    result = runner.invoke(app, ["transcribe", m.id])

    assert result.exit_code == 0, result.output
    health = repo.load_transcript(m.id).health
    assert health is not None and health.degraded and health.retried
    assert Cli.TRANSCRIPT_HEALTH.format(loop=health.loop_share, covered=5, total=20, retried=Cli.RETRIED) in result.output
    assert Cli.TRANSCRIPT_DEGRADED.format(gaps=Cli.NO_TEXT_IN.format(ranges="00:00:00–00:15:00")) in result.output


def test_status_marks_and_counts_degraded_transcripts(tmp_path: Path, monkeypatch):
    from teams_recorder.domain import Segment, Transcript, TranscriptHealth
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    for minute, health in ((0, TranscriptHealth(0.668, 28, 86, True, ((0, 14),))), (10, TranscriptHealth(0.0, 30, 30, False)), (20, None)):
        m = Meeting.start(datetime(2026, 10, 8, 10, minute, 0)); repo.create(m)
        repo.save_transcript(m.id, Transcript([Segment(0, 1, "oi")], "pt", health))

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert "2026-10-08_10-00-00  [transcribed] → next: analyze" + Cli.MEETING_DEGRADED.format(loop=0.668) in result.output
    assert "2026-10-08_10-10-00  [transcribed] → next: analyze\n" in result.output   # healthy, and old (no health): no marker
    assert Cli.DEGRADED_TRANSCRIPTS.format(count=1) in result.output
    assert "wrong sample rate" not in result.output   # no rate-mismatch line while none is flagged


def test_doctor_shows_the_loop_guard(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    vad = project / "data" / "models" / "ggml-silero-v5.1.2.bin"

    missing = runner.invoke(app, ["doctor"]).output

    assert Cli.TRANSCRIPTION_LINE.format(mark=Cli.INFO, max_context=0, share=0.10) in missing
    assert Cli.RETRY_LINE.format(mark=Cli.WARNING, state=Cli.RETRY_SAME, hint=Cli.RETRY_VAD_MISSING.format(
        path=vad, script="scripts/download-model.sh", model="silero-v5.1.2")) in missing
    vad.parent.mkdir(parents=True); vad.write_bytes(b"\x00")
    assert Cli.RETRY_LINE.format(mark=Cli.OK, state=Cli.RETRY_ON_VAD.format(path=vad), hint="") in runner.invoke(app, ["doctor"]).output
    (project / "config.toml").write_text("[transcription]\nretry_on_loop = false\n")
    assert Cli.RETRY_LINE.format(mark=Cli.INFO, state=Cli.RETRY_OFF, hint="") in runner.invoke(app, ["doctor"]).output


def test_a_damaged_transcript_is_reported_not_a_traceback(tmp_path: Path, monkeypatch):
    import json as _json
    from teams_recorder.adapters.outbound import codec
    from teams_recorder.domain import Segment, Transcript, TranscriptHealth
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    m = Meeting.start(datetime(2026, 10, 8, 10, 30, 52)); repo.create(m)
    repo.save_transcript(m.id, Transcript([Segment(0, 1, "oi")], "pt", TranscriptHealth(0.7, 1, 2, True)))
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "sample_analysis_v2.json"
    repo.save_analysis(m.id, codec.analysis_from_dict(_json.loads(fixture.read_text())))
    path = repo.path(m.id, "transcript.json")
    path.write_text(path.read_text().replace('"covered_minutes"', '"covered"'))

    status = runner.invoke(app, ["status"])
    minutes = runner.invoke(app, ["minutes", m.id])

    assert status.exit_code == 0 and Cli.DEGRADED_TRANSCRIPTS.format(count=0) in status.output
    assert minutes.exit_code == 1 and isinstance(minutes.exception, SystemExit)   # a clean error, not a KeyError traceback
    assert "invalid JSON in" in minutes.output and "covered_minutes" in minutes.output


def test_status_reports_a_damaged_file_instead_of_a_traceback(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    plans = project / "data" / "plans"
    plans.mkdir(parents=True)
    (plans / Files.OPEN_ACTIONS).write_text('[{"description": "sem id"}]')

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert "Open actions: unreadable (invalid JSON in" in result.output and Files.OPEN_ACTIONS in result.output
    assert "Meetings: 0" in result.output   # the rest of the status is still shown


def test_status_shows_a_damaged_meeting_on_its_own_line(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    broken, fine = Meeting.start(datetime(2026, 10, 12, 9, 0, 0)), Meeting.start(datetime(2026, 10, 12, 10, 0, 0), title="Daily")
    repo.create(broken); repo.create(fine)
    repo.path(broken.id, "meta.json").write_text('{"id": "%s"}' % broken.id)   # no started_at

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert f"  {broken.id}  [unreadable: invalid JSON in" in result.output
    assert f"{fine.id} Daily  [recording]" in result.output and "Open actions: 0" in result.output


def test_transcribe_and_status_mark_a_teams_track_recorded_at_the_wrong_rate(tmp_path: Path, monkeypatch):
    import json
    from teams_recorder.domain.status import TAP_STATS
    from tests.fakes import FakeTranscriber, speech_transcript
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    m = Meeting.start(datetime(2026, 10, 14, 15, 38, 49)); repo.create(m)
    repo.path(m.id, AUDIO).write_bytes(b"\x00")
    repo.path(m.id, TAP_STATS).write_text(json.dumps({"written_seconds": 709.9, "padded_seconds": 474.9, "short_padded_seconds": 474.9, "gaps": 0}))
    _with_transcribers(monkeypatch, FakeTranscriber(speech_transcript(minutes=12)))

    result = runner.invoke(app, ["transcribe", m.id])

    assert result.exit_code == 0, result.output
    health = repo.load_transcript(m.id).health
    assert health is not None and health.rate_mismatch and not health.degraded
    assert Cli.TRANSCRIPT_RATE_MISMATCH.format(share=health.short_padding_share) in result.output
    status = runner.invoke(app, ["status"])
    assert "2026-10-14_15-38-49  [transcribed] → next: analyze" + Cli.MEETING_RATE_MISMATCH.format(share=health.short_padding_share) in status.output
    assert Cli.RATE_MISMATCH_TRANSCRIPTS.format(count=1) in status.output and Cli.DEGRADED_TRANSCRIPTS.format(count=0) in status.output
