"""CLI `trec`. Commands for future phases exist but report that they are not available yet."""
from __future__ import annotations

import logging
import logging.handlers
import os
import shutil
import signal
from datetime import date
from pathlib import Path

import typer

from teams_recorder import __version__
from teams_recorder.adapters.outbound.launchd import LaunchAgent
from teams_recorder.adapters.outbound.process_finder import find_pid
from teams_recorder.config import ENV_PROJECT_DIR, load_settings
from teams_recorder.container import build_container, teams_tap_binary
from teams_recorder.domain import MeetingStatus, TeamsRecorderError, derive_status, next_step
from teams_recorder.domain.status import ERROR

app = typer.Typer(
    name="trec",
    help="Records, transcribes and analyzes Microsoft Teams meetings.",
    no_args_is_help=True,
    add_completion=False,
)

PHASES: dict[str, int] = {}

agent_app = typer.Typer(help="Installs, removes and inspects the LaunchAgent that keeps the daemon running.", no_args_is_help=True)
app.add_typer(agent_app, name="agent")


def _settings():
    env = os.environ.get(ENV_PROJECT_DIR)
    return load_settings(Path(env) if env else None)


def _pending(repo, status: MeetingStatus) -> list[str]:
    """Meetings whose next step is the given one, including those that failed at it (error.txt is ignored)."""
    return [m.id for m in repo.list_meetings() if derive_status(repo.files(m.id) - {ERROR}) == status]


def _fail(message: str, code: int = 1) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=code)


@app.command()
def version() -> None:
    """Show the version."""
    typer.echo(f"teams-recorder {__version__}")


@app.command()
def status() -> None:
    """List meetings, the status of each one and open actions."""
    settings = _settings()
    c = build_container(settings, headless=True)
    meetings = c.repo.list_meetings()
    typer.echo(f"Data dir: {settings.data_dir}")
    typer.echo(f"API key: {'configured' if settings.has_api_key else 'MISSING'}")
    typer.echo(f"Meetings: {len(meetings)}")
    for m in meetings:
        st = derive_status(c.repo.files(m.id))
        nxt = next_step(st)
        extra = f" → next: {nxt}" if nxt else ""
        title = f" {m.title}" if m.title else ""
        typer.echo(f"  {m.id}{title}  [{st.value}]{extra}")
    active = c.repo.load_active()
    if active:
        typer.echo(f"Recording in progress: {active.meeting.id} (recorder PIDs {active.process_handle.pid}, {active.mic_handle.pid})")
    open_actions = c.repo.load_open_actions()
    typer.echo(f"Open actions: {len(open_actions)}")


@app.command()
def doctor() -> None:
    """Check external dependencies and permissions."""
    settings = _settings()
    checks = {
        "ffmpeg": shutil.which("ffmpeg"),
        "whisper-cli": shutil.which("whisper-cli"),
        "swift": shutil.which("swift"),
        "osascript": shutil.which("osascript"),
        "teams-tap": _teams_tap_path(settings.project_dir),
    }
    ok = True
    for name, found in checks.items():
        mark = "ok " if found else "MISSING"
        ok = ok and bool(found)
        typer.echo(f"[{mark}] {name}: {found or 'not found'}")
    claude_cli = shutil.which("claude")
    typer.echo(f"[{'ok ' if claude_cli else 'info'}] claude (Claude Code CLI): {claude_cli or 'not found'}  → current provider: {settings.llm_provider}")
    model_ok = settings.whisper_model_path.exists()
    ok = ok and model_ok
    typer.echo(f"[{'ok ' if model_ok else 'MISSING'}] whisper model: {settings.whisper_model_path}" + ("" if model_ok else "  → scripts/download-model.sh"))
    if settings.vad_model_path is not None:
        vad_ok = settings.vad_model_path.exists()
        typer.echo(f"[{'ok ' if vad_ok else 'info'}] VAD model: {settings.vad_model_path}" + ("" if vad_ok else "  → scripts/download-model.sh silero-v5.1.2 (without it transcription runs without VAD)"))
    key_needed = settings.llm_provider == "api"
    key_mark = "ok " if settings.has_api_key else ("MISSING" if key_needed else "info")
    typer.echo(f"[{key_mark}] ANTHROPIC_API_KEY in .env" + ("" if key_needed else " (not required with provider = claude-code)"))
    env_file = settings.project_dir / ".env"
    if env_file.exists():
        mode = env_file.stat().st_mode & 0o777
        if mode & 0o077:
            typer.echo(f"[WARNING] .env permissions {oct(mode)}; recommended: chmod 600 .env")
    typer.echo(f"[info] data in {settings.data_dir}")
    llm_ok = settings.has_api_key if key_needed else bool(claude_cli)
    raise typer.Exit(code=0 if ok and llm_ok else 1)


@app.command()
def start(
    pid: int | None = typer.Option(None, help="PID of the process to capture. Default: the running Microsoft Teams."),
    title: str | None = typer.Option(None, help="Meeting title, used in the name and in the status."),
) -> None:
    """Start recording (Teams audio + microphone). Stop with `trec stop`."""
    settings = _settings()
    c = build_container(settings)
    target = pid or find_pid(settings.teams_process_name)
    if target is None:
        _fail(f"process {settings.teams_process_name} is not running; open Teams or pass --pid")
    try:
        active = c.start_recording().execute(target, title)  # type: ignore[arg-type]
    except TeamsRecorderError as exc:
        _fail(str(exc))
    typer.echo(f"Recording meeting {active.meeting.id} (target PID {target}).")
    typer.echo(f"  Teams:       {active.process_handle.out}  (recorder PID {active.process_handle.pid})")
    typer.echo(f"  Microphone:  {active.mic_handle.out}  (recorder PID {active.mic_handle.pid})")
    typer.echo("Stop with `trec stop` or discard with `trec cancel`.")


@app.command()
def stop() -> None:
    """Stop the recording in progress, mix the tracks and produce audio.m4a."""
    c = build_container(_settings())
    active = c.repo.load_active()
    if active is None:
        _fail("no recording in progress")
    try:
        meeting = c.stop_recording().execute(active)  # type: ignore[arg-type]
    except TeamsRecorderError as exc:
        _fail(str(exc))
    minutes = (meeting.duration_seconds or 0) / 60
    typer.echo(f"Meeting {meeting.id} stopped after {minutes:.1f} min.")
    typer.echo(f"  Audio: {c.repo.path(meeting.id, 'audio.m4a')}")
    typer.echo(f"Transcribe with `trec transcribe {meeting.id}`.")


@app.command()
def transcribe(
    meeting_id: str | None = typer.Argument(None, help="Meeting ID. Without an argument: all recorded meetings not yet transcribed."),
) -> None:
    """Transcribe the audio of a meeting (or of all pending ones) locally with whisper.cpp."""
    c = build_container(_settings(), headless=True)
    if meeting_id:
        if not c.repo.exists(meeting_id):
            _fail(f"meeting {meeting_id} does not exist")
        targets = [meeting_id]
    else:
        targets = _pending(c.repo, MeetingStatus.RECORDED)
        if not targets:
            typer.echo("No meeting pending transcription.")
            return
    use_case = c.transcribe_meeting()
    failures = 0
    for mid in targets:
        typer.echo(f"Transcribing {mid}…", nl=False)
        try:
            transcript = use_case.execute(mid)
        except TeamsRecorderError as exc:
            failures += 1
            c.repo.mark_failed(mid, f"transcription: {exc}")
            typer.echo(f" FAILED: {exc}")
            continue
        c.repo.clear_failed(mid)
        typer.echo(f" ok ({len(transcript.segments)} segments, {transcript.duration_seconds/60:.1f} min)")
        typer.echo(f"  Text: {c.repo.path(mid, 'transcript.txt')}")
    if failures:
        raise typer.Exit(code=1)
    typer.echo("Analyze with `trec analyze`.")


@app.command()
def cancel() -> None:
    """Discard the recording in progress without producing a file."""
    c = build_container(_settings())
    active = c.repo.load_active()
    if active is None:
        _fail("no recording in progress")
    c.cancel_recording().execute(active)  # type: ignore[arg-type]
    typer.echo(f"Recording {active.meeting.id} discarded.")  # type: ignore[union-attr]


@app.command()
def analyze(
    meeting_id: str | None = typer.Argument(None, help="Meeting ID. Without an argument: all transcribed meetings not yet analyzed."),
) -> None:
    """Extract summary, decisions, actions and deadlines from the transcript with the Claude API."""
    settings = _settings()
    if settings.llm_provider == "api" and not settings.has_api_key:
        _fail("ANTHROPIC_API_KEY missing from .env (or set llm.provider = \"claude-code\")")
    if settings.llm_provider == "claude-code" and shutil.which("claude") is None:
        _fail("Claude Code (`claude`) not found in PATH")
    c = build_container(settings, headless=True)
    if meeting_id:
        if not c.repo.exists(meeting_id):
            _fail(f"meeting {meeting_id} does not exist")
        targets = [meeting_id]
    else:
        targets = _pending(c.repo, MeetingStatus.TRANSCRIBED)
        if not targets:
            typer.echo("No meeting pending analysis.")
            return
    typer.echo(f"Provider: {settings.llm_provider} ({settings.llm_cli_model if settings.llm_provider == 'claude-code' else settings.llm_model})")
    use_case = c.analyze_meeting()
    failures = 0
    for mid in targets:
        typer.echo(f"Analyzing {mid}…", nl=False)
        try:
            analysis = use_case.execute(mid)
        except TeamsRecorderError as exc:
            failures += 1
            c.repo.mark_failed(mid, f"analysis: {exc}")
            typer.echo(f" FAILED: {exc}")
            continue
        c.repo.clear_failed(mid)
        typer.echo(f" ok ({len(analysis.decisions)} decisions, {len(analysis.my_actions)} actions of yours, {len(analysis.others_actions)} of others)")
        typer.echo(f"  Summary: {analysis.summary}")
        for a in analysis.my_actions:
            due = f" by {a.due.isoformat()}" if a.due else ""
            typer.echo(f"  • {a.description}{due}")
        typer.echo(f"  File: {c.repo.path(mid, 'analysis.json')}")
    if failures:
        raise typer.Exit(code=1)


@app.command()
def daemon(
    once: bool = typer.Option(False, "--once", help="Run a single detection iteration and exit (diagnostics)."),
) -> None:
    """Watch Teams and record, transcribe and analyze meetings automatically. Used by the LaunchAgent."""
    from teams_recorder.adapters.inbound.daemon import Daemon

    settings = _settings()
    _setup_logging(settings.daemon_log)
    c = build_container(settings)
    d = Daemon(c, poll_seconds=settings.poll_seconds, start_after=settings.start_after_positive_polls, stop_after=settings.stop_after_negative_polls)
    if once:
        state = c.detector.poll()  # type: ignore[union-attr]
        typer.echo(f"detector ({settings.teams_process_name}): {state.value}; pid={c.detector.teams_pid()}")  # type: ignore[union-attr]
        return
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: d.request_stop())
    typer.echo(f"daemon watching {settings.teams_process_name}; log at {settings.daemon_log}")
    d.run()


def _setup_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.TimedRotatingFileHandler(path, when="midnight", backupCount=30, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
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


@agent_app.command("install")
def agent_install(
    env: list[str] = typer.Option([], "--env", help="Extra variable for the daemon, in KEY=VALUE format (e.g. TREC_LLM_PROVIDER=claude-code). Repeatable."),
) -> None:
    """Register the daemon with launchd: starts at login and restarts if it dies."""
    extra: dict[str, str] = {}
    for item in env:
        if "=" not in item:
            _fail(f"--env expects KEY=VALUE, got {item!r}")
        k, v = item.split("=", 1)
        extra[k.strip()] = v
    try:
        path = _agent(extra or None).install()
        planner_path = _planner_agent(extra or None).install()
    except RuntimeError as exc:
        _fail(str(exc))
    typer.echo(f"LaunchAgent installed and started: {path}")
    typer.echo(f"Planner scheduled (Mon–Fri {_settings().plan_hour:02d}:00): {planner_path}")
    typer.echo("On the first recording macOS will ask for Microphone and System Audio Recording permissions.")


@agent_app.command("uninstall")
def agent_uninstall() -> None:
    """Stop the daemon and remove the LaunchAgent."""
    existed = _agent().uninstall()
    existed_planner = _planner_agent().uninstall()
    typer.echo("LaunchAgent removed." if existed else "No daemon LaunchAgent installed.")
    typer.echo("Planner removed." if existed_planner else "No planner scheduled.")


@agent_app.command("restart")
def agent_restart() -> None:
    """Restart the daemon (for example after changing config.toml)."""
    try:
        _agent().restart()
    except RuntimeError as exc:
        _fail(str(exc))
    typer.echo("daemon restarted.")


@agent_app.command("status")
def agent_status() -> None:
    """Show whether the daemon is loaded and running."""
    info = _agent().status()
    typer.echo(f"plist: {info['plist']} ({'exists' if info['plist_exists'] else 'missing'})")
    typer.echo(f"loaded: {'yes' if info['loaded'] else 'no'}" + (f"  pid={info['pid']}  state={info['state']}" if info["loaded"] else ""))
    pinfo = _planner_agent().status()
    typer.echo(f"planner: {'scheduled' if pinfo['loaded'] else 'not scheduled'} ({_settings().plan_hour:02d}:00 Mon–Fri)")
    raise typer.Exit(code=0 if info["loaded"] else 1)


@app.command()
def plan(
    day: str | None = typer.Option(None, "--date", help="Day to plan (YYYY-MM-DD). Default: today."),
    purge_after: bool = typer.Option(False, "--purge", help="After the plan, delete audio of old meetings (retention)."),
) -> None:
    """Consolidate the day's analyses into a Markdown plan and update the open actions."""
    settings = _settings()
    if settings.llm_provider == "api" and not settings.has_api_key:
        _fail("ANTHROPIC_API_KEY missing from .env (or set llm.provider = \"claude-code\")")
    if settings.llm_provider == "claude-code" and shutil.which("claude") is None:
        _fail("Claude Code (`claude`) not found in PATH")
    try:
        target = date.fromisoformat(day) if day else date.today()
    except ValueError:
        _fail(f"invalid date: {day!r} (use YYYY-MM-DD)")
    c = build_container(settings)
    typer.echo(f"Planning {target.isoformat()} (provider {settings.llm_provider})…", nl=False)
    try:
        result = c.build_daily_plan().execute(target)  # type: ignore[possibly-undefined]
    except TeamsRecorderError as exc:
        _fail(str(exc))
    typer.echo(f" ok ({len(result.new_actions)} new actions, {len(result.completed_action_ids)} completed, {len(result.overdue_action_ids)} overdue)")
    for pr in result.priorities:
        typer.echo(f"  • {pr}")
    typer.echo(f"  Plan: {settings.data_dir / 'plans' / (target.isoformat() + '.md')}")
    if purge_after:
        purged = c.purge_old_audio().execute()
        typer.echo(f"Audio files removed by retention: {len(purged)}")


@app.command()
def purge() -> None:
    """Delete audio of already transcribed meetings older than N days (config: planner.retention_days)."""
    c = build_container(_settings(), headless=True)
    purged = c.purge_old_audio().execute()
    typer.echo(f"Audio files removed: {len(purged)}")
    for mid in purged:
        typer.echo(f"  {mid}")


def _teams_tap_path(project_dir: Path) -> str | None:
    candidate = teams_tap_binary(project_dir)
    return str(candidate) if candidate.exists() else None


if __name__ == "__main__":
    app()
