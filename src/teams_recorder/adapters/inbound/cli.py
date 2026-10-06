"""CLI `trec`."""
from __future__ import annotations

import logging
import logging.handlers
import os
import shutil
import signal
from datetime import date
from pathlib import Path
from typing import NoReturn

import typer

from teams_recorder import __version__
from teams_recorder.adapters.outbound.launchd import LaunchAgent
from teams_recorder.adapters.outbound.process_finder import find_pid
from teams_recorder.application.ports import MeetingRepository
from teams_recorder.config import Settings, load_settings
from teams_recorder.constants import CLI_NAME, Audio, Bin, Confirm, Env, Files, LlmProvider, Logging
from teams_recorder.container import build_container, teams_tap_binary
from teams_recorder.domain import MeetingStatus, TeamsRecorderError, derive_status, next_step
from teams_recorder.domain.status import ANALYSIS, AUDIO, ERROR, MINUTES, TRANSCRIPT_TXT
from teams_recorder.messages import Cli, Err, Step

app = typer.Typer(
    name=CLI_NAME,
    help=Cli.APP_HELP,
    no_args_is_help=True,
    add_completion=False,
)

agent_app = typer.Typer(help=Cli.AGENT_HELP, no_args_is_help=True)
app.add_typer(agent_app, name="agent")


def _settings() -> Settings:
    env = os.environ.get(Env.PROJECT_DIR)
    return load_settings(Path(env) if env else None)


def _pending(repo: MeetingRepository, status: MeetingStatus) -> list[str]:
    """Meetings whose next step is the given one, including those that failed at it (error.txt is ignored)."""
    return [m.id for m in repo.list_meetings() if derive_status(repo.files(m.id) - {ERROR}) == status]


def _fail(message: str, code: int = 1) -> NoReturn:
    typer.echo(Cli.ERROR_PREFIX.format(message=message), err=True)
    raise typer.Exit(code=code)


def _check_llm_prerequisites(settings: Settings) -> None:
    if settings.llm_provider == LlmProvider.API and not settings.has_api_key:
        _fail(Cli.API_KEY_MISSING)
    if settings.llm_provider == LlmProvider.CLAUDE_CODE and shutil.which(Bin.CLAUDE) is None:
        _fail(Cli.CLAUDE_CLI_MISSING)


@app.command(help=Cli.VERSION_CMD_HELP)
def version() -> None:
    typer.echo(Cli.VERSION.format(version=__version__))


@app.command(help=Cli.STATUS_CMD_HELP)
def status() -> None:
    settings = _settings()
    c = build_container(settings, headless=True)
    meetings = c.repo.list_meetings()
    typer.echo(Cli.DATA_DIR.format(path=settings.data_dir))
    typer.echo(Cli.API_KEY.format(state=Cli.CONFIGURED if settings.has_api_key else Cli.MISSING))
    typer.echo(Cli.MEETINGS.format(count=len(meetings)))
    for m in meetings:
        st = derive_status(c.repo.files(m.id))
        nxt = next_step(st)
        typer.echo(Cli.MEETING_LINE.format(
            meeting_id=m.id,
            title=Cli.MEETING_TITLE.format(title=m.title) if m.title else "",
            status=st.value,
            next=Cli.NEXT_STEP.format(step=nxt) if nxt else "",
        ))
    active = c.repo.load_active()
    if active:
        typer.echo(Cli.RECORDING_IN_PROGRESS.format(meeting_id=active.meeting.id, tap_pid=active.process_handle.pid, mic_pid=active.mic_handle.pid))
    open_actions = c.repo.load_open_actions()
    typer.echo(Cli.OPEN_ACTIONS.format(count=len(open_actions)))


@app.command(help=Cli.DOCTOR_CMD_HELP)
def doctor() -> None:
    settings = _settings()
    checks: dict[str, str | None] = {
        Bin.FFMPEG: shutil.which(Bin.FFMPEG),
        Bin.WHISPER_CLI: shutil.which(Bin.WHISPER_CLI),
        Bin.SWIFT: shutil.which(Bin.SWIFT),
        Bin.OSASCRIPT: shutil.which(Bin.OSASCRIPT),
        Bin.TEAMS_TAP: _teams_tap_path(settings.project_dir),
    }
    ok = True
    for name, found in checks.items():
        ok = ok and bool(found)
        typer.echo(Cli.CHECK.format(mark=Cli.OK if found else Cli.MISSING_MARK, name=name, value=found or Cli.NOT_FOUND))
    claude_cli = shutil.which(Bin.CLAUDE)
    typer.echo(Cli.CLAUDE_CLI_LINE.format(mark=Cli.OK if claude_cli else Cli.INFO, value=claude_cli or Cli.NOT_FOUND, provider=settings.llm_provider))
    model_ok = settings.whisper_model_path.exists()
    ok = ok and model_ok
    typer.echo(Cli.WHISPER_MODEL_LINE.format(
        mark=Cli.OK if model_ok else Cli.MISSING_MARK,
        path=settings.whisper_model_path,
        hint="" if model_ok else Cli.WHISPER_MODEL_HINT.format(script=Files.DOWNLOAD_MODEL_SCRIPT),
    ))
    if settings.vad_model_path is not None:
        vad_ok = settings.vad_model_path.exists()
        typer.echo(Cli.VAD_MODEL_LINE.format(
            mark=Cli.OK if vad_ok else Cli.INFO,
            path=settings.vad_model_path,
            hint="" if vad_ok else Cli.VAD_MODEL_HINT.format(script=Files.DOWNLOAD_MODEL_SCRIPT, model=Audio.DEFAULT_VAD_MODEL),
        ))
    key_needed = settings.llm_provider == LlmProvider.API
    key_mark = Cli.OK if settings.has_api_key else (Cli.MISSING_MARK if key_needed else Cli.INFO)
    typer.echo(Cli.API_KEY_LINE.format(mark=key_mark, hint="" if key_needed else Cli.API_KEY_NOT_REQUIRED))
    env_file = settings.project_dir / Files.DOTENV
    if env_file.exists():
        mode = env_file.stat().st_mode & 0o777
        if mode & 0o077:
            typer.echo(Cli.ENV_PERMISSIONS.format(mode=oct(mode)))
    typer.echo(Cli.DATA_IN.format(path=settings.data_dir))
    llm_ok = settings.has_api_key if key_needed else bool(claude_cli)
    raise typer.Exit(code=0 if ok and llm_ok else 1)


@app.command(help=Cli.START_CMD_HELP)
def start(
    pid: int | None = typer.Option(None, help=Cli.START_PID_HELP),
    title: str | None = typer.Option(None, help=Cli.START_TITLE_HELP),
) -> None:
    settings = _settings()
    c = build_container(settings)
    target = pid or find_pid(settings.teams_process_name)
    if target is None:
        _fail(Cli.TEAMS_NOT_RUNNING.format(name=settings.teams_process_name))
    try:
        active = c.start_recording().execute(target, title)
    except TeamsRecorderError as exc:
        _fail(str(exc))
    typer.echo(Cli.RECORDING_MEETING.format(meeting_id=active.meeting.id, pid=target))
    typer.echo(Cli.TRACK_TEAMS.format(path=active.process_handle.out, pid=active.process_handle.pid))
    typer.echo(Cli.TRACK_MIC.format(path=active.mic_handle.out, pid=active.mic_handle.pid))
    typer.echo(Cli.STOP_HINT)


@app.command(help=Cli.STOP_CMD_HELP)
def stop() -> None:
    c = build_container(_settings())
    active = c.repo.load_active()
    if active is None:
        _fail(Cli.NO_RECORDING)
    try:
        meeting = c.stop_recording().execute(active)
    except TeamsRecorderError as exc:
        _fail(str(exc))
    minutes = (meeting.duration_seconds or 0) / 60
    typer.echo(Cli.STOPPED.format(meeting_id=meeting.id, minutes=minutes))
    typer.echo(Cli.AUDIO_PATH.format(path=c.repo.path(meeting.id, AUDIO)))
    typer.echo(Cli.TRANSCRIBE_HINT.format(meeting_id=meeting.id))


@app.command(help=Cli.TRANSCRIBE_CMD_HELP)
def transcribe(
    meeting_id: str | None = typer.Argument(None, help=Cli.TRANSCRIBE_ARG_HELP),
) -> None:
    c = build_container(_settings(), headless=True)
    if meeting_id:
        if not c.repo.exists(meeting_id):
            _fail(Cli.MEETING_MISSING.format(meeting_id=meeting_id))
        targets = [meeting_id]
    else:
        targets = _pending(c.repo, MeetingStatus.RECORDED)
        if not targets:
            typer.echo(Cli.NO_PENDING_TRANSCRIPTION)
            return
    use_case = c.transcribe_meeting()
    failures = 0
    for mid in targets:
        typer.echo(Cli.TRANSCRIBING.format(meeting_id=mid), nl=False)
        try:
            transcript = use_case.execute(mid)
        except TeamsRecorderError as exc:
            failures += 1
            c.repo.mark_failed(mid, Err.STEP_ERROR.format(step=Step.TRANSCRIPTION, error=exc))
            typer.echo(Cli.FAILED.format(error=exc))
            continue
        c.repo.clear_failed(mid)
        typer.echo(Cli.TRANSCRIBED_OK.format(segments=len(transcript.segments), minutes=transcript.duration_seconds / 60))
        typer.echo(Cli.TEXT_PATH.format(path=c.repo.path(mid, TRANSCRIPT_TXT)))
    if failures:
        raise typer.Exit(code=1)
    typer.echo(Cli.ANALYZE_HINT)


@app.command(help=Cli.CANCEL_CMD_HELP)
def cancel() -> None:
    c = build_container(_settings())
    active = c.repo.load_active()
    if active is None:
        _fail(Cli.NO_RECORDING)
    c.cancel_recording().execute(active)
    typer.echo(Cli.DISCARDED.format(meeting_id=active.meeting.id))


@app.command(help=Cli.ANALYZE_CMD_HELP)
def analyze(
    meeting_id: str | None = typer.Argument(None, help=Cli.ANALYZE_ARG_HELP),
) -> None:
    settings = _settings()
    _check_llm_prerequisites(settings)
    c = build_container(settings, headless=True)
    if meeting_id:
        if not c.repo.exists(meeting_id):
            _fail(Cli.MEETING_MISSING.format(meeting_id=meeting_id))
        targets = [meeting_id]
    else:
        targets = _pending(c.repo, MeetingStatus.TRANSCRIBED)
        if not targets:
            typer.echo(Cli.NO_PENDING_ANALYSIS)
            return
    model = settings.llm_cli_model if settings.llm_provider == LlmProvider.CLAUDE_CODE else settings.llm_model
    typer.echo(Cli.PROVIDER.format(provider=settings.llm_provider, model=model))
    use_case = c.analyze_meeting()
    failures = 0
    for mid in targets:
        typer.echo(Cli.ANALYZING.format(meeting_id=mid), nl=False)
        try:
            analysis = use_case.execute(mid)
        except TeamsRecorderError as exc:
            failures += 1
            c.repo.mark_failed(mid, Err.STEP_ERROR.format(step=Step.ANALYSIS, error=exc))
            typer.echo(Cli.FAILED.format(error=exc))
            continue
        c.repo.clear_failed(mid)
        typer.echo(Cli.ANALYZED_OK.format(decisions=len(analysis.decisions), mine=len(analysis.my_actions), others=len(analysis.others_actions)))
        if analysis.title:
            typer.echo(Cli.TITLE_LINE.format(title=analysis.title))
        typer.echo(Cli.SUMMARY.format(summary=analysis.summary))
        for a in analysis.my_actions:
            typer.echo(Cli.ACTION_LINE.format(description=a.description, due=Cli.ACTION_DUE.format(due=a.due.isoformat()) if a.due else ""))
        typer.echo(Cli.FILE_PATH.format(path=c.repo.path(mid, ANALYSIS)))
        typer.echo(Cli.MINUTES_PATH.format(path=c.repo.path(mid, MINUTES)))
    if failures:
        raise typer.Exit(code=1)


@app.command(help=Cli.MINUTES_CMD_HELP)
def minutes(
    meeting_id: str | None = typer.Argument(None, help=Cli.MINUTES_ARG_HELP),
    all_meetings: bool = typer.Option(False, "--all", help=Cli.MINUTES_ALL_HELP),
) -> None:
    c = build_container(_settings(), headless=True)
    if meeting_id:
        if not c.repo.exists(meeting_id):
            _fail(Cli.MEETING_MISSING.format(meeting_id=meeting_id))
        targets = [meeting_id]
    else:
        analyzed = [m.id for m in c.repo.list_meetings() if ANALYSIS in c.repo.files(m.id)]
        targets = analyzed if all_meetings else [mid for mid in analyzed if MINUTES not in c.repo.files(mid)]
        if not targets:
            typer.echo(Cli.NO_PENDING_MINUTES)
            return
    use_case = c.render_minutes()
    for mid in targets:
        try:
            use_case.execute(mid)
        except TeamsRecorderError as exc:
            _fail(str(exc))
        typer.echo(Cli.MINUTES_WRITTEN.format(path=c.repo.path(mid, MINUTES)))


@app.command(help=Cli.DAEMON_CMD_HELP)
def daemon(
    once: bool = typer.Option(False, "--once", help=Cli.DAEMON_ONCE_HELP),
) -> None:
    from teams_recorder.adapters.inbound.daemon import Daemon

    settings = _settings()
    _setup_logging(settings.daemon_log)
    c = build_container(settings)
    d = Daemon(
        c, poll_seconds=settings.poll_seconds, start_after=settings.start_after_positive_polls, stop_after=settings.stop_after_negative_polls,
        confirm_wait=settings.confirm_timeout_seconds + Confirm.WAIT_MARGIN,
    )
    if once:
        state = c.detector.poll()
        typer.echo(Cli.DETECTOR_STATE.format(name=settings.teams_process_name, state=state.value, pid=c.detector.teams_pid()))
        return
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: d.request_stop())
    typer.echo(Cli.DAEMON_WATCHING.format(name=settings.teams_process_name, path=settings.daemon_log))
    d.run()


def _setup_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(path, when=Logging.ROTATE_WHEN, backupCount=Logging.BACKUP_COUNT, encoding="utf-8")
    handler.setFormatter(logging.Formatter(Logging.FORMAT))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(logging.StreamHandler())


def _agent(extra_env: dict[str, str] | None = None) -> LaunchAgent:
    s = _settings()
    return LaunchAgent(s.project_dir, s.data_dir, extra_env=extra_env)


def _planner_agent(extra_env: dict[str, str] | None = None) -> LaunchAgent:
    s = _settings()
    return LaunchAgent.planner(s.project_dir, s.data_dir, hour=s.plan_hour, extra_env=extra_env)


@agent_app.command("install", help=Cli.AGENT_INSTALL_CMD_HELP)
def agent_install(
    env: list[str] = typer.Option([], "--env", help=Cli.AGENT_ENV_HELP),
) -> None:
    extra: dict[str, str] = {}
    for item in env:
        if "=" not in item:
            _fail(Cli.AGENT_ENV_INVALID.format(item=item))
        k, v = item.split("=", 1)
        extra[k.strip()] = v
    try:
        path = _agent(extra or None).install()
        planner_path = _planner_agent(extra or None).install()
    except RuntimeError as exc:
        _fail(str(exc))
    typer.echo(Cli.AGENT_INSTALLED.format(path=path))
    typer.echo(Cli.PLANNER_SCHEDULED.format(hour=_settings().plan_hour, path=planner_path))
    typer.echo(Cli.PERMISSIONS_HINT)


@agent_app.command("uninstall", help=Cli.AGENT_UNINSTALL_CMD_HELP)
def agent_uninstall() -> None:
    existed = _agent().uninstall()
    existed_planner = _planner_agent().uninstall()
    typer.echo(Cli.AGENT_REMOVED if existed else Cli.AGENT_NOT_INSTALLED)
    typer.echo(Cli.PLANNER_REMOVED if existed_planner else Cli.PLANNER_NOT_SCHEDULED)


@agent_app.command("restart", help=Cli.AGENT_RESTART_CMD_HELP)
def agent_restart() -> None:
    try:
        _agent().restart()
    except RuntimeError as exc:
        _fail(str(exc))
    typer.echo(Cli.DAEMON_RESTARTED)


@agent_app.command("status", help=Cli.AGENT_STATUS_CMD_HELP)
def agent_status() -> None:
    info = _agent().status()
    typer.echo(Cli.PLIST_LINE.format(path=info.plist, state=Cli.EXISTS if info.plist_exists else Cli.MISSING_FILE))
    details = Cli.LOADED_DETAILS.format(pid=info.pid, state=info.state) if info.loaded else ""
    typer.echo(Cli.LOADED_LINE.format(state=Cli.YES if info.loaded else Cli.NO, details=details))
    pinfo = _planner_agent().status()
    typer.echo(Cli.PLANNER_LINE.format(state=Cli.SCHEDULED if pinfo.loaded else Cli.NOT_SCHEDULED, hour=_settings().plan_hour))
    raise typer.Exit(code=0 if info.loaded else 1)


@app.command(help=Cli.PLAN_CMD_HELP)
def plan(
    day: str | None = typer.Option(None, "--date", help=Cli.PLAN_DATE_HELP),
    purge_after: bool = typer.Option(False, "--purge", help=Cli.PLAN_PURGE_HELP),
) -> None:
    settings = _settings()
    _check_llm_prerequisites(settings)
    try:
        target = date.fromisoformat(day) if day else date.today()
    except ValueError:
        _fail(Cli.INVALID_DATE.format(value=day))
    c = build_container(settings)
    typer.echo(Cli.PLANNING.format(day=target.isoformat(), provider=settings.llm_provider), nl=False)
    try:
        result = c.build_daily_plan().execute(target)
    except TeamsRecorderError as exc:
        _fail(str(exc))
    typer.echo(Cli.PLANNED_OK.format(new=len(result.new_actions), completed=len(result.completed_action_ids), overdue=len(result.overdue_action_ids)))
    for pr in result.priorities:
        typer.echo(Cli.PRIORITY_LINE.format(text=pr))
    typer.echo(Cli.PLAN_PATH.format(path=settings.data_dir / Files.PLANS_DIR / Files.PLAN_MARKDOWN.format(day=target.isoformat())))
    if purge_after:
        purged = c.purge_old_audio().execute()
        typer.echo(Cli.PURGED_RETENTION.format(count=len(purged)))


@app.command(help=Cli.PURGE_CMD_HELP)
def purge() -> None:
    c = build_container(_settings(), headless=True)
    purged = c.purge_old_audio().execute()
    typer.echo(Cli.PURGED.format(count=len(purged)))
    for mid in purged:
        typer.echo(Cli.PURGED_LINE.format(meeting_id=mid))


def _teams_tap_path(project_dir: Path) -> str | None:
    candidate = teams_tap_binary(project_dir)
    return str(candidate) if candidate.exists() else None


if __name__ == "__main__":
    app()
