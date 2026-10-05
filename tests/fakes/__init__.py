"""One fake per port. All in memory, no hardware, no network."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

from teams_recorder.application.ports import ActiveRecording, CallState, CaptureHandle
from teams_recorder.domain import (
    Action,
    Analysis,
    DailyPlan,
    Decision,
    Meeting,
    MeetingNotFound,
    RepositoryError,
    Segment,
    Transcript,
)
from teams_recorder.domain.status import LOCK, META, ANALYSIS, ERROR, TRANSCRIPT_JSON, TRANSCRIPT_TXT


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

    def start(self, pid: int, out: Path) -> CaptureHandle:
        if self.fail_on_start:
            raise RuntimeError("tap unavailable")
        FakeProcessCapture._next_pid += 1
        h = CaptureHandle(pid=FakeProcessCapture._next_pid, out=out)
        self.handles.append(h)
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
    def start(self, device: str, out: Path) -> CaptureHandle:  # type: ignore[override]
        return super().start(0, out)


class FakeMixer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[Path], Path]] = []

    def mix(self, tracks: list[Path], out: Path) -> Path:
        self.calls.append((tracks, out))
        return out


class FakeTranscriber:
    def __init__(self, transcript: Transcript | None = None, fail: bool = False) -> None:
        self.transcript = transcript or Transcript(segments=[Segment(0.0, 2.5, "Olá, bom dia a todos.")])
        self.fail = fail
        self.calls: list[tuple[Path, str]] = []

    def transcribe(self, audio: Path, language: str) -> Transcript:
        self.calls.append((audio, language))
        if self.fail:
            raise RuntimeError("whisper blew up")
        return self.transcript


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


class InMemoryMeetingRepository:
    """Simulates the file repository by tracking only the set of file names."""

    def __init__(self) -> None:
        self._recs: dict[str, _Rec] = {}
        self.plans: dict[date, DailyPlan] = {}
        self.open_actions: list[Action] = []
        self.active: ActiveRecording | None = None

    def _get(self, meeting_id: str) -> _Rec:
        try:
            return self._recs[meeting_id]
        except KeyError:
            raise MeetingNotFound(meeting_id) from None

    # helper for tests to seed state
    def seed(self, meeting: Meeting, files: set[str] | None = None, transcript: Transcript | None = None, analysis: Analysis | None = None) -> None:
        self._recs[meeting.id] = _Rec(meeting, {META, *(files or set())}, transcript, analysis)

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

    def mark_failed(self, meeting_id: str, message: str) -> None:
        self._get(meeting_id).files.add(ERROR)
        self.last_error = message

    def clear_failed(self, meeting_id: str) -> None:
        self._get(meeting_id).files.discard(ERROR)

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
