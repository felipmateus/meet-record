"""One fake per port. All in memory, no hardware, no network."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterator

from teams_recorder.application.ports import ActiveRecording, CallState, CaptureHandle, VersionFiles
from teams_recorder.domain import (
    Action,
    Analysis,
    AnalysisError,
    CaptureError,
    ClaimRef,
    CaptureStats,
    CuratorInput,
    CuratorOutput,
    DailyPlan,
    Decision,
    EnergyTimeline,
    Meeting,
    MeetingNotFound,
    Op,
    OpFailure,
    PassRecord,
    PublishError,
    RepositoryError,
    Segment,
    SkippedAction,
    SpeakerLog,
    SpeakersUnavailable,
    StoryDrafts,
    Transcript,
    TranscriptHealth,
    TranscriptionError,
    UserStory,
    Verification,
)
from teams_recorder.domain.status import ANALYSIS, CURATION_ERROR, ERROR, LOCK, META, MINUTES, TRANSCRIPT_JSON, TRANSCRIPT_TXT


class FakeClock:
    def __init__(self, start: datetime | None = None) -> None:
        self.current = start or datetime(2026, 10, 6, 14, 0, 0)

    def now(self) -> datetime:
        return self.current

    def advance(self, **kwargs) -> None:
        self.current += timedelta(**kwargs)


class FakeNotifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def notify(self, title: str, body: str) -> None:
        self.messages.append((title, body))


class FakeProcessCapture:
    _next_pid = 1000

    def __init__(self, fail_on_start: bool = False) -> None:
        self.fail_on_start = fail_on_start
        self.handles: list[CaptureHandle] = []
        self.stopped: list[int] = []
        self.epochs: list[float | None] = []

    def start(self, pid: int, out: Path, epoch: float | None = None) -> CaptureHandle:
        if self.fail_on_start:
            raise RuntimeError("tap unavailable")
        FakeProcessCapture._next_pid += 1
        h = CaptureHandle(pid=FakeProcessCapture._next_pid, out=out)
        self.handles.append(h)
        self.epochs.append(epoch)
        return h

    def stop(self, handle: CaptureHandle) -> Path:
        self.stopped.append(handle.pid)
        return handle.out

    def is_stopped(self, handle: CaptureHandle) -> bool:
        return handle.pid in self.stopped

    def is_running(self, handle: CaptureHandle) -> bool:
        return handle in self.handles and handle.pid not in self.stopped and handle.pid not in getattr(self, "died", set())

    def warmup(self) -> bool:
        return True


class FakeMicCapture(FakeProcessCapture):
    def start(self, device: str, out: Path, epoch: float | None = None) -> CaptureHandle:  # type: ignore[override]
        return super().start(0, out, epoch)


class FakeSpeakerObserver:
    """Records its starts (with the `out` path and the epoch) and stops. `reason` makes `start` raise
    SpeakersUnavailable(reason); `error` makes it raise that exception instead (a failure the port does not promise)."""

    _next_pid = 5000

    def __init__(self, reason: str | None = None, error: Exception | None = None, problem_list: list[str] | None = None,
                 stop_error: Exception | None = None, check_error: Exception | None = None) -> None:
        self.reason = reason
        self.error = error
        self.problem_list = list(problem_list or [])
        self.stop_error = stop_error
        self.check_error = check_error   # makes `is_running` raise (launchctl failing under the daemon's tick)
        self.starts: list[tuple[Path, float]] = []
        self.handles: list[CaptureHandle] = []
        self.stopped: list[int] = []
        self.stale_stops = 0             # calls of `stop_stale`: a stop with no handle to name the job
        self.died: set[int] = set()

    def start(self, out: Path, epoch: float) -> CaptureHandle:
        if self.error is not None:
            raise self.error
        if self.reason is not None:
            raise SpeakersUnavailable(self.reason)
        FakeSpeakerObserver._next_pid += 1
        handle = CaptureHandle(pid=FakeSpeakerObserver._next_pid, out=out)
        self.starts.append((out, epoch))
        self.handles.append(handle)
        return handle

    def stop(self, handle: CaptureHandle) -> Path:
        if self.stop_error is not None:
            raise self.stop_error
        self.stopped.append(handle.pid)
        return handle.out

    def stop_stale(self) -> None:
        if self.stop_error is not None:
            raise self.stop_error
        self.stale_stops += 1

    def is_running(self, handle: CaptureHandle) -> bool:
        if self.check_error is not None:
            raise self.check_error
        return handle in self.handles and handle.pid not in self.stopped and handle.pid not in self.died

    def problems(self) -> list[str]:
        return list(self.problem_list)


class FakeEnergyMeter:
    """Returns the timeline given for a track (keyed by its file name) and records what it measured; a track in `fail`
    raises CaptureError, a track without a timeline too."""

    def __init__(self, timelines: dict[str, EnergyTimeline] | None = None, fail: set[str] | None = None) -> None:
        self.timelines = dict(timelines or {})
        self.fail = set(fail or ())
        self.measured: list[Path] = []

    def measure(self, track: Path) -> EnergyTimeline:
        self.measured.append(track)
        if track.name in self.fail or track.name not in self.timelines:
            raise CaptureError(f"cannot measure {track.name}")
        return self.timelines[track.name]


class FakeMixer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Path], Path]] = []

    def mix(self, tracks: list[Path], out: Path) -> Path:
        self.calls.append((tracks, out))
        return out


class FakeTranscriber:
    """Returns `transcript`; `fail` raises a bug-like error, `fail_cleanly` a TranscriptionError."""

    def __init__(self, transcript: Transcript | None = None, fail: bool = False, fail_cleanly: bool = False) -> None:
        self.transcript = transcript or Transcript(segments=[Segment(0.0, 2.5, "Olá, bom dia a todos.")])
        self.fail = fail
        self.fail_cleanly = fail_cleanly
        self.calls: list[tuple[Path, str]] = []

    def transcribe(self, audio: Path, language: str) -> Transcript:
        self.calls.append((audio, language))
        if self.fail:
            raise RuntimeError("whisper blew up")
        if self.fail_cleanly:
            raise TranscriptionError("whisper-cli timed out")
        return self.transcript


def looped_transcript(minutes: int = 20, loop_minutes: int = 15, line: str = "A CIDADE NO BRASIL") -> Transcript:
    """A meeting whose first `loop_minutes` are one hallucinated line repeated every 5 s (whisper's loop), then speech."""
    segments = [Segment(t, t + 5.0, line) for t in range(0, loop_minutes * 60, 5)]
    segments += [Segment(t, t + 8.0, f"Fala número {t} sobre o relatório.") for t in range(loop_minutes * 60, minutes * 60, 10)]
    return Transcript(segments=segments)


def speech_transcript(minutes: int = 20) -> Transcript:
    """A healthy meeting: different text every 10 s."""
    return Transcript(segments=[Segment(t, t + 8.0, f"Fala número {t} sobre o relatório.") for t in range(0, minutes * 60, 10)])


class FakeAnalyzer:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[Transcript, Meeting]] = []

    def analyze(self, transcript: Transcript, meeting: Meeting) -> Analysis:
        self.calls.append((transcript, meeting))
        if self.fail:
            raise RuntimeError("API is down")
        return Analysis(
            meeting_id="",
            summary=f"Summary of {meeting.id}",
            decisions=[Decision("Go ahead with plan A")],
            my_actions=[Action("Send the report", "me", meeting.id, due=meeting.day + timedelta(days=2))],
        )


class FakePlanner:
    def plan(self, day: date, analyses: list[Analysis], previous_plan: DailyPlan | None, open_actions: list[Action]) -> DailyPlan:
        new = [a for an in analyses for a in an.my_actions]
        overdue = [a.id for a in open_actions if a.is_overdue_on(day)]
        return DailyPlan(
            day=day,
            markdown=f"# Plan {day}\n\n{len(analyses)} meetings, {len(new)} new actions.\n",
            priorities=[a.description for a in new[:3]],
            new_actions=new,
            overdue_action_ids=overdue,
        )


class FakeCallDetector:
    def __init__(self, states: list[CallState], pid: int = 4242) -> None:
        self.states = list(states)
        self.pid = pid

    def poll(self) -> CallState:
        return self.states.pop(0) if self.states else CallState.IDLE

    def teams_pid(self) -> int | None:
        return self.pid


@dataclass
class _Rec:
    meeting: Meeting
    files: set[str] = field(default_factory=set)
    transcript: Transcript | None = None
    analysis: Analysis | None = None
    capture_stats: CaptureStats | None = None
    speaker_log: SpeakerLog | None = None
    energy: dict[str, EnergyTimeline] = field(default_factory=dict)


class InMemoryMeetingRepository:
    """Simulates the file repository by tracking only the set of file names."""

    def __init__(self) -> None:
        self._recs: dict[str, _Rec] = {}
        self.plans: dict[date, DailyPlan] = {}
        self.open_actions: list[Action] = []
        self.active: ActiveRecording | None = None
        self.minutes: dict[str, str] = {}
        self.story_drafts: dict[date, tuple[StoryDrafts, str]] = {}
        self.notice_days: dict[str, date] = {}
        self.unavailable: dict[str, str] = {}   # meeting id -> reason written by write_speakers_unavailable
        self.speaker_log_calls: list[tuple[str, float, float]] = []
        self.curation_errors: dict[str, str] = {}   # meeting id -> text of curation_error.txt

    def _get(self, meeting_id: str) -> _Rec:
        try:
            return self._recs[meeting_id]
        except KeyError:
            raise MeetingNotFound(meeting_id) from None

    # helper for tests to seed state
    def seed(self, meeting: Meeting, files: set[str] | None = None, transcript: Transcript | None = None, analysis: Analysis | None = None,
             capture_stats: CaptureStats | None = None) -> None:
        self._recs[meeting.id] = _Rec(meeting, {META, *(files or set())}, transcript, analysis, capture_stats)

    def create(self, meeting: Meeting) -> None:
        if meeting.id in self._recs:
            raise RepositoryError("already exists")
        self._recs[meeting.id] = _Rec(meeting, {META})

    def save_meta(self, meeting: Meeting) -> None:
        self._get(meeting.id).meeting = meeting

    def load_meta(self, meeting_id: str) -> Meeting:
        return self._get(meeting_id).meeting

    def list_meetings(self) -> list[Meeting]:
        return [r.meeting for _, r in sorted(self._recs.items())]

    def meeting_ids(self) -> list[str]:
        return sorted(self._recs)

    def exists(self, meeting_id: str) -> bool:
        return meeting_id in self._recs

    def files(self, meeting_id: str) -> set[str]:
        return set(self._get(meeting_id).files)

    def path(self, meeting_id: str, filename: str) -> Path:
        self._get(meeting_id)
        return Path("/fake") / meeting_id / filename

    def touch(self, meeting_id: str, filename: str) -> None:
        self._get(meeting_id).files.add(filename)

    def delete_file(self, meeting_id: str, filename: str) -> None:
        self._get(meeting_id).files.discard(filename)

    def delete_meeting(self, meeting_id: str) -> None:
        self._recs.pop(meeting_id, None)

    @contextmanager
    def lock(self, meeting_id: str) -> Iterator[None]:
        rec = self._get(meeting_id)
        if LOCK in rec.files:
            raise RepositoryError("being processed")
        rec.files.add(LOCK)
        try:
            yield
        finally:
            rec.files.discard(LOCK)

    def save_active(self, active: ActiveRecording) -> None:
        self.active = active

    def load_active(self) -> ActiveRecording | None:
        if self.active and self.active.meeting.id not in self._recs:
            self.active = None
        return self.active

    def clear_active(self) -> None:
        self.active = None

    def load_capture_stats(self, meeting_id: str) -> CaptureStats | None:
        return self._get(meeting_id).capture_stats

    def seed_speakers(self, meeting_id: str, log: SpeakerLog | None = None, energy: dict[str, EnergyTimeline] | None = None) -> None:
        rec = self._get(meeting_id)
        rec.speaker_log = log
        rec.energy = dict(energy or {})

    def write_speakers_unavailable(self, meeting_id: str, reason: str) -> None:
        self.unavailable[meeting_id] = reason
        self._get(meeting_id).speaker_log = SpeakerLog(unavailable=reason)

    def load_speaker_log(self, meeting_id: str, fallback_epoch: float, end: float) -> SpeakerLog | None:
        self.speaker_log_calls.append((meeting_id, fallback_epoch, end))
        return self._get(meeting_id).speaker_log

    def save_energy(self, meeting_id: str, energy: dict[str, EnergyTimeline]) -> None:
        self._get(meeting_id).energy = dict(energy)

    def load_energy(self, meeting_id: str) -> dict[str, EnergyTimeline]:
        return dict(self._get(meeting_id).energy)

    def last_notice_day(self, key: str) -> date | None:
        return self.notice_days.get(key)

    def save_notice_day(self, key: str, day: date) -> None:
        self.notice_days[key] = day

    def save_transcript(self, meeting_id: str, transcript: Transcript) -> None:
        rec = self._get(meeting_id)
        rec.transcript = transcript
        rec.files.update({TRANSCRIPT_JSON, TRANSCRIPT_TXT})

    def load_transcript(self, meeting_id: str) -> Transcript:
        t = self._get(meeting_id).transcript
        if t is None:
            raise RepositoryError("no transcript")
        return t

    def save_analysis(self, meeting_id: str, analysis: Analysis) -> None:
        rec = self._get(meeting_id)
        rec.analysis = analysis
        rec.files.add(ANALYSIS)

    def load_analysis(self, meeting_id: str) -> Analysis:
        a = self._get(meeting_id).analysis
        if a is None:
            raise RepositoryError("no analysis")
        return a

    def save_minutes(self, meeting_id: str, markdown: str) -> None:
        rec = self._get(meeting_id)
        rec.files.add(MINUTES)
        self.minutes[meeting_id] = markdown

    def mark_failed(self, meeting_id: str, message: str) -> None:
        self._get(meeting_id).files.add(ERROR)
        self.last_error = message

    def clear_failed(self, meeting_id: str) -> None:
        self._get(meeting_id).files.discard(ERROR)

    def mark_curation_failed(self, meeting_id: str, message: str) -> None:
        self._get(meeting_id).files.add(CURATION_ERROR)
        self.curation_errors[meeting_id] = message

    def clear_curation_failed(self, meeting_id: str) -> None:
        self._get(meeting_id).files.discard(CURATION_ERROR)
        self.curation_errors.pop(meeting_id, None)

    def curation_error(self, meeting_id: str) -> str | None:
        self._get(meeting_id)
        return self.curation_errors.get(meeting_id)

    def save_plan(self, plan: DailyPlan) -> None:
        self.plans[plan.day] = plan

    def load_plan(self, day: date) -> DailyPlan | None:
        return self.plans.get(day)

    def latest_plan_before(self, day: date) -> DailyPlan | None:
        earlier = [d for d in self.plans if d < day]
        return self.plans[max(earlier)] if earlier else None

    def load_open_actions(self) -> list[Action]:
        return list(self.open_actions)

    def save_open_actions(self, actions: list[Action]) -> None:
        self.open_actions = list(actions)

    def save_story_drafts(self, drafts: StoryDrafts, markdown: str) -> None:
        self.story_drafts[drafts.day] = (drafts, markdown)

    def load_story_drafts(self, day: date) -> StoryDrafts | None:
        saved = self.story_drafts.get(day)
        return saved[0] if saved else None

    def recent_story_drafts(self, before: date, days: int) -> list[StoryDrafts]:
        start = before - timedelta(days=days)
        return [self.story_drafts[d][0] for d in sorted(self.story_drafts) if start <= d < before]


class FakeClaimVerifier:
    """Returns the given verdicts (or raises `fail`), recording each call."""

    def __init__(self, verdicts: dict[ClaimRef, Verification] | None = None, fail: Exception | None = None) -> None:
        self.verdicts = verdicts or {}
        self.fail = fail
        self.calls: list[tuple[Meeting, Analysis, Transcript]] = []

    def verify(self, meeting: Meeting, analysis: Analysis, transcript: Transcript) -> dict[ClaimRef, Verification]:
        self.calls.append((meeting, analysis, transcript))
        if self.fail is not None:
            raise self.fail
        return dict(self.verdicts)


class FakeMinutesRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[Meeting, Analysis]] = []
        self.healths: list[TranscriptHealth | None] = []

    def render(self, meeting: Meeting, analysis: Analysis, health: TranscriptHealth | None = None) -> str:
        self.calls.append((meeting, analysis))
        self.healths.append(health)
        return f"# Minutes {meeting.id}\n{analysis.summary}\n"


class FakeStoryWriter:
    """One story per action, except actions whose description starts with "Email", which are skipped."""

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[date, list[Action], list[Analysis], list[UserStory]]] = []

    def draft(self, day: date, actions: list[Action], analyses: list[Analysis], existing: list[UserStory]) -> StoryDrafts:
        self.calls.append((day, actions, analyses, existing))
        if self.fail:
            raise AnalysisError("model is down")
        stories = [UserStory(f"Story for {a.description}", "As someone, I want it", source_action_ids=[a.id])
                   for a in actions if not a.description.startswith("Email")]
        skipped = [SkippedAction(a.id, "not product work") for a in actions if a.description.startswith("Email")]
        return StoryDrafts(day=day, stories=stories, skipped=skipped)


class FakeStoryPublisher:
    """Publishes to memory; fails for the story titles in `fail_on`, or for every story with `fail_all`."""

    def __init__(self, destination: str = "fake-board", fail_on: set[str] | None = None, fail_all: bool = False) -> None:
        self.destination = destination
        self.fail_on = fail_on or set()
        self.fail_all = fail_all
        self.calls: list[tuple[UserStory, date]] = []

    def publish(self, story: UserStory, day: date) -> str:
        self.calls.append((story, day))
        if self.fail_all or story.title in self.fail_on:
            raise PublishError(f"{self.destination} refused {story.title}")
        return f"{self.destination}-{len(self.calls)}"

    def problems(self) -> list[str]:
        return ["not ready"] if self.fail_all else []


class FakeStoryRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[StoryDrafts, list[Action], list[UserStory]]] = []
        self.degraded: list[dict[str, TranscriptHealth] | None] = []

    def render(self, drafts: StoryDrafts, actions: list[Action], existing: list[UserStory],
               degraded: dict[str, TranscriptHealth] | None = None) -> str:
        self.calls.append((drafts, actions, existing))
        self.degraded.append(degraded)
        return f"# Stories {drafts.day}\n{len(drafts.stories)} stories\n"


class FakeActivityCurator:
    """Answers `curate` with the scripted outputs in order (the last one repeats) and `repair` with the scripted op lists,
    recording every input. `during_call` runs inside each call, that is, between the use case's snapshot of the document and its
    re-read, so a test can edit the document "while the model is thinking"."""

    def __init__(self, outputs: list[CuratorOutput] | None = None, repairs: list[list[Op]] | None = None, fail: Exception | None = None,
                 during_call: Callable[[], None] | None = None) -> None:
        self.outputs = list(outputs or [])
        self.repairs = list(repairs or [])
        self.fail = fail
        self.during_call = during_call
        self.inputs: list[CuratorInput] = []
        self.repair_calls: list[tuple[CuratorInput, str, list[OpFailure]]] = []

    def curate(self, data: CuratorInput) -> CuratorOutput:
        self.inputs.append(data)
        if self.during_call:
            self.during_call()
        if self.fail:
            raise self.fail
        if not self.outputs:
            return CuratorOutput(ops=[], user_removed=[], focus=[], summary="", notify=False, ignored=[])
        return self.outputs.pop(0) if len(self.outputs) > 1 else self.outputs[0]

    def repair(self, data: CuratorInput, current: str, failures: list[OpFailure]) -> list[Op]:
        self.repair_calls.append((data, current, list(failures)))
        if self.during_call:
            self.during_call()
        if self.fail:
            raise self.fail
        return self.repairs.pop(0) if self.repairs else []


class InMemoryActivityStore:
    """The activities store in memory. `busy` makes `lock(wait=False)` yield False; `fail_commit` makes the next commit raise, `fail_log` every log_pass;
    `commits` records every commit; the archive is one text whose size is the bytes of the entries appended."""

    def __init__(self, document: str | None = None, base: str | None = None, busy: bool = False) -> None:
        self.document = document
        self.base = base
        self.busy = busy
        self.fail_commit: Exception | None = None
        self.fail_log: Exception | None = None   # makes every log_pass raise
        self.logged: list[PassRecord] = []       # the records written by log_pass (no commit)
        self.records: list[PassRecord] = []
        self.versions: dict[str, VersionFiles] = {}
        self.archive = ""
        self.commits: list[tuple[str, str, list[tuple[str, str]], str | None, PassRecord]] = []
        self.locks: list[bool] = []              # `wait` of every lock() call
        self.truncated: list[PassRecord] = []
        self.document_path = Path("activities") / "atividades.md"

    @contextmanager
    def lock(self, wait: bool = True) -> Iterator[bool]:
        self.locks.append(wait)
        if self.busy and not wait:
            yield False
            return
        yield True

    def read_document(self) -> str | None:
        return self.document

    def read_base(self) -> str | None:
        return self.base

    def recent_archive(self, limit: int) -> list[str]:
        entries = [chunk for chunk in self.archive.split("### ")[1:]]
        return ["### " + "\n".join(entry.split("\n")[:2]).rstrip("\n") for entry in entries[-limit:]] if limit > 0 else []

    def commit(self, before: str, after: str, archived: list[tuple[str, str]], base: str | None, record: PassRecord) -> None:
        if self.fail_commit is not None:
            raise self.fail_commit
        if archived:
            appended = "".join(f"### {reason}\n{text}\n" for text, reason in archived)
            size = len(self.archive.encode("utf-8"))
            record = replace(record, archive_file="arquivo/archive.md", archive_bytes_before=size,
                             archive_bytes_after=size + len(appended.encode("utf-8")))
            self.archive += appended
        self.commits.append((before, after, list(archived), base, record))
        self.versions[record.version] = VersionFiles(before, after, base, self.base)
        self.document = after
        self.base = base
        self.records.append(record)

    def log_pass(self, record: PassRecord) -> None:
        if self.fail_log is not None:
            raise self.fail_log
        self.records.append(record)
        self.logged.append(record)

    def passes(self) -> list[PassRecord]:
        return list(self.records)

    def version(self, name: str) -> VersionFiles:
        try:
            return self.versions[name]
        except KeyError:
            raise RepositoryError(f"no version {name}") from None

    def version_names(self) -> list[str]:
        return sorted(self.versions)

    def truncate_archive(self, record: PassRecord) -> bool:
        if record.archive_file is None or record.archive_bytes_before is None or record.archive_bytes_after is None:
            return True
        data = self.archive.encode("utf-8")
        if len(data) != record.archive_bytes_after:
            return False
        self.archive = data[:record.archive_bytes_before].decode("utf-8")
        self.truncated.append(record)
        return True

    def path(self) -> Path:
        return self.document_path
