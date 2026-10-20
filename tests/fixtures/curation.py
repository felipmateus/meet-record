"""Builders shared by the `CurateMeetings` tests (on fakes and on the file-backed store): analyzed meetings, curator answers, the
ops they carry, and the use case wired to a repository, a store and a curator."""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Sequence

from teams_recorder.application.use_cases.activities import CurateMeetings, doc_format, skeleton
from teams_recorder.domain import (
    Action, Analysis, CuratorOutput, Decision, IgnoredRef, Meeting, Op, OpKind, PassKind, PassRecord, RemovedItem, Segment, StatusChange,
    StatusUpdate, Transcript, TranscriptHealth,
)
from tests.fakes import FakeActivityCurator, FakeClock, FakeNotifier

FMT = doc_format()
NOW = datetime(2026, 10, 19, 10, 12)          # a Monday
SKELETON = skeleton(FMT)
ACTIONS = FMT.heading_actions
WAITING = FMT.heading_waiting


def meeting_id(day: date, hour: int = 9, minute: int = 30) -> str:
    return Meeting.start(datetime(day.year, day.month, day.day, hour, minute, 11)).id


def analysis(mid: str, title: str = "Daily", **kinds: object) -> Analysis:
    """An analysis with one action of the user's unless told otherwise (`my_actions=[]` makes it empty)."""
    fields: dict[str, object] = {"my_actions": [Action("Enviar o cronograma", "usuário", mid, due=date(2026, 10, 20), at="00:03:00")]}
    fields.update(kinds)
    return Analysis(meeting_id=mid, summary="Resumo.", title=title, **fields)  # type: ignore[arg-type]


def empty_analysis(mid: str) -> Analysis:
    return Analysis(meeting_id=mid, summary="Nada a fazer.", title="Curta")


def transcript(minutes: int = 20, health: TranscriptHealth | None = None) -> Transcript:
    """A healthy meeting with a speaker label on every line: one segment every 10 s."""
    return Transcript(segments=[Segment(t, t + 8.0, f"Fala {t} sobre o relatório.", speaker="Marina") for t in range(0, minutes * 60, 10)],
                      health=health)


def seed(repo, started: datetime, title: str = "Daily", content: Callable[[str], Analysis] | None = None,
         health: TranscriptHealth | None = None) -> str:
    """Creates a meeting in `repo` (any repository: in memory or on files) that is analyzed; returns its id. `content` builds
    the analysis from the meeting id."""
    meeting = Meeting.start(started, title=title)
    repo.create(meeting)
    repo.save_transcript(meeting.id, transcript(health=health))
    repo.save_analysis(meeting.id, content(meeting.id) if content is not None else analysis(meeting.id, title))
    return meeting.id


def rec(kind: PassKind, *meetings: str, version: str = "v1", during_edits: str = "", summary: str = "", ts: datetime = NOW) -> PassRecord:
    """A pass record as the store logs it, for tests that seed the pass log."""
    return PassRecord(ts=ts, kind=kind, meetings=tuple(meetings), ops_applied=0, retried=False, retried_by_kind={}, unaccounted_refs=(),
                      ignored=0, user_removed=0, box_rescued=0, during_edits=during_edits, summary=summary, version=version, archive_file=None,
                      archive_bytes_before=None, archive_bytes_after=None, carried_edits="", undoes=None, doc_chars=0, error=None)


def insert(text: str, after: str = ACTIONS, refs: Sequence[str] = ("1.a1",)) -> Op:
    return Op(OpKind.INSERT_AFTER, after, text, refs=tuple(refs))


def replace(target: str, text: str, refs: Sequence[str] = ()) -> Op:
    return Op(OpKind.REPLACE, target, text, refs=tuple(refs))


def archive(target: str, reason: str = "data passou") -> Op:
    return Op(OpKind.ARCHIVE, target, reason=reason)


def answer(ops: Sequence[Op] = (), summary: str = "1 ação nova", notify: bool = False, focus: Sequence[str] = ("**Enviar o cronograma** hoje",),
           user_removed: Sequence[RemovedItem] = (), ignored: Sequence[IgnoredRef] = ()) -> CuratorOutput:
    return CuratorOutput(ops=list(ops), user_removed=list(user_removed), focus=list(focus), summary=summary, notify=notify, ignored=list(ignored))


def status_update(at: str) -> StatusUpdate:
    return StatusUpdate("o timesheet", StatusChange.DONE, "usuário", "o timesheet eu já subi", at=at)


def with_updates(mid: str, *ats: str) -> Analysis:
    return analysis(mid, status_updates=[status_update(at) for at in ats], decisions=[Decision("Seguir.", "00:01:00")])


def build(repo, store, curator: FakeActivityCurator, now: datetime = NOW, **options: object) -> tuple[CurateMeetings, FakeNotifier, FakeClock]:
    notifier, clock = FakeNotifier(), FakeClock(now)
    return CurateMeetings(repo, store, curator, notifier, clock, **options), notifier, clock  # type: ignore[arg-type]
