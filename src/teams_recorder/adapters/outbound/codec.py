"""Conversion between domain entities and JSON dictionaries.

Kept in the adapter so the domain knows nothing about the persistence format.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from teams_recorder.constants import Audio
from teams_recorder.domain import (
    Action,
    ActionStatus,
    Analysis,
    DailyPlan,
    Deadline,
    Decision,
    Meeting,
    MeetingType,
    Priority,
    Publication,
    Segment,
    SkippedAction,
    StoryDrafts,
    Topic,
    Transcript,
    UserStory,
)


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _d(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _parse_d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


# Meeting
def meeting_to_dict(m: Meeting) -> dict[str, Any]:
    return {"id": m.id, "started_at": _dt(m.started_at), "ended_at": _dt(m.ended_at), "pid": m.pid, "title": m.title}


def meeting_from_dict(d: dict[str, Any]) -> Meeting:
    return Meeting(
        id=d["id"],
        started_at=datetime.fromisoformat(d["started_at"]),
        ended_at=_parse_dt(d.get("ended_at")),
        pid=d.get("pid"),
        title=d.get("title"),
    )


# Transcript
def transcript_to_dict(t: Transcript) -> dict[str, Any]:
    return {"language": t.language, "segments": [asdict(s) for s in t.segments]}


def transcript_from_dict(d: dict[str, Any]) -> Transcript:
    return Transcript(
        language=d.get("language", Audio.DEFAULT_LANGUAGE),
        segments=[Segment(float(s["start"]), float(s["end"]), s["text"]) for s in d.get("segments", [])],
    )


# Action
def action_to_dict(a: Action) -> dict[str, Any]:
    return {
        "id": a.id,
        "description": a.description,
        "owner": a.owner,
        "source_meeting": a.source_meeting,
        "due": _d(a.due),
        "status": a.status.value,
        "priority": a.priority.value if a.priority else None,
        "at": a.at,
    }


def action_from_dict(d: dict[str, Any]) -> Action:
    return Action(
        id=d["id"],
        description=d["description"],
        owner=d["owner"],
        source_meeting=d["source_meeting"],
        due=_parse_d(d.get("due")),
        status=ActionStatus(d.get("status", ActionStatus.OPEN)),
        priority=Priority(d["priority"]) if d.get("priority") else None,
        at=d.get("at"),
    )


def _decision_from(value: Any) -> Decision:
    # analyses written before 2026-10-05 stored decisions as plain strings
    if isinstance(value, str):
        return Decision(value)
    return Decision(value["text"], value.get("at"))


# Analysis
def analysis_to_dict(a: Analysis) -> dict[str, Any]:
    return {
        "meeting_id": a.meeting_id,
        "summary": a.summary,
        "title": a.title,
        "purpose": a.purpose,
        "meeting_type": a.meeting_type.value,
        "participants": list(a.participants),
        "topics": [{"title": t.title, "points": list(t.points)} for t in a.topics],
        "decisions": [{"text": dec.text, "at": dec.at} for dec in a.decisions],
        "my_actions": [action_to_dict(x) for x in a.my_actions],
        "others_actions": [action_to_dict(x) for x in a.others_actions],
        "deadlines": [{"what": dl.what, "when": _d(dl.when), "who": dl.who} for dl in a.deadlines],
        "open_questions": list(a.open_questions),
        "next_meetings": list(a.next_meetings),
        "risks": list(a.risks),
    }


def analysis_from_dict(d: dict[str, Any]) -> Analysis:
    return Analysis(
        meeting_id=d["meeting_id"],
        summary=d.get("summary", ""),
        decisions=[_decision_from(x) for x in d.get("decisions", [])],
        my_actions=[action_from_dict(x) for x in d.get("my_actions", [])],
        others_actions=[action_from_dict(x) for x in d.get("others_actions", [])],
        deadlines=[Deadline(x["what"], _parse_d(x.get("when")), x.get("who", "")) for x in d.get("deadlines", [])],
        open_questions=list(d.get("open_questions", [])),
        next_meetings=list(d.get("next_meetings", [])),
        title=d.get("title", ""),
        purpose=d.get("purpose", ""),
        meeting_type=MeetingType(d.get("meeting_type", MeetingType.OTHER)),
        participants=list(d.get("participants", [])),
        topics=[Topic(x["title"], list(x.get("points", []))) for x in d.get("topics", [])],
        risks=list(d.get("risks", [])),
    )


# DailyPlan
def plan_to_dict(p: DailyPlan) -> dict[str, Any]:
    return {
        "day": p.day.isoformat(),
        "markdown": p.markdown,
        "priorities": list(p.priorities),
        "new_actions": [action_to_dict(x) for x in p.new_actions],
        "completed_action_ids": list(p.completed_action_ids),
        "overdue_action_ids": list(p.overdue_action_ids),
    }


def plan_from_dict(d: dict[str, Any]) -> DailyPlan:
    return DailyPlan(
        day=date.fromisoformat(d["day"]),
        markdown=d.get("markdown", ""),
        priorities=list(d.get("priorities", [])),
        new_actions=[action_from_dict(x) for x in d.get("new_actions", [])],
        completed_action_ids=list(d.get("completed_action_ids", [])),
        overdue_action_ids=list(d.get("overdue_action_ids", [])),
    )


# User story drafts
def story_to_dict(s: UserStory) -> dict[str, Any]:
    return {
        "id": s.id,
        "title": s.title,
        "narrative": s.narrative,
        "acceptance_criteria": list(s.acceptance_criteria),
        "details": s.details,
        "open_questions": list(s.open_questions),
        "source_action_ids": list(s.source_action_ids),
        "source_meetings": list(s.source_meetings),
        "priority": s.priority.value if s.priority else None,
        "due": _d(s.due),
        "publications": [
            {"destination": pub.destination, "ref": pub.ref, "published_at": _dt(pub.published_at)} for pub in s.publications
        ],
    }


def story_from_dict(d: dict[str, Any]) -> UserStory:
    return UserStory(
        id=d["id"],
        title=d["title"],
        narrative=d.get("narrative", ""),
        acceptance_criteria=list(d.get("acceptance_criteria", [])),
        details=d.get("details", ""),
        open_questions=list(d.get("open_questions", [])),
        source_action_ids=list(d.get("source_action_ids", [])),
        source_meetings=list(d.get("source_meetings", [])),
        priority=Priority(d["priority"]) if d.get("priority") else None,
        due=_parse_d(d.get("due")),
        publications=[
            Publication(x["destination"], x["ref"], datetime.fromisoformat(x["published_at"])) for x in d.get("publications", [])
        ],
    )


def story_drafts_to_dict(drafts: StoryDrafts) -> dict[str, Any]:
    return {
        "day": drafts.day.isoformat(),
        "stories": [story_to_dict(s) for s in drafts.stories],
        "skipped": [{"action_id": k.action_id, "reason": k.reason, "duplicate_of": k.duplicate_of} for k in drafts.skipped],
    }


def story_drafts_from_dict(d: dict[str, Any]) -> StoryDrafts:
    return StoryDrafts(
        day=date.fromisoformat(d["day"]),
        stories=[story_from_dict(x) for x in d.get("stories", [])],
        skipped=[SkippedAction(x["action_id"], x.get("reason", ""), x.get("duplicate_of")) for x in d.get("skipped", [])],
    )
