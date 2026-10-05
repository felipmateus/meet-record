"""Domain entities and value objects. No I/O, no external dependencies."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from uuid import uuid4

MEETING_ID_FORMAT = "%Y-%m-%d_%H-%M-%S"


def meeting_id_for(started_at: datetime) -> str:
    return started_at.strftime(MEETING_ID_FORMAT)


def _new_action_id() -> str:
    return uuid4().hex[:8]


@dataclass
class Meeting:
    id: str
    started_at: datetime
    ended_at: datetime | None = None
    pid: int | None = None
    title: str | None = None

    @classmethod
    def start(cls, started_at: datetime, pid: int | None = None, title: str | None = None) -> "Meeting":
        return cls(id=meeting_id_for(started_at), started_at=started_at, pid=pid, title=title)

    @property
    def day(self) -> date:
        return self.started_at.date()

    @property
    def duration_seconds(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    segments: list[Segment] = field(default_factory=list)
    language: str = "pt"

    @property
    def text(self) -> str:
        return "\n".join(s.text.strip() for s in self.segments if s.text.strip())

    @property
    def duration_seconds(self) -> float:
        return self.segments[-1].end if self.segments else 0.0

    def as_timestamped_text(self) -> str:
        return "\n".join(f"[{_fmt(s.start)}] {s.text.strip()}" for s in self.segments)


def _fmt(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class ActionStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    OVERDUE = "overdue"


class Priority(StrEnum):
    """Urgency stated (or clearly implied) in the meeting; absent when nobody said it."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MeetingType(StrEnum):
    STANDUP = "standup"
    CLIENT = "client"
    PROJECT_REVIEW = "project_review"
    ONE_ON_ONE = "one_on_one"
    OTHER = "other"


@dataclass
class Action:
    description: str
    owner: str
    source_meeting: str
    due: date | None = None
    status: ActionStatus = ActionStatus.OPEN
    id: str = field(default_factory=_new_action_id)
    priority: Priority | None = None
    at: str | None = None  # transcript timestamp (HH:MM:SS) where it was said, for verification

    def is_overdue_on(self, day: date) -> bool:
        return self.status == ActionStatus.OPEN and self.due is not None and self.due < day


@dataclass(frozen=True)
class Decision:
    text: str
    at: str | None = None  # transcript timestamp (HH:MM:SS) where it was decided


@dataclass(frozen=True)
class Topic:
    title: str
    points: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Deadline:
    what: str
    when: date | None
    who: str


@dataclass
class Analysis:
    meeting_id: str
    summary: str
    decisions: list[Decision] = field(default_factory=list)
    my_actions: list[Action] = field(default_factory=list)
    others_actions: list[Action] = field(default_factory=list)
    deadlines: list[Deadline] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    next_meetings: list[str] = field(default_factory=list)
    title: str = ""
    purpose: str = ""
    meeting_type: MeetingType = MeetingType.OTHER
    participants: list[str] = field(default_factory=list)  # names mentioned (no diarization yet)
    topics: list[Topic] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    @property
    def all_actions(self) -> list[Action]:
        return [*self.my_actions, *self.others_actions]


@dataclass
class DailyPlan:
    day: date
    markdown: str
    priorities: list[str] = field(default_factory=list)
    new_actions: list[Action] = field(default_factory=list)
    completed_action_ids: list[str] = field(default_factory=list)
    overdue_action_ids: list[str] = field(default_factory=list)


def merge_open_actions(current: list[Action], plan: DailyPlan) -> list[Action]:
    """Apply a plan to the open-actions list: drop completed, flag overdue, append new ones."""
    completed = set(plan.completed_action_ids)
    overdue = set(plan.overdue_action_ids)
    result: list[Action] = []
    known_ids: set[str] = set()
    for action in current:
        if action.id in completed:
            continue
        if action.id in overdue:
            action.status = ActionStatus.OVERDUE
        result.append(action)
        known_ids.add(action.id)
    for action in plan.new_actions:
        if action.id not in known_ids:
            result.append(action)
            known_ids.add(action.id)
    return result
