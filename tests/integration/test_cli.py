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
from teams_recorder.domain import Meeting, Publication, StoryDrafts, UserStory
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
    for cmd in ("status", "doctor", "purge", "start", "stop", "transcribe", "analyze", "stories"):
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
    assert Cli.ACTIVITIES_STATUS_NONE in result.output and "Open actions" not in result.output


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
    assert result.exit_code == 1 and "loaded: no" in result.output and "planner" not in result.output


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


def test_unknown_story_destination_stops_the_command(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    (project / "config.toml").write_text('[stories]\ndestinations = ["trello"]\n')
    result = runner.invoke(app, ["stories"])
    message = Err.INVALID_DESTINATION.format(value="trello", options=("backlog-md",))
    assert result.exit_code != 0 and str(result.exception) == message



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
        f'[stories]\nguide = "guide.md"\ndestinations = ["backlog-md"]\npublish = {str(publish).lower()}\n'
        f'dedup_days = {dedup_days}\n[stories.backlog_md]\nproject_dir = "."\n'
    )
    return project


def _drafts(project: Path, *titles: str, day: date = DAY) -> FsMeetingRepository:
    """Drafts on disk and no plan file: publishing and `trec status` need none."""
    fs = FsMeetingRepository(project / "data")
    fs.save_story_drafts(StoryDrafts(day, [UserStory(t, "Como gestor, quero isso", source_text=f"- [ ] {t} #história") for t in titles]), "#\n")
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
    log = project / "data" / Files.LOG_DIR / Files.ACTIVITIES_LOG
    log.parent.mkdir(parents=True)
    log.write_text("not json\n{}\n")

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert "Activities: unreadable (invalid JSON in" in result.output and Files.ACTIVITIES_LOG in result.output
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
    assert f"{fine.id} Daily  [recording]" in result.output and Cli.ACTIVITIES_STATUS_NONE in result.output


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


def test_doctor_shows_the_claim_verifier(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    monkeypatch.delenv("TREC_LLM_PROVIDER", raising=False)
    on = Cli.VERIFICATION_ON.format(model="claude-sonnet-5-5", provider="api", effort="medium")

    no_prompt = runner.invoke(app, ["doctor"]).output   # a bare project has no prompts/ folder

    prompt = project / "prompts" / Files.VERIFY_PROMPT
    assert Cli.VERIFICATION_LINE.format(mark=Cli.WARNING, state=Cli.VERIFICATION_NO_PROMPT.format(state=on, path=prompt)) in no_prompt
    prompt.parent.mkdir(); prompt.write_text("x")
    (project / "config.toml").write_text('[llm]\nprovider = "claude-code"\n')
    on_cli = Cli.VERIFICATION_ON.format(model="sonnet", provider="claude-code", effort="medium")
    assert Cli.VERIFICATION_LINE.format(mark=Cli.OK, state=on_cli) in runner.invoke(app, ["doctor"]).output
    (project / "config.toml").write_text("[verification]\nenabled = false\n")
    assert Cli.VERIFICATION_LINE.format(mark=Cli.INFO, state=Cli.VERIFICATION_OFF) in runner.invoke(app, ["doctor"]).output


def test_status_counts_unconfirmed_claims(tmp_path: Path, monkeypatch):
    from teams_recorder.domain import Analysis, Decision, Verification, VerificationStatus
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    no = Verification(VerificationStatus.UNCONFIRMED, "ninguém disse isso")
    yes = Verification(VerificationStatus.CONFIRMED, "dito")
    for minute, decisions in ((0, [Decision("A", verification=no), Decision("B", verification=no)]),
                              (10, [Decision("C", verification=yes)]), (20, [Decision("D")])):
        m = Meeting.start(datetime(2026, 10, 15, 9, minute, 0)); repo.create(m)
        repo.save_analysis(m.id, Analysis(meeting_id=m.id, summary="s", decisions=decisions))

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert "2026-10-15_09-00-00  [analyzed]" + Cli.MEETING_UNCONFIRMED.format(count=2) in result.output
    assert "2026-10-15_09-10-00  [analyzed]\n" in result.output and "2026-10-15_09-20-00  [analyzed]\n" in result.output
    assert Cli.UNCONFIRMED_CLAIMS.format(claims=2, meetings=1) in result.output


# --- speaker labels ----------------------------------------------------------------------------------------------------
SPEAKERS_BINARY = "native/teams-speakers/.build/release/teams-speakers"


def _speaker_stand_in(project: Path, monkeypatch, trusted: bool) -> list:
    """The helper at its project path is the stand-in; the observer `trec doctor` builds runs it through a fake launchctl
    (never the real one). Returns the launchctl calls."""
    from teams_recorder.adapters.inbound import cli
    from teams_recorder.adapters.outbound.speakers_ax import AxSpeakerObserver
    from teams_recorder.container import teams_speakers_binary
    from tests.integration.test_speakers_observer import STAND_IN, ProcessLaunchctl
    binary = teams_speakers_binary(project)
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{STAND_IN}" "$@"\n')
    binary.chmod(0o755)
    monkeypatch.setenv("FAKE_SPEAKERS_TRUSTED", "1" if trusted else "0")
    launchctl = ProcessLaunchctl()
    monkeypatch.setattr(cli, "build_speaker_observer", lambda settings: AxSpeakerObserver(binary, project / "data" / "run", runner=launchctl))
    return launchctl.calls


def test_it005_doctor_reports_the_helper_and_the_exit_code_is_the_features_own_absence(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    (project / "config.toml").write_text("[speakers]\nenabled = false\n")
    without = runner.invoke(app, ["doctor"])
    assert "speaker labels: off" in without.output
    (project / "config.toml").unlink()

    calls = _speaker_stand_in(project, monkeypatch, trusted=True)
    granted = runner.invoke(app, ["doctor"])
    assert f"[ok ] speaker labels: teams-speakers at {SPEAKERS_BINARY}; Accessibility permission granted\n" in granted.output
    assert [c[1] for c in calls].count("bootstrap") == 1   # the check ran once

    _speaker_stand_in(project, monkeypatch, trusted=False)
    missing = runner.invoke(app, ["doctor"])
    assert (f"[info] speaker labels: teams-speakers at {SPEAKERS_BINARY}; Accessibility permission missing → run `{SPEAKERS_BINARY} --check --prompt`"
            in missing.output)
    assert str(project) not in missing.output.split("speaker labels:")[1].split("\n")[0]
    assert granted.exit_code == missing.exit_code == without.exit_code == 1   # a bare project fails the doctor on its own; the feature changes nothing


def test_it005_doctor_with_everything_else_ready_still_exits_0_with_the_helper_missing_its_permission(tmp_path: Path, monkeypatch):
    project = _project(tmp_path, monkeypatch)
    monkeypatch.setenv("TREC_LLM_PROVIDER", "claude-code")
    monkeypatch.setattr("teams_recorder.adapters.inbound.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("teams_recorder.adapters.inbound.cli._tool_path", lambda name, project_dir: f"/usr/bin/{name}")
    monkeypatch.setattr("teams_recorder.adapters.inbound.cli._teams_tap_path", lambda settings: "/usr/bin/teams-tap")
    model = project / "data" / "models" / "ggml-large-v3-turbo-q5_0.bin"
    model.parent.mkdir(parents=True); model.write_bytes(b"\x00")
    guide = project / "prompts" / "user_story_guide.md"
    guide.parent.mkdir(); guide.write_text("x")
    _speaker_stand_in(project, monkeypatch, trusted=False)

    result = runner.invoke(app, ["doctor"])

    assert "[info] speaker labels:" in result.output
    assert result.exit_code == 0, result.output


def _transcribed_with(project: Path, minute: int, labels, speakers=()):
    from teams_recorder.domain import Segment, Transcript
    repo = FsMeetingRepository(project / "data")
    m = Meeting.start(datetime(2026, 10, 17, 9, minute, 0), title=f"M{minute}"); repo.create(m)
    segments = [Segment(float(i), i + 1.0, "oi", name) for i, name in enumerate(speakers)] or [Segment(0, 1, "oi")]
    repo.save_transcript(m.id, Transcript(segments, "pt", labels=labels))
    return m


def test_status_shows_the_labelled_share_per_meeting(tmp_path: Path, monkeypatch):
    from teams_recorder.domain import LabelSummary
    project = _project(tmp_path, monkeypatch)
    _transcribed_with(project, 0, LabelSummary(167, 214, None), ("Felipe",))
    _transcribed_with(project, 10, LabelSummary(0, 214, "no-window"))
    _transcribed_with(project, 20, LabelSummary(0, 214, "no-observer"))   # feature off, Windows, no observer data: no segment
    _transcribed_with(project, 30, None)                                   # made before the feature: no segment

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0, result.output
    assert "2026-10-17_09-00-00 M0  [transcribed] → next: analyze  · speakers 78%\n" in result.output
    assert "2026-10-17_09-10-00 M10  [transcribed] → next: analyze  · speakers 0% (no Teams meeting window was read during the call)\n" in result.output
    assert "2026-10-17_09-20-00 M20  [transcribed] → next: analyze\n" in result.output
    assert "2026-10-17_09-30-00 M30  [transcribed] → next: analyze\n" in result.output


def test_status_puts_the_speakers_segment_before_the_health_markers(tmp_path: Path, monkeypatch):
    from teams_recorder.domain import LabelSummary, Segment, Transcript, TranscriptHealth
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    m = Meeting.start(datetime(2026, 10, 8, 10, 0, 0)); repo.create(m)
    repo.save_transcript(m.id, Transcript([Segment(0, 1, "oi")], "pt", TranscriptHealth(0.668, 28, 86, True, ((0, 14),)), labels=LabelSummary(5, 10, None)))

    result = runner.invoke(app, ["status"])

    assert "[transcribed] → next: analyze  · speakers 50%" + Cli.MEETING_DEGRADED.format(loop=0.668) in result.output


def test_transcribe_prints_the_speakers_line_after_the_language_line(tmp_path: Path, monkeypatch):
    from teams_recorder.domain import Segment, Transcript
    from tests.fakes import FakeTranscriber
    project = _project(tmp_path, monkeypatch)
    repo = FsMeetingRepository(project / "data")
    m = Meeting.start(datetime(2026, 10, 17, 9, 30, 12)); repo.create(m)
    repo.path(m.id, AUDIO).write_bytes(b"\x00")
    _with_transcribers(monkeypatch, FakeTranscriber(Transcript([Segment(0, 10, "primeira fala " * 5), Segment(10, 20, "segunda fala " * 5)], "pt")))

    result = runner.invoke(app, ["transcribe", m.id])

    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    health = next(i for i, line in enumerate(lines) if line.startswith("  Health:"))
    assert lines[health + 1].startswith("  Language: ")   # the language line sits between the health block and the speakers line
    assert lines[health + 2] == "  Speakers: no labels (no observer data for this meeting)"   # no speakers.jsonl in this meeting
    assert lines[health + 3].startswith("  Text: ")


def test_start_prints_the_observer_line(tmp_path: Path, monkeypatch):
    from dataclasses import replace
    from teams_recorder.adapters.inbound import cli
    from tests.fakes import FakeMicCapture, FakeNotifier, FakeProcessCapture, FakeSpeakerObserver
    project = _project(tmp_path, monkeypatch)
    build = cli.build_container

    def with_observer(observer):
        monkeypatch.setattr(cli, "build_container", lambda settings, **kw: replace(
            build(settings, **kw), process_capture=FakeProcessCapture(), mic_capture=FakeMicCapture(), notifier=FakeNotifier(), speakers=observer))

    with_observer(FakeSpeakerObserver())
    started = runner.invoke(app, ["start", "--pid", "1"])
    assert started.exit_code == 0, started.output
    meeting_id = next(line for line in started.output.splitlines() if line.startswith("Recording meeting")).split()[2]
    assert f"  Speakers:    {project}/data/recordings/{meeting_id}/speakers.jsonl  (observer PID " in started.output
    assert started.output.index("  Microphone:") < started.output.index("  Speakers:") < started.output.index("Stop with")
    runner.invoke(app, ["cancel"])

    for reason, text in (("permission-missing", "not running (Accessibility permission missing; see trec doctor)"),
                         ("binary-missing", "not running (teams-speakers not built; see trec doctor)"),
                         ("start-failed", "not running (it failed to start; see data/log/speakers.log)")):
        with_observer(FakeSpeakerObserver(reason=reason))
        result = runner.invoke(app, ["start", "--pid", "1"])
        assert result.exit_code == 0, result.output
        assert f"  Speakers:    {text}\n" in result.output
        runner.invoke(app, ["cancel"])

    with_observer(None)   # [speakers] enabled = false (or Windows): no observer, no line
    result = runner.invoke(app, ["start", "--pid", "1"])
    assert result.exit_code == 0 and "Speakers:" not in result.output
    runner.invoke(app, ["cancel"])


# --- language detection (docs/tasks/language-detection/_tests.md E2E-001, E2E-002) ---------------------------------------------
def _recorded_at(repo: FsMeetingRepository, when: datetime, minutes: float | None = None) -> Meeting:
    from datetime import timedelta
    m = Meeting.start(when)
    if minutes is not None:
        m.ended_at = m.started_at + timedelta(minutes=minutes)
    repo.create(m)
    return m


def test_e2e001_an_english_meeting_is_transcribed_in_english_and_marked_in_status(tmp_path: Path, monkeypatch):
    import json
    import shutil
    import subprocess

    import pytest
    from tests.integration.test_transcriber_whispercpp import ScriptedLanguageDetector, ScriptedTranscriber
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    project = _project(tmp_path, monkeypatch)
    (project / "config.toml").write_text('[transcription]\nlanguage = "auto"\n')
    repo = FsMeetingRepository(project / "data")
    m = _recorded_at(repo, datetime(2026, 10, 23, 14, 0, 5), minutes=3)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=180", "-c:a", "aac",
                    str(repo.path(m.id, AUDIO))], check=True)
    model, detect_log, transcribe_log = project / "ggml-fake.bin", project / "detect.log", project / "transcribe.log"
    model.write_bytes(b"\x00" * 16)
    detector = ScriptedLanguageDetector(model, script=("--langs", "en:0.99,en:0.98,en:0.97", "--log", str(detect_log)))
    transcriber = ScriptedTranscriber(model, script=("--log", str(transcribe_log)))
    _with_container(monkeypatch, transcriber=transcriber, retry_transcriber=None, language_detector=detector)

    transcribed = runner.invoke(app, ["transcribe", m.id])

    assert transcribed.exit_code == 0, transcribed.output
    assert "  Language: en (heard in 3 of 3 counted samples; 3 taken)\n" in transcribed.output
    stored = json.loads(repo.path(m.id, "transcript.json").read_text(encoding="utf-8"))
    assert stored["language"] == "en" and stored["language_detection"]["reason"] == "majority"
    assert len(detect_log.read_text(encoding="utf-8").splitlines()) == 1   # one detection call: the scripted detector ran
    (call,) = [json.loads(line) for line in transcribe_log.read_text(encoding="utf-8").splitlines()]
    assert call[call.index("-l") + 1] == "en"   # whisper was asked for English

    status = runner.invoke(app, ["status"])

    assert status.exit_code == 0, status.output
    line = next(line for line in status.output.splitlines() if line.startswith(f"  {m.id}"))
    assert line.endswith("  · en")


def _with_container(monkeypatch, **fields):
    from dataclasses import replace
    from teams_recorder.adapters.inbound import cli
    build = cli.build_container
    monkeypatch.setattr(cli, "build_container", lambda settings, **kw: replace(build(settings, **kw), **fields))


def test_e2e002_each_meeting_gets_its_own_language_line_in_place_with_one_of_them_degraded(tmp_path: Path, monkeypatch):
    from tests.fakes import FakeLanguageDetector, FakeTranscriber, looped_transcript, speech_transcript
    project = _project(tmp_path, monkeypatch)
    (project / "config.toml").write_text('[transcription]\nlanguage = "auto"\nretry_on_loop = false\n')
    repo = FsMeetingRepository(project / "data")
    a, b = _recorded_at(repo, datetime(2026, 10, 23, 9, 0, 0), minutes=20), _recorded_at(repo, datetime(2026, 10, 23, 10, 0, 0), minutes=20)
    for m in (a, b):
        repo.path(m.id, AUDIO).write_bytes(b"\x00")
    detector = FakeLanguageDetector({repo.path(a.id, AUDIO): ["en"] * 3, repo.path(b.id, AUDIO): ["pt"] * 3})
    transcriber = FakeTranscriber(speech_transcript(minutes=20), by_audio={repo.path(b.id, AUDIO): looped_transcript(minutes=20, loop_minutes=15)})
    _with_container(monkeypatch, transcriber=transcriber, retry_transcriber=None, language_detector=detector)

    result = runner.invoke(app, ["transcribe"])

    assert result.exit_code == 0, result.output
    assert result.output.count("  Language:") == 2
    block_a, block_b = (result.output.split(f"Transcribing {m.id}")[1].split("Transcribing")[0].splitlines() for m in (a, b))
    labels = lambda block: [line.split(":")[0].strip() for line in block if line.startswith("  ")]   # noqa: E731 - the indented lines of one meeting
    assert labels(block_a) == ["Health", "Language", "Speakers", "Text"]
    assert labels(block_b) == ["Health", "WARNING", "Language", "Speakers", "Text"]   # in place: after the degraded warning, before Speakers and Text
    assert block_a[2].startswith("  Language: en (") and block_b[3].startswith("  Language: pt (")
    assert repo.load_transcript(a.id).language == "en" and repo.load_transcript(b.id).language == "pt"
