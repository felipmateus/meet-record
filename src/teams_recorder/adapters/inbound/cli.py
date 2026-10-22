"""CLI `trec`."""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
import shutil
import signal
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Callable, NoReturn

import typer

from teams_recorder import __version__
from teams_recorder.adapters.outbound.disk_space import DataDirDiskSpace
from teams_recorder.adapters.outbound.launchd import LaunchAgent
from teams_recorder.adapters.outbound.process_finder import find_pid
from teams_recorder.adapters.outbound.repository_fs import FsMeetingRepository
from teams_recorder.adapters.outbound.scheduler_windows import ScheduledTask
from teams_recorder.application.ports import ActiveRecording, MeetingRepository
from teams_recorder.application.use_cases import TagDraftResult, gaps_text, stories_waiting
from teams_recorder.application.use_cases.activities import ActivitiesStatus, NotCurated, PassResult, batches, passes_by_day
from teams_recorder.config import Settings, find_tool, load_settings
from teams_recorder.constants import CLI_NAME, Activities, Audio, Bin, Confirm, Env, Files, Legacy, LlmProvider, Logging, Parse, Platform
from teams_recorder.container import (
    Container, build_container, build_retry_transcriber, build_speaker_observer, build_story_publishers, teams_speakers_binary, teams_tap_binary,
)
from teams_recorder.domain import (
    CuratorBusy, LabelSummary, LanguageReason, LanguageRules, MeetingStatus, NothingToUndo, SkippedAction, SpeakerReason, TeamsRecorderError, Transcript, UndoStale,
    counted_tally, derive_status, next_step, unconfirmed, verifications,
)
from teams_recorder.domain.status import ANALYSIS, AUDIO, ERROR, MINUTES, TRANSCRIPT_JSON, TRANSCRIPT_TXT
from teams_recorder.messages import ActivityDoc, Cli, Err, Notify, Step

app = typer.Typer(
    name=CLI_NAME,
    help=Cli.APP_HELP,
    no_args_is_help=True,
    add_completion=False,
)

agent_app = typer.Typer(help=Cli.AGENT_HELP, no_args_is_help=True)
app.add_typer(agent_app, name="agent")

activities_app = typer.Typer(help=Cli.ACTIVITIES_HELP, invoke_without_command=True)
app.add_typer(activities_app, name="activities")


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
    # A damaged data file is reported on its own line (the repository's error names the file) and the rest
    # of the status is still shown; the command then exits 1.
    unreadable = False
    meeting_ids = c.repo.meeting_ids()
    typer.echo(Cli.DATA_DIR.format(path=settings.data_dir))
    typer.echo(Cli.API_KEY.format(state=Cli.CONFIGURED if settings.has_api_key else Cli.MISSING))
    typer.echo(Cli.MEETINGS.format(count=len(meeting_ids)))
    degraded = rate_mismatched = unconfirmed_claims = unconfirmed_meetings = 0
    for meeting_id in meeting_ids:
        try:
            m = c.repo.load_meta(meeting_id)
        except TeamsRecorderError as exc:
            unreadable = True
            typer.echo(Cli.MEETING_UNREADABLE.format(meeting_id=meeting_id, error=exc))
            continue
        files = c.repo.files(m.id)
        st = derive_status(files)
        nxt = next_step(st)
        transcript = _load_transcript(c.repo, m.id) if TRANSCRIPT_JSON in files else None
        health = transcript.health if transcript else None
        marker = _speakers_segment(transcript.labels if transcript else None)
        if health is not None and health.degraded:
            degraded += 1
            marker += Cli.MEETING_DEGRADED.format(loop=health.loop_share)
        if health is not None and health.rate_mismatch:
            rate_mismatched += 1
            marker += Cli.MEETING_RATE_MISMATCH.format(share=health.short_padding_share)
        flagged = _unconfirmed_count(c.repo, m.id) if ANALYSIS in files else 0
        if flagged:
            unconfirmed_claims += flagged
            unconfirmed_meetings += 1
            marker += Cli.MEETING_UNCONFIRMED.format(count=flagged)
        marker += _language_segment(transcript)
        typer.echo(Cli.MEETING_LINE.format(
            meeting_id=m.id,
            title=Cli.MEETING_TITLE.format(title=m.title) if m.title else "",
            status=st.value,
            next=Cli.NEXT_STEP.format(step=nxt) if nxt else "",
            health=marker,
        ))
    typer.echo(Cli.DEGRADED_TRANSCRIPTS.format(count=degraded))
    if rate_mismatched:   # only meetings recorded since 2026-10-14 can be flagged, so the line stays out until one is
        typer.echo(Cli.RATE_MISMATCH_TRANSCRIPTS.format(count=rate_mismatched))
    typer.echo(Cli.UNCONFIRMED_CLAIMS.format(claims=unconfirmed_claims, meetings=unconfirmed_meetings))
    try:
        active = c.repo.load_active()
        if active:
            typer.echo(Cli.RECORDING_IN_PROGRESS.format(meeting_id=active.meeting.id, tap_pid=active.process_handle.pid, mic_pid=active.mic_handle.pid))
    except TeamsRecorderError as exc:
        unreadable = True
        typer.echo(Cli.ACTIVE_UNREADABLE.format(error=exc))
    try:
        typer.echo(_activities_status_line(c.activities_summary().execute()))
    except TeamsRecorderError as exc:
        unreadable = True
        typer.echo(Cli.ACTIVITIES_STATUS_UNREADABLE.format(error=exc))
    if c.story_publishers:
        try:
            typer.echo(Cli.STORIES_WAITING.format(count=len(c.stories_waiting())))
        except TeamsRecorderError as exc:
            unreadable = True
            typer.echo(Cli.STORIES_WAITING_UNREADABLE.format(error=exc))
    if unreadable:
        raise typer.Exit(code=1)


def _activities_status_line(status: ActivitiesStatus) -> str:
    """The `Activities:` line of `trec status`: the open items of the document that are the user's and those waiting on others,
    and when it was last updated. A section whose heading the user renamed or removed is left out."""
    if not status.exists:
        return Cli.ACTIVITIES_STATUS_NONE
    labelled = ((ActivityDoc.HEADING_ACTIONS, Cli.ACTIVITIES_COUNT_ACTIONS), (ActivityDoc.HEADING_WAITING, Cli.ACTIVITIES_COUNT_WAITING))
    counts = Cli.ACTIVITIES_COUNT_SEPARATOR.join(template.format(count=status.counts[heading]) for heading, template in labelled if heading in status.counts)
    last = Cli.ACTIVITIES_STATUS_LAST.format(when=_when(status.last_pass.ts)) if status.last_pass is not None else ""
    return Cli.ACTIVITIES_STATUS.format(counts=counts or Cli.ACTIVITIES_STATUS_NO_COUNTS, last=last)


def _load_transcript(repo: MeetingRepository, meeting_id: str) -> Transcript | None:
    """A meeting's saved transcript; None when it is unreadable (its health and speaker summary are then unknown)."""
    try:
        return repo.load_transcript(meeting_id)
    except TeamsRecorderError:
        return None


def _no_labels_text(reason: str | None) -> str:
    """The reason table of `trec transcribe` for a transcript without a label; a summary with no reason counts as no observer data."""
    return Cli.SPEAKERS_REASON.get(reason or SpeakerReason.NO_OBSERVER, reason or "")


def _speakers_segment(labels: LabelSummary | None) -> str:
    """The `trec status` segment of a meeting line: the labelled share, `0%` with the reason when nothing was labelled,
    nothing for transcripts without a summary and for those of meetings with no observer data (feature off, Windows, old)."""
    if labels is None:
        return ""
    if labels.labelled:
        return Cli.MEETING_SPEAKERS.format(share=labels.share or 0.0)
    if (labels.reason or SpeakerReason.NO_OBSERVER) == SpeakerReason.NO_OBSERVER:
        return ""
    return Cli.MEETING_SPEAKERS_NONE.format(reason=_no_labels_text(labels.reason))


def _speakers_line(transcript: Transcript) -> str | None:
    """The `Speakers:` line of `trec transcribe`; None for a transcript without a summary."""
    labels = transcript.labels
    if labels is None:
        return None
    if labels.labelled:
        names = Cli.SPEAKER_NAMES_SEPARATOR.join(transcript.speakers)
        return Cli.SPEAKERS_LABELLED.format(share=labels.share or 0.0, eligible=labels.eligible, names=names)
    return Cli.SPEAKERS_NO_LABELS.format(reason=_no_labels_text(labels.reason))


def _language_segment(transcript: Transcript | None) -> str:
    """The `trec status` language marker of a meeting line: the code of a transcript that is not in Portuguese, else nothing
    (Portuguese, and meetings without a readable transcript)."""
    if transcript is None or transcript.language == Audio.DEFAULT_LANGUAGE:
        return ""
    return Cli.MEETING_LANGUAGE.format(language=transcript.language)


def _language_line(transcript: Transcript, allowed: tuple[str, ...]) -> str:
    """The `Language:` line of `trec transcribe`: the language and how it was chosen. `allowed` is `[transcription] languages`."""
    detection = transcript.language_detection
    language = transcript.language
    if detection is None:
        return Cli.LANGUAGE_FIXED.format(language=language)
    taken = len(detection.samples)
    match detection.reason:
        case LanguageReason.MAJORITY:
            return Cli.LANGUAGE_DETECTED.format(language=language, votes=detection.votes, counted=detection.counted, taken=taken)
        case LanguageReason.NO_USABLE_SAMPLE:
            head, last = allowed[:-1], allowed[-1]
            names = (Cli.LANGUAGE_LIST_SEPARATOR.join(head) + Cli.LANGUAGE_ALTERNATIVE + last) if head else last
            return Cli.LANGUAGE_NO_USABLE_SAMPLE.format(language=language, allowed=names, taken=taken)
        case LanguageReason.TOO_FEW_VOTES:
            tally = counted_tally(detection, allowed)
            heard = next((code for code, count in tally.items() if count), "")
            return Cli.LANGUAGE_TOO_FEW_VOTES.format(language=language, heard=heard, needed=LanguageRules().min_votes, taken=taken)
        case LanguageReason.NO_MAJORITY:
            tally = counted_tally(detection, allowed)
            items = Cli.LANGUAGE_LIST_SEPARATOR.join(Cli.LANGUAGE_TALLY_ITEM.format(language=code, count=count) for code, count in tally.items())
            return Cli.LANGUAGE_NO_MAJORITY.format(language=language, counted=detection.counted, tally=items)
        case LanguageReason.DETECTION_FAILED:
            return Cli.LANGUAGE_DETECTION_FAILED.format(language=language)


def _unconfirmed_count(repo: MeetingRepository, meeting_id: str) -> int:
    """How many claims of a meeting's analysis are marked unconfirmed (⚠️ in its minutes); 0 for analyses never
    verified, or unreadable ones."""
    try:
        return sum(unconfirmed(v) for v in verifications(repo.load_analysis(meeting_id)))
    except TeamsRecorderError:
        return 0


@app.command(help=Cli.DOCTOR_CMD_HELP)
def doctor() -> None:
    settings = _settings()
    windows = settings.platform is Platform.WINDOWS
    tools = (Bin.POWERSHELL, Bin.SCHTASKS) if windows else (Bin.SWIFT, Bin.OSASCRIPT)
    checks: dict[str, str | None] = {
        Bin.FFMPEG: _tool_path(Bin.FFMPEG, settings.project_dir),
        Bin.WHISPER_CLI: _tool_path(Bin.WHISPER_CLI, settings.project_dir),
        **{tool: shutil.which(tool) for tool in tools},
        Bin.TEAMS_TAP: _teams_tap_path(settings),
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
        hint="" if model_ok else Cli.WHISPER_MODEL_HINT.format(script=Files.DOWNLOAD_MODEL_SCRIPT_WINDOWS if windows else Files.DOWNLOAD_MODEL_SCRIPT),
    ))
    if settings.vad_model_path is not None:
        vad_ok = settings.vad_model_path.exists()
        typer.echo(Cli.VAD_MODEL_LINE.format(
            mark=Cli.OK if vad_ok else Cli.INFO,
            path=settings.vad_model_path,
            hint="" if vad_ok else Cli.VAD_MODEL_HINT.format(script=Files.DOWNLOAD_MODEL_SCRIPT, model=Audio.DEFAULT_VAD_MODEL),
        ))
    _check_transcript_health(settings)
    _check_verification(settings)
    _check_speakers(settings)
    _check_activities(settings)
    key_needed = settings.llm_provider == LlmProvider.API
    typer.echo(Cli.API_KEY_LINE.format(mark=_mark(settings.has_api_key, key_needed), hint="" if key_needed else Cli.API_KEY_NOT_REQUIRED))
    env_file = settings.project_dir / Files.DOTENV
    if env_file.exists():
        mode = env_file.stat().st_mode & 0o777
        if mode & 0o077:
            typer.echo(Cli.ENV_PERMISSIONS.format(mode=oct(mode)))
    free = DataDirDiskSpace(settings.data_dir).free_bytes()
    if free is not None:
        low = free < Audio.LOW_DISK_HOURS * settings.raw_bytes_per_hour
        typer.echo(Cli.DISK_LINE.format(mark=Cli.WARNING if low else Cli.OK, free=free / 1e9, hours=free / settings.raw_bytes_per_hour, path=settings.data_dir))
    typer.echo(Cli.STORY_GUIDE_LINE.format(mark=_mark(settings.story_guide_path.is_file(), False), path=settings.story_guide_path, hint=""))
    ok = _check_destinations(settings) and ok
    typer.echo(Cli.DATA_IN.format(path=settings.data_dir))
    llm_ok = settings.has_api_key if key_needed else bool(claude_cli)
    raise typer.Exit(code=0 if ok and llm_ok else 1)


def _check_activities(settings: Settings) -> None:
    """Doctor line for the activities document: ok with the last pass, not created yet, or how many meetings analyzed in the last
    10 working days have no successful pass (failed or never attempted). Never fails the doctor."""
    try:
        status = build_container(settings, headless=True).activities_summary().execute()
    except TeamsRecorderError as exc:
        typer.echo(Cli.DOCTOR_ACTIVITIES_UNREADABLE.format(mark=Cli.WARNING, error=exc))
        return
    path = _relative(status.path, settings.project_dir)
    count = len(status.not_curated)
    if not status.exists:
        mark, state = Cli.INFO, Cli.DOCTOR_ACTIVITIES_NONE
    elif count:
        mark, state = Cli.WARNING, (Cli.DOCTOR_ACTIVITIES_NOT_CURATED if count > 1 else Cli.DOCTOR_ACTIVITIES_NOT_CURATED_ONE).format(count=count)
    elif status.last_pass is not None:
        mark, state = Cli.OK, Cli.DOCTOR_ACTIVITIES_OK.format(when=_when(status.last_pass.ts))
    else:
        mark, state = Cli.OK, Cli.DOCTOR_ACTIVITIES_OK_NO_PASS
    typer.echo(Cli.DOCTOR_ACTIVITIES.format(mark=mark, path=path, state=state))


def _check_transcript_health(settings: Settings) -> None:
    """Doctor lines for the hallucination-loop guard: the decoding setting, the threshold and the retry. Never fails the doctor."""
    typer.echo(Cli.TRANSCRIPTION_LINE.format(mark=Cli.INFO, max_context=settings.whisper_max_context, share=settings.max_loop_share))
    retry = build_retry_transcriber(settings)
    vad = settings.retry_vad_model_path
    vad_missing = vad is not None and not vad.exists() and settings.vad_model_path is None
    script = Files.DOWNLOAD_MODEL_SCRIPT_WINDOWS if settings.platform is Platform.WINDOWS else Files.DOWNLOAD_MODEL_SCRIPT
    hint = Cli.RETRY_VAD_MISSING.format(path=vad, script=script, model=settings.vad_model) if vad_missing else ""
    if not settings.retry_on_loop:
        state, mark = Cli.RETRY_OFF, Cli.INFO
    elif retry is None:
        state, mark = Cli.RETRY_SAME, Cli.WARNING if hint else Cli.INFO
    else:
        state = Cli.RETRY_ON_VAD.format(path=retry.vad_model_path) if retry.vad_model_path else Cli.RETRY_ON
        mark = Cli.WARNING if hint else Cli.OK
    typer.echo(Cli.RETRY_LINE.format(mark=mark, state=state, hint=hint))
    if settings.detects_language:
        typer.echo(Cli.LANGUAGE_MODE_AUTO.format(mark=Cli.INFO, languages=Cli.LANGUAGE_LIST_SEPARATOR.join(settings.languages), fallback=settings.fallback_language))
    else:
        typer.echo(Cli.LANGUAGE_MODE_FIXED.format(mark=Cli.INFO, language=settings.language))


def _last_labels(repo: MeetingRepository) -> tuple[str, LabelSummary] | None:
    """The latest transcribed meeting and its speaker summary; None when there is none, or it has no summary (made before the feature)."""
    for meeting_id in reversed(repo.meeting_ids()):
        if TRANSCRIPT_JSON in repo.files(meeting_id):
            transcript = _load_transcript(repo, meeting_id)
            return (meeting_id, transcript.labels) if transcript is not None and transcript.labels is not None else None
    return None


def _check_speakers(settings: Settings) -> None:
    """Doctor line for the speaker helper: off, not built, permission missing, or ready; a ready helper also reports how the last
    recording went and a warning when that recording reported the permission missing. Never fails the doctor. Not shown on Windows
    (the helper reads the macOS Accessibility API). Runs the observer's check once: it is a short-lived launchd job."""
    if settings.platform is Platform.WINDOWS:
        return
    observer = build_speaker_observer(settings)
    if observer is None:
        typer.echo(Cli.SPEAKERS_LINE.format(mark=Cli.INFO, state=Cli.SPEAKERS_OFF))
        return
    binary = teams_speakers_binary(settings.project_dir)
    shown = _relative(binary, settings.project_dir)
    try:
        problems = [text.replace(str(binary), shown) for text in observer.problems()]
    except (OSError, TeamsRecorderError) as exc:
        problems = [Err.SPEAKERS_PROBLEM_CHECK.format(detail=exc)]
    if problems:
        detail = Cli.SPEAKERS_PROBLEMS_SEPARATOR.join(problems)
        typer.echo(Cli.SPEAKERS_LINE.format(mark=Cli.INFO, state=Cli.SPEAKERS_AT.format(path=shown, detail=detail) if binary.exists() else detail))
        return
    last = _last_labels(FsMeetingRepository(settings.data_dir))
    if last is not None and last[1].reason == SpeakerReason.PERMISSION_MISSING:
        typer.echo(Cli.SPEAKERS_LINE.format(mark=Cli.WARNING, state=Cli.SPEAKERS_MISMATCH.format(meeting_id=last[0], binary=shown)))
        return
    detail = Cli.SPEAKERS_GRANTED
    if last is not None:
        labels = last[1]
        outcome = Cli.SPEAKERS_OBSERVER_RAN.format(share=labels.share or 0.0) if labels.labelled else _no_labels_text(labels.reason)
        detail += Cli.SPEAKERS_LAST_RECORDING.format(meeting_id=last[0], outcome=outcome)
    typer.echo(Cli.SPEAKERS_LINE.format(mark=Cli.OK, state=Cli.SPEAKERS_AT.format(path=shown, detail=detail)))


def _relative(path: Path, base: Path) -> str:
    """`path` as shown to the user: relative to the project when it sits inside it."""
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _check_verification(settings: Settings) -> None:
    """Doctor line for the claim verifier: off, or its model, provider and effort. Never fails the doctor: without
    its prompt each verification fails and leaves the claims unverified, and the analysis goes on."""
    if not settings.verify_enabled:
        typer.echo(Cli.VERIFICATION_LINE.format(mark=Cli.INFO, state=Cli.VERIFICATION_OFF))
        return
    model = settings.verify_cli_model if settings.llm_provider is LlmProvider.CLAUDE_CODE else settings.verify_model
    state = Cli.VERIFICATION_ON.format(model=model, provider=settings.llm_provider, effort=settings.verify_effort)
    prompt = settings.prompts_dir / Files.VERIFY_PROMPT
    if prompt.is_file():
        typer.echo(Cli.VERIFICATION_LINE.format(mark=Cli.OK, state=state))
    else:
        typer.echo(Cli.VERIFICATION_LINE.format(mark=Cli.WARNING, state=Cli.VERIFICATION_NO_PROMPT.format(state=state, path=prompt)))


def _mark(found: bool, required: bool) -> str:
    """Doctor mark for something optional unless `required`: ok, MISSING when required, info otherwise."""
    return Cli.OK if found else (Cli.MISSING_MARK if required else Cli.INFO)


def _check_destinations(settings: Settings) -> bool:
    """One doctor line per story destination; problems only fail the doctor when stories are published automatically."""
    ready = True
    for publisher in build_story_publishers(settings):
        problems = publisher.problems()
        ready = ready and (not problems or not settings.story_auto_publish)
        state = Cli.DESTINATION_NOT_READY if problems else Cli.DESTINATION_READY
        typer.echo(Cli.DESTINATION_LINE.format(mark=_mark(not problems, settings.story_auto_publish), destination=publisher.destination, state=state))
        for problem in problems:
            typer.echo(Cli.DESTINATION_PROBLEM.format(problem=problem))
    return ready


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
    if c.speakers is not None:   # no line when the feature is off (or on Windows): there is no observer to report on
        if active.speakers_handle is not None:
            typer.echo(Cli.TRACK_SPEAKERS.format(path=active.speakers_handle.out, pid=active.speakers_handle.pid))
        else:
            reason = _observer_not_started(c.repo, active)
            pointer = Cli.SPEAKERS_SEE_LOG if reason == SpeakerReason.START_FAILED else Cli.SPEAKERS_SEE_DOCTOR
            typer.echo(Cli.TRACK_SPEAKERS_OFF.format(reason=Cli.SPEAKERS_NOT_STARTED.get(reason, reason), pointer=pointer))
    typer.echo(Cli.STOP_HINT)


def _observer_not_started(repo: MeetingRepository, active: ActiveRecording) -> str:
    """Why the observer did not start, as the recording use case wrote it to speakers.jsonl; a failure to start when that is unreadable."""
    started = active.meeting.started_at.timestamp()
    try:
        log = repo.load_speaker_log(active.meeting.id, started, started)
    except TeamsRecorderError:
        log = None
    return (log.unavailable if log is not None else None) or SpeakerReason.START_FAILED.value


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
    settings = _settings()
    c = build_container(settings, headless=True)
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
        health = transcript.health
        if health is not None:
            typer.echo(Cli.TRANSCRIPT_HEALTH.format(loop=health.loop_share, covered=health.covered_minutes, total=health.total_minutes,
                                                    retried=Cli.RETRIED if health.retried else ""))
            if health.degraded:
                typer.echo(Cli.TRANSCRIPT_DEGRADED.format(gaps=Cli.NO_TEXT_IN.format(ranges=gaps_text(health)) if health.uncovered else ""))
            if health.rate_mismatch:
                typer.echo(Cli.TRANSCRIPT_RATE_MISMATCH.format(share=health.short_padding_share))
        typer.echo(_language_line(transcript, settings.languages))
        speakers_line = _speakers_line(transcript)
        if speakers_line is not None:
            typer.echo(speakers_line)
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
    analyzed: list[str] = []
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
        analyzed.append(mid)
    if analyzed and settings.activities_enabled:   # a curation failure never changes the exit code: the analyses succeeded
        _curate_passes(c, batches(analyzed))
    if failures:
        raise typer.Exit(code=1)


def _meeting_label(repo: MeetingRepository, meeting_id: str) -> str:
    """`Revisão de sprint (19/10)`: a meeting as the curation lines name it; its id when its metadata cannot be read."""
    try:
        meeting = repo.load_meta(meeting_id)
    except TeamsRecorderError:
        return meeting_id
    return Cli.CURATING_MEETING.format(title=meeting.title or meeting_id, day=meeting.day)


def _meeting_title(repo: MeetingRepository, meeting_id: str) -> str:
    """The meeting's title for a line that names the pass; its id when its metadata cannot be read or it has no title."""
    try:
        return repo.load_meta(meeting_id).title or meeting_id
    except TeamsRecorderError:
        return meeting_id


def _curate_passes(c: Container, passes: list[list[str]]) -> int:
    """Runs the curator pass by pass (each of at most one batch), printing a line for the meetings a pass curated, one for
    each that failed and one for each deferred (not attempted: an unfinished pass stopped the round). Waits for the curator when the daemon holds it. Returns how many meetings failed."""
    use_case = c.curate_meetings()
    failures = 0
    for ids in passes:
        try:
            result = use_case.execute(ids, wait=True, on_wait=lambda: typer.echo(Cli.CURATE_WAITING))
        except TeamsRecorderError as exc:   # the lock or the document could not be reached: nothing of this pass ran
            result = PassResult((), (), tuple((meeting_id, str(exc)) for meeting_id in ids), None, 0)
        if result.curated:
            meetings = Cli.CURATING_SEPARATOR.join(_meeting_label(c.repo, meeting_id) for meeting_id in result.curated)
            line = Cli.CURATING.format(meetings=meetings) + Cli.CURATED_OK.format(edits=result.edits)
            typer.echo(line + (Cli.CURATED_SUMMARY.format(summary=result.summary) if result.summary else ""))
        if result.unfinished is not None:
            typer.echo(Cli.CURATION_UNFINISHED.format(reason=result.unfinished))
        for meeting_id in result.deferred:
            typer.echo(Cli.CURATION_DEFERRED.format(meeting=_meeting_label(c.repo, meeting_id)))
        for meeting_id, reason in result.failed:
            typer.echo(Cli.CURATING.format(meetings=_meeting_label(c.repo, meeting_id)) + Cli.CURATION_FAILED.format(reason=reason))
        failures += len(result.failed)
    return failures


def _when(at: datetime) -> str:
    return Cli.WHEN.format(weekday=Cli.WEEKDAYS_SHORT[at.weekday()], at=at)


def _not_curated_line(item: NotCurated) -> str:
    """`<id> (<title>): <why> → trec activities curate <id>`; the why is the stored error without its `Activity curation failed:` lead."""
    lead = Err.CURATION_FAILED.format(reason="")
    if item.reason is None:
        reason = Cli.ACTIVITIES_NOT_ATTEMPTED
    else:
        reason = item.reason.removeprefix(lead).strip() or item.reason
    title = Cli.ACTIVITIES_NOT_CURATED_TITLE.format(title=item.title) if item.title else ""
    return Cli.ACTIVITIES_NOT_CURATED_LINE.format(meeting_id=item.meeting_id, title=title, reason=reason)


def _open_document(path: Path, *, platform: str = sys.platform, startfile: Callable[[str], None] | None = None,
                   run: Callable[..., object] = subprocess.run) -> None:
    """Opens the document with the default application: `open` on macOS, `os.startfile` on Windows. The OS calls are
    parameters so tests fake them."""
    if platform == Platform.WINDOWS:
        opener = startfile or getattr(os, Cli.STARTFILE)   # only Windows has it: looked up here, not imported
        opener(str(path))
    else:
        run([Bin.OPEN, str(path)], check=True)


@activities_app.callback(help=Cli.ACTIVITIES_HELP)
def activities(
    ctx: typer.Context,
    open_document: bool = typer.Option(False, "--open", help=Cli.ACTIVITIES_OPEN_HELP),
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    settings = _settings()
    c = build_container(settings, headless=True)
    try:
        status = c.activities_summary().execute()
    except TeamsRecorderError as exc:
        _fail(str(exc))
    if not status.exists:
        typer.echo(Cli.ACTIVITIES_NO_DOCUMENT)
        return
    typer.echo(Cli.ACTIVITIES_DOCUMENT.format(path=_relative(status.path, settings.project_dir)))
    if status.updated is not None:
        after = Cli.ACTIVITIES_AFTER.format(titles=Cli.CURATING_SEPARATOR.join(status.titles)) if status.titles else ""
        typer.echo(Cli.ACTIVITIES_UPDATED.format(when=_when(status.updated), after=after))
    if status.focus:
        typer.echo(Cli.ACTIVITIES_FOCUS)
        for line in status.focus:
            typer.echo(Cli.ACTIVITIES_FOCUS_LINE.format(line=line))
    labelled = ((ActivityDoc.HEADING_ACTIONS, Cli.ACTIVITIES_COUNT_ACTIONS), (ActivityDoc.HEADING_WAITING, Cli.ACTIVITIES_COUNT_WAITING),
                (ActivityDoc.HEADING_AGENDA, Cli.ACTIVITIES_COUNT_AGENDA), (ActivityDoc.HEADING_CONTEXT, Cli.ACTIVITIES_COUNT_CONTEXT))
    counts = [template.format(count=status.counts[heading]) for heading, template in labelled if heading in status.counts]
    if counts:
        typer.echo(Cli.ACTIVITIES_OPEN.format(counts=Cli.ACTIVITIES_COUNT_SEPARATOR.join(counts)))
    if status.last_pass is not None:
        summary = Cli.CURATED_SUMMARY.format(summary=status.last_pass.summary) if status.last_pass.summary else ""
        typer.echo(Cli.ACTIVITIES_LAST_PASS.format(when=_when(status.last_pass.ts), summary=summary))
    else:
        typer.echo(Cli.ACTIVITIES_NO_PASS)
    if status.not_curated:
        typer.echo(Cli.ACTIVITIES_NOT_CURATED)
        for item in reversed(status.not_curated):   # the most recent first
            typer.echo(_not_curated_line(item))
    if open_document:
        try:
            _open_document(status.path)
        except (OSError, subprocess.SubprocessError) as exc:
            _fail(Cli.ACTIVITIES_OPEN_FAILED.format(path=status.path, error=exc))


def _state(repo: MeetingRepository, meeting_id: str) -> MeetingStatus:
    """Where a meeting stands in the pipeline, an `error.txt` of a failed step set aside (as `_pending` does)."""
    return derive_status(repo.files(meeting_id) - {ERROR})


def _analyzed_days(repo: MeetingRepository, since: date) -> dict[str, date]:
    """The analyzed meetings held on or after `since`, by id; a meeting whose metadata cannot be read is left out."""
    found: dict[str, date] = {}
    for meeting_id in repo.meeting_ids():
        if _state(repo, meeting_id) is not MeetingStatus.ANALYZED:
            continue
        try:
            day = repo.load_meta(meeting_id).day
        except TeamsRecorderError:
            continue
        if day >= since:
            found[meeting_id] = day
    return found


@activities_app.command("curate", help=Cli.CURATE_CMD_HELP)
def activities_curate(
    meeting_ids: list[str] = typer.Argument(None, help=Cli.CURATE_ARG_HELP),
    since: str | None = typer.Option(None, "--since", help=Cli.CURATE_SINCE_HELP),
    yes: bool = typer.Option(False, "--yes", help=Cli.CURATE_YES_HELP),
) -> None:
    settings = _settings()
    ids = list(meeting_ids or [])
    if ids and since is not None:
        _fail(Cli.CURATE_ONE_TARGET)
    if not ids and since is None:
        _fail(Cli.CURATE_NEEDS_TARGET)
    c = build_container(settings, headless=True)
    if since is not None:
        first = _day(since)
        days = _analyzed_days(c.repo, first)
        if not days:
            typer.echo(Cli.CURATE_NOTHING_SINCE.format(since=first.isoformat()))
            return
    else:
        for meeting_id in ids:
            if not c.repo.exists(meeting_id):
                _fail(Cli.MEETING_MISSING.format(meeting_id=meeting_id))
            state = _state(c.repo, meeting_id)
            if state is not MeetingStatus.ANALYZED:
                typer.echo(Cli.CURATE_NOT_ANALYZED.format(meeting_id=meeting_id, state=state.value), err=True)
                raise typer.Exit(code=1)
        days = {meeting_id: c.repo.load_meta(meeting_id).day for meeting_id in ids}
    _check_llm_prerequisites(settings)
    passes = passes_by_day(days)
    if since is not None and not yes:
        step = Activities.ESTIMATE_STEP_MINUTES
        minutes = -(-len(passes) * Activities.EST_SECONDS_PER_PASS // (60 * step)) * step   # rounded up to a multiple of `step`
        question = Cli.CURATE_CONFIRM.format(meetings=len(days), passes=len(passes), via=Cli.CURATE_VIA[settings.llm_provider], minutes=minutes)
        if not typer.confirm(question, default=False):
            typer.echo(Cli.CURATE_DECLINED)
            return
    if _curate_passes(c, passes):
        raise typer.Exit(code=1)


def _undo_failure(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


@activities_app.command("undo", help=Cli.UNDO_CMD_HELP)
def activities_undo(yes: bool = typer.Option(False, "--yes", help=Cli.UNDO_YES_HELP)) -> None:
    c = build_container(_settings(), headless=True)
    use_case = c.undo_last_pass()
    try:
        preview = use_case.preview()
    except TeamsRecorderError as exc:
        _fail(str(exc))
    if preview is None:
        _undo_failure(Err.NOTHING_TO_UNDO)
    record = preview.record
    titles = Cli.CURATING_SEPARATOR.join(_meeting_title(c.repo, meeting_id) for meeting_id in record.meetings)
    typer.echo(Cli.UNDO_LAST_PASS.format(
        when=_when(record.ts), after=Cli.ACTIVITIES_AFTER.format(titles=titles) if titles else "",
        summary=Cli.UNDO_SUMMARY.format(summary=record.summary) if record.summary else ""))
    typer.echo(Cli.UNDO_DIFF_NOW)
    typer.echo(Cli.UNDO_DIFF_BEFORE)
    if preview.diff:
        typer.echo(preview.diff)
    if preview.edited_after:
        typer.echo(Cli.UNDO_EDITED_AFTER_ONE if preview.edited_after == 1 else Cli.UNDO_EDITED_AFTER.format(count=preview.edited_after))
    if not yes and not typer.confirm(Cli.UNDO_CONFIRM, default=False):
        typer.echo(Cli.UNDO_DECLINED)
        return
    try:
        result = use_case.execute(preview.version)
    except CuratorBusy:
        _undo_failure(Cli.UNDO_BUSY)
    except (NothingToUndo, UndoStale) as exc:
        _undo_failure(str(exc))
    except TeamsRecorderError as exc:
        _fail(str(exc))
    typer.echo(Cli.UNDO_RESTORED.format(meeting_ids=" ".join(result.meetings),
                                        that=Cli.UNDO_THAT_ONE if len(result.meetings) == 1 else Cli.UNDO_THOSE))
    if result.archive_left_in_place:
        typer.echo(Cli.UNDO_ARCHIVE_CHANGED)


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


def _agent(extra_env: dict[str, str] | None = None) -> LaunchAgent | ScheduledTask:
    s = _settings()
    if s.platform is Platform.WINDOWS:
        return ScheduledTask(s.project_dir, s.data_dir)
    return LaunchAgent(s.project_dir, s.data_dir, extra_env=extra_env)


def _remove_legacy_planner() -> None:
    """Removes the daily planner job an older version installed (its only use: `uninstall()`), and says so when it was there.
    A failure to remove it is a warning, not an error: the callers go on with the daemon."""
    s = _settings()
    windows = s.platform is Platform.WINDOWS
    legacy = ScheduledTask(s.project_dir, s.data_dir, name=Legacy.PLANNER_TASK) if windows else LaunchAgent(s.project_dir, s.data_dir, label=Legacy.PLANNER_LABEL)
    try:
        existed = legacy.uninstall()
    except RuntimeError as exc:   # a leftover job must never stop the daemon from being installed, restarted or removed
        typer.echo(Cli.LEGACY_PLANNER_REMOVE_FAILED.format(name=Legacy.PLANNER_TASK if windows else Legacy.PLANNER_LABEL, error=exc), err=True)
        return
    if existed:
        typer.echo(Cli.LEGACY_PLANNER_REMOVED.format(name=Legacy.PLANNER_TASK if windows else Legacy.PLANNER_LABEL))


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
    windows = _settings().platform is Platform.WINDOWS
    if extra and windows:
        _fail(Cli.AGENT_ENV_UNSUPPORTED)
    try:
        path = _agent(extra or None).install()
    except RuntimeError as exc:
        _fail(str(exc))
    typer.echo((Cli.TASK_INSTALLED if windows else Cli.AGENT_INSTALLED).format(path=path))
    _remove_legacy_planner()
    typer.echo(Cli.PERMISSIONS_HINT_WINDOWS if windows else Cli.PERMISSIONS_HINT)


@agent_app.command("uninstall", help=Cli.AGENT_UNINSTALL_CMD_HELP)
def agent_uninstall() -> None:
    existed = _agent().uninstall()
    typer.echo(Cli.AGENT_REMOVED if existed else Cli.AGENT_NOT_INSTALLED)
    _remove_legacy_planner()


@agent_app.command("restart", help=Cli.AGENT_RESTART_CMD_HELP)
def agent_restart() -> None:
    _remove_legacy_planner()   # first: the old job would fail every weekday at 18:00 even when the restart itself fails
    try:
        _agent().restart()
    except RuntimeError as exc:
        _fail(str(exc))
    typer.echo(Cli.DAEMON_RESTARTED)


@agent_app.command("status", help=Cli.AGENT_STATUS_CMD_HELP)
def agent_status() -> None:
    info = _agent().status()
    line = Cli.TASK_LINE if _settings().platform is Platform.WINDOWS else Cli.PLIST_LINE
    typer.echo(line.format(path=info.plist, state=Cli.EXISTS if info.plist_exists else Cli.MISSING_FILE))
    details = Cli.LOADED_DETAILS.format(pid=info.pid if info.pid is not None else "-", state=info.state) if info.loaded else ""
    typer.echo(Cli.LOADED_LINE.format(state=Cli.YES if info.loaded else Cli.NO, details=details))
    raise typer.Exit(code=0 if info.loaded else 1)


@app.command(help=Cli.STORIES_CMD_HELP)
def stories() -> None:
    settings = _settings()
    _check_llm_prerequisites(settings)
    c = build_container(settings, headless=True)
    if not _draft_then_publish(c):
        raise typer.Exit(code=1)


def _plural(count: int, many: str, one: str) -> str:
    return one if count == 1 else many.format(count=count)


def _story_line(line: str) -> str:
    """A tagged line as `trec stories` shows it: its title, without list marker, checkbox, tag, emphasis, link syntax or what follows."""
    text = re.sub(Parse.ACTIVITY_ITEM_PREFIX, "", line)
    text = re.sub(Parse.ACTIVITY_LINK, r"\1", text).replace(ActivityDoc.STORY_TAG, "").replace(ActivityDoc.EMPHASIS, "")
    return " ".join(re.split(Parse.ACTIVITY_TITLE_END, text, maxsplit=1)[0].split())


def _skip_reason(skipped: SkippedAction, titles: dict[str, str]) -> str:
    """Why a block is not a story: a duplicate says which story already exists, any other skip its stored reason."""
    if skipped.duplicate_of in titles:
        return Cli.STORIES_EXISTS_REASON.format(title=titles[skipped.duplicate_of])
    return skipped.reason


def _draft_stories(c: Container) -> TagDraftResult | None:
    """Drafts a story for every item tagged in the activities document and reports it; None (and a notification) on failure."""
    shown = _relative(c.activity_store.path(), c.settings.project_dir)
    if c.activity_store.read_document() is None:
        _fail(Cli.STORIES_NO_DOCUMENT.format(path=shown))
    drafted = False

    def announce(count: int) -> None:
        nonlocal drafted
        drafted = True
        typer.echo(_plural(count, Cli.DRAFTING_TAGGED, Cli.DRAFTING_TAGGED_ONE), nl=False)

    try:
        result = c.draft_stories_from_tags().execute(announce)
    except TeamsRecorderError as exc:
        typer.echo(Cli.FAILED.format(error=exc) if drafted else Cli.ERROR_PREFIX.format(message=exc), err=not drafted)
        c.notifier.notify(Notify.STORIES_FAILED, Notify.STORIES_FAILED_BODY.format(day=c.clock.now().date().isoformat(), error=exc))
        return None
    if result.nothing_tagged:
        typer.echo(Cli.STORIES_NOTHING_TAGGED.format(tag=ActivityDoc.STORY_TAG, path=shown))
        return result
    if drafted:
        cards = sum(1 for s in result.stories if s.is_task_card)
        exist = sum(1 for k in result.skipped if k.duplicate_of in result.titles)
        parts = [
            _plural(len(result.stories) - cards, Cli.STORIES_COUNT, Cli.STORIES_COUNT_ONE) if len(result.stories) > cards else "",
            _plural(cards, Cli.TASK_CARDS_COUNT, Cli.TASK_CARDS_COUNT_ONE) if cards else "",
            _plural(exist, Cli.STORIES_EXIST, Cli.STORIES_EXIST_ONE) if exist else "",
            Cli.STORIES_SKIPPED_COUNT.format(count=len(result.skipped) - exist) if len(result.skipped) > exist else "",
        ]
        typer.echo(Cli.STORIES_OK.format(parts=Cli.STORIES_PARTS_SEPARATOR.join(part for part in parts if part)))
    for story in result.stories:
        typer.echo(Cli.STORY_LINE.format(title=story.title))
    for skipped in result.skipped:
        typer.echo(Cli.STORIES_SKIPPED_LINE.format(line=_story_line(skipped.source_line or ""), reason=_skip_reason(skipped, result.titles)))
    if result.replaced and not drafted:
        typer.echo(_plural(result.replaced, Cli.STORIES_REPLACED, Cli.STORIES_REPLACED_ONE).format(count=result.replaced, path=shown))
    if result.edited:
        typer.echo(_plural(result.edited, Cli.STORIES_EDITED, Cli.STORIES_EDITED_ONE))
    if result.deferred:
        typer.echo(Cli.STORIES_DEFERRED)
    if result.drafts_path is not None:
        typer.echo(Cli.STORIES_PATH.format(path=_relative(result.drafts_path, c.settings.project_dir)))
    return result


def _draft_then_publish(c: Container) -> bool:
    """Drafts the stories of the tagged items and, with [stories] publish on, sends today's drafts to the destinations."""
    result = _draft_stories(c)
    if result is None:
        return False
    if c.settings.story_auto_publish and c.story_publishers and result.drafts_path is not None:
        return _publish_stories(c, c.clock.now().date())
    return True


@app.command(help=Cli.PUBLISH_CMD_HELP)
def publish(
    day: str | None = typer.Option(None, "--date", help=Cli.PUBLISH_DATE_HELP),
    only: str | None = typer.Option(None, "--only", help=Cli.PUBLISH_ONLY_HELP),
) -> None:
    settings = _settings()
    target = _day(day)
    numbers = _story_numbers(only)
    c = build_container(settings, headless=True)
    if not c.story_publishers:
        _fail(Cli.NO_DESTINATIONS)
    if not _publish_stories(c, target, numbers):
        raise typer.Exit(code=1)


def _publish_stories(c: Container, day: date, only: list[int] | None = None) -> bool:
    """Publishes a day's drafts and reports each story; False when anything failed."""
    typer.echo(Cli.PUBLISHING.format(day=day.isoformat()))
    try:
        report = c.publish_user_stories().execute(day, only)
    except TeamsRecorderError as exc:  # before or between stories (no drafts, a failed save): the use case did not notify
        typer.echo(Cli.ERROR_PREFIX.format(message=exc), err=True)
        c.notifier.notify(Notify.PUBLISH_FAILED, Notify.PUBLISH_ERROR_BODY.format(day=day.isoformat(), error=exc))
        return False
    for published in report.published:
        typer.echo(Cli.PUBLISHED_LINE.format(title=published.story.title, destination=published.publication.destination,
                                             ref=published.publication.ref))
    if report.already_published:
        typer.echo(Cli.ALREADY_PUBLISHED.format(count=report.already_published))
    for failure in report.failures:
        typer.echo(Cli.PUBLISH_FAILURE_LINE.format(title=failure.story.title, destination=failure.destination, error=failure.error))
    if not (report.published or report.already_published or report.failures):
        typer.echo(Cli.NOTHING_TO_PUBLISH)
    return not report.failures


def _story_numbers(value: str | None) -> list[int] | None:
    """`--only 1,3` as story numbers; None means every story."""
    if value is None:
        return None
    parts = value.split(",")
    if not all(re.fullmatch(Parse.STORY_NUMBER, part) for part in parts) or any(int(p) < 1 for p in parts):
        _fail(Cli.INVALID_ONLY.format(value=value))
    return [int(part) for part in parts]


def _day(value: str | None) -> date:
    try:
        return date.fromisoformat(value) if value else date.today()
    except ValueError:
        _fail(Cli.INVALID_DATE.format(value=value))


@app.command(help=Cli.PURGE_CMD_HELP)
def purge() -> None:
    c = build_container(_settings(), headless=True)
    purged = c.purge_old_audio().execute()
    typer.echo(Cli.PURGED.format(count=len(purged)))
    for mid in purged:
        typer.echo(Cli.PURGED_LINE.format(meeting_id=mid))


def _teams_tap_path(settings: Settings) -> str | None:
    candidate = teams_tap_binary(settings.project_dir, settings.platform)
    return str(candidate) if candidate.exists() else None


def _tool_path(name: str, project_dir: Path) -> str | None:
    found = find_tool(name, project_dir)
    return found if Path(found).is_absolute() else None


def _attach_streams_to_logs() -> None:
    """Under pythonw (the Windows scheduled tasks) there is no stdout/stderr: send them to
    <data>/log/<command>.out.log / .err.log, like launchd does on macOS."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    command = sys.argv[1] if len(sys.argv) > 1 else CLI_NAME
    log_dir = _settings().log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    if sys.stdout is None:
        sys.stdout = open(log_dir / Files.AGENT_OUT_LOG.format(name=command), "a", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(log_dir / Files.AGENT_ERR_LOG.format(name=command), "a", encoding="utf-8")  # noqa: SIM115


if __name__ == "__main__":
    _attach_streams_to_logs()
    app()
